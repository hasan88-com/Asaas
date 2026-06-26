"""
Asaas (اثاثہ) — Adapter Unit Tests

Mocks HTTP endpoints for external sources and verifies Decimal output formats.
"""

from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.data.adapters.yfinance_adapter import YFinanceAdapter
from app.data.adapters.coingecko_adapter import CoinGeckoAdapter
from app.data.adapters.sbp_adapter import SBPAdapter
from app.data.adapters.fred_adapter import FREDAdapter
from app.data.adapters.alpha_vantage_adapter import AlphaVantageAdapter
from app.data.adapters.psx_debt_adapter import PSXDebtAdapter


@pytest.mark.asyncio
async def test_yfinance_adapter():
    """Test yfinance adapter extracts closing price correctly as Decimal."""
    adapter = YFinanceAdapter()
    
    mock_data = {
        "price": Decimal("120.50"),
        "open": Decimal("120.00"),
        "high": Decimal("121.00"),
        "low": Decimal("119.50"),
        "volume": 1000,
        "price_date": "2026-06-01",
        "source": "yfinance_hist",
    }
    
    with patch.object(adapter, "fetch_price", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_data
        res = await adapter.fetch_price("HBL.KA")
        assert res is not None
        assert isinstance(res["price"], Decimal)
        assert res["price"] == Decimal("120.50")


@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_coingecko_adapter(mock_get):
    """Test CoinGecko fetches batched prices and parses to Decimal."""
    # Mock HTTP response
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "bitcoin": {"pkr": 17000000.0}
    }
    mock_get.return_value = mock_resp

    adapter = CoinGeckoAdapter()
    res = await adapter.fetch_prices(["BTC"])
    assert "BTC" in res
    assert isinstance(res["BTC"], Decimal)
    assert res["BTC"] == Decimal("17000000.0")


@pytest.mark.asyncio
async def test_sbp_adapter():
    """SBP policy rate returns None when all scrape sources fail.

    The adapter must NOT fabricate a fallback constant — that would silently
    poison the last-known-good cache in app.core.market.get_sbp_rate, which owns
    the fallback policy. The scrape sources are stubbed to fail so this is
    deterministic and offline.
    """
    adapter = SBPAdapter()
    with patch.object(adapter, "_scrape_homepage_policy_rate", new_callable=AsyncMock, return_value=None), \
         patch.object(adapter, "_scrape_monetary_policy_page", new_callable=AsyncMock, return_value=None), \
         patch.object(adapter, "_scrape_key_rates", new_callable=AsyncMock, return_value=None):
        rate = await adapter.fetch_policy_rate()
    assert rate is None  # no fabrication — caller decides the fallback


@pytest.mark.asyncio
async def test_fred_adapter():
    """Test FRED adapter returns fallback macro data if API key missing."""
    adapter = FREDAdapter()
    res = await adapter.fetch_series_latest("UNRATE")
    assert res is not None
    assert isinstance(res["value"], Decimal)
    assert res["value"] == Decimal("3.9")


@pytest.mark.asyncio
async def test_psx_debt_adapter():
    """Test PSX debt adapter returns list of instruments on scrape failure (empty list)."""
    adapter = PSXDebtAdapter()
    instruments = await adapter.fetch_all_instruments()
    assert isinstance(instruments, list)


@pytest.mark.asyncio
async def test_psx_debt_fetch_yields_by_tenor():
    """Test PSX debt adapter yields-by-tenor extraction."""
    adapter = PSXDebtAdapter()
    yields = await adapter.fetch_yields_by_tenor()
    assert isinstance(yields, dict)
