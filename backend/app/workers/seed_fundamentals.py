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

# PSX large-caps by sector (bare tickers → .KA appended).
SEED_TICKERS: list[str] = [
    # Commercial Banks
    "HBL", "UBL", "MCB", "BAFL", "MEBL", "NBP", "BAHL", "AKBL",
    # Cement
    "LUCK", "DGKC", "MLCF", "FCCL", "KOHC", "PIOC", "ACPL",
    # Oil & Gas Exploration
    "OGDC", "PPL", "MARI", "POL",
    # Fertilizer
    "ENGRO", "FFC", "EFERT", "FATIMA",
    # Oil & Gas Marketing / Refinery
    "PSO", "APL", "SHEL", "SNGP", "SSGC", "ATRL", "NRL",
    # Power
    "HUBC", "KAPCO", "NPL", "NCPL",
    # Technology
    "SYS", "TRG", "NETSOL", "AVN",
    # Automobile
    "INDU", "HCAR", "MTL", "PSMC",
    # Chemicals
    "EPCL", "ICI", "LOTCHEM", "BERG",
    # Textile
    "NML", "ILP", "GATM", "KTML",
    # Food
    "NESTLE", "EFOODS", "FFL",
    # Pharma
    "SEARL", "AGP", "HINOON", "GLAXO", "ABOT",
    # Misc large-caps seen in user queries
    "BBFL", "RMPL",
]


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
            sector = info.get("sector")
            # Populate sector/industry so peer-median industry P/E works.
            if sector:
                async with async_session_factory() as db:
                    inst = (await db.execute(select(Instrument).where(Instrument.symbol == sym))).scalar_one()
                    inst.sector = inst.sector or sector
                    inst.metadata_ = {**(inst.metadata_ or {}), "yf_sector": sector, "yf_industry": info.get("industry")}
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
