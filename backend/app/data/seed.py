"""
Asaas (اثاثہ) — Database Seeding Script

Seeds the instruments table with the initial MVP asset universe:
- PSX Stocks (KSE-100 liquid subset)
- Cryptocurrencies
- Government Securities (MTBs, PIBs, GIS)
- Commodities (Gold, Oil)

Government Securities (per SBP):
- MTBs (Market Treasury Bills): Short-term, 3/6/12 month tenors, fortnightly auctions on Wednesdays
- PIBs (Pakistan Investment Bonds): Medium-to-long term, 3/5/10/20 year tenors
- GIS (Government Islamic Sukuk): Shariah compliant, 3-year tenors, Fixed/Variable Rate Rentals
"""

from __future__ import annotations

import asyncio
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session_factory
from app.models.instrument import Instrument

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("asaas.seed")

# MVP Instrument Universe
SEED_INSTRUMENTS = [
    # --- PSX Stocks ---
    {
        "symbol": "HBL.KA",
        "name": "Habib Bank Limited",
        "asset_class": "psx_stock",
        "sector": "Commercial Banks",
        "currency": "PKR",
        "data_source": "yfinance",
        "metadata_": {"exchange": "PSX"},
    },
    {
        "symbol": "ENGRO.KA",
        "name": "Engro Corporation Limited",
        "asset_class": "psx_stock",
        "sector": "Fertilizer",
        "currency": "PKR",
        "data_source": "yfinance",
        "metadata_": {"exchange": "PSX"},
    },
    {
        "symbol": "LUCK.KA",
        "name": "Lucky Cement Limited",
        "asset_class": "psx_stock",
        "sector": "Cement",
        "currency": "PKR",
        "data_source": "yfinance",
        "metadata_": {"exchange": "PSX"},
    },
    {
        "symbol": "OGDC.KA",
        "name": "Oil & Gas Development Company Limited",
        "asset_class": "psx_stock",
        "sector": "Oil & Gas Exploration Companies",
        "currency": "PKR",
        "data_source": "yfinance",
        "metadata_": {"exchange": "PSX"},
    },
    {
        "symbol": "MCB.KA",
        "name": "MCB Bank Limited",
        "asset_class": "psx_stock",
        "sector": "Commercial Banks",
        "currency": "PKR",
        "data_source": "yfinance",
        "metadata_": {"exchange": "PSX"},
    },

    # --- Cryptocurrencies ---
    {
        "symbol": "BTC",
        "name": "Bitcoin",
        "asset_class": "crypto",
        "sector": "Digital Currency",
        "currency": "PKR",  # We quote prices converted/fetched in PKR
        "data_source": "coingecko",
        "metadata_": {"coingecko_id": "bitcoin"},
    },
    {
        "symbol": "ETH",
        "name": "Ethereum",
        "asset_class": "crypto",
        "sector": "Digital Currency",
        "currency": "PKR",
        "data_source": "coingecko",
        "metadata_": {"coingecko_id": "ethereum"},
    },
    {
        "symbol": "SOL",
        "name": "Solana",
        "asset_class": "crypto",
        "sector": "Digital Currency",
        "currency": "PKR",
        "data_source": "coingecko",
        "metadata_": {"coingecko_id": "solana"},
    },

    # --- Fixed Income: Government Securities ---
    # MTBs (Market Treasury Bills) — short-term, highly liquid
    # Auctions: fortnightly on Wednesdays, settlement T+1
    # Tenors: 3M, 6M, 12M
    {
        "symbol": "MTB-3M",
        "name": "Pakistan Govt 3-Month Treasury Bill",
        "asset_class": "tbill",
        "sector": "Sovereign Debt",
        "currency": "PKR",
        "data_source": "sbp",
        "metadata_": {
            "tenor": "3M",
            "type": "MTB",
            "auction_frequency": "fortnightly",
            "settlement": "T+1",
            "description": "Short-term government security, highly liquid",
        },
    },
    {
        "symbol": "MTB-6M",
        "name": "Pakistan Govt 6-Month Treasury Bill",
        "asset_class": "tbill",
        "sector": "Sovereign Debt",
        "currency": "PKR",
        "data_source": "sbp",
        "metadata_": {
            "tenor": "6M",
            "type": "MTB",
            "auction_frequency": "fortnightly",
            "settlement": "T+1",
        },
    },
    {
        "symbol": "MTB-12M",
        "name": "Pakistan Govt 12-Month Treasury Bill",
        "asset_class": "tbill",
        "sector": "Sovereign Debt",
        "currency": "PKR",
        "data_source": "sbp",
        "metadata_": {
            "tenor": "12M",
            "type": "MTB",
            "auction_frequency": "fortnightly",
            "settlement": "T+1",
        },
    },

    # PIBs (Pakistan Investment Bonds) — medium-to-long term
    # Auctions: on need basis per pre-announced calendar
    # Tenors: 3Y, 5Y, 10Y, 20Y
    {
        "symbol": "PIB-3Y",
        "name": "Pakistan Investment Bond 3-Year",
        "asset_class": "tbill",
        "sector": "Sovereign Debt",
        "currency": "PKR",
        "data_source": "sbp",
        "metadata_": {
            "tenor": "3Y",
            "type": "PIB",
            "auction_frequency": "need_basis",
            "description": "Medium-term government bond",
        },
    },
    {
        "symbol": "PIB-5Y",
        "name": "Pakistan Investment Bond 5-Year",
        "asset_class": "tbill",
        "sector": "Sovereign Debt",
        "currency": "PKR",
        "data_source": "sbp",
        "metadata_": {
            "tenor": "5Y",
            "type": "PIB",
            "auction_frequency": "need_basis",
        },
    },
    {
        "symbol": "PIB-10Y",
        "name": "Pakistan Investment Bond 10-Year",
        "asset_class": "tbill",
        "sector": "Sovereign Debt",
        "currency": "PKR",
        "data_source": "sbp",
        "metadata_": {
            "tenor": "10Y",
            "type": "PIB",
            "auction_frequency": "need_basis",
        },
    },
    {
        "symbol": "PIB-20Y",
        "name": "Pakistan Investment Bond 20-Year",
        "asset_class": "tbill",
        "sector": "Sovereign Debt",
        "currency": "PKR",
        "data_source": "sbp",
        "metadata_": {
            "tenor": "20Y",
            "type": "PIB",
            "auction_frequency": "need_basis",
        },
    },

    # GIS (Government Islamic Sukuk) — Shariah compliant
    # Issued in 3-year tenors, Fixed Rate (FRR) or Variable Rate (VRR)
    {
        "symbol": "GIS-3Y-FRR",
        "name": "Govt Islamic Sukuk 3-Year Fixed Rate",
        "asset_class": "tbill",
        "sector": "Sovereign Debt",
        "currency": "PKR",
        "data_source": "sbp",
        "metadata_": {
            "tenor": "3Y",
            "type": "GIS",
            "rental_type": "FRR",
            "shariah_compliant": True,
            "description": "Islamic debt instrument, fixed rate rental",
        },
    },
    {
        "symbol": "GIS-3Y-VRR",
        "name": "Govt Islamic Sukuk 3-Year Variable Rate",
        "asset_class": "tbill",
        "sector": "Sovereign Debt",
        "currency": "PKR",
        "data_source": "sbp",
        "metadata_": {
            "tenor": "3Y",
            "type": "GIS",
            "rental_type": "VRR",
            "shariah_compliant": True,
            "description": "Islamic debt instrument, variable rate rental",
        },
    },

    # --- Commodities ---
    {
        "symbol": "GC=F",
        "name": "Gold Futures (COMEX)",
        "asset_class": "commodity",
        "sector": "Precious Metals",
        "currency": "USD",  # Converted to PKR in dashboard
        "data_source": "yfinance",
        "metadata_": {"exchange": "COMEX"},
    },
    {
        "symbol": "CL=F",
        "name": "Crude Oil Futures (NYMEX)",
        "asset_class": "commodity",
        "sector": "Energy",
        "currency": "USD",
        "data_source": "yfinance",
        "metadata_": {"exchange": "NYMEX"},
    },
]


async def seed_data():
    """Seed instruments table."""
    logger.info("Starting database seeding...")
    async with async_session_factory() as session:
        for inst_data in SEED_INSTRUMENTS:
            # Check if symbol already exists
            symbol = inst_data["symbol"]
            result = await session.execute(
                select(Instrument).where(Instrument.symbol == symbol)
            )
            existing = result.scalar_one_or_none()

            if not existing:
                instrument = Instrument(
                    symbol=symbol,
                    name=inst_data["name"],
                    asset_class=inst_data["asset_class"],
                    sector=inst_data["sector"],
                    currency=inst_data["currency"],
                    data_source=inst_data["data_source"],
                    metadata_=inst_data["metadata_"],
                )
                session.add(instrument)
                logger.info(f"Adding instrument: {symbol}")
            else:
                logger.info(f"Instrument already exists: {symbol}")

        await session.commit()
    logger.info("Database seeding completed.")


if __name__ == "__main__":
    asyncio.run(seed_data())
