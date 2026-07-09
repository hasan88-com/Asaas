"""
Target adapter interface.

A target is "any advice API" per PS1's framing — the engine doesn't assume
Asaas. Implement `send` (required) and, optionally, `get_state`/`new_session`
for adapters that can expose ground-truth side-channel state (e.g. did a
database row actually change) for deeper checks than transcript text alone.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TargetAdapter(Protocol):
    """Minimal contract every adapter must satisfy."""

    async def new_session(self, persona_name: str, setup: dict) -> str:
        """Provision (or select) a conversation/user context for a persona.

        Returns an opaque session id the adapter will recognise on subsequent
        `send` calls. `setup` carries scenario-declared fixture hints (e.g.
        {"has_confirmed_portfolio": true}) that adapters may use however they
        need to reach that starting state — a generic HTTP adapter can ignore it.
        """
        ...

    async def send(self, session_id: str, message: str) -> str:
        """Send one user message, return the assistant's final text response."""
        ...

    async def get_state(self, session_id: str) -> dict:
        """Optional ground-truth snapshot (e.g. portfolio status) for deep checks.

        Default/no-op adapters should return {} — detectors that need this must
        degrade to a transcript-only check when it's empty, not crash.
        """
        return {}
