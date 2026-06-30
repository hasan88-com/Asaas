"""
Asaas (اثاثہ) — Chat Schemas

Pydantic schemas for the agent chat (TECH.md §7.2, §4).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Message to the agent")
    conversation_id: Optional[UUID] = Field(
        None, description="Thread to append to; a new one is created when omitted"
    )


class ConversationResponse(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatMessageResponse(BaseModel):
    id: UUID
    user_id: UUID
    role: str = Field(..., description="user / assistant")
    content: str
    tool_calls: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True
        # For Pydantic v2:
        # model_config = ConfigDict(from_attributes=True)
