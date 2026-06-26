"""
Role: Profiler

Extracts risk profile data from conversational input and persists it via
analyze_profile tool. Returns to orchestrator after one turn (no self-chaining).
"""

from __future__ import annotations

import json
import logging
import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_router import call_llm
from app.agent.memory import format_history
from app.agent.prompts.profiler_prompt import SYSTEM_PROMPT
from app.agent.tools.analyze_profile import analyze_profile
from app.agent.types import AgentState

logger = logging.getLogger("asaas.agent.roles.profiler")


async def run_profiler(
    state: AgentState,
    db: AsyncSession,
) -> AgentState:
    """
    Gather risk profile fields via conversation.
    If LLM response contains a complete JSON block, save the profile.
    Always returns to orchestrator after one LLM call (AGENT_RULES.md §2).
    """
    context_summary = json.dumps(state["context"], default=str)

    parts = [
        f"Current investor context: {context_summary}",
        format_history(state.get("history", [])),
        f"User message: {state['user_message']}",
    ]
    user_content = "\n\n".join(p for p in parts if p)

    try:
        response_text = await call_llm(
            task="light",
            system_prompt=SYSTEM_PROMPT,
            user_message=user_content,
        )
    except Exception as exc:
        logger.error("Profiler LLM call failed: %s", exc)
        state["response"] = (
            "I'm having trouble processing your profile right now. "
            "Please try again in a moment."
        )
        return state

    # Attempt to extract and save a complete JSON profile block
    json_match = re.search(r"```json\s*(\{.*?\})\s*```", response_text, re.DOTALL)
    if json_match:
        try:
            profile_data = json.loads(json_match.group(1))
            user_id = UUID(state["user_id"])
            tool_result = await analyze_profile(
                db=db, user_id=user_id, profile_data=profile_data
            )
            if tool_result.get("saved"):
                state["response"] = (
                    "Your investor profile has been saved.\n\n"
                    f"**Risk tolerance:** {tool_result['risk_tolerance']}  \n"
                    f"**Horizon:** {tool_result['horizon']}  \n"
                    f"**Investor mode:** {tool_result['investor_mode']}  \n"
                    f"**Goal:** {tool_result['goal']}\n\n"
                    "Ready to build your portfolio? Say 'suggest a portfolio' and "
                    "I'll run the optimizer."
                )
                return state
        except (json.JSONDecodeError, KeyError, Exception) as exc:
            logger.warning("Profile JSON parse failed: %s", exc)

    # LLM is still gathering information — return its clarifying questions
    state["response"] = response_text
    return state
