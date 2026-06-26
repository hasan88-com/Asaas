"""
Asaas (اثاثہ) — CoinGecko Adapter

Fetches batched crypto prices to respect rate limits (10-50 calls/min).
Uses Decimal for precision, handles errors (RULES.md A2.4, A2.6, A3.5).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional
from datetime import date, datetime, timezone

import httpx

from app.core.config import get_settings

logger = logging.getLogger("asaas.coingecko_adapter")
settings = get_settings()


class CoinGeckoAdapter:
    """Adapter for CoinGecko API."""

    # Default mapping of currency symbol to CoinGecko coin ID
    SYMBOL_TO_ID = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "BNB": "binancecoin",
        "XRP": "ripple",
        "ADA": "cardano",
        "DOGE": "dogecoin",
    }

    def __init__(self):
        self.api_key = settings.coingecko_api_key
        # Demo keys use the public host; the demo header is added per-request.
        self.base_url = "https://api.coingecko.com/api/v3"

    async def fetch_prices(self, symbols: List[str]) -> Dict[str, Decimal]:
        """
        Batch fetch prices for multiple crypto symbols in a single call.
        Returns a dict mapping symbol to Decimal price in USD or PKR.
        """
        if not symbols:
            return {}

        coin_ids = []
        id_to_symbol = {}
        for s in symbols:
            upper_s = s.upper()
            cg_id = self.SYMBOL_TO_ID.get(upper_s)
            if cg_id:
                coin_ids.append(cg_id)
                id_to_symbol[cg_id] = upper_s
            else:
                # Fallback to lowercased symbol if not in dictionary
                fallback_id = upper_s.lower()
                coin_ids.append(fallback_id)
                id_to_symbol[fallback_id] = upper_s

        ids_param = ",".join(coin_ids)
        vs_currency = "pkr"

        url = f"{self.base_url}/simple/price"
        params = {
            "ids": ids_param,
            "vs_currencies": vs_currency,
        }
        headers = {}
        if self.api_key:
            headers["x-cg-demo-api-key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params, headers=headers)
                if response.status_code != 200:
                    logger.error(f"CoinGecko API returned status {response.status_code}: {response.text}")
                    return {}

                data = response.json()
                prices = {}
                for cg_id, price_info in data.items():
                    symbol = id_to_symbol.get(cg_id)
                    if symbol and vs_currency in price_info:
                        prices[symbol] = Decimal(str(price_info[vs_currency]))
                return prices

        except Exception as e:
            logger.error(f"Failed to fetch CoinGecko prices: {e}")
            return {}

    async def fetch_market_chart(
        self, symbol: str, days: int = 730, vs_currency: str = "pkr"
    ) -> List[Dict[str, Any]]:
        """Daily price history for backfill (the original spot series, not an ETF).

        Returns [{price_date, open, high, low, close, volume}] oldest→newest.
        CoinGecko market_chart gives close + volume only (OHL left None — the DB
        loader fills them from close). Priced in PKR to match how spot crypto is
        already stored. Empty list on failure.
        """
        cg_id = self.SYMBOL_TO_ID.get(symbol.upper(), symbol.lower())
        url = f"{self.base_url}/coins/{cg_id}/market_chart"
        # No 'interval' param: days>90 returns daily granularity automatically,
        # and 'interval=daily' is gated on paid plans (would 401 a demo key).
        params = {"vs_currency": vs_currency, "days": str(days)}
        headers = {}
        if self.api_key:
            headers["x-cg-demo-api-key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(url, params=params, headers=headers)
            if resp.status_code != 200:
                logger.warning("CoinGecko market_chart %s for %s: %s", resp.status_code, symbol, resp.text[:120])
                return []
            data = resp.json()
            # One row per day (last sample wins for a given date).
            by_date: Dict[date, Dict[str, Any]] = {}
            for ts, px in data.get("prices", []):
                d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date()
                by_date[d] = {
                    "price_date": d, "open": None, "high": None, "low": None,
                    "close": Decimal(str(px)), "volume": None,
                }
            return [by_date[d] for d in sorted(by_date)]
        except Exception as e:
            logger.error("Failed to fetch CoinGecko market_chart for %s: %s", symbol, e)
            return []
