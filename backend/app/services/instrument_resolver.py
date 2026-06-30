"""
Asaas (اثاثہ) — Instrument Resolver

Resolves a ticker symbol to an `Instrument` row, creating it on demand for a
valid-looking PSX symbol that hasn't been seeded yet. Without this, any PSX
ticker not in the small hand-seeded list (HBL.KA, ENGRO.KA, ...) 404s even
though the PSXAdapter waterfall can fetch its history live.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.price import Price

logger = logging.getLogger("asaas.services.instrument_resolver")

# PSX symbols: 2-12 uppercase letters/digits, optionally suffixed `.KA`.
_PSX_SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,12}(\.KA)?$")


def _looks_like_psx_symbol(symbol: str) -> bool:
    return bool(_PSX_SYMBOL_RE.match(symbol.strip().upper()))


async def resolve_instrument(symbol: str, db: AsyncSession) -> Optional[Instrument]:
    """Look up an existing Instrument by symbol; if missing and the symbol
    looks like a PSX ticker, fetch its history live and register it. Returns
    None if the symbol can't be resolved by any path."""
    result = await db.execute(select(Instrument).where(Instrument.symbol == symbol))
    instrument = result.scalar_one_or_none()
    if instrument is not None:
        return instrument

    if not _looks_like_psx_symbol(symbol):
        return None

    from app.data.adapters.psx_adapter import PSXAdapter

    base = symbol.strip().upper().replace(".KA", "")
    rows = await PSXAdapter().fetch_history(base, years=1)
    if not rows:
        return None

    canonical_symbol = f"{base}.KA"
    stmt = (
        pg_insert(Instrument)
        .values(
            symbol=canonical_symbol,
            name=base,
            asset_class="psx_stock",
            currency="PKR",
            data_source="psx",
            metadata_={"exchange": "PSX"},
        )
        .on_conflict_do_nothing(index_elements=["symbol"])
    )
    await db.execute(stmt)
    await db.commit()

    result = await db.execute(select(Instrument).where(Instrument.symbol == canonical_symbol))
    instrument = result.scalar_one_or_none()
    if instrument is None:
        return None

    now = datetime.now(timezone.utc)
    for r in rows:
        close = r.get("close")
        if close is None:
            continue
        vals = dict(
            instrument_id=instrument.id,
            price=close,
            price_date=r["price_date"],
            open=r.get("open"),
            high=r.get("high"),
            low=r.get("low"),
            volume=r.get("volume"),
            source="psx",
            fetched_at=now,
        )
        price_stmt = pg_insert(Price).values(**vals).on_conflict_do_update(
            index_elements=["instrument_id", "price_date"],
            set_={k: v for k, v in vals.items() if k not in ("instrument_id", "price_date")},
        )
        await db.execute(price_stmt)
    await db.commit()

    logger.info("Resolved new PSX instrument on demand: %s (%d price rows)", canonical_symbol, len(rows))
    return instrument
