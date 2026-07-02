"""
Asaas (اثاثہ) — Watchlist Integration Tests

Per-user instrument watchlist: add / list (grouped client-side) / remove,
duplicate adds are idempotent, unknown symbols 404. Auth is mocked by
overriding get_current_user; HTTP via httpx ASGITransport (same pattern as
test_wallet.py).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.security import get_current_user
from app.models.instrument import Instrument
from app.models.user import User


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _fake_prices(symbols, db=None):
    return {s.upper(): Decimal("123.45") for s in symbols}


async def _seed_user(db_session) -> User:
    user = User(id=uuid4(), email=f"watch_{uuid4().hex[:10]}@example.com", full_name="Watch User")
    db_session.add(user)
    await db_session.commit()
    db_session.expunge(user)
    return user


async def _seed_instrument(db_session, asset_class: str = "psx_stock") -> str:
    symbol = f"WL{uuid4().hex[:6].upper()}" + (".KA" if asset_class == "psx_stock" else "")
    inst = Instrument(symbol=symbol, name="Watchlist Test Co", asset_class=asset_class,
                      sector="Banking", currency="PKR", is_active=True)
    db_session.add(inst)
    await db_session.commit()
    return symbol


@pytest.mark.asyncio
async def test_watchlist_add_list_remove(db_session, monkeypatch):
    monkeypatch.setattr("app.data.cache.get_prices", _fake_prices)
    user = await _seed_user(db_session)
    stock = await _seed_instrument(db_session, "psx_stock")
    crypto = await _seed_instrument(db_session, "crypto")

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with _client() as ac:
            # Empty to start.
            res = await ac.get("/api/v1/watchlist")
            assert res.status_code == 200
            assert res.json()["items"] == []

            # Add a stock and a crypto.
            res = await ac.post("/api/v1/watchlist", json={"symbol": stock})
            assert res.status_code == 201
            assert res.json()["symbol"] == stock
            res = await ac.post("/api/v1/watchlist", json={"symbol": crypto})
            assert res.status_code == 201

            # List returns both with prices from the cache layer.
            res = await ac.get("/api/v1/watchlist")
            items = res.json()["items"]
            assert {i["symbol"] for i in items} == {stock, crypto}
            assert {i["asset_class"] for i in items} == {"psx_stock", "crypto"}
            assert all(Decimal(i["price"]) == Decimal("123.45") for i in items)

            # Remove one; the other stays.
            victim = items[0]
            res = await ac.delete(f"/api/v1/watchlist/{victim['id']}")
            assert res.status_code == 204
            res = await ac.get("/api/v1/watchlist")
            remaining = res.json()["items"]
            assert len(remaining) == 1
            assert remaining[0]["symbol"] != victim["symbol"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_watchlist_duplicate_add_is_idempotent(db_session, monkeypatch):
    monkeypatch.setattr("app.data.cache.get_prices", _fake_prices)
    user = await _seed_user(db_session)
    symbol = await _seed_instrument(db_session)

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with _client() as ac:
            first = await ac.post("/api/v1/watchlist", json={"symbol": symbol})
            second = await ac.post("/api/v1/watchlist", json={"symbol": symbol})
            assert first.json()["id"] == second.json()["id"]

            res = await ac.get("/api/v1/watchlist")
            assert len(res.json()["items"]) == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_watchlist_unseeded_symbol_registers_via_hint(db_session, monkeypatch):
    """Unseeded non-PSX symbols (crypto/commodity/bond pickers) register on
    demand from the asset_class hint instead of 404ing."""
    monkeypatch.setattr("app.data.cache.get_prices", _fake_prices)
    user = await _seed_user(db_session)
    symbol = f"C{uuid4().hex[:5].upper()}"  # not seeded anywhere

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with _client() as ac:
            res = await ac.post("/api/v1/watchlist", json={
                "symbol": symbol, "asset_class": "crypto", "name": "Hint Coin",
            })
            assert res.status_code == 201
            body = res.json()
            assert body["symbol"] == symbol
            assert body["asset_class"] == "crypto"
            assert body["name"] == "Hint Coin"
            assert body["currency"] == "USD"  # so the price cache converts to PKR

            # Bond hint maps onto the tbill class used by the seed data.
            res = await ac.post("/api/v1/watchlist", json={
                "symbol": f"B{uuid4().hex[:5].upper()}TFC1", "asset_class": "bond", "name": "Hint TFC",
            })
            assert res.status_code == 201
            assert res.json()["asset_class"] == "tbill"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_watchlist_unknown_symbol_404_and_foreign_delete_404(db_session):
    user = await _seed_user(db_session)

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with _client() as ac:
            # Symbol that can't resolve (not seeded, not a plausible PSX ticker).
            res = await ac.post("/api/v1/watchlist", json={"symbol": "not-a-symbol!!"})
            assert res.status_code == 404

            res = await ac.delete(f"/api/v1/watchlist/{uuid4()}")
            assert res.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
