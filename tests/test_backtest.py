"""Tests for the evaluation/backtest harness.

The metric math is pure (no LLM, no network) and is exercised here with
hand-computed known answers. The per-point LLM run is injected so the
orchestration (date sampling, resume-skip) is testable without API calls.
"""

from __future__ import annotations

import math

import pytest

from tradingagents import backtest
from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision


def _row(ticker, date, rating, confidence, alpha, holding=5, raw=None):
    """Build a result row; raw defaults to alpha when not given."""
    return {
        "ticker": ticker,
        "date": date,
        "rating": rating,
        "confidence": confidence,
        "raw_return": alpha if raw is None else raw,
        "alpha_return": alpha,
        "holding_days": holding,
        "benchmark": "SPY",
    }


# Known-answer dataset (see hand calculation in the test below).
SAMPLE_ROWS = [
    _row("AAPL", "2025-01-02", "Buy", "high", 0.10),
    _row("AAPL", "2025-02-03", "Buy", "high", -0.04),
    _row("AAPL", "2025-03-03", "Sell", "high", -0.06),
    _row("MSFT", "2025-01-02", "Overweight", "medium", 0.02),
    _row("MSFT", "2025-02-03", "Hold", "low", 0.01),
    _row("MSFT", "2025-03-03", "Underweight", "low", 0.03),
    _row("NVDA", "2025-01-02", "Buy", "medium", None),  # unresolved: too recent
]


def test_direction_mapping():
    assert backtest._direction("Buy") == 1
    assert backtest._direction("Overweight") == 1
    assert backtest._direction("Hold") == 0
    assert backtest._direction("Underweight") == -1
    assert backtest._direction("Sell") == -1
    assert backtest._direction("buy") == 1  # case-insensitive
    assert backtest._direction("garbage") == 0
    assert backtest._direction(None) == 0


def test_summary_headline_metrics():
    s = backtest.summarize(SAMPLE_ROWS)

    # 7 total, 6 resolved (Hold counts), 5 directional (exclude Hold + unresolved).
    assert s["n_total"] == 7
    assert s["n_resolved"] == 6
    assert s["n_directional"] == 5
    assert s["coverage"] == pytest.approx(6 / 7)

    # strategy returns s = direction * alpha = [+.10, -.04, +.06, +.02, -.03]
    # hits (s > 0): T, F, T, T, F -> 3/5
    assert s["hit_rate"] == pytest.approx(0.6)
    # mean captured alpha = 0.11 / 5
    assert s["mean_alpha"] == pytest.approx(0.022)

    # sample std (ddof=1) of strat, then annualize by sqrt(252/5)
    strat = [0.10, -0.04, 0.06, 0.02, -0.03]
    mean = sum(strat) / 5
    sd = math.sqrt(sum((x - mean) ** 2 for x in strat) / 4)
    expected_sharpe = (mean / sd) * math.sqrt(252 / 5)
    assert s["signal_sharpe"] == pytest.approx(expected_sharpe, rel=1e-6)

    # cumulative alpha [.10,.06,.12,.14,.11]; worst peak-to-trough = -0.04
    assert s["max_drawdown"] == pytest.approx(-0.04)


def test_calibration_table():
    s = backtest.summarize(SAMPLE_ROWS)
    cal = {(b["rating"], b["confidence"]): b for b in s["calibration"]}

    assert cal[("Buy", "high")]["n"] == 2
    assert cal[("Buy", "high")]["mean_alpha"] == pytest.approx(0.03)  # (.10 + -.04)/2
    assert cal[("Buy", "high")]["hit_rate"] == pytest.approx(0.5)  # one right, one wrong

    assert cal[("Sell", "high")]["hit_rate"] == pytest.approx(1.0)  # short, alpha -ve
    assert cal[("Overweight", "medium")]["hit_rate"] == pytest.approx(1.0)
    assert cal[("Underweight", "low")]["hit_rate"] == pytest.approx(0.0)  # short, alpha +ve

    # Hold is resolved but has no directional hit semantics.
    assert cal[("Hold", "low")]["n"] == 1
    assert cal[("Hold", "low")]["hit_rate"] is None


