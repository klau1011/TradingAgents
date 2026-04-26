"""Per-run in-memory OHLCV cache.

Eliminates duplicate yfinance fetches within a single analysis run by keying
DataFrames on ``(symbol, ...)`` tuples and storing them in a
:class:`contextvars.ContextVar` so concurrent runs (e.g. the FastAPI backend
executing multiple analyses in parallel) maintain independent caches.

Usage::

    from tradingagents.dataflows.ohlcv_cache import start_run_cache

    with start_run_cache():
        # Any nested ``load_ohlcv`` / ``get_YFin_data_online`` calls share
        # one in-memory cache for the duration of the ``with`` block.
        graph.invoke(...)

When no cache is active, ``cache_get`` always returns ``None`` and ``cache_put``
is a no-op, so call sites can be wrapped unconditionally without affecting
ad-hoc usage of the data-fetching helpers.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Cache key shape: tuple of strings. Helpers build them so call sites stay
# compact. ``None`` sentinel means "no active cache".
CacheKey = Tuple[str, ...]
_cache_var: ContextVar[Optional[dict]] = ContextVar("ohlcv_cache", default=None)


@contextmanager
def start_run_cache() -> Iterator[dict]:
    """Activate a fresh per-run cache for the duration of the ``with`` block."""
    cache: dict = {}
    token = _cache_var.set(cache)
    try:
        yield cache
    finally:
        _cache_var.reset(token)


def cache_get(key: CacheKey) -> Optional[Any]:
    """Return the cached value (a copy when it's a DataFrame) or ``None``."""
    cache = _cache_var.get()
    if cache is None:
        return None
    value = cache.get(key)
    if value is None:
        return None
    logger.debug("ohlcv_cache HIT key=%s", key)
    # Defensive copy so downstream mutations (filtering, slicing) don't
    # poison the next consumer of the same key.
    if isinstance(value, pd.DataFrame):
        return value.copy()
    return value


def cache_put(key: CacheKey, value: Any) -> None:
    """Store ``value`` under ``key`` if a cache is active; otherwise a no-op."""
    cache = _cache_var.get()
    if cache is None:
        return
    if isinstance(value, pd.DataFrame):
        cache[key] = value.copy()
    else:
        cache[key] = value
    logger.debug("ohlcv_cache STORE key=%s", key)
