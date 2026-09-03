from __future__ import annotations

import json
import logging
from collections import OrderedDict
from datetime import datetime
from threading import Lock
from time import monotonic, perf_counter, time
from uuid import UUID

from app.core.config import settings
from app.schemas.analytics_catalog import AnalyticsCatalogRunRead, AnalyticsCatalogRunRequest

logger = logging.getLogger(__name__)


class _AggregateCacheEntry:
    __slots__ = ("expires_at", "result")

    def __init__(self, *, expires_at: float, result: AnalyticsCatalogRunRead) -> None:
        self.expires_at = expires_at
        self.result = result


_cache_lock = Lock()
_aggregate_cache: OrderedDict[str, _AggregateCacheEntry] = OrderedDict()


def _cache_key(
    *,
    workspace_id: UUID,
    request: AnalyticsCatalogRunRequest,
    as_of: datetime | None,
) -> str:
    # Pydantic's JSON-mode dump is deterministic after we sort keys here. The
    # workspace is part of the key so aggregate results can never cross tenants.
    payload = json.dumps(
        request.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    ttl = max(1, settings.analytics_aggregate_cache_ttl_seconds)
    epoch = as_of.timestamp() if as_of is not None else time()
    # Relative periods move with the clock. Bucketing the as-of time prevents a
    # cached "last N days" result from being reused at a materially different
    # point in time while still absorbing duplicate requests within the TTL.
    as_of_bucket = int(epoch // ttl)
    return f"{workspace_id}:{as_of_bucket}:{payload}"


def get_cached_aggregate(
    *,
    workspace_id: UUID,
    request: AnalyticsCatalogRunRequest,
    as_of: datetime | None,
) -> AnalyticsCatalogRunRead | None:
    """Return a short-lived aggregate result, never a patient-list result.

    This is deliberately a micro-cache rather than a long-lived reporting
    cache. It absorbs duplicate clicks/refreshes while keeping the maximum
    staleness bounded by ANALYTICS_AGGREGATE_CACHE_TTL_SECONDS. Exports bypass
    this cache so downloaded data is always re-executed against the database.
    """
    ttl = settings.analytics_aggregate_cache_ttl_seconds
    max_entries = settings.analytics_aggregate_cache_max_entries
    if ttl <= 0 or max_entries <= 0:
        return None

    key = _cache_key(workspace_id=workspace_id, request=request, as_of=as_of)
    now = monotonic()
    with _cache_lock:
        entry = _aggregate_cache.get(key)
        if entry is None:
            return None
        if entry.expires_at <= now:
            _aggregate_cache.pop(key, None)
            return None
        _aggregate_cache.move_to_end(key)
        return entry.result.model_copy(deep=True)


def put_cached_aggregate(
    *,
    workspace_id: UUID,
    request: AnalyticsCatalogRunRequest,
    result: AnalyticsCatalogRunRead,
    as_of: datetime | None,
) -> None:
    if result.result_kind == "patient_list":
        return
    ttl = settings.analytics_aggregate_cache_ttl_seconds
    max_entries = settings.analytics_aggregate_cache_max_entries
    if ttl <= 0 or max_entries <= 0:
        return

    key = _cache_key(workspace_id=workspace_id, request=request, as_of=as_of)
    now = monotonic()
    with _cache_lock:
        # Opportunistically remove expired entries before enforcing the bound.
        expired = [cache_key for cache_key, entry in _aggregate_cache.items() if entry.expires_at <= now]
        for cache_key in expired:
            _aggregate_cache.pop(cache_key, None)
        _aggregate_cache[key] = _AggregateCacheEntry(
            expires_at=now + ttl,
            result=result.model_copy(deep=True),
        )
        _aggregate_cache.move_to_end(key)
        while len(_aggregate_cache) > max_entries:
            _aggregate_cache.popitem(last=False)


def clear_analytics_aggregate_cache() -> None:
    """Testing/operations hook; normal correctness never depends on the cache."""
    with _cache_lock:
        _aggregate_cache.clear()


def log_catalog_execution(
    *,
    workspace_id: UUID,
    analysis_key: str,
    started_at: float,
    cache_hit: bool,
    rows: int,
) -> None:
    elapsed_ms = round((perf_counter() - started_at) * 1000.0, 1)
    logger.info(
        "analytics catalog workspace_id=%s analysis_key=%s cache_hit=%s rows=%s duration_ms=%s",
        workspace_id,
        analysis_key,
        cache_hit,
        rows,
        elapsed_ms,
    )
