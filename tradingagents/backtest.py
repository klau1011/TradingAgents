"""Evaluation / backtest harness: score the multi-agent analysis over a date range.

This is a *signal evaluation*, not a portfolio simulation. It measures whether the
Portfolio Manager's rating predicts forward alpha vs the per-market benchmark.

# ponytail: signal-eval only — no position simulation or overlapping-position
# netting. A flat per-call transaction cost and confidence-based weighting are
# supported; a real portfolio simulator is a different problem from "does the
# rating predict alpha".

Reuses the already-built outcome math on ``TradingAgentsGraph``
(``_fetch_returns`` / ``_resolve_benchmark``) and the structured decision it
already returns in ``final_state["pm_decision"]`` — this module is orchestration
and aggregation, not new analytics.
"""

from __future__ import annotations

import json
import logging
import math
import random
from collections import defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path

import pandas as pd

from tradingagents.agents.utils.rating import direction as _direction

logger = logging.getLogger(__name__)

# "social" (StockTwits/Reddit) returns "now" content regardless of the trade
# date, so including it in a historical backtest leaks future information. The
# other three analysts are date-bounded (price/indicators pinned to the trade
# date; yfinance news is start/end bounded; statement fundamentals filtered by
# curr_date) EXCEPT for the tools that read "now" — get_live_quote (market),
# get_prediction_markets (news), get_fundamentals and
# get_analyst_recommendations (fundamentals), and get_insider_transactions
# (news). Those are neutralized via the ``disable_lookahead_tools`` config
# flag set in ``_isolated_config`` below, which is what actually makes this
# default safe. (Residual: the ETF profile tools still read "now"; guard them
# the same way if ETF backtests become a real use case.)
LOOKAHEAD_SAFE_ANALYSTS = ("market", "news", "fundamentals")

_RATING_ORDER = {"Buy": 0, "Overweight": 1, "Hold": 2, "Underweight": 3, "Sell": 4}
_CONF_ORDER = {"high": 0, "medium": 1, "low": 2}

# Position weight per confidence level for the confidence-weighted metric.
_CONF_WEIGHT = {"low": 0.5, "medium": 1.0, "high": 1.5}
_N_RANDOM_TRIALS = 1000


# ---------------------------------------------------------------------------
# Pure helpers (no LLM, no network) — these are what the tests exercise.
# ---------------------------------------------------------------------------


def sample_dates(start: str, end: str, cadence_days: int) -> list[str]:
    """Business days in [start, end], every ``cadence_days``-th, as YYYY-MM-DD."""
    days = pd.bdate_range(start=start, end=end)
    return [d.strftime("%Y-%m-%d") for d in days[:: max(1, cadence_days)]]


def _sharpe(strat: list[float], directional: list[dict]) -> float | None:
    """Annualized Sharpe of the per-call strategy alpha series.

    # ponytail: this is a *signal* Sharpe (per-call alpha, equal weight), not a
    # portfolio Sharpe. Annualized by the mean holding period; mixed horizons
    # make the annualization approximate.
    """
    n = len(strat)
    if n < 2:
        return None
    mean = sum(strat) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in strat) / (n - 1))
    if sd == 0:
        return None
    holds = [r["holding_days"] for r in directional if r.get("holding_days")]
    mean_hold = (sum(holds) / len(holds)) if holds else 0
    ann = math.sqrt(252 / mean_hold) if mean_hold else 1.0
    return (mean / sd) * ann


def _max_drawdown(strat: list[float]) -> float | None:
    """Worst peak-to-trough of the cumulative (additive) strategy alpha. <= 0."""
    if not strat:
        return None
    cum = peak = mdd = 0.0
    for s in strat:
        cum += s
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    return mdd


def _calibration(resolved: list[dict]) -> list[dict]:
    """Per (rating, confidence) bucket: n, hit-rate, mean (raw) alpha.

    Hit-rate is the share of calls whose alpha sign matches the rating's
    direction; it is ``None`` for Hold (no direction). Mean alpha is the raw
    alpha so Buy buckets read positive and Sell buckets read negative.
    """
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in resolved:
        buckets[(r["rating"], r.get("confidence") or "medium")].append(r)

    out = []
    for (rating, conf), rs in buckets.items():
        d = _direction(rating)
        alphas = [r["alpha_return"] for r in rs]
        hit_rate = (
            None if d == 0
            else sum(1 for r in rs if d * r["alpha_return"] > 0) / len(rs)
        )
        out.append({
            "rating": rating,
            "confidence": conf,
            "n": len(rs),
            "hit_rate": hit_rate,
            "mean_alpha": sum(alphas) / len(alphas),
        })
    out.sort(key=lambda b: (_RATING_ORDER.get(b["rating"], 99),
                            _CONF_ORDER.get(b["confidence"], 99)))
    return out


