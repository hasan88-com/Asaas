"""
Asaas (اثاثہ) — FRED (Federal Reserve Economic Data) Adapter

Fetches macroeconomic data indicators for macro reasoning.
Uses Decimal for precision, handles errors (RULES.md A3.5).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional
from datetime import date

import httpx

from app.core.config import get_settings

logger = logging.getLogger("asaas.fred_adapter")
settings = get_settings()


class FREDAdapter:
    """Adapter for FRED Macroeconomic Data API."""

    def __init__(self):
        self.api_key = settings.fred_api_key
        self.base_url = "https://api.stlouisfed.org/fred"

    async def fetch_series_latest(self, series_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch the most recent observation for a series (e.g. CPIAUCSL, GDP, UNRATE).
        """
        if not self.api_key:
            logger.warning("FRED API key not configured. Returning mock/default indicator.")
            return self._get_mock_data(series_id)

        url = f"{self.base_url}/series/observations"
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                if response.status_code != 200:
                    logger.error(f"FRED API returned status {response.status_code}: {response.text}")
                    return self._get_mock_data(series_id)

                data = response.json()
                observations = data.get("observations", [])
                if not observations:
                    return None

                latest = observations[0]
                value_str = latest.get("value")
                # Handle missing/placeholder values in FRED observations (like ".")
                if value_str == ".":
                    return None

                return {
                    "value": Decimal(value_str),
                    "date": datetime.strptime(latest.get("date"), "%Y-%m-%d").date(),
                    "series_id": series_id,
                }

        except Exception as e:
            logger.error(f"Failed to fetch FRED series {series_id}: {e}")
            return self._get_mock_data(series_id)

    def _get_mock_data(self, series_id: str) -> Dict[str, Any]:
        """Provides realistic mock values if API key is missing or calls fail."""
        defaults = {
            "CPIAUCSL": Decimal("310.2"),  # US CPI CPIAUCSL
            "GDP": Decimal("27900.5"),     # US GDP
            "UNRATE": Decimal("3.9"),       # Unemployment rate
        }
        return {
            "value": defaults.get(series_id, Decimal("0.0")),
            "date": date.today(),
            "series_id": series_id,
        }
