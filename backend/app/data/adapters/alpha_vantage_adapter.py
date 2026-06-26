"""
Asaas (اثاثہ) — Alpha Vantage Adapter

Backup price source for commodities.
Enforces a hard limit of 25 calls/day using Redis (RULES.md A2.4, A3.5).
Uses Decimal for prices.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import date, datetime, timezone

import httpx
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.redis import redis_client

logger = logging.getLogger("asaas.alpha_vantage_adapter")
settings = get_settings()


class AlphaVantageAdapter:
    """Adapter for Alpha Vantage, restricted to backup commodity quotes."""

    def __init__(self):
        self.api_key = settings.alpha_vantage_api_key
        self.base_url = "https://www.alphavantage.co/query"

    async def fetch_commodity_price(self, symbol: str) -> Optional[Decimal]:
        """
        Fetch the current price of a commodity (e.g. WTI, BRENT, COPPER, GAS).
        Increments a Redis quota counter and prevents execution if limit (25/day) is reached.
        """
        if not self.api_key:
            logger.warning("Alpha Vantage API key not configured.")
            return None

        # Check and increment Redis quota counter (key unique per day)
        today_str = date.today().strftime("%Y-%m-%d")
        quota_key = f"quota:alphavantage:{today_str}"

        try:
            current_count = await redis_client.get(quota_key)
            if current_count and int(current_count) >= 25:
                logger.error(f"Alpha Vantage daily limit of 25 calls reached. Call for {symbol} blocked.")
                return None

            # Increment count and set 36h TTL
            pipe = redis_client.pipeline()
            pipe.incr(quota_key)
            pipe.expire(quota_key, 129600)  # 36 hours
            await pipe.execute()

        except Exception as e:
            logger.error(f"Failed to verify Alpha Vantage quota via Redis: {e}")
            return None

        # Call Alpha Vantage
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
            "apikey": self.api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.base_url, params=params)
                if response.status_code != 200:
                    logger.error(f"Alpha Vantage returned status {response.status_code}")
                    return None

                data = response.json()
                quote = data.get("Global Quote", {})
                price_str = quote.get("05. price")
                if price_str:
                    price = Decimal(price_str)
                    logger.info(f"Alpha Vantage fetched backup price for {symbol}: {price}")
                    return price

                logger.warning(f"No price field in Alpha Vantage response for {symbol}: {data}")
                return None

        except Exception as e:
            logger.error(f"Failed to fetch commodity price from Alpha Vantage for {symbol}: {e}")
            return None