def _baselines(resolved: list[dict], *, cost: float, seed: int) -> dict:
    """Null strategies over the same resolved points.

    The signal has to beat these to be worth anything: buy-and-hold of the
    evaluated names (raw), always-Buy (alpha), and random ±1 direction (alpha
    distribution over ``_N_RANDOM_TRIALS`` seeded trials). Cost is charged per
    call for the directional baselines, same as the strategy.
    """
    if not resolved:
        return {"buy_hold_raw": None, "always_buy_alpha": None,
                "random_alpha_mean": None, "random_alpha_std": None}
    raws = [r["raw_return"] for r in resolved if r.get("raw_return") is not None]
    alphas = [r["alpha_return"] for r in resolved]
    rng = random.Random(seed)
    trial_means = [
        sum(rng.choice((1, -1)) * a - cost for a in alphas) / len(alphas)
        for _ in range(_N_RANDOM_TRIALS)
    ]
    mean_t = sum(trial_means) / len(trial_means)
    std_t = math.sqrt(
        sum((x - mean_t) ** 2 for x in trial_means) / (len(trial_means) - 1)
    )
    return {
        "buy_hold_raw": (sum(raws) / len(raws)) if raws else None,
        "always_buy_alpha": sum(a - cost for a in alphas) / len(alphas),
        "random_alpha_mean": mean_t,
        "random_alpha_std": std_t,
    }


