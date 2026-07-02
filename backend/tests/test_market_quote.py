"""
Asaas (اثاثہ) — Market Quote Tests

GET /market/quote/{symbol} powers the buy form's price auto-fill: always PKR,
any asset class, price_pkr null when no quote exists.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.instrument import Instrument


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_instrument(db_session, asset_class: str = "psx_stock") -> str:
    symbol = f"MQ{uuid4().hex[:6].upper()}" + (".KA" if asset_class == "psx_stock" else "")
    db_session.add(Instrument(symbol=symbol, name="Quote Test Co", asset_class=asset_class,
                              sector="Banking", currency="PKR", is_active=True))
    await db_session.commit()
    return symbol


@pytest.mark.asyncio
async def test_quote_returns_pkr_price(db_session, monkeypatch):
    async def _fake_price(symbol, db):
        return Decimal("456.78")
    monkeypatch.setattr("app.data.cache.get_price", _fake_price)

    symbol = await _seed_instrument(db_session)
    async with _client() as ac:
        res = await ac.get(f"/api/v1/market/quote/{symbol}")
        assert res.status_code == 200
        body = res.json()
        assert body["symbol"] == symbol
        assert Decimal(body["price_pkr"]) == Decimal("456.78")


@pytest.mark.asyncio
async def test_quote_null_when_no_price(db_session, monkeypatch):
    async def _no_price(symbol, db):
        return None
    monkeypatch.setattr("app.data.cache.get_price", _no_price)

    symbol = await _seed_instrument(db_session, "tbill")
    async with _client() as ac:
        res = await ac.get(f"/api/v1/market/quote/{symbol}")
        assert res.status_code == 200
        assert res.json()["price_pkr"] is None


@pytest.mark.asyncio
async def test_quote_unknown_symbol_404(db_session):
    async with _client() as ac:
        res = await ac.get("/api/v1/market/quote/not-a-symbol!!")
        assert res.status_code == 404
