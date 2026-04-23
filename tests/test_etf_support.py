"""Tests for ETF-specific data path: detection, routing, analyst tool selection."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.dataflows import interface
from tradingagents.dataflows import y_finance_etf


# ---------------------------------------------------------------------------
# Routing / category registration
# ---------------------------------------------------------------------------


def test_etf_data_category_registered() -> None:
    assert "etf_data" in interface.TOOLS_CATEGORIES
    tools = interface.TOOLS_CATEGORIES["etf_data"]["tools"]
    assert set(tools) == {
        "get_etf_profile",
        "get_etf_holdings",
        "get_etf_sector_weights",
        "get_etf_correlation",
    }


@pytest.mark.parametrize(
    "method",
    ["get_etf_profile", "get_etf_holdings", "get_etf_sector_weights", "get_etf_correlation"],
)
def test_etf_methods_routed_to_yfinance(method: str) -> None:
    assert method in interface.VENDOR_METHODS
    assert "yfinance" in interface.VENDOR_METHODS[method]


def test_route_to_vendor_dispatches_etf_method(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = "ETF_PROFILE_OK"
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_etf_profile",
        {"yfinance": lambda *a, **kw: sentinel},
    )
    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "yfinance")
    assert interface.route_to_vendor("get_etf_profile", "SPY") == sentinel


# ---------------------------------------------------------------------------
# Instrument-kind detection
# ---------------------------------------------------------------------------


def test_detect_instrument_kind_etf() -> None:
    from tradingagents.agents.utils import agent_utils

    fake_ticker = MagicMock()
    fake_ticker.info = {"quoteType": "ETF", "longName": "Test ETF", "category": "Large Blend"}
    with patch("yfinance.Ticker", return_value=fake_ticker):
        kind, info = agent_utils.detect_instrument_kind("XYZ")
    assert kind == "etf"
    assert info["category"] == "Large Blend"


def test_detect_instrument_kind_equity() -> None:
    from tradingagents.agents.utils import agent_utils

    fake_ticker = MagicMock()
    fake_ticker.info = {"quoteType": "EQUITY"}
    with patch("yfinance.Ticker", return_value=fake_ticker):
        kind, _ = agent_utils.detect_instrument_kind("AAPL")
    assert kind == "equity"


def test_detect_instrument_kind_failure_returns_unknown() -> None:
    from tradingagents.agents.utils import agent_utils

    with patch("yfinance.Ticker", side_effect=RuntimeError("network down")):
        kind, info = agent_utils.detect_instrument_kind("???")
    assert kind == "unknown"
    assert info == {}


def test_build_instrument_context_includes_etf_marker() -> None:
    from tradingagents.agents.utils import agent_utils

    fake_ticker = MagicMock()
    fake_ticker.info = {
        "quoteType": "ETF",
        "longName": "SPDR S&P 500",
        "category": "Large Blend",
        "totalAssets": 650_000_000_000,
        "netExpenseRatio": 0.0945,
    }
    with patch("yfinance.Ticker", return_value=fake_ticker):
        ctx = agent_utils.build_instrument_context("SPY")
    assert "ETF" in ctx
    assert "Large Blend" in ctx
    assert "expense ratio" in ctx
    assert "0.09%" in ctx  # already in percent units


# ---------------------------------------------------------------------------
# Fundamentals analyst tool selection
# ---------------------------------------------------------------------------


def test_fundamentals_analyst_uses_etf_tools_for_etf() -> None:
    from langchain_core.runnables import RunnableLambda

    from tradingagents.agents.analysts import fundamentals_analyst as fa

    captured: dict = {}

    def _fake_invoke(_):
        res = MagicMock()
        res.tool_calls = []
        res.content = "ok"
        return res

    class FakeLLM:
        def bind_tools(self, tools):
            captured["names"] = [t.name for t in tools]
            return RunnableLambda(_fake_invoke)

    fake_ticker = MagicMock()
    fake_ticker.info = {"quoteType": "ETF", "longName": "Test", "category": "Large Blend"}

    node = fa.create_fundamentals_analyst(FakeLLM())
    with patch("yfinance.Ticker", return_value=fake_ticker):
        node({
            "trade_date": "2026-04-22",
            "company_of_interest": "SPY",
            "messages": [],
        })

    names = set(captured["names"])
    assert "get_etf_profile" in names
    assert "get_etf_holdings" in names
    assert "get_etf_sector_weights" in names
    assert "get_etf_correlation" in names
    # Equity-only tools should NOT be bound for ETFs.
    assert "get_balance_sheet" not in names
    assert "get_income_statement" not in names


def test_fundamentals_analyst_uses_equity_tools_for_stock() -> None:
    from langchain_core.runnables import RunnableLambda

    from tradingagents.agents.analysts import fundamentals_analyst as fa

    captured: dict = {}

    def _fake_invoke(_):
        res = MagicMock()
        res.tool_calls = []
        res.content = "ok"
        return res

    class FakeLLM:
        def bind_tools(self, tools):
            captured["names"] = [t.name for t in tools]
            return RunnableLambda(_fake_invoke)

    fake_ticker = MagicMock()
    fake_ticker.info = {"quoteType": "EQUITY"}

    node = fa.create_fundamentals_analyst(FakeLLM())
    with patch("yfinance.Ticker", return_value=fake_ticker):
        node({
            "trade_date": "2026-04-22",
            "company_of_interest": "AAPL",
            "messages": [],
        })

    names = set(captured["names"])
    assert "get_balance_sheet" in names
    assert "get_income_statement" in names
    assert "get_etf_profile" not in names


# ---------------------------------------------------------------------------
# y_finance_etf formatters & correlation math
# ---------------------------------------------------------------------------


def test_format_pct_handles_already_percent_values() -> None:
    assert y_finance_etf._format_pct(0.0945) == "0.09%"
    assert y_finance_etf._format_pct(None) == "N/A"


def test_format_fraction_pct_multiplies_by_100() -> None:
    assert y_finance_etf._format_fraction_pct(0.0114) == "1.14%"
    assert y_finance_etf._format_fraction_pct(None) == "N/A"


def test_format_unix_date_handles_epoch_seconds() -> None:
    assert y_finance_etf._format_unix_date(727660800) == "1993-01-22"
    assert y_finance_etf._format_unix_date(None) == "N/A"
    assert y_finance_etf._format_unix_date(0) == "N/A"


def test_get_etf_correlation_computes_from_cached_ohlcv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two perfectly correlated price series should yield correlation ~1.0."""
    dates = pd.date_range("2024-01-01", periods=120, freq="B")
    a = pd.DataFrame({"Date": dates, "Close": [100 + i for i in range(120)]})
    b = pd.DataFrame({"Date": dates, "Close": [200 + 2 * i for i in range(120)]})

    def fake_load_ohlcv(symbol, curr_date):
        return a.copy() if symbol == "AAA" else b.copy()

    monkeypatch.setattr(y_finance_etf, "load_ohlcv", fake_load_ohlcv)

    out = y_finance_etf.get_etf_correlation("AAA", "BBB", "2024-06-30", 252)
    assert "Pearson correlation" in out
    # Linear-related series produce correlation very close to 1.
    assert "1.000" in out or "0.99" in out


def test_get_etf_correlation_reports_short_history(monkeypatch: pytest.MonkeyPatch) -> None:
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    df = pd.DataFrame({"Date": dates, "Close": list(range(10))})
    monkeypatch.setattr(y_finance_etf, "load_ohlcv", lambda *_a, **_k: df.copy())
    out = y_finance_etf.get_etf_correlation("AAA", "BBB", "2024-06-30", 252)
    assert "need at least 30" in out
