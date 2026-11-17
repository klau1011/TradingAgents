"""Fork lesson ranking, with upstream point-in-time boundaries."""

import pytest

from tradingagents.memory import TradingMemoryLog
from tradingagents.memory.log import _parse_pct


def make_log(tmp_path):
    return TradingMemoryLog({"memory_log_path": str(tmp_path / "trading_memory.md")})


def _seed_completed(tmp_path, ticker, date, decision, reflection, alpha, resolved=None):
    resolution = f" | resolved:{resolved}" if resolved else ""
    with (tmp_path / "trading_memory.md").open("a", encoding="utf-8") as file:
        file.write(
            f"[{date} | {ticker} | Buy | +1.0% | {alpha} | 5d{resolution}]\n\n"
            f"DECISION:\n{decision}\n\nREFLECTION:\n{reflection}{TradingMemoryLog._SEPARATOR}"
        )


@pytest.mark.unit
class TestCrossTickerRelevance:

    def test_parse_pct(self):
        assert _parse_pct("+3.2%") == 3.2
        assert _parse_pct("-1.5%") == -1.5
        assert _parse_pct("n/a") is None
        assert _parse_pct(None) is None
        assert _parse_pct("") is None

    def test_cross_ticker_ordered_by_abs_alpha(self, tmp_path):
        log = make_log(tmp_path)
        _seed_completed(tmp_path, "AAPL", "2026-01-05", "d", "AAPL lesson.", alpha="+1.0%")
        _seed_completed(tmp_path, "MSFT", "2026-01-06", "d", "MSFT lesson.", alpha="-8.0%")
        _seed_completed(tmp_path, "TSLA", "2026-01-07", "d", "TSLA lesson.", alpha="+3.0%")
        _seed_completed(tmp_path, "AMZN", "2026-01-08", "d", "AMZN lesson.", alpha="+0.2%")
        ctx = log.get_past_context("NVDA")
        assert "AMZN lesson." not in ctx  # smallest |alpha| drops out of top 3
        assert (
            ctx.index("MSFT lesson.")
            < ctx.index("TSLA lesson.")
            < ctx.index("AAPL lesson.")
        )

    def test_tie_break_most_recent_first(self, tmp_path):
        log = make_log(tmp_path)
        _seed_completed(tmp_path, "AAPL", "2026-01-05", "d", "Older lesson.", alpha="+2.0%")
        _seed_completed(tmp_path, "MSFT", "2026-01-06", "d", "Newer lesson.", alpha="-2.0%")
        ctx = log.get_past_context("NVDA")
        assert ctx.index("Newer lesson.") < ctx.index("Older lesson.")

    def test_unparseable_alpha_sorts_last(self, tmp_path):
        log = make_log(tmp_path)
        _seed_completed(tmp_path, "AAPL", "2026-01-06", "d", "No-alpha lesson.", alpha="n/a")
        _seed_completed(tmp_path, "MSFT", "2026-01-05", "d", "Small-alpha lesson.", alpha="+0.1%")
        ctx = log.get_past_context("NVDA")
        assert ctx.index("Small-alpha lesson.") < ctx.index("No-alpha lesson.")

    def test_same_ticker_stays_recency_ordered(self, tmp_path):
        log = make_log(tmp_path)
        _seed_completed(tmp_path, "NVDA", "2026-01-05", "Old decision.", "r", alpha="+9.0%")
        _seed_completed(tmp_path, "NVDA", "2026-01-06", "New decision.", "r", alpha="+0.1%")
        ctx = log.get_past_context("NVDA")
        assert ctx.index("New decision.") < ctx.index("Old decision.")


def test_ranking_cannot_include_future_outcomes(tmp_path):
    log = make_log(tmp_path)
    _seed_completed(tmp_path, "AAPL", "2026-01-05", "d", "known lesson", "+1%", "2026-01-10")
    _seed_completed(tmp_path, "MSFT", "2026-01-06", "d", "future lesson", "+99%", "2026-01-20")
    _seed_completed(tmp_path, "TSLA", "2026-01-04", "d", "undated lesson", "+90%")
    context = log.get_past_context("NVDA", n_cross=1, as_of="2026-01-15")
    assert "known lesson" in context
    assert "future lesson" not in context and "undated lesson" not in context


def test_alpha_ties_use_decision_date_when_backfilled(tmp_path):
    log = make_log(tmp_path)
    _seed_completed(tmp_path, "AAPL", "2026-06-05", "d", "newer", "+2%")
    _seed_completed(tmp_path, "MSFT", "2026-01-05", "d", "backfilled", "-2%")
    context = log.get_past_context("NVDA")
    assert context.index("newer") < context.index("backfilled")
