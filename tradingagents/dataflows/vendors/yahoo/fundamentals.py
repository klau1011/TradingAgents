from datetime import datetime
from typing import Annotated

import pandas as pd
import yfinance as yf

from tradingagents.dataflows.date_window import (
    withhold_live_profile,
    withhold_undated_statements,
    withhold_undisclosed_trades,
)
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.net import vendor_reachable
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.common import (
    YAHOO_HOST,
    raise_for_empty,
    yf_retry,
)

# Quote currencies Yahoo gives in a minor unit, and the main unit of each.
_MAIN_UNIT = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS"}


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None
):
    """Get company fundamentals overview from yfinance.

    ``Ticker.info`` is a present-day snapshot with no historical vintage, so a
    past ``as_of_date`` withholds it through the shared point-in-time guard
    (``date_window.withhold_live_profile``, #1300).
    """
    canonical = normalize_symbol(ticker)

    # Guard before the request: the response would only be discarded, and the
    # answer does not depend on it.
    withheld = withhold_live_profile(as_of_date, canonical)
    if withheld:
        return withheld

    info = yf_retry(lambda: yf.Ticker(canonical).info)
    if not info:
        raise_for_empty(ticker, canonical, "fundamentals")

    if str(info.get("quoteType", "")).upper() == "ETF":
        from tradingagents.dataflows.vendors.yahoo.etf import get_etf_profile
        return get_etf_profile(canonical, as_of_date)

    # Yahoo gives these two in percent (dividendYield 0.41 is 0.41%; debtToEquity
    # 78.4 is 78.4%, a ratio of 0.78) but the margins and returns as fractions,
    # so each carries its unit.
    dividend_yield, debt_to_equity = info.get("dividendYield"), info.get("debtToEquity")
    # Money figures come in three currencies (#1456): price levels in the quote
    # currency, which can be a minor unit (London in pence, GBp); market cap and
    # per-share figures in that currency's main unit (GBP), as Yahoo's own P/E
    # and P/B are computed against them; income figures in the currency the
    # company reports in (an ADR quotes in USD, reports in TWD), or bare when
    # Yahoo does not say which.
    quote = info.get("currency")
    main = _MAIN_UNIT.get(quote, quote)
    reported = info.get("financialCurrency")

    def money(key, currency):
        value = info.get(key)
        return None if value is None else f"{value} {currency}" if currency else value

    fields = [
        ("Name", info.get("longName")),
        ("Sector", info.get("sector")),
        ("Industry", info.get("industry")),
        ("Market Cap", money("marketCap", main)),
        ("PE Ratio (TTM)", info.get("trailingPE")),
        ("Forward PE", info.get("forwardPE")),
        ("PEG Ratio", info.get("pegRatio")),
        ("Price to Book", info.get("priceToBook")),
        ("EPS (TTM)", money("trailingEps", main)),
        ("Forward EPS", money("forwardEps", main)),
        ("Dividend Yield", None if dividend_yield is None else f"{dividend_yield}%"),
        ("Beta", info.get("beta")),
        ("52 Week High", money("fiftyTwoWeekHigh", quote)),
        ("52 Week Low", money("fiftyTwoWeekLow", quote)),
        ("50 Day Average", money("fiftyDayAverage", quote)),
        ("200 Day Average", money("twoHundredDayAverage", quote)),
        ("Revenue (TTM)", money("totalRevenue", reported)),
        ("Gross Profit", money("grossProfits", reported)),
        ("EBITDA", money("ebitda", reported)),
        ("Net Income", money("netIncomeToCommon", reported)),
        ("Profit Margin", info.get("profitMargins")),
        ("Operating Margin", info.get("operatingMargins")),
        ("Return on Equity", info.get("returnOnEquity")),
        ("Return on Assets", info.get("returnOnAssets")),
        ("Debt to Equity", None if debt_to_equity is None
         else f"{debt_to_equity}% ({debt_to_equity / 100:.2f}x)"),
        ("Current Ratio", info.get("currentRatio")),
        ("Book Value", money("bookValue", main)),
        ("Free Cash Flow", money("freeCashflow", reported)),
    ]

    lines = [f"{label}: {v}" for label, v in fields if v is not None]

    # yfinance returns a stub dict (e.g. {"trailingPegRatio": None}) for
    # unknown symbols, so `info` is truthy but every field is empty. Treat
    # "no usable fields" as no data rather than emitting a bare header the
    # agent might fabricate around.
    if not lines:
        raise_for_empty(ticker, canonical, "fundamental fields")

    return f"# Company Fundamentals for {canonical}\n\n" + "\n".join(lines)


