"""
Asaas (اثاثہ) — Auth Schemas

Supabase handles register/login/refresh — no password fields here.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserResponse(BaseModel):
    """Public user representation returned by /auth/me and /auth/session."""
    id: UUID
    email: EmailStr
    full_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
