"""
Conversation memory helper.

Turns the recent-message list (loaded by the orchestrator from `chat_messages`)
into a compact, labeled block that each role can interpolate into its LLM
`user_message`. The block is omitted entirely when there is no history, so
roles can append it unconditionally without leaving empty sections in prompts.

History contains user-authored text (already sent to the LLM on prior turns via
`user_message`), so injecting prior turns does not introduce a new class of PII
exposure. Tool-call payloads / absolute amounts are never carried here — only
`role` + `content`.
"""

from __future__ import annotations

from typing import Any, Dict, List

# How the assistant speaker is labelled inside the rendered history block.
_ASSISTANT_LABEL = "Asaas"
_USER_LABEL = "User"


def format_history(history: List[Dict[str, Any]]) -> str:
    """
    Render recent conversation turns as a labeled block.

    Args:
        history: list of {"role": "user"|"assistant", "content": str} dicts,
                 oldest first. Tolerates missing/empty entries.

    Returns:
        A formatted string suitable for inclusion in an LLM user_message:

            Recent conversation:
            User: what about gold?
            Asaas: Gold currently sits at ~8% of your mix...

        Returns "" when history is empty or contains no usable turns, so the
        caller can append the result without producing an empty section.
    """
    if not history:
        return ""

    lines: List[str] = []
    for turn in history:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role", "")).strip().lower()
        content = str(turn.get("content", "")).strip()
        if not content:
            continue
        if role == "assistant":
            label = _ASSISTANT_LABEL
        elif role == "user":
            label = _USER_LABEL
        else:
            # Unknown roles (future-proofing) — still rendered, labeled as-is.
            label = role.capitalize() or _USER_LABEL
        lines.append(f"{label}: {content}")

    if not lines:
        return ""

    return "Recent conversation:\n" + "\n".join(lines)
