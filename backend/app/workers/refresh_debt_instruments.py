"""
Asaas (اثاثہ) — Debt Instrument Refresh Worker

Keeps the generic tenor placeholders (MTB-3M, PIB-5Y, …) in the `instruments`
table backed by REAL, current data so the optimizer never suggests matured or
nominal debt:

  * For each tbill/bond placeholder, resolve the CURRENT ACTIVE instrument for
    its tenor from the live PSX debt market (PSXDebtAdapter.get_instrument now
    picks a future-dated, non-nominal representative), and copy its
    maturity_date and (real) face_value onto the placeholder.
  * Safely retire any instrument with a real PAST maturity (is_active=False).

Face values are stored exactly as PSX reports (already in rupees) — no ×1000.
RULES.md A2.6 (Decimal money).
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import select, update

from app.core.db import async_session_factory
from app.models.instrument import Instrument
from app.data.adapters.psx_debt_adapter import PSXDebtAdapter

logger = logging.getLogger("asaas.workers.refresh_debt_instruments")


async def run_refresh_debt_instruments() -> None:
    """Populate maturity_date/face_value for debt placeholders + retire matured."""
    logger.info("Starting debt-instrument refresh...")
    adapter = PSXDebtAdapter()

    async with async_session_factory() as session:
        result = await session.execute(
            select(Instrument).where(Instrument.asset_class.in_(["tbill", "bond"]))
        )
        placeholders = result.scalars().all()

        updated = 0
        for inst in placeholders:
            try:
                rep = await adapter.get_instrument(inst.symbol)
            except Exception as exc:
                logger.warning("Debt lookup failed for %s: %s", inst.symbol, exc)
                continue
            if not rep:
                # GIS-3Y-FRR/VRR, tenors with no active instrument, or a scrape
                # hiccup — leave the placeholder unchanged (never retire on miss).
                continue

            maturity = PSXDebtAdapter._parse_maturity(rep.get("maturity_date"))
            if maturity is not None:
                inst.maturity_date = maturity

            # Only store a real face value (>= ₨1000); leave NULL for nominal "1"
            # rows so the optimizer's face_value filter never drops a valid tenor.
            fv = rep.get("face_value")
            try:
                if fv is not None and float(fv) >= 1000:
                    inst.face_value = Decimal(str(fv))
            except (TypeError, ValueError):
                pass

            updated += 1
            logger.info(
                "Refreshed %s -> %s (maturity=%s, face_value=%s)",
                inst.symbol, rep.get("security_code"), inst.maturity_date, inst.face_value,
            )

        # Safe retire: only rows with a real, already-passed maturity.
        await session.execute(
            update(Instrument)
            .where(
                Instrument.maturity_date.is_not(None),
                Instrument.maturity_date < date.today(),
            )
            .values(is_active=False)
        )

        await session.commit()
        logger.info("Debt-instrument refresh complete: %d placeholders updated.", updated)
