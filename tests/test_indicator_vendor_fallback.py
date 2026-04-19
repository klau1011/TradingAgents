from __future__ import annotations

import pytest

from tradingagents.dataflows import interface


def test_route_to_vendor_falls_back_when_primary_indicator_vendor_rejects_indicator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "alpha_vantage")

    def alpha_vantage_impl(*args, **kwargs):
        calls.append("alpha_vantage")
        raise ValueError("Indicator rvol is not supported")

    def yfinance_impl(*args, **kwargs):
        calls.append("yfinance")
        return "YFINANCE_FALLBACK_OK"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_indicators",
        {
            "alpha_vantage": alpha_vantage_impl,
            "yfinance": yfinance_impl,
        },
    )

    value = interface.route_to_vendor("get_indicators", "AAPL", "rvol", "2026-02-09", 5)

    assert value == "YFINANCE_FALLBACK_OK"
    assert calls == ["alpha_vantage", "yfinance"]


def test_route_to_vendor_raises_last_value_error_when_all_indicator_vendors_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "alpha_vantage")

    def alpha_vantage_impl(*args, **kwargs):
        raise ValueError("alpha_vantage: Indicator rvol is not supported")

    def yfinance_impl(*args, **kwargs):
        raise ValueError("yfinance: Indicator rvol is not supported")

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_indicators",
        {
            "alpha_vantage": alpha_vantage_impl,
            "yfinance": yfinance_impl,
        },
    )

    with pytest.raises(ValueError, match="not supported"):
        interface.route_to_vendor("get_indicators", "AAPL", "rvol", "2026-02-09", 5)
