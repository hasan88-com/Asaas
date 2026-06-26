"""
Asaas (اثاثہ) — Historical Price Backfill (Phase A)

One-shot (and monthly) job that fills the `prices` table with 1–2yr of daily
OHLCV per instrument, so technicals / optimizer / risk read DB-first instead of
live-scraping yfinance on every request. Idempotent: re-running upserts the same
(instrument_id, price_date) rows — no duplicates. Instruments with no data from
any source are skipped + logged.

Sourcing (waterfall per class):
  psx_stock              → PSXAdapter (DPS → psx-data-reader → yfinance .KA)
  crypto                 → CoinGecko market_chart (PKR) → yfinance BTC-USD
  commodity/global/index → yfinance history (=F / .* / ^KSE)
  tbill/bond             → skipped (yields, not a price series)

Also ensures a `^KSE` index instrument exists and backfills it, so beta/CAPM
can read the benchmark from the DB.

Run one-shot:  python -m app.workers.backfill_prices
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Tuple

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.db import async_session_factory
from app.models.instrument import Instrument
from app.models.price import Price

logger = logging.getLogger("asaas.workers.backfill_prices")

_KSE_SYMBOL = "^KSE"

# Bare crypto ticker → yfinance USD spot pair (fallback only; primary is CoinGecko PKR).
_CRYPTO_YF = {
    "BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD",
    "BNB": "BNB-USD", "XRP": "XRP-USD", "ADA": "ADA-USD", "DOGE": "DOGE-USD",
}


async def _history_for(inst: Instrument, years: int) -> Tuple[List[Dict[str, Any]], str]:
    """Return (rows, source) of daily OHLCV for one instrument, by asset class."""
    ac = inst.asset_class
    sym = inst.symbol

    if ac == "psx_stock":
        from app.data.adapters.psx_adapter import PSXAdapter
        return await PSXAdapter().fetch_history(sym, years=years), "psx"

    if ac == "crypto":
        from app.data.adapters.coingecko_adapter import CoinGeckoAdapter
        rows = await CoinGeckoAdapter().fetch_market_chart(sym, days=365 * years)
        if rows:
            return rows, "coingecko"
        from app.data.adapters.yfinance_adapter import YFinanceAdapter
        yf_sym = _CRYPTO_YF.get(sym.upper(), sym)
        return await YFinanceAdapter().fetch_history(yf_sym, period=f"{years}y"), "yfinance"

    if ac in ("commodity", "global_stock", "index"):
        from app.data.adapters.yfinance_adapter import YFinanceAdapter
        return await YFinanceAdapter().fetch_history(sym, period=f"{years}y"), "yfinance"

    # tbill / bond / mutual_fund: no real OHLCV price series — skip.
    return [], "skip"


async def _upsert_rows(session, instrument_id, rows: List[Dict[str, Any]], source: str) -> int:
    """Idempotent upsert of OHLCV rows for one instrument. Returns row count."""
    now = datetime.now(timezone.utc)
    n = 0
    for r in rows:
        close = r.get("close")
        if close is None:
            continue
        vals = dict(
            instrument_id=instrument_id,
            price=close,                       # Decimal → NUMERIC
            price_date=r["price_date"],
            open=r.get("open"),
            high=r.get("high"),
            low=r.get("low"),
            volume=r.get("volume"),
            source=source,
            fetched_at=now,
        )
        stmt = pg_insert(Price).values(**vals).on_conflict_do_update(
            index_elements=["instrument_id", "price_date"],
            set_={k: v for k, v in vals.items() if k not in ("instrument_id", "price_date")},
        )
        await session.execute(stmt)
        n += 1
    await session.commit()
    return n


async def _ensure_kse(session) -> Instrument:
    """Ensure a ^KSE index instrument exists (benchmark for beta/CAPM)."""
    res = await session.execute(select(Instrument).where(Instrument.symbol == _KSE_SYMBOL))
    kse = res.scalar_one_or_none()
    if kse is None:
        kse = Instrument(
            symbol=_KSE_SYMBOL, name="KSE-100 Index", asset_class="index",
            currency="PKR", data_source="yfinance", is_active=False,
        )
        session.add(kse)
        await session.commit()
        await session.refresh(kse)
        logger.info("Created ^KSE benchmark instrument")
    return kse


async def run_backfill_prices(years: int = 2) -> Dict[str, int]:
    """Backfill historical prices for all active instruments + the ^KSE benchmark."""
    logger.info("Starting price backfill (%dyr)…", years)
    summary = {"ok": 0, "skipped": 0, "bars": 0}

    async with async_session_factory() as session:
        kse = await _ensure_kse(session)
        active = (await session.execute(
            select(Instrument).where(Instrument.is_active == True)  # noqa: E712
        )).scalars().all()

        # De-dupe (^KSE is inactive, so add it explicitly).
        targets = list(active) + [kse]
        for inst in targets:
            try:
                rows, source = await _history_for(inst, years)
                if not rows:
                    summary["skipped"] += 1
                    logger.info("backfill skip %s (%s, no data)", inst.symbol, inst.asset_class)
                    continue
                n = await _upsert_rows(session, inst.id, rows, source)
                summary["ok"] += 1
                summary["bars"] += n
                logger.info("backfilled %s: %d bars (%s)", inst.symbol, n, source)
            except Exception as exc:
                summary["skipped"] += 1
                logger.error("backfill failed for %s: %s", inst.symbol, exc)

    logger.info("Price backfill complete: %s", summary)
    return summary


async def prices_table_is_sparse(min_rows: int = 100) -> bool:
    """True if the prices table has fewer than `min_rows` rows (cold DB)."""
    try:
        async with async_session_factory() as session:
            count = await session.scalar(select(func.count()).select_from(Price))
        return (count or 0) < min_rows
    except Exception:
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_backfill_prices())
