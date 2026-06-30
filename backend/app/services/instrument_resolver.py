"""
Asaas (اثاثہ) — Instrument Resolver

The `instruments` table is seeded with only a handful of PSX stocks, so market
and holdings endpoints used to 404 on any other valid PSX ticker — even though
``PSXAdapter`` can fetch it. This resolver returns the existing row, or lazily
creates one (and backfills ~1y of prices) for a valid PSX ticker on first use.

Read-only for non-PSX / unknown symbols (returns None — callers 404). Never
raises; never fabricates data — an instrument is only created when PSX actually
returns price history for it.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument

logger = logging.getLogger("asaas.services.instrument_resolver")

_PSX_SUFFIX = ".KA"
# A bare PSX equity ticker is short and alphanumeric (e.g. LUCK, HBL, OGDC).
_TICKER_RE = re.compile(r"^[A-Z0-9]{2,15}$")


def _psx_candidate(symbol: str) -> Optional[str]:
    """The `.KA` symbol to try for a PSX lookup, or None if `symbol` doesn't
    look like a PSX equity ticker (so we don't auto-create junk rows)."""
    s = symbol.upper().strip()
    if s.endswith(_PSX_SUFFIX):
        return s
    if _TICKER_RE.match(s):
        return f"{s}{_PSX_SUFFIX}"
    return None


async def resolve_instrument(symbol: str, db: AsyncSession) -> Optional[Instrument]:
    """Return the Instrument for ``symbol``, creating it for a valid PSX ticker
    that isn't seeded yet (and backfilling ~1y of prices). Returns None when the
    symbol can't be resolved or PSX has no data for it. Never raises."""
    sym = symbol.upper().strip()

    # 1. Already known — by the exact symbol, or with .KA appended.
    inst = (await db.execute(
        select(Instrument).where(Instrument.symbol == sym)
    )).scalar_one_or_none()
    if inst is not None:
        return inst

    candidate = _psx_candidate(sym)
    if candidate is None:
        return None
    if candidate != sym:
        inst = (await db.execute(
            select(Instrument).where(Instrument.symbol == candidate)
        )).scalar_one_or_none()
        if inst is not None:
            return inst

    # 2. Not seeded — try PSX. Only create a row if real history comes back.
    try:
        from app.data.adapters.psx_adapter import PSXAdapter
        history = await PSXAdapter().fetch_history(candidate, years=1)
    except Exception as exc:
        logger.warning("PSX history fetch failed for %s: %s", candidate, exc)
        return None

    if not history:
        logger.info("No PSX data for %s — not creating an instrument.", candidate)
        return None

    inst = Instrument(
        symbol=candidate,
        name=candidate,
        asset_class="psx_stock",
        currency="PKR",
        data_source="psx",
        is_active=True,
        metadata_={"exchange": "PSX", "auto_created": True},
    )
    db.add(inst)
    await db.flush()  # assign inst.id before backfilling prices

    try:
        from app.workers.backfill_prices import _upsert_rows
        n = await _upsert_rows(db, inst.id, history, source="psx")  # commits
        logger.info("Auto-created PSX instrument %s with %d price rows.", candidate, n)
    except Exception as exc:
        logger.warning("Price backfill failed for new instrument %s: %s", candidate, exc)
        try:
            await db.commit()  # keep the instrument row even if the backfill failed
        except Exception:
            await db.rollback()
            return None

    return inst