def test_summarize_empty():
    s = backtest.summarize([])
    assert s["n_total"] == 0
    assert s["hit_rate"] is None
    assert s["signal_sharpe"] is None
    assert s["max_drawdown"] is None
    assert s["calibration"] == []


def test_lookahead_safe_default_excludes_social():
    assert "social" not in backtest.LOOKAHEAD_SAFE_ANALYSTS
    assert backtest.LOOKAHEAD_SAFE_ANALYSTS == ("market", "news", "fundamentals")


def test_sample_dates_cadence():
    import pandas as pd

    dates = backtest.sample_dates("2025-01-01", "2025-03-31", cadence_days=21)
    assert dates[0] == "2025-01-01"  # first business day in range
    assert len(dates) >= 3
    assert all(d2 > d1 for d1, d2 in zip(dates, dates[1:], strict=False))  # ascending
    # consecutive picks are exactly `cadence_days` business days apart
    for d1, d2 in zip(dates, dates[1:], strict=False):
        assert len(pd.bdate_range(d1, d2)) - 1 == 21


def test_run_backtest_resume_skips_recorded_points(tmp_path):
    """A second run must not re-invoke the (expensive) per-point runner for
    points already in the results file."""
    results_path = tmp_path / "results.jsonl"
    calls = []

    def fake_run_point(ticker, date, *, selected_analysts, config, holding_days):
        calls.append((ticker, date))
        return _row(ticker, date, "Buy", "high", 0.05, holding=holding_days)

    # First run over a 2-date schedule for one ticker.
    rows1 = backtest.run_backtest(
        ["AAPL"], "2025-01-01", "2025-03-31",
        cadence_days=40, holding_days=5,
        results_path=results_path, run_point=fake_run_point,
    )
    first_call_count = len(calls)
    assert first_call_count >= 1
    assert len(rows1) == first_call_count

    # Second run with the same schedule: every point already recorded -> no calls.
    calls.clear()
    rows2 = backtest.run_backtest(
        ["AAPL"], "2025-01-01", "2025-03-31",
        cadence_days=40, holding_days=5,
        results_path=results_path, run_point=fake_run_point,
    )
    assert calls == []  # fully resumed
    assert len(rows2) == first_call_count


def test_run_backtest_skips_failing_point(tmp_path):
    """A point whose runner raises is skipped (not persisted) so the sweep
    finishes and a re-run retries it."""
    results_path = tmp_path / "results.jsonl"
    dates = backtest.sample_dates("2025-01-01", "2025-06-30", 40)
    fail_date = dates[0]
    assert len(dates) >= 2  # need a survivor to prove the sweep continued

    def flaky_run_point(ticker, date, *, selected_analysts, config, holding_days):
        if date == fail_date:
            raise RuntimeError("transient LLM error")
        return _row(ticker, date, "Buy", "high", 0.05, holding=holding_days)

    rows = backtest.run_backtest(
        ["AAPL"], "2025-01-01", "2025-06-30",
        cadence_days=40, holding_days=5,
        results_path=results_path, run_point=flaky_run_point,
    )
    # The failing date is absent; the rest of the sweep completed.
    assert fail_date not in [r["date"] for r in rows]
    assert len(rows) == len(dates) - 1
    # Nothing about the failure was written to disk (so a re-run retries it).
    assert len(backtest._load_existing(results_path)) == len(rows)


def test_render_report_smoke():
    report = backtest.render_report(backtest.summarize(SAMPLE_ROWS))
    assert "Hit-rate" in report or "hit-rate" in report
    assert "Calibration" in report


# --- Part A: confidence on the final decision ----------------------------------


def test_portfolio_decision_confidence_roundtrips():
    d = PortfolioDecision(
        rating="Buy",
        confidence="high",
        executive_summary="Enter on strength.",
        investment_thesis="Fundamentals and trend agree.",
    )
    assert d.confidence == "high"
    assert "**Confidence**: high" in render_pm_decision(d)


def test_portfolio_decision_confidence_defaults_to_medium():
    d = PortfolioDecision(
        rating="Hold",
        executive_summary="No action.",
        investment_thesis="Mixed signals.",
    )
    assert d.confidence == "medium"
