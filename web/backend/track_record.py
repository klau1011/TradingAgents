"""Read-side summary of the decision log.

The memory log already records every rating and its realized alpha, but only
the agents ever read it. This turns it into a scoreboard: what was called, how
it turned out, and whether the calls beat the benchmark often enough to trust.
"""

from __future__ import annotations

from typing import Any

from tradingagents.agents.utils.memory import TradingMemoryLog, _parse_pct
from tradingagents.agents.utils.rating import direction
from tradingagents.default_config import DEFAULT_CONFIG


def _scored(entry: dict) -> bool:
    """True when the call took a side and the outcome is known.

    Hold takes no position, so it has no directional outcome to be right about
    and is excluded from the hit rate rather than counted as a miss.
    """
    return (
        not entry.get("pending")
        and direction(entry.get("rating")) != 0
        and _parse_pct(entry.get("alpha")) is not None
    )


def _is_hit(entry: dict) -> bool:
    """A call is a hit when realized alpha moved the way the rating implied."""
    return direction(entry["rating"]) * _parse_pct(entry["alpha"]) > 0


def _summarize(entries: list[dict]) -> dict[str, Any]:
    scored = [e for e in entries if _scored(e)]
    hits = [e for e in scored if _is_hit(e)]
    alphas = [_parse_pct(e["alpha"]) for e in scored]
    return {
        "total": len(entries),
        "pending": sum(1 for e in entries if e.get("pending")),
        "scored": len(scored),
        "hits": len(hits),
        # None rather than 0.0 so the UI can distinguish "no data yet" from
        # "every call missed".
        "hit_rate": len(hits) / len(scored) if scored else None,
        "avg_alpha": sum(alphas) / len(alphas) if alphas else None,
    }


def get_track_record(config: dict | None = None) -> dict[str, Any]:
    """Return overall and per-ticker performance from the decision log."""
    entries = TradingMemoryLog(config or DEFAULT_CONFIG).load_entries()

    by_ticker: dict[str, list[dict]] = {}
    for entry in entries:
        by_ticker.setdefault(entry["ticker"], []).append(entry)

    tickers = [
        {
            "ticker": ticker,
            **_summarize(rows),
            # Most recent first so a rating flip is visible at a glance.
            "entries": [
                {
                    "date": e["date"],
                    "rating": e["rating"],
                    "pending": e["pending"],
                    "raw": e["raw"],
                    "alpha": e["alpha"],
                    "holding": e["holding"],
                    "reflection": e["reflection"],
                }
                for e in reversed(rows)
            ],
        }
        for ticker, rows in by_ticker.items()
    ]
    # Most-analyzed first; ties broken alphabetically for a stable order.
    tickers.sort(key=lambda t: (-t["total"], t["ticker"]))

    return {"overall": _summarize(entries), "tickers": tickers}
