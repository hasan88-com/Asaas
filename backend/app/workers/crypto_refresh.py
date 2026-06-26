"""
Asaas (اثاثہ) — Crypto Refresh Worker

Interval job to batch fetch and refresh prices for all held cryptocurrencies,
maintaining a 30-60s hot cache to respect limits (RULES.md A2.4, TECH.md §6).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from datetime import date, datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session_factory
from app.models.instrument import Instrument
from app.models.holding import Holding
from app.models.portfolio import Portfolio
from app.models.price import Price
from app.data.adapters.coingecko_adapter import CoinGeckoAdapter
from app.data.cache import set_cached_price

logger = logging.getLogger("asaas.workers.crypto_refresh")


async def refresh_crypto_prices():
    """Batch refresh held crypto prices."""
    logger.info("Starting Crypto Refresh Job...")
    async with async_session_factory() as session:
        # Find all unique crypto symbols currently in confirmed/tracked portfolios
        result = await session.execute(
            select(Instrument.symbol)
            .join(Holding, Holding.instrument_id == Instrument.id)
            .join(Portfolio, Holding.portfolio_id == Portfolio.id)
            .where(
                Instrument.asset_class == "crypto",
                Portfolio.status.in_(["confirmed", "tracked"])
            )
            .distinct()
        )
        symbols = [r[0] for r in result.all()]

        if not symbols:
            logger.info("No active cryptocurrency holdings to refresh.")
            return

        logger.info(f"Held cryptocurrencies to refresh: {symbols}")

        # Batch fetch from CoinGecko
        adapter = CoinGeckoAdapter()
        prices = await adapter.fetch_prices(symbols)

        now = datetime.now(timezone.utc)
        for symbol, price_val in prices.items():
            try:
                # Find instrument
                inst_res = await session.execute(
                    select(Instrument).where(Instrument.symbol == symbol)
                )
                inst = inst_res.scalar_one_or_none()
                if not inst:
                    continue

                # Upsert into DB
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                insert_vals = dict(
                    instrument_id=inst.id,
                    price=float(price_val),
                    price_date=now.date(),
                    source="coingecko_refresh",
                    fetched_at=now,
                )
                stmt = pg_insert(Price).values(**insert_vals).on_conflict_do_update(
                    index_elements=["instrument_id", "price_date"],
                    set_={k: v for k, v in insert_vals.items() if k not in ("instrument_id", "price_date")},
                )
                await session.execute(stmt)

                # Update hot cache (60 seconds TTL)
                await set_cached_price(symbol, price_val, 60)
                logger.info(f"Refreshed and cached {symbol}: {price_val}")

            except Exception as e:
                logger.error(f"Failed to save refreshed price for {symbol}: {e}")

        await session.commit()
    logger.info("Crypto Refresh Job completed.")
