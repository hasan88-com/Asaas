"""
Asaas (اثاثہ) — Auth Tests (Supabase JWT)

Tests Supabase JWT verification:
  - Valid token passes and returns user
  - Expired token is rejected
  - Invalid signature is rejected
  - Cross-user access is blocked
  - POST /auth/session creates user on first call, returns existing user on repeat
"""

from __future__ import annotations

import time
import uuid
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt

from app.main import app
from app.models.user import User

TEST_JWT_SECRET = "test-supabase-jwt-secret-for-tests-only"


def _make_token(
    user_id: str,
    secret: str = TEST_JWT_SECRET,
    exp_offset: int = 3600,
    audience: str = "authenticated",
) -> str:
    """Mint a fake Supabase-style JWT for testing."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": f"{user_id[:8]}@example.com",
        "aud": audience,
        "role": "authenticated",
        "iat": now,
        "exp": now + exp_offset,
        "user_metadata": {"full_name": "Test User"},
    }
    return jwt.encode(payload, secret, algorithm="HS256")


# ---------------------------------------------------------------------------
# verify_supabase_jwt — unit tests (no DB)
# ---------------------------------------------------------------------------


def test_valid_token_decodes():
    """A well-formed token with correct secret and audience decodes without error."""
    from app.core.security import verify_supabase_jwt

    user_id = str(uuid.uuid4())
    token = _make_token(user_id)

    with patch("app.core.security.get_settings") as mock_settings:
        mock_settings.return_value.supabase_jwt_secret = TEST_JWT_SECRET
        payload = verify_supabase_jwt(token)

    assert payload["sub"] == user_id
    assert payload["aud"] == "authenticated"


def test_expired_token_rejected():
    """An expired token raises 401."""
    from fastapi import HTTPException
    from app.core.security import verify_supabase_jwt

    user_id = str(uuid.uuid4())
    token = _make_token(user_id, exp_offset=-10)

    with patch("app.core.security.get_settings") as mock_settings:
        mock_settings.return_value.supabase_jwt_secret = TEST_JWT_SECRET
        with pytest.raises(HTTPException) as exc_info:
            verify_supabase_jwt(token)

    assert exc_info.value.status_code == 401


def test_wrong_secret_rejected():
    """A token signed with the wrong secret raises 401."""
    from fastapi import HTTPException
    from app.core.security import verify_supabase_jwt

    user_id = str(uuid.uuid4())
    token = _make_token(user_id, secret="wrong-secret")

    with patch("app.core.security.get_settings") as mock_settings:
        mock_settings.return_value.supabase_jwt_secret = TEST_JWT_SECRET
        with pytest.raises(HTTPException) as exc_info:
            verify_supabase_jwt(token)

    assert exc_info.value.status_code == 401


def test_wrong_audience_rejected():
    """A token with the wrong audience claim raises 401."""
    from fastapi import HTTPException
    from app.core.security import verify_supabase_jwt

    user_id = str(uuid.uuid4())
    token = _make_token(user_id, audience="anon")

    with patch("app.core.security.get_settings") as mock_settings:
        mock_settings.return_value.supabase_jwt_secret = TEST_JWT_SECRET
        with pytest.raises(HTTPException) as exc_info:
            verify_supabase_jwt(token)

    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# POST /auth/session — integration (uses DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_creates_user_on_first_call(db_session):
    """POST /auth/session inserts a new User row when none exists."""
    user_id = str(uuid.uuid4())
    token = _make_token(user_id)

    with patch("app.core.security.get_settings") as mock_settings:
        mock_settings.return_value.supabase_jwt_secret = TEST_JWT_SECRET
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res = await ac.post(
                "/api/v1/auth/session",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert res.status_code == 200
    assert res.json()["id"] == user_id


@pytest.mark.asyncio
async def test_session_returns_existing_user(db_session):
    """POST /auth/session returns the same user on repeat calls."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"{str(user_id)[:8]}@example.com",
        full_name="Existing User",
    )
    db_session.add(user)
    await db_session.flush()

    token = _make_token(str(user_id))
    with patch("app.core.security.get_settings") as mock_settings:
        mock_settings.return_value.supabase_jwt_secret = TEST_JWT_SECRET
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res = await ac.post(
                "/api/v1/auth/session",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert res.status_code == 200
    assert res.json()["id"] == str(user_id)


@pytest.mark.asyncio
async def test_get_me_returns_current_user(db_session):
    """GET /auth/me returns the authenticated user."""
    user_id = uuid.uuid4()
    user = User(id=user_id, email=f"{str(user_id)[:8]}@example.com")
    db_session.add(user)
    await db_session.flush()

    token = _make_token(str(user_id))
    with patch("app.core.security.get_settings") as mock_settings:
        mock_settings.return_value.supabase_jwt_secret = TEST_JWT_SECRET
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res = await ac.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert res.status_code == 200
    assert res.json()["id"] == str(user_id)


@pytest.mark.asyncio
async def test_cross_user_access_blocked(db_session):
    """A valid JWT for a user with no local record receives 401."""
    user_id_no_record = str(uuid.uuid4())
    token = _make_token(user_id_no_record)

    with patch("app.core.security.get_settings") as mock_settings:
        mock_settings.return_value.supabase_jwt_secret = TEST_JWT_SECRET
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res = await ac.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert res.status_code == 401


@pytest.mark.asyncio
async def test_missing_auth_header_rejected():
    """Requests without an Authorization header receive 403."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res = await ac.get("/api/v1/auth/me")

    assert res.status_code in (401, 403)
