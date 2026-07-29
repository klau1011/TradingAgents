"""Tests for the read-side scoreboard over the decision log."""

import pytest

from tradingagents.agents.utils.memory import TradingMemoryLog
from web.backend.track_record import get_track_record

SEP = TradingMemoryLog._SEPARATOR


def _log(tmp_path, tags):
    """Write a log whose entries carry the given tag lines."""
    path = tmp_path / "memory.md"
    path.write_text(
        SEP.join(f"{tag}\n\nDECISION:\nd\n\nREFLECTION:\nr" for tag in tags),
        encoding="utf-8",
    )
    return {"memory_log_path": str(path)}


@pytest.mark.unit
class TestTrackRecord:
    def test_scores_direction_against_realized_alpha(self, tmp_path):
        config = _log(tmp_path, [
            "[2026-01-05 | NOW | Overweight | +3.0% | +2.0% | 5d]",   # long, up   -> hit
            "[2026-01-06 | NOW | Underweight | -3.0% | -2.0% | 5d]",  # short, down-> hit
            "[2026-01-07 | NOW | Overweight | -3.0% | -2.0% | 5d]",   # long, down -> miss
        ])
        overall = get_track_record(config)["overall"]
        assert (overall["scored"], overall["hits"]) == (3, 2)
        assert overall["hit_rate"] == pytest.approx(2 / 3)

    def test_hold_is_excluded_not_counted_as_a_miss(self, tmp_path):
        """Hold takes no position, so it has no direction to be wrong about."""
        config = _log(tmp_path, [
            "[2026-01-05 | AAPL | Hold | +3.0% | +2.0% | 5d]",
            "[2026-01-06 | AAPL | Overweight | +3.0% | +2.0% | 5d]",
        ])
        overall = get_track_record(config)["overall"]
        assert overall["total"] == 2
        assert (overall["scored"], overall["hits"]) == (1, 1)
        assert overall["hit_rate"] == 1.0

    def test_pending_entries_counted_but_not_scored(self, tmp_path):
        config = _log(tmp_path, [
            "[2026-01-05 | NBIS | Underweight | pending]",
            "[2026-01-06 | NBIS | Overweight | +1.0% | +1.0% | 5d]",
        ])
        overall = get_track_record(config)["overall"]
        assert (overall["total"], overall["pending"], overall["scored"]) == (2, 1, 1)

    def test_no_scored_calls_yields_null_not_zero(self, tmp_path):
        """A null hit rate must not render as 0% — they mean different things."""
        config = _log(tmp_path, ["[2026-01-05 | NBIS | Underweight | pending]"])
        overall = get_track_record(config)["overall"]
        assert overall["hit_rate"] is None
        assert overall["avg_alpha"] is None

    def test_groups_by_ticker_most_analyzed_first(self, tmp_path):
        config = _log(tmp_path, [
            "[2026-01-05 | NOW | Overweight | +1.0% | +1.0% | 5d]",
            "[2026-01-06 | NOW | Overweight | +1.0% | +1.0% | 5d]",
            "[2026-01-07 | AAPL | Hold | +1.0% | +1.0% | 5d]",
        ])
        tickers = get_track_record(config)["tickers"]
        assert [t["ticker"] for t in tickers] == ["NOW", "AAPL"]
        assert tickers[0]["total"] == 2

    def test_entries_are_most_recent_first(self, tmp_path):
        """A rating flip should be visible without reading to the bottom."""
        config = _log(tmp_path, [
            "[2026-01-05 | NOW | Overweight | +1.0% | +1.0% | 5d]",
            "[2026-01-20 | NOW | Underweight | -1.0% | -1.0% | 5d]",
        ])
        entries = get_track_record(config)["tickers"][0]["entries"]
        assert [e["date"] for e in entries] == ["2026-01-20", "2026-01-05"]

    def test_empty_log_is_not_an_error(self, tmp_path):
        path = tmp_path / "memory.md"
        path.write_text("", encoding="utf-8")
        record = get_track_record({"memory_log_path": str(path)})
        assert record["tickers"] == []
        assert record["overall"]["total"] == 0
