"""
Asaas (اثاثہ) — Price Cache Layer

Implements a read-through price cache: Redis -> DB -> External Adapter.
Saves external API calls and respects limits.
All monetary values handled as Decimal (RULES.md A2.6, A3.4).
"""

from __future__ import annotations

import asyncio
import json
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import redis_client
from app.models.instrument import Instrument
from app.models.price import Price
from app.data.adapters.yfinance_adapter import YFinanceAdapter
from app.data.adapters.coingecko_adapter import CoinGeckoAdapter
from app.data.adapters.sbp_adapter import SBPAdapter
from app.data.adapters.alpha_vantage_adapter import AlphaVantageAdapter

logger = logging.getLogger("asaas.price_cache")


async def get_cached_price(symbol: str) -> Optional[Decimal]:
    """Retrieve hot price from Redis if it exists."""
    try:
        val = await redis_client.get(f"price:{symbol}")
        if val:
            return Decimal(val)
    except Exception as e:
        logger.warning(f"Failed to read from Redis cache for {symbol}: {e}")
    return None


async def set_cached_price(symbol: str, price: Decimal, ttl_seconds: int):
    """Write price to Redis with a TTL."""
    try:
        await redis_client.setex(f"price:{symbol}", ttl_seconds, str(price))
    except Exception as e:
        logger.warning(f"Failed to write to Redis cache for {symbol}: {e}")


async def get_price(symbol: str, db: AsyncSession) -> Optional[Decimal]:
    """
    Main read-through entry point.
    Checks Redis -> Checks DB -> Fetches Adapter -> Updates DB & Redis.
    """
    symbol_upper = symbol.upper()

    # 1. Try Redis cache
    cached = await get_cached_price(symbol_upper)
    if cached is not None:
        return cached

    # 2. Lookup instrument metadata in DB to know asset class
    result = await db.execute(
        select(Instrument).where(Instrument.symbol == symbol_upper)
    )
    instrument = result.scalar_one_or_none()
    if not instrument:
        logger.error(f"Cannot fetch price for unregistered instrument: {symbol_upper}")
        return None

    # Define TTL based on asset class
    # Crypto: 60 seconds (volatile)
    # Stocks/Commodities: EOD EOD (e.g., 4 hours or 24 hours)
    # T-bills: 24 hours (rare updates)
    asset_class = instrument.asset_class
    if asset_class == "crypto":
        ttl = 60
    elif asset_class in ("psx_stock", "global_stock", "commodity"):
        ttl = 14400  # 4 hours cache window for EOD
    else:
        ttl = 86400  # 24 hours for fixed income

    # 3. Try DB prices table (check if fresh enough)
    price_result = await db.execute(
        select(Price)
        .where(Price.instrument_id == instrument.id)
        .order_by(Price.price_date.desc())
    )
    latest_db_price = price_result.scalars().first()

    now = datetime.now(timezone.utc)
    is_fresh = False
    if latest_db_price:
        age = now - latest_db_price.fetched_at
        if asset_class == "crypto" and age < timedelta(seconds=60):
            is_fresh = True
        elif asset_class in ("psx_stock", "global_stock", "commodity") and age < timedelta(hours=4):
            # If market is closed, latest DB price is sufficient
            is_fresh = True
        elif asset_class == "tbill" and age < timedelta(hours=24):
            is_fresh = True

    if is_fresh and latest_db_price:
        db_price_decimal = Decimal(str(latest_db_price.price))
        await set_cached_price(symbol_upper, db_price_decimal, ttl)
        return db_price_decimal

    # 4. Fetch from Adapter
    fetched_data = None
    if asset_class in ("psx_stock", "global_stock", "commodity"):
        adapter = YFinanceAdapter()
        fetched_data = await adapter.fetch_price(symbol_upper)

        # Fallback to Alpha Vantage for commodities if yfinance fails
        if not fetched_data and asset_class == "commodity":
            logger.info(f"yfinance failed for {symbol_upper}. Trying Alpha Vantage backup.")
            av_adapter = AlphaVantageAdapter()
            av_price = await av_adapter.fetch_commodity_price(symbol_upper)
            if av_price:
                fetched_data = {
                    "price": av_price,
                    "price_date": date.today(),
                    "source": "alphavantage",
                }

    elif asset_class == "crypto":
        cg_adapter = CoinGeckoAdapter()
        cg_prices = await cg_adapter.fetch_prices([symbol_upper])
        if symbol_upper in cg_prices:
            fetched_data = {
                "price": cg_prices[symbol_upper],
                "price_date": date.today(),
                "source": "coingecko",
            }

    elif asset_class == "tbill":
        sbp_adapter = SBPAdapter()
        rates = await sbp_adapter.fetch_tbill_rates()
        if symbol_upper in rates:
            fetched_data = {
                "price": rates[symbol_upper],
                "price_date": date.today(),
                "source": "sbp",
            }

    if fetched_data:
        price_val = fetched_data["price"]
        insert_vals = dict(
            instrument_id=instrument.id,
            price=float(price_val),
            price_date=fetched_data["price_date"],
            open=float(fetched_data["open"]) if fetched_data.get("open") is not None else None,
            high=float(fetched_data["high"]) if fetched_data.get("high") is not None else None,
            low=float(fetched_data["low"]) if fetched_data.get("low") is not None else None,
            volume=fetched_data.get("volume"),
            source=fetched_data.get("source") or "adapter",
            fetched_at=now,
        )
        stmt = pg_insert(Price).values(**insert_vals).on_conflict_do_update(
            index_elements=["instrument_id", "price_date"],
            set_={k: v for k, v in insert_vals.items() if k not in ("instrument_id", "price_date")},
        )
        await db.execute(stmt)
        await db.commit()

        # Update cache
        await set_cached_price(symbol_upper, price_val, ttl)
        return price_val

    # 5. Last resort fallback to stale DB price if adapter failed
    if latest_db_price:
        logger.warning(f"Adapter fetch failed. Falling back to stale DB price for {symbol_upper}.")
        db_price_decimal = Decimal(str(latest_db_price.price))
        # Cache for a short time so we don't spam the adapter in next requests
        await set_cached_price(symbol_upper, db_price_decimal, 30)
        return db_price_decimal

    return None


