"""
Asaas (اثاثہ) — Auth API Router

Supabase handles registration, login, and token refresh on the client side.
This router provides:
  GET  /auth/me      — returns the current user from a verified Supabase JWT
  POST /auth/session — verifies JWT and upserts the local user record (call after registration)
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import bearer_scheme, get_current_user, verify_supabase_jwt
from app.models.user import User
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return current_user


@router.post("/session", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def establish_session(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify a Supabase JWT and upsert the local user record.
    Call this once after registration (or on first login) so the backend
    has a row in the `users` table matching the Supabase auth.users.id.
    Returns the user — 200 on existing user, 200 on first creation.
    """
    payload = verify_supabase_jwt(credentials.credentials)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject claim.",
        )

    user_id = UUID(sub)
    email = payload.get("email") or payload.get("user_metadata", {}).get("email", "")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        full_name = payload.get("user_metadata", {}).get("full_name")
        user = User(id=user_id, email=email, full_name=full_name)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif user.email != email and email:
        # Keep email in sync with Supabase
        user.email = email
        await db.commit()
        await db.refresh(user)

    return user
