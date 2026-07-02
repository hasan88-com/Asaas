"""
Asaas (اثاثہ) — Instrument Resolver

Resolves a ticker symbol to an `Instrument` row, creating it on demand when
it hasn't been seeded yet:
- PSX tickers: validated against the symbol pattern, history fetched live via
  the PSXAdapter waterfall, then registered.
- Other classes (crypto / commodity / debt): registered from an explicit
  `asset_class` hint supplied by the caller (the frontend picker knows the
  class). Crypto/commodity rows get currency="USD" so the price cache's
  USD→PKR conversion applies; prices arrive lazily via the cache adapters.
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


# Frontend picker hint → instruments.asset_class (bonds share the tbill class,
# matching the seed data). Equity is absent on purpose: PSX tickers go through
# the history-validating PSX path below.
_HINT_CLASS = {
    "crypto": "crypto",
    "commodity": "commodity",
    "tbill": "tbill",
    "bond": "tbill",
}

_CLASS_META = {
    "crypto": {"currency": "USD", "data_source": "coingecko", "sector": "Digital Currency"},
    "commodity": {"currency": "USD", "data_source": "yfinance", "sector": "Commodities"},
    "tbill": {"currency": "PKR", "data_source": "manual", "sector": "Sovereign Debt"},
}


async def _register_from_hint(
    symbol: str, asset_class: str, name: Optional[str], db: AsyncSession
) -> Optional[Instrument]:
    """Create a non-PSX instrument row from the caller's asset-class hint."""
    meta = _CLASS_META[asset_class]
    stmt = (
        pg_insert(Instrument)
        .values(
            symbol=symbol,
            name=name or symbol,
            asset_class=asset_class,
            sector=meta["sector"],
            currency=meta["currency"],
            data_source=meta["data_source"],
            metadata_={"registered": "on_demand"},
        )
        .on_conflict_do_nothing(index_elements=["symbol"])
    )
    await db.execute(stmt)
    await db.commit()
    result = await db.execute(select(Instrument).where(Instrument.symbol == symbol))
    instrument = result.scalar_one_or_none()
    if instrument is not None:
        logger.info("Registered %s instrument on demand: %s", asset_class, symbol)
    return instrument


async def resolve_instrument(
    symbol: str,
    db: AsyncSession,
    asset_class: Optional[str] = None,
    name: Optional[str] = None,
) -> Optional[Instrument]:
    """Look up an existing Instrument by symbol; if missing, register it on
    demand — via live PSX history for PSX-looking tickers, or directly from
    the `asset_class` hint (crypto/commodity/tbill/bond) when the caller
    provides one. Returns None if the symbol can't be resolved by any path."""
    symbol = symbol.strip().upper()
    result = await db.execute(select(Instrument).where(Instrument.symbol == symbol))
    instrument = result.scalar_one_or_none()
    if instrument is not None:
        return instrument

    hinted_class = _HINT_CLASS.get((asset_class or "").lower())
    if hinted_class:
        return await _register_from_hint(symbol, hinted_class, name, db)

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