def _statement(ticker, freq, as_of_date, title, quarterly_attr, annual_attr) -> str:
    """One financial statement as CSV, for a run dated today."""
    canonical = normalize_symbol(ticker)
    withheld = withhold_undated_statements(as_of_date, canonical, title)
    if withheld:
        return withheld
    what = title.lower()
    attr = quarterly_attr if freq.lower() == "quarterly" else annual_attr
    data = yf_retry(lambda: getattr(yf.Ticker(canonical), attr))
    if data is None or data.empty:
        raise_for_empty(ticker, canonical, f"{what} data")
    return f"# {title} data for {canonical} ({freq})\n" + data.to_csv()


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    as_of_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get balance sheet data from yfinance."""
    return _statement(ticker, freq, as_of_date, "Balance Sheet", "quarterly_balance_sheet", "balance_sheet")


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    as_of_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get cash flow data from yfinance."""
    return _statement(ticker, freq, as_of_date, "Cash Flow", "quarterly_cashflow", "cashflow")


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    as_of_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get income statement data from yfinance."""
    return _statement(ticker, freq, as_of_date, "Income Statement", "quarterly_income_stmt", "income_stmt")


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str | None, "analysis date, yyyy-mm-dd"] = None,
):
    """Get insider transactions data from yfinance, for a run dated today."""
    canonical = normalize_symbol(ticker)
    withheld = withhold_undisclosed_trades(as_of_date, canonical)
    if withheld:
        return withheld
    data = yf_retry(lambda: yf.Ticker(canonical).insider_transactions)

    # Empty is normal here (many valid symbols have no insider filings),
    # so report it plainly rather than treating the symbol as invalid.
    if data is None or data.empty:
        if not vendor_reachable(YAHOO_HOST):
            raise VendorUnavailableError("Yahoo Finance is unreachable; insider filings were not retrieved")
        return f"No insider transactions reported for symbol '{canonical}'"

    return f"# Insider Transactions data for {canonical}\n" + data.to_csv()


def get_company_profile(ticker: str) -> dict:
    """Yahoo's current profile for ``ticker``: name, sector, industry and the like."""
    return yf_retry(lambda: yf.Ticker(normalize_symbol(ticker)).info) or {}


def get_analyst_recommendations(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: str | None = None,
):
    """Get Wall Street analyst recommendations and price targets from yfinance."""
    withheld = withhold_live_profile(as_of_date, normalize_symbol(ticker))
    if withheld:
        return withheld
    try:
        ticker_obj = yf.Ticker(normalize_symbol(ticker))
        sections = []

        # Price targets
        try:
            targets = yf_retry(lambda: ticker_obj.analyst_price_targets)
            if targets is not None and not (isinstance(targets, pd.DataFrame) and targets.empty):
                sections.append(f"## Analyst Price Targets for {normalize_symbol(ticker)}")
                if isinstance(targets, dict):
                    for k, v in targets.items():
                        if v is not None:
                            sections.append(f"{k}: {v}")
                else:
                    sections.append(str(targets))
        except Exception:
            pass

        # Recommendations summary
        try:
            recs = yf_retry(lambda: ticker_obj.recommendations)
            if recs is not None and not recs.empty:
                sections.append(f"\n## Recent Analyst Recommendations for {normalize_symbol(ticker)}")
                sections.append(recs.head(20).to_csv())
        except Exception:
            pass

        # Upgrades / downgrades
        try:
            upgrades = yf_retry(lambda: ticker_obj.upgrades_downgrades)
            if upgrades is not None and not upgrades.empty:
                sections.append(f"\n## Recent Upgrades/Downgrades for {normalize_symbol(ticker)}")
                sections.append(upgrades.head(20).to_csv())
        except Exception:
            pass

        if not sections:
            return f"No analyst recommendation data found for symbol '{ticker}'"

        header = f"# Analyst Recommendations for {normalize_symbol(ticker)}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + "\n".join(sections)

    except Exception as e:
        return f"Error retrieving analyst recommendations for {ticker}: {str(e)}"


def get_live_quote(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: str | None = None,
) -> str:
    """Get a near-real-time quote snapshot (~15 min delayed) from yfinance.

    Returns last price, day range, volume, previous close, and percent change.
    Useful mid-trading-day when daily OHLCV bars only reflect the open.
    """
    withheld = withhold_live_profile(as_of_date, normalize_symbol(ticker))
    if withheld:
        return withheld
    try:
        t = yf.Ticker(normalize_symbol(ticker))
        fi = t.fast_info

        last = fi.get("lastPrice")
        prev_close = fi.get("previousClose")
        day_high = fi.get("dayHigh")
        day_low = fi.get("dayLow")
        last_volume = fi.get("lastVolume")
        mkt_cap = fi.get("marketCap")

        if last is None:
            return f"No live quote available for '{ticker}'"

        pct_change = ""
        if prev_close and prev_close != 0:
            change = ((last - prev_close) / prev_close) * 100
            pct_change = f"Change from prev close: {change:+.2f}%\n"

        header = f"# Live Quote Snapshot for {normalize_symbol(ticker)}\n"
        header += f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (delayed ~15 min)\n\n"

        lines = [
            f"Last Price: {last:.2f}" if last else None,
            f"Previous Close: {prev_close:.2f}" if prev_close else None,
            pct_change.strip() if pct_change else None,
            f"Day Range: {day_low:.2f} - {day_high:.2f}" if day_low and day_high else None,
            f"Volume: {last_volume:,.0f}" if last_volume else None,
            f"Market Cap: {mkt_cap:,.0f}" if mkt_cap else None,
        ]

        return header + "\n".join(line for line in lines if line)

    except Exception as e:
        return f"Error retrieving live quote for {ticker}: {str(e)}"
