"""
Asaasa — Fundamentals seed worker

Pre-loads the `instrument_fundamentals` DB cache + assigns PSX sectors for a
broad PSX universe, so the Valuation tab / Raabta AI serve P/E / EV-EBITDA / P/B
/ DCF and the industry-P/E×EPS verdict for common tickers even when yfinance is
rate-limited — and so each sector has many peers (real peer-median industry P/E).

Fundamentals come from dps.psx.com.pk (official, via _yf_get_fundamentals which
now prefers the PSX source for .KA); sectors come from the authoritative map
below (PSX sector classification).

    python -m app.workers.seed_fundamentals
Idempotent: re-running refreshes snapshots (merge-upsert).
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.db import async_session_factory
from app.models.instrument import Instrument
from app.services.valuation import _yf_get_fundamentals, _fundamentals_cache

logger = logging.getLogger("asaas.workers.seed_fundamentals")

# Authoritative PSX ticker → sector map (top ~200 by market cap).
TICKER_SECTOR: dict[str, str] = {
    "OGDC": "Oil & Gas Exploration Companies", "PPL": "Oil & Gas Exploration Companies", "POL": "Oil & Gas Exploration Companies",
    "UBL": "Commercial Banks", "MEBL": "Commercial Banks", "MCB": "Commercial Banks", "HBL": "Commercial Banks",
    "NBP": "Commercial Banks", "SCBPL": "Commercial Banks", "ABL": "Commercial Banks", "BAHL": "Commercial Banks",
    "BAFL": "Commercial Banks", "AKBL": "Commercial Banks", "FABL": "Commercial Banks", "HMB": "Commercial Banks",
    "BOP": "Commercial Banks", "BML": "Commercial Banks", "BOK": "Commercial Banks", "SNBL": "Commercial Banks",
    "JSBL": "Commercial Banks", "SBL": "Commercial Banks", "BIPL": "Commercial Banks",
    "FFC": "Fertilizer", "FATIMA": "Fertilizer", "EFERT": "Fertilizer",
    "MARI": "Oil & Gas Marketing Companies", "PSO": "Oil & Gas Marketing Companies", "SNGP": "Oil & Gas Marketing Companies",
    "APL": "Oil & Gas Marketing Companies", "SSGC": "Oil & Gas Marketing Companies", "HASCOL": "Oil & Gas Marketing Companies",
    "SPSL": "Oil & Gas Marketing Companies",
    "LUCK": "Cement", "BWCL": "Cement", "FCCL": "Cement", "MLCF": "Cement", "KOHC": "Cement", "DGKC": "Cement",
    "CHCC": "Cement", "PIOC": "Cement", "ACPL": "Cement", "THCCL": "Cement", "GWLC": "Cement", "FLYNG": "Cement", "POWER": "Cement",
    "PAKT": "Tobacco",
    "ENGROH": "Conglomerates",
    "NESTLE": "Food & Personal Care Products", "COLG": "Food & Personal Care Products", "UPFL": "Food & Personal Care Products",
    "NATF": "Food & Personal Care Products", "RMPL": "Food & Personal Care Products", "FCEPL": "Food & Personal Care Products",
    "MUREB": "Food & Personal Care Products", "BBFL": "Food & Personal Care Products", "UNITY": "Food & Personal Care Products",
    "BFAGRO": "Food & Personal Care Products", "TOMCL": "Food & Personal Care Products", "GDL": "Food & Personal Care Products", "FFL": "Food & Personal Care Products",
    "PTC": "Technology & Communication", "SYS": "Technology & Communication", "AIRLINK": "Technology & Communication",
    "TRG": "Technology & Communication", "NETSOL": "Technology & Communication", "AVN": "Technology & Communication", "HUMNL": "Technology & Communication",
    "HUBC": "Power Generation & Distribution", "KEL": "Power Generation & Distribution", "CNERGY": "Power Generation & Distribution",
    "WAFI": "Power Generation & Distribution", "EPQL": "Power Generation & Distribution", "PKGP": "Power Generation & Distribution",
    "NPL": "Power Generation & Distribution", "NCPL": "Power Generation & Distribution", "KAPCO": "Power Generation & Distribution",
    "ATLH": "Automobile Assembler", "INDU": "Automobile Assembler", "SAZEW": "Automobile Assembler", "MTL": "Automobile Assembler",
    "HCAR": "Automobile Assembler", "GHNI": "Automobile Assembler", "AGTL": "Automobile Assembler", "HINO": "Automobile Assembler", "GAL": "Automobile Assembler",
    "SLM": "Automobile Parts & Accessories", "THALL": "Automobile Parts & Accessories", "TBL": "Automobile Parts & Accessories",
    "PTL": "Automobile Parts & Accessories", "ATBA": "Automobile Parts & Accessories",
    "PIAHCLA": "Transport", "PIAHCLB": "Transport", "PNSC": "Transport", "SRVI": "Transport", "PIBTL": "Transport",
    "ILP": "Textile Composite", "ISIL": "Textile Composite", "NML": "Textile Composite", "IBFL": "Textile Composite",
    "DLL": "Textile Composite", "FML": "Textile Composite", "IDYM": "Textile Composite", "NCL": "Textile Composite",
    "TICL": "Textile Composite",
    "KTML": "Textile Weaving", "SAPT": "Textile Weaving", "STYLERS": "Textile Weaving", "JKSM": "Textile Weaving",
    "GATM": "Textile Weaving", "FZCM": "Textile Weaving", "TATM": "Textile Weaving", "MSOT": "Textile Weaving",
    "BTL": "Textile Weaving", "SURC": "Textile Weaving", "GADT": "Textile Weaving", "ZAHID": "Textile Weaving",
    "GATI": "Textile Weaving", "SFL": "Textile Weaving", "TREET": "Textile Weaving", "PREMA": "Textile Weaving", "MEHT": "Textile Weaving",
    "GLAXO": "Pharmaceuticals", "ABOT": "Pharmaceuticals", "HALEON": "Pharmaceuticals", "SEARL": "Pharmaceuticals",
    "HINOON": "Pharmaceuticals", "HPL": "Pharmaceuticals", "BFBIO": "Pharmaceuticals", "FEROZ": "Pharmaceuticals", "CPHL": "Pharmaceuticals",
    "LCI": "Chemical", "LOTCHEM": "Chemical", "AGL": "Chemical", "EPCL": "Chemical", "PAKOXY": "Chemical",
    "NICL": "Chemical", "SITC": "Chemical", "ARPL": "Chemical", "ICL": "Chemical", "GCIL": "Chemical",
    "ATRL": "Refinery", "NRL": "Refinery", "PRL": "Refinery",
    "DCR": "Real Estate Investment Trust",
    "TSML": "Sugar & Allied Industries", "JVDC": "Sugar & Allied Industries", "JDWS": "Sugar & Allied Industries",
    "SHSML": "Sugar & Allied Industries", "AABS": "Sugar & Allied Industries", "KPUS": "Sugar & Allied Industries",
    "HABSM": "Sugar & Allied Industries", "SML": "Sugar & Allied Industries",
    "PKGS": "Paper & Board", "PABC": "Paper & Board", "CEPB": "Paper & Board", "SEPL": "Paper & Board",
    "AHCL": "Investment Banks", "AKDSL": "Investment Banks", "JSCL": "Investment Banks", "AHL": "Investment Banks",
    "MCBIM": "Investment Banks", "SPEL": "Investment Banks", "GGL": "Investment Banks", "OLPL": "Investment Banks",
    "AMBL": "Investment Banks", "IMS": "Investment Banks",
    "GHGL": "Glass & Ceramics", "TGL": "Glass & Ceramics", "GVGL": "Glass & Ceramics", "BGL": "Glass & Ceramics",
    "ISL": "Engineering", "MUGHAL": "Engineering", "MUGHALC": "Engineering", "INIL": "Engineering", "SIEM": "Engineering",
    "ASL": "Engineering", "CSAP": "Engineering",
    "IGIHL": "Insurance", "AICL": "Insurance", "EFUG": "Insurance", "JLICL": "Insurance", "EFUL": "Insurance",
    "EWIC": "Insurance", "JGICL": "Insurance", "PAKRI": "Insurance", "ATIL": "Insurance", "ALIFE": "Insurance",
    "PAEL": "Cable & Electrical Goods", "FCL": "Cable & Electrical Goods", "PCAL": "Cable & Electrical Goods",
    "SGF": "Leather & Tanneries", "BATA": "Leather & Tanneries",
    "AGP": "Vanaspati & Allied Industries", "PSYL": "Synthetic & Rayon", "IPAK": "Packaging",
    "PSX": "Miscellaneous", "SHFA": "Miscellaneous", "PSEL": "Miscellaneous", "ZAL": "Miscellaneous", "MACTER": "Miscellaneous",
}
SEED_TICKERS: list[str] = list(TICKER_SECTOR.keys())


async def _ensure_instrument(db, symbol: str, sector: str | None) -> Instrument:
    inst = (await db.execute(select(Instrument).where(Instrument.symbol == symbol))).scalar_one_or_none()
    if inst is None:
        inst = Instrument(symbol=symbol, name=symbol, asset_class="psx_stock", currency="PKR",
                           sector=sector, data_source="psx", is_active=True, metadata_={"exchange": "PSX", "seed": True})
        db.add(inst)
    else:
        if sector:
            inst.sector = sector
    await db.commit()


async def run_seed(delay: float = 0.8) -> dict:
    ok = miss = 0
    for base, sector in TICKER_SECTOR.items():
        sym = f"{base}.KA"
        try:
            async with async_session_factory() as db:
                await _ensure_instrument(db, sym, sector)
            _fundamentals_cache.pop(sym, None)
            bundle = await _yf_get_fundamentals(sym)  # PSX(dps) + yfinance, auto-persists
            info = bundle.get("info") or {}
            has_pe = info.get("trailingPE") is not None
            ok += 1 if has_pe else 0
            miss += 0 if has_pe else 1
            logger.info("seed %-10s %s sector=%s pe=%s", sym, "OK" if has_pe else "MISS", sector, info.get("trailingPE"))
        except Exception as exc:
            miss += 1
            logger.warning("seed %s failed: %s", sym, exc)
        await asyncio.sleep(delay)
    return {"ok": ok, "miss": miss, "total": len(TICKER_SECTOR)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(asyncio.run(run_seed()))
