"""
Asaas (اثاثہ) — Chat API Router

POST /chat   — sends a message; returns SSE stream (event: content/tool/done)
GET  /chat/history — returns ordered chat history for the current user
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.orchestrator import AgentOrchestrator
from app.core.db import async_session_factory, get_db
from app.core.security import get_current_user
from app.models.chat_message import ChatMessage
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.chat import ChatMessageResponse, ChatRequest, ConversationResponse

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger("asaas.api.chat")


def _sse(payload: dict) -> str:
    """Encode a single SSE data frame. Event type is inside the JSON."""
    return f"data: {json.dumps(payload)}\n\n"


async def _agent_sse_generator(
    user_id, user_message: str, conversation_id=None
) -> AsyncGenerator[str, None]:
    """
    Run the LangGraph orchestrator and stream the response as SSE.
    Creates its own DB session so it stays alive after the route handler returns.
    Saves the assistant reply to chat_messages after streaming completes.
    """
    try:
        yield _sse({"event": "tool", "tool": "orchestrator", "status": "running"})

        agent_role = "chat"
        response_text = ""
        try:
            async with async_session_factory() as db:
                orchestrator = AgentOrchestrator(db)
                response_text, agent_role = await orchestrator.process_message(
                    user_id, user_message, conversation_id
                )
        except Exception as exc:
            logger.error("Orchestrator error for user %s: %s", user_id, exc)
            response_text = "I encountered an error. Please try again in a moment."

        yield _sse({"event": "tool", "tool": "orchestrator", "status": "done"})

        # Stream response word by word
        words = response_text.split()
        for word in words:
            yield _sse({"event": "content", "delta": word + " "})
            await asyncio.sleep(0.03)

        yield _sse({"event": "done", "agentRole": agent_role})

        # Save assistant reply to database (under the conversation thread)
        try:
            async with async_session_factory() as db:
                assistant_msg = ChatMessage(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    role="assistant",
                    content=response_text,
                    tool_calls={"agent_role": agent_role},
                )
                db.add(assistant_msg)
                if conversation_id is not None:
                    conv = await db.get(Conversation, conversation_id)
                    if conv is not None:
                        conv.updated_at = datetime.now(timezone.utc)
                await db.commit()
        except Exception as exc:
            logger.error("Failed to save assistant reply for user %s: %s", user_id, exc)

    except asyncio.CancelledError:
        # Client disconnected — stop cleanly without sending an error event
        logger.info("SSE stream cancelled for user %s (client disconnected)", user_id)
        raise
    except Exception as exc:
        logger.error("Unhandled SSE generator error for user %s: %s", user_id, exc, exc_info=True)
        try:
            yield _sse({"event": "error", "message": "An unexpected error occurred. Please try again."})
            yield _sse({"event": "done", "agentRole": "chat"})
        except Exception:
            pass  # connection already broken


@router.post("")
async def send_chat_message(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message to Raabta AI. Returns an SSE stream.
    Resolves/creates the conversation thread, saves the user message, then the
    generator streams + saves the assistant reply under the same thread.
    """
    # Resolve the conversation: use the given one (must be owned) or open a new one.
    conv: Conversation | None = None
    if payload.conversation_id is not None:
        conv = await db.get(Conversation, payload.conversation_id)
        if conv is None or conv.user_id != current_user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    if conv is None:
        conv = Conversation(user_id=current_user.id, title=_title_from(payload.message))
        db.add(conv)
        await db.flush()
    elif conv.title == "New chat":
        # First real message in a freshly-created thread → auto-title it.
        conv.title = _title_from(payload.message)

    user_msg = ChatMessage(
        user_id=current_user.id,
        conversation_id=conv.id,
        role="user",
        content=payload.message,
    )
    db.add(user_msg)
    await db.commit()

    return StreamingResponse(
        _agent_sse_generator(current_user.id, payload.message, conv.id),
        media_type="text/event-stream",
        headers={"X-Conversation-Id": str(conv.id)},
    )


def _title_from(message: str) -> str:
    """Short topic title from the first user message (no extra LLM call)."""
    t = " ".join(message.strip().split())
    return (t[:48] + "…") if len(t) > 48 else (t or "New chat")


@router.get("/conversations", response_model=List[ConversationResponse])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The current user's conversation threads, most-recently-updated first."""
    res = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
    )
    return list(res.scalars().all())


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Open a new (empty) conversation thread."""
    conv = Conversation(user_id=current_user.id, title="New chat")
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


@router.get("/conversations/{conversation_id}", response_model=List[ChatMessageResponse])
async def get_conversation_messages(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ordered messages for one of the current user's conversations."""
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    res = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return list(res.scalars().all())


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation and its messages (cascade)."""
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    await db.delete(conv)
    await db.commit()


@router.get("/history", response_model=List[ChatMessageResponse])
async def get_chat_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve ordered conversation history for the current user."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.asc())
    )
    return result.scalars().all()
