"""
Asaas (اثاثہ) — Performance & Drift Service

Computes current portfolio value, P&L, updates snapshots,
and detects asset allocation drift (TECH.md §2, §6, §7.2).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from datetime import date, datetime, timezone
from typing import Dict, Any, List, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.portfolio import Portfolio
from app.models.holding import Holding
from app.models.instrument import Instrument
from app.models.flag import Flag
from app.models.snapshot import PortfolioSnapshot
from app.data.cache import get_price
from app.core.market import get_usd_pkr_rate

logger = logging.getLogger("asaas.services.performance")


class PerformanceService:
    """Calculates portfolio value metrics and checks for weight drift."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def update_portfolio_metrics(self, portfolio_id: UUID) -> Tuple[Decimal, Decimal, Decimal]:
        """
        Recalculates the current value of the portfolio and updates expected metrics.
        Returns: (total_value_pkr, pnl_absolute, pnl_percent)
        """
        logger.info("update_portfolio_metrics START portfolio_id=%s", portfolio_id)
        result = await self.db.execute(
            select(Portfolio)
            .options(selectinload(Portfolio.holdings))
            .where(Portfolio.id == portfolio_id)
        )
        portfolio = result.scalar_one_or_none()
        if not portfolio:
            return Decimal("0.00"), Decimal("0.00"), Decimal("0.00")

        total_value = Decimal("0.00")
        cost_basis = Decimal("0.00")

        for holding in portfolio.holdings:
            inst_res = await self.db.execute(
                select(Instrument).where(Instrument.id == holding.instrument_id)
            )
            inst = inst_res.scalar_one()

            # Retrieve price from cache/db
            latest_price = await get_price(inst.symbol, self.db)
            if latest_price is None:
                latest_price = Decimal(str(holding.entry_price or 0))

            qty = Decimal(str(holding.quantity or 0))
            entry = Decimal(str(holding.entry_price or 0))

            # Conversion for commodities (USD to PKR) — live FX rate
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

            total_value += qty * px_pkr
            cost_basis += qty * entry_pkr

        pnl_abs = total_value - cost_basis
        pnl_pct = pnl_abs / cost_basis if cost_basis > 0 else Decimal("0.00")

        logger.info(
            "update_portfolio_metrics END portfolio_id=%s total=%s pnl_abs=%s pnl_pct=%s",
            portfolio_id, total_value, pnl_abs, pnl_pct,
        )

        # Upsert today's snapshot so performance history accumulates over time
        today = date.today()
        stmt = pg_insert(PortfolioSnapshot).values(
            portfolio_id=portfolio_id,
            snapshot_date=today,
            total_value_pkr=total_value,
            pnl_absolute=pnl_abs,
            pnl_percent=pnl_pct,
        ).on_conflict_do_update(
            index_elements=["portfolio_id", "snapshot_date"],
            set_={
                "total_value_pkr": total_value,
                "pnl_absolute": pnl_abs,
                "pnl_percent": pnl_pct,
            },
        )
        await self.db.execute(stmt)
        await self.db.commit()
        logger.info("Snapshot upserted portfolio_id=%s date=%s", portfolio_id, today)

        return total_value, pnl_abs, pnl_pct

    async def check_and_flag_drift(self, portfolio_id: UUID, drift_threshold: Decimal = Decimal("0.10")):
        """
        Calculates current holding weights and checks if they drift from target_weight.
        If a holding drifts by more than `drift_threshold` (e.g. 10% absolute deviation),
        creates a drift Flag in the database (RULES.md A1.1: no auto-action, just flag).
        """
        result = await self.db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        )
        portfolio = result.scalar_one_or_none()
        if not portfolio or portfolio.status == "draft":
            return

        total_value = Decimal("0.00")
        holding_values: List[Tuple[Holding, Instrument, Decimal]] = []

        # 1. Compute current value for each holding
        for holding in portfolio.holdings:
            inst_res = await self.db.execute(
                select(Instrument).where(Instrument.id == holding.instrument_id)
            )
            inst = inst_res.scalar_one()

            latest_price = await get_price(inst.symbol, self.db)
            if latest_price is None:
                latest_price = Decimal(str(holding.entry_price or 0))

            qty = Decimal(str(holding.quantity or 0))

            px_pkr = latest_price
            if inst.currency == "USD":
                try:
                    fx_rate = await get_usd_pkr_rate()
                except RuntimeError:
                    fx_rate = None
                if fx_rate is not None:
                    px_pkr = latest_price * fx_rate

            val = qty * px_pkr
            total_value += val
            holding_values.append((holding, inst, val))

        if total_value <= 0:
            return

        # 2. Check each holding's actual weight vs target weight
        drift_detected = False
        drift_messages = []

        for holding, inst, val in holding_values:
            actual_weight = val / total_value
            target_weight = Decimal(str(holding.target_weight or 0))

            # Store updated actual weight
            holding.actual_weight = float(actual_weight)

            deviation = abs(actual_weight - target_weight)
            if deviation > drift_threshold:
                drift_detected = True
                drift_messages.append(
                    f"{inst.symbol} has drifted to {actual_weight:.1%} (target: {target_weight:.1%})"
                )

        if drift_detected:
            # Check if we already have an active drift flag
            flag_res = await self.db.execute(
                select(Flag).where(
                    Flag.portfolio_id == portfolio_id,
                    Flag.type == "drift",
                    Flag.status == "pending"
                )
            )
            existing_flag = flag_res.scalar_one_or_none()

            msg = "Portfolio drift detected: " + "; ".join(drift_messages)

            if not existing_flag:
                new_flag = Flag(
                    portfolio_id=portfolio_id,
                    type="drift",
                    severity="medium",
                    message=msg,
                    status="pending",
                )
                self.db.add(new_flag)
                logger.info(f"Created drift flag for portfolio {portfolio_id}: {msg}")
            else:
                existing_flag.message = msg
                logger.info(f"Updated existing drift flag for portfolio {portfolio_id}")

        await self.db.commit()