# Bound concurrent cold fetches so we never exhaust the connection pooler even
# for large portfolios; still fully concurrent for typical (≤10) holding counts.
_PRICE_FETCH_CONCURRENCY = 10


async def _get_price_isolated(symbol: str, sem: "asyncio.Semaphore") -> tuple[str, Optional[Decimal]]:
    """Resolve one cold price on its OWN short-lived session (concurrency-safe)."""
    from app.core.db import async_session_factory
    async with sem:
        async with async_session_factory() as session:
            return symbol, await get_price(symbol, session)


async def get_prices(symbols: List[str], db: Optional[AsyncSession] = None) -> Dict[str, Optional[Decimal]]:
    """
    Fetch many prices concurrently, keyed by UPPERCASED symbol. Bit-for-bit
    identical to calling ``get_price`` per symbol — only faster.

    Warm Redis hits are read concurrently (Redis-only, no DB). Cold misses are
    ALSO fetched concurrently, each on its own short-lived session: get_price
    commits on the cold path, and one asyncpg session can't run concurrent ops —
    but separate sessions can, and the DB write is an idempotent
    ``on_conflict_do_update`` so concurrent same-row writes are safe by design.
    ``db`` is accepted but unused (cold misses use fresh sessions).
    """
    uniq = list(dict.fromkeys(s.upper() for s in symbols))
    cached = await asyncio.gather(*(get_cached_price(s) for s in uniq))

    out: Dict[str, Optional[Decimal]] = {}
    misses: List[str] = []
    for sym, val in zip(uniq, cached):
        if val is not None:
            out[sym] = val
        else:
            misses.append(sym)

    if misses:
        sem = asyncio.Semaphore(_PRICE_FETCH_CONCURRENCY)
        results = await asyncio.gather(*(_get_price_isolated(s, sem) for s in misses))
        out.update(dict(results))

    return out
