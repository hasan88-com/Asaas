"""
Role: Chat (Front-Door)

Handles general conversation, platform guidance, and any intent that
doesn't route to a specialist. Returns to orchestrator after one LLM call
(AGENT_RULES.md §6: no self-chaining).
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_router import call_llm
from app.agent.memory import format_history
from app.agent.prompts.chat_prompt import SYSTEM_PROMPT
from app.agent.types import AgentState

logger = logging.getLogger("asaas.agent.roles.chat")


async def run_chat(
    state: AgentState,
    db: AsyncSession,
) -> AgentState:
    """
    Handle general conversation.
    Abstracted context is included so the LLM can reference portfolio status
    without seeing any PII.
    """
    context_summary = json.dumps(state["context"], default=str)

    parts = [
        f"Investor context: {context_summary}",
        format_history(state.get("history", [])),
        f"User: {state['user_message']}",
    ]
    user_content = "\n\n".join(p for p in parts if p)

    try:
        response_text = await call_llm(
            task="chat",
            system_prompt=SYSTEM_PROMPT,
            user_message=user_content,
        )
    except Exception as exc:
        logger.error("Chat LLM call failed: %s", exc)
        response_text = (
            "I'm having trouble connecting right now. Please try again in a moment. "
            "ASAAS provides suggestions only — not financial advice."
        )

    state["response"] = response_text
    return state
