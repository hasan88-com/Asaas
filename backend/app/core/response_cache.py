"""
Asaas (اثاثہ) — Response Cache

Lightweight per-endpoint JSON cache backed by Redis, for read-mostly endpoints
(/news/feed, /flags, /portfolio). Stores the already-serialized response body so
a repeat load hits Redis instead of re-querying Postgres. Short TTLs plus
explicit invalidation on mutations keep it fresh.

Transport/serving layer only — cached payloads are byte-identical to a fresh
serialization of the same data.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

from app.core.redis import redis_client

logger = logging.getLogger("asaas.response_cache")

_PREFIX = "cache:resp:v1:"


async def get_cached(key: str) -> Optional[Any]:
    """Return the cached JSON payload for ``key``, or None on miss/error."""
    try:
        raw = await redis_client.get(_PREFIX + key)
        if raw:
            return json.loads(raw)
    except Exception as exc:  # cache must never break the request
        logger.debug("response cache get failed (%s): %s", key, exc)
    return None


async def set_cached(key: str, payload: Any, ttl: int) -> None:
    try:
        await redis_client.setex(_PREFIX + key, ttl, json.dumps(payload, default=str))
    except Exception as exc:
        logger.debug("response cache set failed (%s): %s", key, exc)


async def invalidate(*keys: str) -> None:
    if not keys:
        return
    try:
        await redis_client.delete(*[_PREFIX + k for k in keys])
    except Exception as exc:
        logger.debug("response cache invalidate failed: %s", exc)


# --- Key builders ---------------------------------------------------------

NEWS_FEED_KEY = "news_feed"  # global: the feed is not user-specific


def portfolio_key(user_id: UUID) -> str:
    return f"portfolio:{user_id}"


def flags_key(user_id: UUID) -> str:
    return f"flags:{user_id}"