def _by_confidence(directional: list[dict], strat: list[float]) -> list[dict]:
    """Per confidence level over directional calls: n, hit-rate, mean captured alpha."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for r, s in zip(directional, strat, strict=True):
        buckets[r.get("confidence") or "medium"].append(s)
    out = [
        {
            "confidence": conf,
            "n": len(ss),
            "hit_rate": sum(1 for s in ss if s > 0) / len(ss),
            "mean_alpha": sum(ss) / len(ss),
        }
        for conf, ss in buckets.items()
    ]
    out.sort(key=lambda b: _CONF_ORDER.get(b["confidence"], 99))
    return out


def _confidence_weighted_alpha(directional: list[dict], strat: list[float]) -> float | None:
    """Mean captured alpha with positions scaled by confidence (0.5/1.0/1.5).

    Cost is already inside ``strat``, so scaling a call scales its cost too —
    consistent with sizing the actual position.
    """
    if not directional:
        return None
    weights = [
        _CONF_WEIGHT.get(r.get("confidence") or "medium", 1.0) for r in directional
    ]
    return sum(w * s for w, s in zip(weights, strat, strict=True)) / sum(weights)


def summarize(rows: list[dict], *, cost: float = 0.0, seed: int = 7) -> dict:
    """Aggregate result rows into headline metrics + calibration and baselines.

    ``cost`` is a flat round-trip transaction cost as a return fraction (e.g.
    0.001 = 10 bps), charged once per directional call (Hold trades nothing).
    It flows into every strategy metric and the directional baselines.
    """
    n_total = len(rows)
    resolved = [r for r in rows if r.get("alpha_return") is not None]
    directional = [r for r in resolved if _direction(r["rating"]) != 0]
    strat = [_direction(r["rating"]) * r["alpha_return"] - cost for r in directional]
    raws = [r["raw_return"] for r in directional if r.get("raw_return") is not None]

    # Drawdown is path-dependent, so it must be chronological — the input/JSONL
    # order is per-ticker, which would make a multi-ticker drawdown depend on
    # ticker argument order. Aggregate same-date calls (equal weight) into one
    # cumulative step and walk by date. (Hit-rate/mean/Sharpe above are
    # order-independent, so they stay on the raw per-call series.)
    by_date: dict[str, float] = defaultdict(float)
    for r, s in zip(directional, strat, strict=True):
        by_date[r["date"]] += s
    dd_series = [by_date[d] for d in sorted(by_date)]

    return {
        "n_total": n_total,
        "n_resolved": len(resolved),
        "n_directional": len(directional),
        "coverage": (len(resolved) / n_total) if n_total else None,
        "cost": cost,
        "hit_rate": (sum(1 for s in strat if s > 0) / len(strat)) if strat else None,
        "mean_alpha": (sum(strat) / len(strat)) if strat else None,
        "mean_raw": (sum(raws) / len(raws)) if raws else None,
        "signal_sharpe": _sharpe(strat, directional),
        "max_drawdown": _max_drawdown(dd_series),
        "confidence_weighted_alpha": _confidence_weighted_alpha(directional, strat),
        "baselines": _baselines(resolved, cost=cost, seed=seed),
        "by_confidence": _by_confidence(directional, strat),
        "calibration": _calibration(resolved),
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:+.1%}"


def _num(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def render_report(summary: dict, *, meta: dict | None = None) -> str:
    """Render the summary as a markdown report."""
    lines = ["# Backtest report", ""]
    if meta:
        lines += [f"- {k}: {v}" for k, v in meta.items()] + [""]
    base = summary["baselines"]
    lines += [
        "> Signal evaluation, not a portfolio simulation: rating direction vs "
        "forward alpha, equal weight per call. The social (sentiment) analyst "
        "is excluded unless `--include-social` was passed, because its "
        "StockTwits/Reddit sources read 'now' and leak into historical dates. "
        "Other 'now'-reading tools (live quote, prediction markets, "
        "fundamentals overview, analyst recommendations, insider transactions) "
        "are disabled in evaluation mode; ETF profile data may still read "
        "'now'.",
        "",
        f"- points: {summary['n_total']}   resolved: {summary['n_resolved']}   "
        f"coverage: {_pct(summary['coverage'])}",
        f"- directional calls: {summary['n_directional']}",
        f"- transaction cost per directional call: {_pct(summary['cost'])}",
        f"- Hit-rate: {_num(summary['hit_rate'])}",
        f"- Mean captured alpha: {_pct(summary['mean_alpha'])}",
        f"- Confidence-weighted alpha: {_pct(summary['confidence_weighted_alpha'])}",
        f"- Signal Sharpe (annualized): {_num(summary['signal_sharpe'])}",
        f"- Max drawdown (cumulative alpha): {_pct(summary['max_drawdown'])}",
        "",
        "## Baselines (same points, no signal)",
        "",
        f"- Buy & hold (raw return): {_pct(base['buy_hold_raw'])}",
        f"- Always-Buy (alpha): {_pct(base['always_buy_alpha'])}",
        f"- Random ±1 (alpha, mean ± std over {_N_RANDOM_TRIALS} trials): "
        f"{_pct(base['random_alpha_mean'])} ± {_pct(base['random_alpha_std'])}",
        "",
        "## By confidence (directional calls)",
        "",
        "| Confidence | n | Hit-rate | Mean alpha |",
        "| --- | --- | --- | --- |",
    ]
    for b in summary["by_confidence"]:
        lines.append(
            f"| {b['confidence']} | {b['n']} | "
            f"{_num(b['hit_rate'])} | {_pct(b['mean_alpha'])} |"
        )
    lines += [
        "",
        "## Calibration (rating × confidence)",
        "",
        "| Rating | Confidence | n | Hit-rate | Mean alpha |",
        "| --- | --- | --- | --- | --- |",
    ]
    for b in summary["calibration"]:
        lines.append(
            f"| {b['rating']} | {b['confidence']} | {b['n']} | "
            f"{_num(b['hit_rate'])} | {_pct(b['mean_alpha'])} |"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestration (runs the agents — expensive; injected for tests).
# ---------------------------------------------------------------------------


def _load_existing(results_path: Path) -> list[dict]:
    if not results_path.exists():
        return []
    return [
        json.loads(line)
        for line in results_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _key(ticker: str, date: str) -> tuple[str, str]:
    return (ticker.upper(), date)


def _append_row(results_path: Path, row: dict) -> None:
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with results_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def _run_point_llm(
    ticker: str, date: str, *, selected_analysts, config, holding_days: int,
) -> dict:
    """Run the full pipeline for one (ticker, date) and resolve its outcome."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = TradingAgentsGraph(list(selected_analysts), config=config)
    final_state, signal = graph.propagate(ticker, date)
    pm = (final_state or {}).get("pm_decision") or {}
    rating = pm.get("rating") or signal or "Hold"
    confidence = pm.get("confidence") or "medium"
    benchmark = graph._resolve_benchmark(ticker)
    raw, alpha, days = graph._fetch_returns(ticker, date, holding_days, benchmark)
    return {
        "ticker": ticker.upper(),
        "date": date,
        "rating": rating,
        "confidence": confidence,
        "raw_return": raw,
        "alpha_return": alpha,
        "holding_days": days,
        "benchmark": benchmark,
    }


