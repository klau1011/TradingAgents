from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_fundamentals(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """
    Retrieve comprehensive fundamental data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing comprehensive fundamental data
    """
    # The overview reads live company info (TTM ratios, current price context)
    # regardless of curr_date, so in a historical backtest it would leak the
    # future. Disabled in evaluation mode (see backtest.py); the statement
    # tools below are date-bounded and stay available.
    if get_config().get("disable_lookahead_tools"):
        return (
            "DATA_UNAVAILABLE: the fundamentals overview is disabled in "
            "backtest/evaluation mode (it reads current company info, which "
            "leaks the future on a historical date). Use get_balance_sheet, "
            "get_income_statement, or get_cashflow (quarterly, date-bounded) "
            "instead."
        )
    return route_to_vendor("get_fundamentals", ticker, curr_date)


@tool
def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve balance sheet data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing balance sheet data
    """
    return route_to_vendor("get_balance_sheet", ticker, freq, curr_date)


@tool
def get_cashflow(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve cash flow statement data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing cash flow statement data
    """
    return route_to_vendor("get_cashflow", ticker, freq, curr_date)


@tool
def get_income_statement(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve income statement data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing income statement data
    """
    return route_to_vendor("get_income_statement", ticker, freq, curr_date)


@tool
def get_analyst_recommendations(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """
    Retrieve Wall Street analyst recommendations, price targets, and recent upgrades/downgrades.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
    Returns:
        str: A formatted report containing analyst recommendations and price targets
    """
    # Recommendations reflect current Wall Street views with no historical
    # bound, so they leak the future on a historical date.
    if get_config().get("disable_lookahead_tools"):
        return (
            "DATA_UNAVAILABLE: analyst recommendations are disabled in "
            "backtest/evaluation mode (they reflect current Wall Street "
            "views, which leak the future on a historical date)."
        )
    return route_to_vendor("get_analyst_recommendations", ticker)
