"""Tests for ETF-specific data path: detection, routing, analyst tool selection."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.dataflows import router as interface
from tradingagents.dataflows.vendors.yahoo import etf as y_finance_etf

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


def test_build_instrument_context_includes_etf_marker() -> None:
    from tradingagents.agents.context import build_instrument_context
    ctx = build_instrument_context("SPY", identity={
        "quote_type": "ETF", "company_name": "SPDR S&P 500", "category": "Large Blend",
        "total_assets": 650_000_000_000, "expense_ratio": 0.0945,
    })
    assert "ETF" in ctx
    assert "Large Blend" in ctx
    assert "expense ratio" in ctx
    assert "0.0945%" in ctx


def test_historical_etf_context_hides_current_metrics() -> None:
    from tradingagents.agents.context import build_instrument_context
    ctx = build_instrument_context("SPY", identity={
        "quote_type": "ETF", "category": "Large Blend", "expense_ratio": 0.0945,
    }, trade_date="2020-01-01")
    assert "is an ETF" in ctx
    assert "Large Blend" not in ctx
    assert "0.0945%" not in ctx


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
            "instrument_context": "SPY is an ETF",
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


@pytest.mark.parametrize("tool", [
    y_finance_etf.get_etf_profile,
    y_finance_etf.get_etf_holdings,
    y_finance_etf.get_etf_sector_weights,
])
def test_etf_current_snapshot_is_withheld_for_historical_run(monkeypatch, tool):
    def unexpected_request(*args, **kwargs):
        raise AssertionError("historical snapshot must not fetch current data")
    monkeypatch.setattr(y_finance_etf.yf, "Ticker", unexpected_request)
    result = tool("SPY", curr_date="2020-01-01")
    assert "withheld" in result.lower() or "unavailable" in result.lower()


def test_market_only_analysis_can_compare_an_etf_to_its_benchmark(monkeypatch):
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    from tradingagents.agents import tools
    from tradingagents.agents.analysts import market_analyst
    from tradingagents.graph.analyst_execution import build_analyst_execution_plan

    bound = []

    class FakeLLM:
        def bind_tools(self, offered):
            bound.extend(offered)
            return RunnableLambda(lambda _: AIMessage(content="ETF market report"))

    market_analyst.create_market_analyst(FakeLLM())({
        "company_of_interest": "SPY", "trade_date": "2020-01-03",
        "instrument_context": "SPY is an ETF", "messages": [],
    })
    spec = build_analyst_execution_plan(["market"]).specs[0]
    assert tools.get_etf_correlation in bound
    assert tools.get_etf_correlation in spec.tools

    routed = []
    monkeypatch.setattr(tools, "route_to_vendor", lambda *args: routed.append(args) or "correlation")
    assert tools.get_etf_correlation.func(
        "SPY", benchmark="QQQ", curr_date="2030-01-01", trade_date="2020-01-03"
    ) == "correlation"
    assert routed == [("get_etf_correlation", "SPY", "QQQ", "2020-01-03", 252)]
