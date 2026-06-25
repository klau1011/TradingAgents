"""Evaluation / backtest harness: score the multi-agent analysis over a date range.

This is a *signal evaluation*, not a portfolio simulation. It measures whether the
Portfolio Manager's rating predicts forward alpha vs the per-market benchmark.

# ponytail: signal-eval only — no position sizing, transaction costs, or
# overlapping-position netting. Add those only if/when the "sized decisions"
# track lands; they are a different problem from "does the rating predict alpha".

Reuses the already-built outcome math on ``TradingAgentsGraph``
(``_fetch_returns`` / ``_resolve_benchmark``) and the structured decision it
already returns in ``final_state["pm_decision"]`` — this module is orchestration
and aggregation, not new analytics.
"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# "social" (StockTwits/Reddit) returns "now" content regardless of the trade
# date, so including it in a historical backtest leaks future information. The
# other three analysts are date-bounded (price/indicators pinned to the trade
# date; yfinance news is start/end bounded), so they are the safe default.
LOOKAHEAD_SAFE_ANALYSTS = ("market", "news", "fundamentals")

_LONG = {"buy", "overweight"}
_SHORT = {"sell", "underweight"}

_RATING_ORDER = {"Buy": 0, "Overweight": 1, "Hold": 2, "Underweight": 3, "Sell": 4}
_CONF_ORDER = {"high": 0, "medium": 1, "low": 2}


# ---------------------------------------------------------------------------
# Pure helpers (no LLM, no network) — these are what the tests exercise.
# ---------------------------------------------------------------------------


def _direction(rating: str | None) -> int:
    """Map a 5-tier rating to a position direction: +1 long, -1 short, 0 flat."""
    r = (rating or "").strip().lower()
    if r in _LONG:
        return 1
    if r in _SHORT:
        return -1
    return 0


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


def summarize(rows: list[dict]) -> dict:
    """Aggregate result rows into headline metrics + a calibration table."""
    n_total = len(rows)
    resolved = [r for r in rows if r.get("alpha_return") is not None]
    directional = [r for r in resolved if _direction(r["rating"]) != 0]
    strat = [_direction(r["rating"]) * r["alpha_return"] for r in directional]
    raws = [r["raw_return"] for r in directional if r.get("raw_return") is not None]

    return {
        "n_total": n_total,
        "n_resolved": len(resolved),
        "n_directional": len(directional),
        "coverage": (len(resolved) / n_total) if n_total else None,
        "hit_rate": (sum(1 for s in strat if s > 0) / len(strat)) if strat else None,
        "mean_alpha": (sum(strat) / len(strat)) if strat else None,
        "mean_raw": (sum(raws) / len(raws)) if raws else None,
        "signal_sharpe": _sharpe(strat, directional),
        "max_drawdown": _max_drawdown(strat),
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
    lines += [
        "> Signal evaluation, not a portfolio simulation: rating direction vs "
        "forward alpha, equal weight, no sizing/costs. The social (sentiment) "
        "analyst is excluded unless `--include-social` was passed, because its "
        "StockTwits/Reddit sources read 'now' and leak into historical dates. "
        "Residual leakage (restated fundamentals, news recency) may remain.",
        "",
        f"- points: {summary['n_total']}   resolved: {summary['n_resolved']}   "
        f"coverage: {_pct(summary['coverage'])}",
        f"- directional calls: {summary['n_directional']}",
        f"- Hit-rate: {_num(summary['hit_rate'])}",
        f"- Mean captured alpha: {_pct(summary['mean_alpha'])}",
        f"- Signal Sharpe (annualized): {_num(summary['signal_sharpe'])}",
        f"- Max drawdown (cumulative alpha): {_pct(summary['max_drawdown'])}",
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
    skips any point already recorded there, so a killed run resumes for free.
    ``run_point`` is injected in tests; production uses the LLM pipeline.
    """
    results_path = Path(results_path)
    dates = sample_dates(start, end, cadence_days)

    if holding_days > cadence_days:
        logger.warning(
            "holding_days (%d) > cadence_days (%d): forward windows overlap, "
            "which inflates Sharpe and drawdown.", holding_days, cadence_days,
        )

    rows = _load_existing(results_path)
    done = {_key(r["ticker"], r["date"]) for r in rows}
    runner = run_point or _run_point_llm

    skipped = sum(
        1 for t in tickers for d in dates if _key(t, d) in done
    )
    if skipped:
        logger.info("Resuming: skipping %d already-evaluated points.", skipped)

    for ticker in tickers:
        for date in dates:
            if _key(ticker, date) in done:
                continue
            try:
                row = runner(
                    ticker, date,
                    selected_analysts=selected_analysts,
                    config=config,
                    holding_days=holding_days,
                )
            except Exception as e:
                # One bad point (LLM/network blip, bad ticker) must not kill an
                # expensive multi-point sweep. Don't persist it, so a re-run
                # retries it while the completed points are skipped.
                logger.warning("Skipping %s on %s: %s", ticker, date, e)
                continue
            _append_row(results_path, row)
            rows.append(row)
            done.add(_key(ticker, date))

    return rows
