"""
Asaas (اثاثہ) — Redis Client

Provides shared, asynchronous access to Redis for rate-limiting,
caching, and guest tracking.
"""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import get_settings

settings = get_settings()

# Global async Redis client
redis_client: Redis = Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    protocol=2,  # RESP2 — compatible with Redis 5.x (tporadowski Windows build)
)


async def get_redis() -> Redis:
    """FastAPI dependency to retrieve the Redis client."""
    return redis_client
