"""ETF-specific data fetchers built on top of yfinance.

Provides profile, holdings, sector weights, and benchmark correlation tools.
Uses the same caching directory and ``yf_retry`` wrapper as the rest of the
yfinance vendor layer. Heavy ``funds_data`` lookups are cached on disk for
24 hours since holdings/sectors/expense ratio change infrequently.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Annotated

import pandas as pd
import yfinance as yf

from .config import get_config
from .stockstats_utils import load_ohlcv, yf_retry

# Holdings/sectors update slowly; cache aggressively.
_ETF_CACHE_MAX_AGE_SECONDS = 24 * 60 * 60  # 24 hours


def _etf_cache_path(symbol: str, kind: str, ext: str = "json") -> str:
    config = get_config()
    cache_dir = os.path.join(config["data_cache_dir"], "etf")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{symbol.upper()}-{kind}.{ext}")


def _read_json_cache(path: str):
    if not os.path.exists(path):
        return None
    age = time.time() - os.path.getmtime(path)
    if age > _ETF_CACHE_MAX_AGE_SECONDS:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_json_cache(path: str, payload) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, default=str)
    except Exception:
        pass


def _is_etf(info: dict) -> bool:
    return str(info.get("quoteType", "")).upper() == "ETF"


def _format_pct(value) -> str:
    """Format a value yfinance already returns in percent units (e.g. 0.0945 = 0.09%)."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _format_fraction_pct(value) -> str:
    """Format a value yfinance returns as a fraction (e.g. 0.0945 = 9.45%)."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _format_unix_date(value) -> str:
    """Format a Unix epoch (seconds) as YYYY-MM-DD; pass through other inputs."""
    if value in (None, "", 0):
        return "N/A"
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError, OverflowError):
        return str(value)


def _get_funds_data(ticker_obj):
    """Return ``funds_data`` or ``None`` if unavailable for this ticker."""
    try:
        return ticker_obj.funds_data
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public tool implementations
# ---------------------------------------------------------------------------


def get_etf_profile(
    ticker: Annotated[str, "ETF ticker symbol"],
    curr_date: Annotated[str, "current date (unused, for routing parity)"] = None,
) -> str:
    """Return ETF profile: expense ratio, AUM, category, yield, NAV, beta, fund family."""
    symbol = ticker.upper()
    cache_path = _etf_cache_path(symbol, "profile")
    cached = _read_json_cache(cache_path)
    if cached is not None:
        info = cached.get("info", {})
        overview = cached.get("fund_overview") or {}
        description = cached.get("description") or ""
    else:
        try:
            t = yf.Ticker(symbol)
            info = yf_retry(lambda: t.info) or {}
            fd = _get_funds_data(t)
            overview = {}
            description = ""
            if fd is not None:
                try:
                    overview = yf_retry(lambda: fd.fund_overview) or {}
                except Exception:
                    overview = {}
                try:
                    description = yf_retry(lambda: fd.description) or ""
                except Exception:
                    description = ""
            _write_json_cache(
                cache_path,
                {"info": info, "fund_overview": overview, "description": description},
            )
        except Exception as e:
            return f"Error retrieving ETF profile for {ticker}: {e}"

    if not _is_etf(info):
        return (
            f"'{ticker}' does not appear to be an ETF "
            f"(quoteType={info.get('quoteType', 'unknown')})."
        )

    fields = [
        ("Name", info.get("longName") or info.get("shortName")),
        ("Category", info.get("category")),
        ("Fund Family", info.get("fundFamily")),
        ("Total Assets (AUM)", info.get("totalAssets")),
        ("NAV Price", info.get("navPrice")),
        ("Net Expense Ratio", _format_pct(info.get("netExpenseRatio") or overview.get("netExpenseRatio"))),
        ("Annual Report Expense Ratio", _format_pct(info.get("annualReportExpenseRatio"))),
        ("SEC Yield", _format_fraction_pct(info.get("yield"))),
        ("Trailing Dividend Yield", _format_fraction_pct(info.get("trailingAnnualDividendYield"))),
        ("Forward Dividend Yield", _format_pct(info.get("dividendYield"))),
        ("YTD Return", _format_pct(info.get("ytdReturn"))),
        ("3-Year Avg Return", _format_fraction_pct(info.get("threeYearAverageReturn"))),
        ("5-Year Avg Return", _format_fraction_pct(info.get("fiveYearAverageReturn"))),
        ("Beta (3Y)", info.get("beta3Year") or info.get("beta")),
        ("52 Week High", info.get("fiftyTwoWeekHigh")),
        ("52 Week Low", info.get("fiftyTwoWeekLow")),
        ("Inception Date", _format_unix_date(info.get("fundInceptionDate"))),
        ("Legal Type", info.get("legalType")),
        ("Investment Strategy", overview.get("categoryName") or overview.get("family")),
    ]

    lines = [f"{label}: {value}" for label, value in fields if value not in (None, "", "N/A")]
    if description:
        lines.append("")
        lines.append("## Description")
        lines.append(description.strip())

    header = (
        f"# ETF Profile for {symbol}\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + "\n".join(lines)


def get_etf_holdings(
    ticker: Annotated[str, "ETF ticker symbol"],
    top_n: Annotated[int, "number of top holdings to return"] = 25,
    curr_date: Annotated[str, "current date (unused, for routing parity)"] = None,
) -> str:
    """Return the ETF's top holdings (constituents and weights)."""
    symbol = ticker.upper()
    cache_path = _etf_cache_path(symbol, "holdings", ext="csv")

    df = None
    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age <= _ETF_CACHE_MAX_AGE_SECONDS:
            try:
                df = pd.read_csv(cache_path, index_col=0)
            except Exception:
                df = None

    if df is None:
        try:
            t = yf.Ticker(symbol)
            fd = _get_funds_data(t)
            if fd is None:
                return f"No holdings data available for '{ticker}'."
            df = yf_retry(lambda: fd.top_holdings)
        except Exception as e:
            return f"Error retrieving ETF holdings for {ticker}: {e}"

        if df is None or (hasattr(df, "empty") and df.empty):
            return f"No holdings data available for '{ticker}'."
        try:
            df.to_csv(cache_path)
        except Exception:
            pass

    try:
        df = df.head(int(top_n))
    except Exception:
        pass

    header = (
        f"# Top {len(df)} Holdings for {symbol}\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + df.to_csv()


def get_etf_sector_weights(
    ticker: Annotated[str, "ETF ticker symbol"],
    curr_date: Annotated[str, "current date (unused, for routing parity)"] = None,
) -> str:
    """Return the ETF's sector weight breakdown."""
    symbol = ticker.upper()
    cache_path = _etf_cache_path(symbol, "sectors")
    cached = _read_json_cache(cache_path)
    if cached is not None:
        weights = cached
    else:
        try:
            t = yf.Ticker(symbol)
            fd = _get_funds_data(t)
            if fd is None:
                return f"No sector weight data available for '{ticker}'."
            weights = yf_retry(lambda: fd.sector_weightings)
        except Exception as e:
            return f"Error retrieving sector weights for {ticker}: {e}"

        if not weights:
            return f"No sector weight data available for '{ticker}'."

        # ``sector_weightings`` may be a dict {sector: weight} or a DataFrame.
        if isinstance(weights, pd.DataFrame):
            weights = weights.iloc[:, 0].to_dict()
        elif isinstance(weights, pd.Series):
            weights = weights.to_dict()

        _write_json_cache(cache_path, weights)

    if not isinstance(weights, dict) or not weights:
        return f"No sector weight data available for '{ticker}'."

    sorted_items = sorted(weights.items(), key=lambda kv: float(kv[1] or 0), reverse=True)
    lines = [f"{sector}: {_format_fraction_pct(weight)}" for sector, weight in sorted_items]

    header = (
        f"# Sector Weights for {symbol}\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + "\n".join(lines)


def get_etf_correlation(
    ticker: Annotated[str, "ETF ticker symbol"],
    benchmark: Annotated[str, "benchmark ticker (e.g. SPY, QQQ, IWM)"] = "SPY",
    curr_date: Annotated[str, "current date YYYY-MM-DD (look-ahead cutoff)"] = None,
    lookback_days: Annotated[int, "trading-day window for correlation"] = 252,
) -> str:
    """Compute Pearson correlation of daily returns vs. a benchmark."""
    symbol = ticker.upper()
    bench = (benchmark or "SPY").upper()
    if curr_date is None:
        curr_date = datetime.now().strftime("%Y-%m-%d")

    try:
        a = load_ohlcv(symbol, curr_date)
        b = load_ohlcv(bench, curr_date)
    except Exception as e:
        return f"Error loading price history for correlation: {e}"

    if a.empty or b.empty:
        return f"Insufficient price history to compute correlation for {symbol} vs {bench}."

    a_close = a.set_index("Date")["Close"].astype(float).pct_change()
    b_close = b.set_index("Date")["Close"].astype(float).pct_change()

    joined = pd.concat([a_close, b_close], axis=1, join="inner").dropna()
    joined.columns = [symbol, bench]
    joined = joined.tail(int(lookback_days))

    if len(joined) < 30:
        return (
            f"Only {len(joined)} overlapping return observations for {symbol} vs {bench}; "
            "need at least 30 to compute a meaningful correlation."
        )

    corr = joined[symbol].corr(joined[bench])
    cov = joined[symbol].cov(joined[bench])
    var_b = joined[bench].var()
    beta = (cov / var_b) if var_b else float("nan")
    ann_vol_a = joined[symbol].std() * (252 ** 0.5)
    ann_vol_b = joined[bench].std() * (252 ** 0.5)

    header = (
        f"# Benchmark Correlation: {symbol} vs {bench}\n"
        f"# Window: trailing {len(joined)} trading days through {curr_date}\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    body = (
        f"Pearson correlation (daily returns): {corr:.3f}\n"
        f"Beta vs {bench}: {beta:.3f}\n"
        f"Annualized volatility {symbol}: {ann_vol_a * 100:.2f}%\n"
        f"Annualized volatility {bench}: {ann_vol_b * 100:.2f}%\n"
    )
    return header + body
