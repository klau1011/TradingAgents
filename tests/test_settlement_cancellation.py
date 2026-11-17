"""Settlement cancellation avoids new calls while retaining completed work."""

from threading import Event
from unittest.mock import MagicMock

import pytest

from tradingagents.memory import TradingMemoryLog, settlement


@pytest.fixture
def pending_log(tmp_path):
    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "memory.md")})
    for ticker, date in (("AAPL", "2025-01-02"), ("AAPL", "2025-01-03"), ("MSFT", "2025-01-02")):
        log.store_decision(ticker, date, "Rating: Buy")
    return log


def test_stop_before_pass_makes_no_price_or_reflection_calls(pending_log, monkeypatch):
    fetch = MagicMock()
    reflector = MagicMock()
    monkeypatch.setattr(settlement, "fetch_returns", fetch)
    result = settlement.settle_pending("AAPL", pending_log, reflector, {}, should_stop=lambda: True)
    assert result.settled == result.failed == []
    fetch.assert_not_called()
    reflector.reflect_on_final_decision.assert_not_called()
    assert len(pending_log.get_pending_entries()) == 3


def test_stop_after_price_fetch_skips_reflection(pending_log, monkeypatch):
    stopped = Event()
    reflector = MagicMock()

    def fetch(*args, **kwargs):
        stopped.set()
        return 0.1, 0.08, 5, "2025-01-10"

    monkeypatch.setattr(settlement, "fetch_returns", fetch)
    result = settlement.settle_pending("AAPL", pending_log, reflector, {}, should_stop=stopped.is_set)
    assert result.settled == result.failed == []
    reflector.reflect_on_final_decision.assert_not_called()
    assert len(pending_log.get_pending_entries()) == 3


def test_stop_during_reflection_saves_completed_work_and_stops_remaining_tickers(pending_log, monkeypatch):
    stopped = Event()
    fetch = MagicMock(return_value=(0.1, 0.08, 5, "2025-01-10"))
    reflector = MagicMock()

    def reflect(**kwargs):
        stopped.set()
        return "Completed lesson."

    reflector.reflect_on_final_decision.side_effect = reflect
    monkeypatch.setattr(settlement, "fetch_returns", fetch)
    result = settlement.settle_all_pending(pending_log, reflector, {}, should_stop=stopped.is_set)
    assert result.settled == [("AAPL", "2025-01-02")]
    assert result.failed == []
    assert fetch.call_count == reflector.reflect_on_final_decision.call_count == 1
    assert len(pending_log.get_pending_entries()) == 2
    assert pending_log.load_entries()[0]["reflection"] == "Completed lesson."
