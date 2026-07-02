"""
Asaas (اثاثہ) — Wallet Integration Tests

Virtual PKR cash wallet: lazy account creation, deposits/withdrawals with the
append-only ledger, the insufficient-funds guard on buys, and cash credit on
sells. Auth is mocked by overriding get_current_user (Supabase owns real auth);
HTTP is driven via httpx ASGITransport, same pattern as test_portfolio.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func as sa_func, select

from app.main import app
from app.core.security import get_current_user
from app.models.holding import Holding
from app.models.instrument import Instrument
from app.models.portfolio import Portfolio
from app.models.user import User


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _noop_snapshot(portfolio_id) -> None:
    return None


async def _noop_warm() -> None:
    return None


async def _no_price(*args, **kwargs):
    return None


def _quiet_background(monkeypatch) -> None:
    """Keep buy/sell tests offline: no snapshot writes, price warming, or
    live price lookups (weights recompute degrades gracefully to no-op)."""
    monkeypatch.setattr("app.api.portfolio._write_initial_snapshot", _noop_snapshot)
    monkeypatch.setattr("app.workers.warm_prices.run_warm_prices", _noop_warm)
    monkeypatch.setattr("app.data.cache.get_price", _no_price)


async def _seed_user(db_session) -> User:
    user = User(id=uuid4(), email=f"wallet_{uuid4().hex[:10]}@example.com", full_name="Wallet User")
    db_session.add(user)
    await db_session.commit()
    # Detach so an endpoint-triggered rollback can't expire the object the
    # get_current_user mock keeps returning (expired attrs can't lazy-refresh
    # from async request context).
    db_session.expunge(user)
    return user


async def _seed_portfolio_and_instrument(db_session, user: User) -> tuple[object, str]:
    """Returns (portfolio_id, symbol) as plain values — a rollback inside an
    endpoint expires seeded ORM objects, and refreshing them lazily from an
    async test raises."""
    # Unique per test — the session-scoped test schema persists committed rows
    # across tests and Instrument.symbol is unique.
    symbol = f"WT{uuid4().hex[:6].upper()}.KA"
    inst = Instrument(symbol=symbol, name="Wallet Test Co", asset_class="psx_stock",
                      sector="Banking", currency="PKR", is_active=True)
    portfolio = Portfolio(user_id=user.id, name="Wallet Test Portfolio",
                          status="confirmed", confirmed_at=datetime.now(timezone.utc))
    db_session.add_all([inst, portfolio])
    await db_session.flush()
    portfolio_id = portfolio.id
    await db_session.commit()
    return portfolio_id, symbol


@pytest.mark.asyncio
async def test_wallet_lazy_creates_at_zero(db_session):
    user = await _seed_user(db_session)

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with _client() as ac:
            res = await ac.get("/api/v1/wallet")
            assert res.status_code == 200
            body = res.json()
            assert Decimal(body["balance"]) == 0
            assert body["currency"] == "PKR"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_deposit_withdraw_and_ledger(db_session):
    user = await _seed_user(db_session)

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with _client() as ac:
            res = await ac.post("/api/v1/wallet/deposit", json={"amount": 100000})
            assert res.status_code == 200
            assert Decimal(res.json()["balance"]) == Decimal("100000")

            # Over-withdraw is rejected and the balance is untouched.
            res = await ac.post("/api/v1/wallet/withdraw", json={"amount": 200000})
            assert res.status_code == 422
            assert "Insufficient funds" in res.json()["detail"]

            res = await ac.post("/api/v1/wallet/withdraw", json={"amount": 50000})
            assert res.status_code == 200
            assert Decimal(res.json()["balance"]) == Decimal("50000")

            res = await ac.get("/api/v1/wallet/transactions")
            assert res.status_code == 200
            body = res.json()
            assert body["total"] == 2
            types = [t["type"] for t in body["items"]]
            assert types == ["withdrawal", "deposit"]  # newest first
            assert Decimal(body["items"][0]["balance_after"]) == Decimal("50000")
            assert Decimal(body["items"][1]["balance_after"]) == Decimal("100000")
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_buy_with_insufficient_funds_rejected(db_session, monkeypatch):
    _quiet_background(monkeypatch)
    user = await _seed_user(db_session)
    portfolio_id, symbol = await _seed_portfolio_and_instrument(db_session, user)

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with _client() as ac:
            res = await ac.post("/api/v1/portfolio/holdings/add", json={
                "symbol": symbol, "quantity": 10, "entry_price": 100,
            })
            assert res.status_code == 422
            assert "Insufficient funds" in res.json()["detail"]

            # No holding was created and the balance is still zero.
            count = (await db_session.execute(
                select(sa_func.count()).select_from(Holding)
                .where(Holding.portfolio_id == portfolio_id)
            )).scalar_one()
            assert count == 0

            res = await ac.get("/api/v1/wallet")
            assert Decimal(res.json()["balance"]) == 0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_buy_and_sell_move_cash(db_session, monkeypatch):
    _quiet_background(monkeypatch)
    user = await _seed_user(db_session)
    _portfolio_id, symbol = await _seed_portfolio_and_instrument(db_session, user)

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with _client() as ac:
            await ac.post("/api/v1/wallet/deposit", json={"amount": 10000})

            # Buy 10 @ ₨100 → debit ₨1,000.
            res = await ac.post("/api/v1/portfolio/holdings/add", json={
                "symbol": symbol, "quantity": 10, "entry_price": 100,
            })
            assert res.status_code == 201
            # The response's holdings collection is stale in tests (all requests
            # share one session + identity map) — read the holding from the DB.
            holding_id = str((await db_session.execute(
                select(Holding.id).where(Holding.portfolio_id == _portfolio_id)
            )).scalar_one())

            res = await ac.get("/api/v1/wallet")
            assert Decimal(res.json()["balance"]) == Decimal("9000")

            res = await ac.get("/api/v1/wallet/transactions")
            buy_txn = res.json()["items"][0]
            assert buy_txn["type"] == "buy"
            assert buy_txn["symbol"] == symbol
            assert Decimal(buy_txn["amount"]) == Decimal("1000")

            # Partial sell 5 @ ₨120 → credit ₨600.
            res = await ac.post("/api/v1/portfolio/holdings/sell", json={
                "holding_id": holding_id, "quantity": 5, "price": 120,
            })
            assert res.status_code == 200
            res = await ac.get("/api/v1/wallet")
            assert Decimal(res.json()["balance"]) == Decimal("9600")

            # Full liquidation of the remaining 5 → holding gone, ledger survives.
            res = await ac.post("/api/v1/portfolio/holdings/sell", json={
                "holding_id": holding_id, "quantity": 5, "price": 120,
            })
            assert res.status_code == 200
            remaining = (await db_session.execute(
                select(sa_func.count()).select_from(Holding)
                .where(Holding.portfolio_id == _portfolio_id)
            )).scalar_one()
            assert remaining == 0

            res = await ac.get("/api/v1/wallet")
            assert Decimal(res.json()["balance"]) == Decimal("10200")

            res = await ac.get("/api/v1/wallet/transactions")
            body = res.json()
            assert body["total"] == 4  # deposit, buy, sell, sell
            latest = body["items"][0]
            assert latest["type"] == "sell"
            assert latest["symbol"] == symbol  # symbol survives holding deletion
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_sell_more_than_held_still_rejected(db_session, monkeypatch):
    """The pre-existing insufficient-holdings guard fires before any cash moves."""
    _quiet_background(monkeypatch)
    user = await _seed_user(db_session)
    _portfolio_id, symbol = await _seed_portfolio_and_instrument(db_session, user)

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with _client() as ac:
            await ac.post("/api/v1/wallet/deposit", json={"amount": 5000})
            res = await ac.post("/api/v1/portfolio/holdings/add", json={
                "symbol": symbol, "quantity": 10, "entry_price": 100,
            })
            assert res.status_code == 201
            holding_id = str((await db_session.execute(
                select(Holding.id)
                .join(Portfolio, Portfolio.id == Holding.portfolio_id)
                .where(Portfolio.id == _portfolio_id)
            )).scalar_one())

            res = await ac.post("/api/v1/portfolio/holdings/sell", json={
                "holding_id": holding_id, "quantity": 99, "price": 120,
            })
            assert res.status_code == 422
            assert "Insufficient holdings" in res.json()["detail"]

            # Balance unchanged by the failed sell (5000 - 1000 buy).
            res = await ac.get("/api/v1/wallet")
            assert Decimal(res.json()["balance"]) == Decimal("4000")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
