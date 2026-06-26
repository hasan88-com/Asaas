"""
Asaas (اثاثہ) — User Schemas
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserResponse(BaseModel):
    """Public user representation."""
    id: UUID
    email: EmailStr
    full_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
