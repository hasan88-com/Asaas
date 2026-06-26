"""
Asaas (اثاثہ) — Daily EOD Worker Job

APScheduler job to:
1. Fetch and update daily EOD prices for all active stocks and commodities.
2. Generate and write immutable daily portfolio snapshots (portfolio_snapshots table).
Values computed as Decimal (RULES.md A2.6, TECH.md §6).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from datetime import date, datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session_factory
from app.models.instrument import Instrument
from app.models.price import Price
from app.models.portfolio import Portfolio
from app.models.holding import Holding
from app.models.snapshot import PortfolioSnapshot
from app.data.cache import get_price
from app.core.market import get_usd_pkr_rate

logger = logging.getLogger("asaas.workers.daily_eod")


async def run_daily_eod():
    """Daily EOD task runner."""
    logger.info("Starting Daily EOD Job...")
    async with async_session_factory() as session:
        # 1. Fetch EOD prices for all active instruments (stocks, commodities, t-bills)
        result = await session.execute(
            select(Instrument).where(Instrument.is_active == True)
        )
        instruments = result.scalars().all()

        logger.info(f"Updating prices for {len(instruments)} active instruments...")
        for inst in instruments:
            try:
                # get_price automatically handles reading-through cache / adapters & saving to DB
                price_val = await get_price(inst.symbol, session)
                logger.info(f"Updated price for {inst.symbol}: {price_val}")
            except Exception as e:
                logger.error(f"Failed to update price for {inst.symbol}: {e}")

        # 2. Update portfolio snapshots
        # Query all portfolios that are active (confirmed or tracked)
        port_result = await session.execute(
            select(Portfolio).where(Portfolio.status.in_(["confirmed", "tracked"]))
        )
        portfolios = port_result.scalars().all()

        today_date = datetime.now(timezone.utc).date()
        logger.info(f"Generating snapshots for {len(portfolios)} portfolios...")

        for port in portfolios:
            try:
                # Calculate current portfolio value
                total_value = Decimal("0.00")
                cost_basis = Decimal("0.00")
                breakdown = {}

                # Holdings are selectin loaded
                for holding in port.holdings:
                    # Resolve instrument
                    inst_res = await session.execute(
                        select(Instrument).where(Instrument.id == holding.instrument_id)
                    )
                    inst = inst_res.scalar_one()

                    # Retrieve latest price
                    latest_price = await get_price(inst.symbol, session)
                    if latest_price is None:
                        latest_price = Decimal(str(holding.entry_price or 0))

                    qty = Decimal(str(holding.quantity or 0))
                    entry = Decimal(str(holding.entry_price or 0))

                    # Value calculations (converted to PKR if needed, commodities are in USD in DB)
                    px_pkr = latest_price
                    entry_pkr = entry

                    if inst.currency == "USD":
                        try:
                            fx_rate = await get_usd_pkr_rate()
                        except RuntimeError:
                            fx_rate = None
                        if fx_rate is not None:
                            px_pkr = latest_price * fx_rate
                            entry_pkr = entry * fx_rate

                    val = qty * px_pkr
                    total_value += val
                    cost_basis += qty * entry_pkr

                    # Add to breakdown
                    asset_class = inst.asset_class
                    breakdown[asset_class] = breakdown.get(asset_class, 0.0) + float(val)

                # Compute P&L
                pnl_abs = total_value - cost_basis
                pnl_pct = pnl_abs / cost_basis if cost_basis > 0 else Decimal("0.00")

                # Upsert daily snapshot
                snap_res = await session.execute(
                    select(PortfolioSnapshot).where(
                        PortfolioSnapshot.portfolio_id == port.id,
                        PortfolioSnapshot.snapshot_date == today_date
                    )
                )
                snapshot = snap_res.scalar_one_or_none()

                if not snapshot:
                    snapshot = PortfolioSnapshot(
                        portfolio_id=port.id,
                        snapshot_date=today_date,
                        total_value_pkr=float(total_value),
                        pnl_absolute=float(pnl_abs),
                        pnl_percent=float(pnl_pct),
                        breakdown=breakdown
                    )
                    session.add(snapshot)
                else:
                    snapshot.total_value_pkr = float(total_value)
                    snapshot.pnl_absolute = float(pnl_abs)
                    snapshot.pnl_percent = float(pnl_pct)
                    snapshot.breakdown = breakdown

                logger.info(f"Saved snapshot for portfolio {port.id}: value={total_value}, P&L={pnl_pct:.2%}")

            except Exception as e:
                logger.error(f"Failed to generate snapshot for portfolio {port.id}: {e}")

        await session.commit()
    logger.info("Daily EOD Job completed successfully.")
