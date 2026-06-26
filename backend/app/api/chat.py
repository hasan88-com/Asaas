"""
Asaas (اثاثہ) — Chat API Router

POST /chat   — sends a message; returns SSE stream (event: content/tool/done)
GET  /chat/history — returns ordered chat history for the current user
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator, List

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.orchestrator import AgentOrchestrator
from app.core.db import async_session_factory, get_db
from app.core.security import get_current_user
from app.models.chat_message import ChatMessage
from app.models.user import User
from app.schemas.chat import ChatMessageResponse, ChatRequest

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger("asaas.api.chat")


def _sse(payload: dict) -> str:
    """Encode a single SSE data frame. Event type is inside the JSON."""
    return f"data: {json.dumps(payload)}\n\n"


async def _agent_sse_generator(
    user_id, user_message: str
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
                response_text, agent_role = await orchestrator.process_message(user_id, user_message)
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

        # Save assistant reply to database
        try:
            async with async_session_factory() as db:
                assistant_msg = ChatMessage(
                    user_id=user_id,
                    role="assistant",
                    content=response_text,
                    tool_calls={"agent_role": agent_role},
                )
                db.add(assistant_msg)
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
    Send a message to the agent. Returns SSE stream.
    Saves user message before streaming; assistant reply is saved by the generator.
    """
    user_msg = ChatMessage(
        user_id=current_user.id,
        role="user",
        content=payload.message,
    )
    db.add(user_msg)
    await db.commit()

    return StreamingResponse(
        _agent_sse_generator(current_user.id, payload.message),
        media_type="text/event-stream",
    )


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