def _isolated_config(config: dict | None, out_dir: Path) -> dict:
    """Config for an evaluation run: isolated state + look-ahead guard.

    A backtest must not touch live state. Without this, every point would
    read/write the user's real memory log (storing historical decisions and
    feeding eval-generated reflections into later live *and* backtest runs) and
    write graph logs/caches under the user's results dir. So:

    - ``memory_log_path=None`` → no-memory eval mode: each point is an
      independent measurement (TradingMemoryLog no-ops when the path is unset).
    - ``results_dir``/``data_cache_dir`` redirected under the backtest output.
    - ``checkpoint_enabled=False`` → no per-point checkpoint churn.
    - ``disable_lookahead_tools=True`` → neutralizes the "now"-reading tools
      (get_live_quote, get_prediction_markets, get_fundamentals,
      get_analyst_recommendations, get_insider_transactions) that the
      date-bounded default analysts can otherwise call.
    """
    from tradingagents.default_config import DEFAULT_CONFIG

    cfg = dict(config if config is not None else DEFAULT_CONFIG)
    cfg["memory_log_path"] = None
    cfg["results_dir"] = str(out_dir / "graph_logs")
    cfg["data_cache_dir"] = str(out_dir / "cache")
    cfg["checkpoint_enabled"] = False
    cfg["disable_lookahead_tools"] = True
    return cfg


def run_backtest(
    tickers: Sequence[str],
    start: str,
    end: str,
    *,
    cadence_days: int = 21,
    holding_days: int = 5,
    selected_analysts: Sequence[str] = LOOKAHEAD_SAFE_ANALYSTS,
    config: dict | None = None,
    results_path: str | Path,
    run_point: Callable | None = None,
) -> list[dict]:
    """Evaluate the system over ``tickers`` across [start, end].

    Appends one JSONL row per evaluated (ticker, date) to ``results_path`` and
    skips any point already *resolved* there, so a killed run resumes for free.
    ``run_point`` is injected in tests; production uses the LLM pipeline.
    """
    results_path = Path(results_path)
    dates = sample_dates(start, end, cadence_days)
    eval_config = _isolated_config(config, results_path.parent)

    if holding_days > cadence_days:
        logger.warning(
            "holding_days (%d) > cadence_days (%d): forward windows overlap, "
            "which inflates Sharpe and drawdown.", holding_days, cadence_days,
        )

    # Only points with a *resolved* outcome are complete. An unresolved row
    # (price data too recent or a transient fetch failure) must not look done
    # forever, or its outcome would never be retried once data arrives — so we
    # drop unresolved rows from both the resume set and the report and re-run
    # them below. (New runs never persist unresolved rows; this guards files
    # left by an interrupted older run.)
    rows = [r for r in _load_existing(results_path) if r.get("alpha_return") is not None]
    done = {_key(r["ticker"], r["date"]) for r in rows}
    runner = run_point or _run_point_llm

    skipped = sum(
        1 for t in tickers for d in dates if _key(t, d) in done
    )
    if skipped:
        logger.info("Resuming: skipping %d already-resolved points.", skipped)

    for ticker in tickers:
        for date in dates:
            if _key(ticker, date) in done:
                continue
            try:
                row = runner(
                    ticker, date,
                    selected_analysts=selected_analysts,
                    config=eval_config,
                    holding_days=holding_days,
                )
            except Exception as e:
                # One bad point (LLM/network blip, bad ticker) must not kill an
                # expensive multi-point sweep. Don't persist it, so a re-run
                # retries it while the completed points are skipped.
                logger.warning("Skipping %s on %s: %s", ticker, date, e)
                continue
            if row.get("alpha_return") is None:
                # Decision ran but the forward outcome isn't resolvable yet
                # (too recent) or the price fetch failed. Treat like a failure:
                # don't persist, so a later run retries it. (ponytail: this
                # re-runs the LLM on retry; acceptable since historical
                # backtests resolve first try and only the recent edge hits it.)
                logger.warning(
                    "Outcome unresolved for %s on %s; not persisting so a later "
                    "run retries it.", ticker, date,
                )
                continue
            _append_row(results_path, row)
            rows.append(row)
            done.add(_key(ticker, date))

    return rows
