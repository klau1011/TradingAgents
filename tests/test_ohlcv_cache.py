"""Tests for the per-run OHLCV cache (tradingagents.dataflows.ohlcv_cache)."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import patch

import pandas as pd
import pytest

from tradingagents.dataflows.ohlcv_cache import (
    cache_get,
    cache_put,
    start_run_cache,
)


def test_no_active_cache_is_noop():
    cache_put(("ohlcv", "AAPL", "2026-04-25"), pd.DataFrame({"x": [1]}))
    assert cache_get(("ohlcv", "AAPL", "2026-04-25")) is None


def test_active_cache_round_trips_dataframe():
    df = pd.DataFrame({"Close": [100.0, 101.0]})
    with start_run_cache():
        cache_put(("ohlcv", "AAPL", "2026-04-25"), df)
        got = cache_get(("ohlcv", "AAPL", "2026-04-25"))
        assert got is not None
        assert list(got["Close"]) == [100.0, 101.0]


def test_cache_returns_defensive_copy():
    df = pd.DataFrame({"Close": [100.0]})
    with start_run_cache():
        cache_put(("ohlcv", "AAPL", "2026-04-25"), df)
        first = cache_get(("ohlcv", "AAPL", "2026-04-25"))
        first.loc[0, "Close"] = 999.0  # mutate the returned copy
        second = cache_get(("ohlcv", "AAPL", "2026-04-25"))
        assert second.loc[0, "Close"] == 100.0


def test_cache_isolated_across_runs():
    """Two sequential ``start_run_cache`` blocks must not share state."""
    with start_run_cache():
        cache_put(("ohlcv", "AAPL", "2026-04-25"), pd.DataFrame({"x": [1]}))
        assert cache_get(("ohlcv", "AAPL", "2026-04-25")) is not None

    with start_run_cache():
        # Fresh cache; previous put is invisible.
        assert cache_get(("ohlcv", "AAPL", "2026-04-25")) is None


def test_load_ohlcv_dedupes_within_run():
    """Two ``load_ohlcv`` calls inside a run trigger only one fetch."""
    from tradingagents.dataflows import stockstats_utils

    fake_payload = pd.DataFrame(
        {
            "Date": pd.date_range("2024-01-01", periods=3),
            "Open": [1.0, 2.0, 3.0],
            "High": [1.0, 2.0, 3.0],
            "Low": [1.0, 2.0, 3.0],
            "Close": [1.0, 2.0, 3.0],
            "Volume": [10, 20, 30],
        }
    )

    fetch_calls = {"n": 0}

    def fake_yf_retry(thunk, *_args, **_kwargs):
        fetch_calls["n"] += 1
        df = fake_payload.set_index("Date")
        return df

    # Force the file-cache miss branch so we always hit the (mocked) network.
    with patch.object(stockstats_utils.os.path, "exists", return_value=False), \
        patch.object(stockstats_utils, "yf_retry", side_effect=fake_yf_retry), \
        patch.object(stockstats_utils.os, "makedirs"), \
        patch("pandas.DataFrame.to_csv"):
        with start_run_cache():
            stockstats_utils.load_ohlcv("AAPL", "2026-04-25")
            stockstats_utils.load_ohlcv("AAPL", "2026-04-25")
            assert fetch_calls["n"] == 1, "second call should hit the per-run cache"

        # New run -> fresh cache -> fetch fires again.
        with start_run_cache():
            stockstats_utils.load_ohlcv("AAPL", "2026-04-25")
            assert fetch_calls["n"] == 2


def test_concurrent_runs_have_independent_caches():
    """Two threads each in their own ``start_run_cache`` must not collide."""
    barrier = threading.Barrier(2)
    results: dict = {}

    def worker(symbol: str, value: float) -> None:
        with start_run_cache():
            cache_put(("ohlcv", symbol, "2026-04-25"), pd.DataFrame({"Close": [value]}))
            barrier.wait()  # both threads now have entries; ensure no leak
            got = cache_get(("ohlcv", symbol, "2026-04-25"))
            other = cache_get(("ohlcv", "OTHER" if symbol == "AAPL" else "AAPL", "2026-04-25"))
            results[symbol] = (got.loc[0, "Close"], other)

    t1 = threading.Thread(target=worker, args=("AAPL", 100.0))
    t2 = threading.Thread(target=worker, args=("MSFT", 200.0))
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert results["AAPL"] == (100.0, None)
    assert results["MSFT"] == (200.0, None)


def test_concurrent_runs_async_have_independent_caches():
    """``contextvars`` propagate per-task in asyncio; verify cache isolation."""

    async def task(symbol: str, value: float) -> tuple:
        with start_run_cache():
            cache_put(("ohlcv", symbol, "2026-04-25"), pd.DataFrame({"Close": [value]}))
            await asyncio.sleep(0)  # yield to the other task
            got = cache_get(("ohlcv", symbol, "2026-04-25"))
            other_symbol = "MSFT" if symbol == "AAPL" else "AAPL"
            other = cache_get(("ohlcv", other_symbol, "2026-04-25"))
            return got.loc[0, "Close"], other

    async def runner():
        return await asyncio.gather(task("AAPL", 100.0), task("MSFT", 200.0))

    a, b = asyncio.run(runner())
    assert a == (100.0, None)
    assert b == (200.0, None)
