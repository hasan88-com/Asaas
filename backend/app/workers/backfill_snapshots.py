"""
Asaas — Portfolio Snapshot Backfill

Retroactively generates daily portfolio snapshots from the existing price
history in the `prices` table. Runs once after portfolio creation so the
performance chart shows real historical data immediately rather than waiting
for daily EOD jobs to accumulate entries.

For each portfolio:
  - Iterates every calendar date from portfolio creation to yesterday
  - Looks up each holding's price on that date from the `prices` table
  - Falls back to the nearest earlier price when no exact match exists
  - Upserts a PortfolioSnapshot row (idempotent — safe to re-run)

Tbills / bonds have no OHLCV series; their entry_price is used as a constant.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.db import async_session_factory
from app.models.holding import Holding
from app.models.instrument import Instrument
from app.models.portfolio import Portfolio
from app.models.price import Price
from app.models.snapshot import PortfolioSnapshot

logger = logging.getLogger("asaas.workers.backfill_snapshots")

_NO_PRICE_CLASSES = {"tbill", "bond", "mutual_fund"}


async def _price_on_or_before(session, instrument_id, target_date: date) -> Decimal | None:
    """Return the most recent closing price on or before target_date."""
    res = await session.execute(
        select(Price.price)
        .where(Price.instrument_id == instrument_id, Price.price_date <= target_date)
        .order_by(Price.price_date.desc())
        .limit(1)
    )
    row = res.scalar_one_or_none()
    return Decimal(str(row)) if row is not None else None


async def backfill_snapshots_for_portfolio(portfolio_id) -> int:
    """
    Generate missing historical snapshots for one portfolio.
    Returns the number of snapshot rows inserted/updated.
    """
    async with async_session_factory() as session:
        # Load portfolio with holdings + instruments
        port_res = await session.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        )
        portfolio = port_res.scalar_one_or_none()
        if portfolio is None:
            logger.warning("backfill_snapshots: portfolio %s not found", portfolio_id)
            return 0

        holdings_res = await session.execute(
            select(Holding).where(Holding.portfolio_id == portfolio_id)
        )
        holdings = holdings_res.scalars().all()
        if not holdings:
            return 0

        # Resolve instruments for each holding
        instrument_map: dict = {}
        for h in holdings:
            inst_res = await session.execute(
                select(Instrument).where(Instrument.id == h.instrument_id)
            )
            instrument_map[h.instrument_id] = inst_res.scalar_one()

        # Determine date range: portfolio creation date → yesterday
        created_at = portfolio.created_at
        if created_at is None:
            return 0
        start_date = created_at.date() if hasattr(created_at, "date") else created_at
        yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
        if start_date > yesterday:
            return 0

        # Fetch FX rate once (used for USD instruments)
        fx_rate: Decimal | None = None
        try:
            from app.core.market import get_usd_pkr_rate
            fx_rate = await get_usd_pkr_rate()
        except Exception:
            fx_rate = None

        count = 0
        current = start_date
        while current <= yesterday:
            total_value = Decimal("0.00")
            cost_basis = Decimal("0.00")
            breakdown: dict[str, float] = {}

            for h in holdings:
                inst = instrument_map[h.instrument_id]
                qty = Decimal(str(h.quantity or 0))
                entry = Decimal(str(h.entry_price or 0))

                if inst.asset_class in _NO_PRICE_CLASSES:
                    # Use face/entry value as constant price
                    px = entry
                else:
                    px = await _price_on_or_before(session, h.instrument_id, current)
                    if px is None:
                        px = entry  # no history at all — use entry price

                px_pkr = px
                entry_pkr = entry
                if inst.currency == "USD" and fx_rate is not None:
                    px_pkr = px * fx_rate
                    entry_pkr = entry * fx_rate

                val = qty * px_pkr
                total_value += val
                cost_basis += qty * entry_pkr

                ac = inst.asset_class
                breakdown[ac] = breakdown.get(ac, 0.0) + float(val)

            pnl_abs = total_value - cost_basis
            pnl_pct = pnl_abs / cost_basis if cost_basis > 0 else Decimal("0.00")

            stmt = pg_insert(PortfolioSnapshot).values(
                portfolio_id=portfolio_id,
                snapshot_date=current,
                total_value_pkr=float(total_value),
                pnl_absolute=float(pnl_abs),
                pnl_percent=float(pnl_pct),
                breakdown=breakdown,
            ).on_conflict_do_update(
                index_elements=["portfolio_id", "snapshot_date"],
                set_={
                    "total_value_pkr": float(total_value),
                    "pnl_absolute": float(pnl_abs),
                    "pnl_percent": float(pnl_pct),
                    "breakdown": breakdown,
                },
            )
            await session.execute(stmt)
            count += 1
            current += timedelta(days=1)

        await session.commit()
        logger.info(
            "backfill_snapshots: portfolio %s — %d snapshots upserted (%s → %s)",
            portfolio_id, count, start_date, yesterday,
        )
        return count


async def run_backfill_snapshots() -> None:
    """Backfill snapshots for all active portfolios (scheduled job)."""
    logger.info("Starting snapshot backfill for all portfolios…")
    async with async_session_factory() as session:
        res = await session.execute(
            select(Portfolio.id).where(Portfolio.status.in_(["confirmed", "tracked"]))
        )
        ids = res.scalars().all()

    for pid in ids:
        try:
            await backfill_snapshots_for_portfolio(pid)
        except Exception as exc:
            logger.error("backfill_snapshots failed for portfolio %s: %s", pid, exc)

    logger.info("Snapshot backfill complete for %d portfolios.", len(ids))
