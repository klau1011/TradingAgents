from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_etf_profile(
    ticker: Annotated[str, "ETF ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve ETF profile data: expense ratio, AUM, category, fund family,
    yield, NAV, beta, inception date, and investment strategy description.
    Use this instead of company-fundamentals tools when the instrument is an ETF.
    Args:
        ticker (str): ETF ticker symbol
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted ETF profile report
    """
    return route_to_vendor("get_etf_profile", ticker, curr_date)


@tool
def get_etf_holdings(
    ticker: Annotated[str, "ETF ticker symbol"],
    top_n: Annotated[int, "number of top holdings to return"] = 25,
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve the ETF's top constituent holdings with their portfolio weights.
    Useful for assessing concentration risk and underlying exposure.
    Args:
        ticker (str): ETF ticker symbol
        top_n (int): Number of top holdings to return (default 25)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A CSV-formatted list of top holdings and weights
    """
    return route_to_vendor("get_etf_holdings", ticker, top_n, curr_date)


@tool
def get_etf_sector_weights(
    ticker: Annotated[str, "ETF ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve the ETF's sector allocation breakdown.
    Useful for understanding thematic/sector exposure and diversification.
    Args:
        ticker (str): ETF ticker symbol
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted sector weight report
    """
    return route_to_vendor("get_etf_sector_weights", ticker, curr_date)


@tool
def get_etf_correlation(
    ticker: Annotated[str, "ETF ticker symbol"],
    benchmark: Annotated[str, "benchmark ticker (e.g. SPY, QQQ, IWM)"] = "SPY",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
    lookback_days: Annotated[int, "trading-day window for correlation"] = 252,
) -> str:
    """
    Compute Pearson correlation, beta, and annualized volatility of the ETF's
    daily returns versus a benchmark over the trailing window. Useful for
    assessing whether an ETF adds diversification beyond a benchmark like SPY.
    Args:
        ticker (str): ETF ticker symbol
        benchmark (str): Benchmark ticker, default "SPY"
        curr_date (str): Current date you are trading at, yyyy-mm-dd
        lookback_days (int): Window size in trading days, default 252
    Returns:
        str: A formatted correlation/beta/volatility report
    """
    return route_to_vendor(
        "get_etf_correlation", ticker, benchmark, curr_date, lookback_days
    )
