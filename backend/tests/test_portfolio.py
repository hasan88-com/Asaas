"""
Asaas (اثاثہ) — Portfolio Integration Tests

Tests portfolio suggestions, confirming positions, and guest mode rate limit rules.

Auth is handled by Supabase (there is no /auth/register endpoint), so these tests
mock authentication by overriding the get_current_user dependency rather than
minting a real JWT. HTTP is driven via httpx ASGITransport (the `app=` shortcut
was removed in httpx 0.28+).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.security import get_current_user
from app.models.instrument import Instrument
from app.models.risk_profile import RiskProfile
from app.models.user import User


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_suggest_and_confirm_portfolio_flow(db_session):
    """Suggest + confirm flow works for an authenticated user (JWT-mocked)."""
    # Seed a user, a matching risk profile, and a couple of instruments.
    user = User(id=uuid4(), email="portfolio_user@example.com", full_name="Portfolio User")
    db_session.add(user)
    await db_session.flush()

    hbl = Instrument(symbol="HBL.KA", name="Habib Bank", asset_class="psx_stock",
                     sector="Banking", currency="PKR", is_active=True)
    db_session.add_all([
        hbl,
        Instrument(symbol="BTC", name="Bitcoin", asset_class="crypto",
                   currency="PKR", is_active=True),
    ])
    db_session.add(RiskProfile(
        user_id=user.id,
        risk_tolerance="moderate",
        horizon="medium",
        investor_mode="long_term",
        initial_capital=Decimal("500000"),
        goal="growth",
    ))
    await db_session.flush()

    async def _mock_user():
        return user

    app.dependency_overrides[get_current_user] = _mock_user
    try:
        async with _client() as ac:
            # Suggest — empty body is valid (all overrides optional).
            res_suggest = await ac.post("/api/v1/portfolio/suggest", json={})
            assert res_suggest.status_code == 200
            port_data = res_suggest.json()
            assert port_data["status"] == "draft"
            assert port_data["expected_return"] is not None

            # Confirm with a real instrument so the draft transitions cleanly.
            # (A bogus instrument_id would raise an unhandled IntegrityError that
            # ASGITransport propagates into the test rather than returning 500.)
            confirm_payload = {
                "holdings": [
                    {
                        "instrument_id": str(hbl.id),
                        "actual_weight": 1.0,
                        "quantity": 10.0,
                        "entry_price": 100.0,
                    }
                ]
            }
            res_confirm = await ac.post("/api/v1/portfolio/confirm", json=confirm_payload)
            assert res_confirm.status_code in (200, 201)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_guest_analyze_rate_limiting(db_session):
    """Guest analyze returns 429 once the per-IP/cookie quota is exceeded."""
    guest_payload = {
        "holdings": [
            {"symbol": "BTC", "qty": 1.5, "entry_price": 15000000.0, "asset_class": "crypto"}
        ],
        "risk_tolerance": "moderate",
        "horizon": "medium",
        "goal": "growth",
    }

    # The IP counter increments on every call (before price resolution), and the
    # hard cap is 5 — so the 6th call is rejected regardless of earlier outcomes.
    async with _client() as ac:
        status_codes = []
        for _ in range(6):
            res = await ac.post("/api/v1/portfolio/analyze-guest", json=guest_payload)
            status_codes.append(res.status_code)

    assert 429 in status_codes
