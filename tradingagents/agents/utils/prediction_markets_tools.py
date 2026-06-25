from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_prediction_markets(
    topic: Annotated[
        str,
        "Event topic/keyword, e.g. 'Fed rate cut', 'recession 2026', "
        "'US election', or a sector/company event.",
    ],
    limit: Annotated[int | None, "Max markets to return; omit for a default of 6"] = None,
) -> str:
    """
    Retrieve live, market-implied probabilities for forward-looking events from
    prediction markets (Polymarket): Fed decisions, recession, elections,
    geopolitics, crypto. Returns the most-traded open markets matching the
    topic, each with its implied probability, traded volume, resolution date,
    and recent move. Uses the configured prediction_markets vendor.

    Args:
        topic (str): Event keyword(s) to search
        limit (int): Max markets to return; omit for a default of 6

    Returns:
        str: A formatted markdown report of matching prediction markets
    """
    # Polymarket odds are live ("now") regardless of the analysis date, so in a
    # historical backtest they leak current market-implied probabilities into a
    # past date. Disabled in evaluation mode (see backtest.py).
    if get_config().get("disable_lookahead_tools"):
        return (
            "DATA_UNAVAILABLE: live prediction-market odds are disabled in "
            "backtest/evaluation mode (they read current probabilities, which "
            "leak the future on a historical date). Proceed without "
            "prediction-market signal."
        )
    return route_to_vendor("get_prediction_markets", topic, limit)
