from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows import y_finance


def _synthetic_ohlcv(rows: int = 40) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=rows, freq="D")
    base_price = 100.0
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": [base_price + i * 0.2 for i in range(rows)],
            "High": [base_price + i * 0.25 + 1 for i in range(rows)],
            "Low": [base_price + i * 0.15 - 1 for i in range(rows)],
            "Close": [base_price + i * 0.2 for i in range(rows)],
            "Volume": [1000 + i * 50 for i in range(rows)],
        }
    )


@pytest.mark.parametrize(
    ("indicator", "assertion"),
    [
        ("rvol", lambda v: v > 1.0),
        ("volume_zscore", lambda v: v > 0.0),
        ("volume_trend_slope", lambda v: v > 0.0),
    ],
)
def test_custom_volume_indicators_on_rising_volume(monkeypatch: pytest.MonkeyPatch, indicator: str, assertion) -> None:
    monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: _synthetic_ohlcv())

    values = y_finance._get_stock_stats_bulk("AAPL", indicator, "2026-02-09")
    latest_day = sorted(values.keys())[-1]
    latest_value = values[latest_day]

    assert latest_value != "N/A"
    numeric = float(latest_value)
    assert assertion(numeric)


def test_volume_z_score_alias_via_public_indicator_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: _synthetic_ohlcv())

    output = y_finance.get_stock_stats_indicators_window(
        symbol="AAPL",
        indicator="volume_z_score",
        curr_date="2026-02-09",
        look_back_days=5,
    )

    assert "## volume_zscore values" in output
    assert "not supported" not in output.lower()


def test_custom_indicator_window_fallback_does_not_emit_blank_values(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_bulk(*args, **kwargs):
        raise RuntimeError("forced bulk failure")

    monkeypatch.setattr(y_finance, "_get_stock_stats_bulk", _raise_bulk)
    monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: _synthetic_ohlcv())

    output = y_finance.get_stock_stats_indicators_window(
        symbol="AAPL",
        indicator="rvol",
        curr_date="2026-02-09",
        look_back_days=3,
    )

    date_lines = [
        line
        for line in output.splitlines()
        if len(line) >= 11 and line[4] == "-" and line[7] == "-" and ":" in line
    ]

    assert date_lines
    for line in date_lines:
        assert line.split(":", 1)[1].strip(), f"expected non-blank indicator value in line: {line}"
