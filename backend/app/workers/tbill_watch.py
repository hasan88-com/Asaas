"""
Asaas (اثاثہ) — SBP Rate & Government Securities Watch Worker

Worker job that scrapes the State Bank of Pakistan (SBP) site to verify interest rate shifts
and updates yields for all government securities (MTBs, PIBs, GIS), triggering repricing flags.

SBP conducts auctions of marketable government securities:
- MTBs: fortnightly auctions on Wednesdays, settlement T+1
- PIBs: need basis per pre-announced calendar
- GIS: Shariah compliant, 3-year tenors, Fixed/Variable Rate Rentals

RULES.md A1.4, A2.6, TECH.md §6
"""

from __future__ import annotations

import logging
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session_factory
from app.models.price import Price
from app.models.instrument import Instrument
from app.data.adapters.sbp_adapter import SBPAdapter
from app.services.rate_impact import RateImpactService

logger = logging.getLogger("asaas.workers.tbill_watch")


async def run_tbill_watch():
    """Periodic task to inspect SBP policy rate and update government securities yields."""
    logger.info("Starting SBP Rate & Government Securities Watch Job...")
    async with async_session_factory() as session:
        # 1. Scrape latest policy rate from SBP (None if all sources fail)
        adapter = SBPAdapter()
        new_rate = await adapter.fetch_policy_rate()

        from app.core.redis import redis_client
        if new_rate is None:
            # Can't detect a change without a live rate — skip the rate-shift
            # check this cycle (don't overwrite the cache with a guess) and
            # proceed to the yields update below.
            logger.warning("SBP policy rate scrape returned no value — skipping rate-shift check this run.")
        else:
            # 2. Get latest recorded policy rate from Redis cache
            cached_rate_str = await redis_client.get("sbp:policy_rate")

            if cached_rate_str:
                old_rate = Decimal(cached_rate_str)
            else:
                # First run, assume rate matches new rate
                old_rate = new_rate
                await redis_client.set("sbp:policy_rate", str(new_rate))

            if new_rate != old_rate:
                logger.info(f"Monetary Policy Rate shift detected! {old_rate:.2%} -> {new_rate:.2%}")

                # Update cache key
                await redis_client.set("sbp:policy_rate", str(new_rate))

                # Trigger Rate Impact Service
                service = RateImpactService(session)
                await service.apply_policy_rate_change(old_rate, new_rate)
                logger.info("Policy rate impact adjustment applied.")
            else:
                logger.info(f"SBP Policy Rate unchanged at {new_rate:.2%}.")

        # 3. Update government securities yields (MTBs, PIBs, GIS)
        govSecurities = await adapter.fetch_tbill_rates()
        for symbol, yield_val in govSecurities.items():
            # Check instrument exists
            inst_res = await session.execute(
                select(Instrument).where(Instrument.symbol == symbol)
            )
            inst = inst_res.scalar_one_or_none()
            if not inst:
                logger.debug(f"Instrument not found in DB: {symbol}, skipping")
                continue

            # Check if this price is already written today
            today_date = datetime.now(timezone.utc).date()
            price_res = await session.execute(
                select(Price).where(
                    Price.instrument_id == inst.id,
                    Price.price_date == today_date
                )
            )
            existing_price = price_res.scalar_one_or_none()

            if not existing_price:
                db_price = Price(
                    instrument_id=inst.id,
                    price=float(yield_val),
                    price_date=today_date,
                    source="sbp_watch",
                )
                session.add(db_price)
                logger.info(f"Updated yield for {symbol}: {yield_val:.2%}")

        await session.commit()
    logger.info("SBP Rate & Government Securities Watch Job completed.")
