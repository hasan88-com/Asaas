"""
Asaas (اثاثہ) — Rate Impact Service

Analyzes how State Bank of Pakistan (SBP) policy rate changes impact government securities
(MTBs, PIBs, GIS) and asset valuations, generating rate_impact Flags.

SBP conducts auctions of marketable government securities:
- MTBs (Market Treasury Bills): short-term, 3/6/12 month tenors, fortnightly auctions
- PIBs (Pakistan Investment Bonds): medium-to-long term, 3/5/10/20 year tenors
- GIS (Government Islamic Sukuk): Shariah compliant, 3-year tenors

RULES.md A1.4, A2.6, A3.5
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import List
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.price import Price
from app.models.portfolio import Portfolio
from app.models.holding import Holding
from app.models.flag import Flag
from app.data.cache import get_price

logger = logging.getLogger("asaas.services.rate_impact")


# Duration multipliers for interest rate sensitivity
# Longer duration = higher price sensitivity to rate changes
DURATION_MULTIPLIERS = {
    "MTB-3M": Decimal("0.25"),   # ~3 month duration
    "MTB-6M": Decimal("0.50"),   # ~6 month duration
    "MTB-12M": Decimal("0.90"),  # ~12 month duration
    "PIB-3Y": Decimal("2.70"),   # ~3 year duration
    "PIB-5Y": Decimal("4.30"),   # ~5 year duration
    "PIB-10Y": Decimal("7.50"),  # ~10 year duration
    "PIB-20Y": Decimal("12.00"), # ~20 year duration
    "GIS-3Y-FRR": Decimal("2.70"),  # Fixed rate, similar to PIB-3Y
    "GIS-3Y-VRR": Decimal("1.50"),  # Variable rate, lower duration
}


class RateImpactService:
    """Computes fixed-income pricing adjustments based on SBP interest rates."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def apply_policy_rate_change(self, old_rate: Decimal, new_rate: Decimal):
        """
        Updates government security yields and calculates impact on active portfolios.
        Saves flags warning users of valuation impacts.

        Price impact formula:
          ΔPrice ≈ -Duration × ΔYield × CurrentPrice
        """
        delta_rate = new_rate - old_rate
        if delta_rate == 0:
            return

        logger.info(f"Applying SBP rate change from {old_rate:.2%} to {new_rate:.2%} (delta: {delta_rate:+.2%})")

        # 1. Fetch all government security instruments (MTBs, PIBs, GIS)
        inst_res = await self.db.execute(
            select(Instrument).where(Instrument.asset_class == "tbill")
        )
        securities = inst_res.scalars().all()
        security_ids = [s.id for s in securities]

        if not securities:
            return

        # 2. Update yields/prices for each security type
        for security in securities:
            symbol = security.symbol
            latest_yield = await get_price(symbol, self.db)
            if latest_yield is None:
                logger.warning("No yield data for %s — skipping rate impact", symbol)
                continue

            new_yield = latest_yield + delta_rate

            # Save new price/yield record
            db_price = Price(
                instrument_id=security.id,
                price=float(new_yield),
                price_date=datetime.now(timezone.utc).date(),
                source="sbp_rate_impact",
            )
            self.db.add(db_price)
            logger.info(f"Updated yield for {symbol}: {latest_yield:.2%} → {new_yield:.2%}")

        await self.db.commit()

        # 3. Find active portfolios holding these securities and create flags
        portfolios_res = await self.db.execute(
            select(Portfolio)
            .join(Holding, Holding.portfolio_id == Portfolio.id)
            .where(
                Holding.instrument_id.in_(security_ids),
                Portfolio.status.in_(["confirmed", "tracked"])
            )
            .distinct()
        )
        portfolios = portfolios_res.scalars().all()

        for port in portfolios:
            # Check if rate impact flag already exists
            flag_res = await self.db.execute(
                select(Flag).where(
                    Flag.portfolio_id == port.id,
                    Flag.type == "rate_impact",
                    Flag.status == "pending"
                )
            )
            existing_flag = flag_res.scalar_one_or_none()

            sign = "+" if delta_rate > 0 else ""
            delta_bps = int(delta_rate * 10000)

            # Count holdings by type
            holdings_res = await self.db.execute(
                select(Holding, Instrument)
                .join(Instrument, Holding.instrument_id == Instrument.id)
                .where(
                    Holding.portfolio_id == port.id,
                    Instrument.asset_class == "tbill"
                )
            )
            holdings = holdings_res.all()

            # Categorize holdings
            mtb_count = sum(1 for h, inst in holdings if inst.symbol.startswith("MTB"))
            pib_count = sum(1 for h, inst in holdings if inst.symbol.startswith("PIB"))
            gis_count = sum(1 for h, inst in holdings if inst.symbol.startswith("GIS"))

            # Build impact message
            impact_parts = []
            if mtb_count > 0:
                impact_parts.append(f"{mtb_count} MTB(s)")
            if pib_count > 0:
                impact_parts.append(f"{pib_count} PIB(s)")
            if gis_count > 0:
                impact_parts.append(f"{gis_count} GIS")

            holdings_str = " + ".join(impact_parts) if impact_parts else "government securities"

            msg = (
                f"SBP changed policy rate to {new_rate:.2%} ({sign}{delta_bps} bps). "
                f"Your portfolio holds {holdings_str} that are now repriced. "
                f"{'Short-term MTBs reprice quickly; longer-term PIBs have higher interest rate risk. ' if pib_count > 0 else ''}"
                f"Review allocation."
            )

            severity = "high" if abs(delta_rate) >= Decimal("0.01") else "medium"

            if not existing_flag:
                flag = Flag(
                    portfolio_id=port.id,
                    type="rate_impact",
                    severity=severity,
                    message=msg,
                    status="pending",
                )
                self.db.add(flag)
                logger.info(f"Created rate impact flag for portfolio {port.id}")
            else:
                existing_flag.message = msg
                existing_flag.severity = severity
                logger.info(f"Updated rate impact flag for portfolio {port.id}")

        await self.db.commit()
