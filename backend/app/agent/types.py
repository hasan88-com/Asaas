"""Shared type definitions for the LangGraph agent state."""

from __future__ import annotations

from typing import Any, Dict, Optional
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """Immutable-friendly state passed between LangGraph nodes."""

    user_id: str                    # str(UUID) — for tool calls, never to LLM
    conversation_id: Optional[str]  # str(UUID) or None — scopes loaded history to one thread
    user_message: str               # raw user input
    intent: str                     # filled by classify node
    context: Dict[str, Any]         # PII-free abstracted context for LLM prompts
    portfolio_id: Optional[str]     # str(UUID) or None — for tool calls, never to LLM
    response: str                   # final response text
    history: list                   # [{"role","content"}] last N turns — never tool_calls/PII
