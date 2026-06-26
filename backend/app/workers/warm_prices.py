"""
Asaas (اثاثہ) — Price Cache Warmer

Keeps the price cache warm for instruments held in active portfolios so a
dashboard load hits warm Redis (get_price returns instantly, no adapter call).
The daily EOD job warms the whole universe once a day, but the stock/commodity
Redis TTL is ~4h — this job refreshes held instruments in between (and on
startup / right after holdings change) so the dashboard never pays the
cold-fetch tax.

Uses the concurrent ``get_prices`` (each cold miss on its own short-lived
session) so the whole warm completes in ~2s instead of ~12s sequential.
Identical to calling get_price normally — same adapter, same TTL rules.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.db import async_session_factory
from app.data.cache import get_prices
from app.models.holding import Holding
from app.models.instrument import Instrument
from app.models.portfolio import Portfolio

logger = logging.getLogger("asaas.workers.warm_prices")


async def run_warm_prices() -> None:
    """Refresh prices for every instrument held in a confirmed/tracked portfolio."""
    logger.info("Starting price cache warm for held instruments...")

    async with async_session_factory() as session:
        res = await session.execute(
            select(Instrument.symbol)
            .join(Holding, Holding.instrument_id == Instrument.id)
            .join(Portfolio, Holding.portfolio_id == Portfolio.id)
            .where(Portfolio.status.in_(["confirmed", "tracked"]))
            .distinct()
        )
        symbols = [row[0] for row in res.all()]

    if not symbols:
        logger.info("Price cache warm: no held instruments to warm.")
        return

    # Concurrent (fresh session per cold miss); already-warm symbols are no-ops.
    prices = await get_prices(symbols)
    warmed = sum(1 for v in prices.values() if v is not None)
    failed = [s for s, v in prices.items() if v is None]

    if failed:
        logger.warning(
            "Price cache warm: %d/%d warmed, %d failed: %s",
            warmed, len(symbols), len(failed), ", ".join(sorted(failed)),
        )
    else:
        logger.info("Price cache warm complete: %d/%d held instruments warmed.", warmed, len(symbols))
