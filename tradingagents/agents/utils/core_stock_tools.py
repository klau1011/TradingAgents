from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve stock price data (OHLCV) for a given ticker symbol.
    Uses the configured core_stock_apis vendor.
    Args:
        symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: A formatted dataframe containing the stock price data for the specified ticker symbol in the specified date range.
    """
    return route_to_vendor("get_stock_data", symbol, start_date, end_date)


@tool
def get_live_quote(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """
    Get a near-real-time quote snapshot (~15 min delayed) for a ticker.
    Returns last price, day change, day range, and volume.
    Useful for seeing where the stock is trading right now.
    Args:
        symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
    Returns:
        str: A formatted snapshot of the current quote.
    """
    # A live quote reads "now" regardless of the analysis date, so in a
    # historical backtest it would reveal the future price. Disabled in
    # evaluation mode (see backtest.py); use get_stock_data /
    # get_verified_market_snapshot, which are bounded by the trade date.
    if get_config().get("disable_lookahead_tools"):
        return (
            "DATA_UNAVAILABLE: live quote is disabled in backtest/evaluation mode "
            "(it reads the current price, which leaks the future on a historical "
            "date). Use get_stock_data or get_verified_market_snapshot bounded by "
            "the trade date instead."
        )
    return route_to_vendor("get_live_quote", symbol)
