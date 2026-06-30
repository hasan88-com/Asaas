"""
Asaasa — Fundamentals seed worker

Pre-loads the `instrument_fundamentals` DB cache for a broad set of PSX
large-caps across many sectors, so the Valuation tab / Raabta AI can serve
P/E / EV-EBITDA / P/B / DCF and the industry-P/E×EPS verdict for common tickers
even when yfinance is rate-limited on the deployed (Render) IP — and so each
sector has several stocks (making the peer-median industry P/E meaningful).

Run from a context where Yahoo is reachable (e.g. locally):
    python -m app.workers.seed_fundamentals
Idempotent: re-running just refreshes snapshots (merge-upsert).
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.db import async_session_factory
from app.models.instrument import Instrument
from app.services.valuation import _yf_get_fundamentals, _fundamentals_cache

logger = logging.getLogger("asaas.workers.seed_fundamentals")

# PSX large-caps grouped by sector (bare tickers → .KA appended). We assign the
# sector from THIS grouping, not yfinance (which omits `sector` for .KA), so the
# peer-median industry P/E has real same-sector populations.
SECTOR_MAP: dict[str, list[str]] = {
    "Commercial Banks": ["HBL", "UBL", "MCB", "BAFL", "MEBL", "NBP", "BAHL", "AKBL"],
    "Cement": ["LUCK", "DGKC", "MLCF", "FCCL", "KOHC", "PIOC", "ACPL"],
    "Oil & Gas Exploration Companies": ["OGDC", "PPL", "MARI", "POL"],
    "Fertilizer": ["ENGRO", "FFC", "EFERT", "FATIMA"],
    "Oil & Gas Marketing Companies": ["PSO", "APL", "SHEL", "SNGP", "SSGC"],
    "Refinery": ["ATRL", "NRL"],
    "Power Generation & Distribution": ["HUBC", "KAPCO", "NPL", "NCPL"],
    "Technology & Communication": ["SYS", "TRG", "NETSOL", "AVN"],
    "Automobile Assembler": ["INDU", "HCAR", "MTL", "PSMC"],
    "Chemical": ["EPCL", "ICI", "LOTCHEM", "BERG"],
    "Textile Composite": ["NML", "ILP", "GATM", "KTML"],
    "Food & Personal Care Products": ["NESTLE", "EFOODS", "FFL"],
    "Pharmaceuticals": ["SEARL", "AGP", "HINOON", "GLAXO", "ABOT"],
    "Miscellaneous": ["BBFL", "RMPL"],
}
# bare ticker -> PSX sector
TICKER_SECTOR: dict[str, str] = {t: sec for sec, ts in SECTOR_MAP.items() for t in ts}
SEED_TICKERS: list[str] = list(TICKER_SECTOR.keys())


async def _ensure_instrument(db, symbol: str) -> Instrument:
    inst = (await db.execute(select(Instrument).where(Instrument.symbol == symbol))).scalar_one_or_none()
    if inst is None:
        inst = Instrument(symbol=symbol, name=symbol, asset_class="psx_stock", currency="PKR",
                           data_source="yfinance", is_active=True, metadata_={"exchange": "PSX", "seed": True})
        db.add(inst)
        await db.commit()
        await db.refresh(inst)
    return inst


async def run_seed(tickers: list[str] | None = None, delay: float = 1.0) -> dict:
    tickers = tickers or SEED_TICKERS
    ok = miss = 0
    for base in tickers:
        sym = f"{base}.KA"
        try:
            async with async_session_factory() as db:
                inst = await _ensure_instrument(db, sym)
            _fundamentals_cache.pop(sym, None)
            bundle = await _yf_get_fundamentals(sym)  # fetches live + auto-persists
            info = bundle.get("info") or {}
            # Assign the curated PSX sector (yfinance omits sector for .KA), so
            # peer-median industry P/E has real same-sector populations.
            sector = TICKER_SECTOR.get(base) or info.get("sector")
            if sector:
                async with async_session_factory() as db:
                    inst = (await db.execute(select(Instrument).where(Instrument.symbol == sym))).scalar_one()
                    inst.sector = sector
                    inst.metadata_ = {**(inst.metadata_ or {}), "yf_sector": info.get("sector"), "yf_industry": info.get("industry")}
                    await db.commit()
            has = not bundle.get("stale") or bool(info.get("trailingPE"))
            if has:
                ok += 1
            else:
                miss += 1
            logger.info("seed %-10s %s sector=%s", sym, "OK" if has else "MISS", sector)
        except Exception as exc:
            miss += 1
            logger.warning("seed %s failed: %s", sym, exc)
        await asyncio.sleep(delay)  # be gentle on Yahoo
    return {"ok": ok, "miss": miss, "total": len(tickers)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(asyncio.run(run_seed()))
