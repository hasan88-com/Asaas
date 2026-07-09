"""
Direct-to-orchestrator adapter for Asaas.

Bypasses HTTP/SSE and drives `app.agent.orchestrator.AgentOrchestrator`
directly against a caller-supplied AsyncSession — the same pattern
`backend/tests/test_agent.py` uses for `test_no_auto_action_on_confirm_message`.
This is what lets the engine assert ground truth (did the portfolio row
actually change?) rather than just eyeballing the reply text, and it runs
without spinning up uvicorn.

Requires the backend's dependencies to be importable (run this from within
`backend/`'s virtualenv, or with `backend/` on PYTHONPATH) and a reachable
Postgres — set TEST_DATABASE_URL as the existing test suite does.

App imports are deferred into __init__ so the rest of the engine (scenario
loading, detectors, scoring, reporting, the HTTP adapter) stays usable in a
bare environment with none of the backend's dependencies installed.
"""

from __future__ import annotations

import uuid
from typing import Any


class AsaasDirectAdapter:
    """Implements engine.targets.base.TargetAdapter against a live DB session."""

    def __init__(self, db_session: Any):
        try:
            from app.agent.orchestrator import AgentOrchestrator  # noqa: F401
            from app.models.holding import Holding  # noqa: F401
            from app.models.instrument import Instrument  # noqa: F401
            from app.models.portfolio import Portfolio  # noqa: F401
            from app.models.risk_profile import RiskProfile  # noqa: F401
            from app.models.user import User  # noqa: F401
        except ImportError as exc:  # pragma: no cover - environment guard
            raise RuntimeError(
                "AsaasDirectAdapter requires the backend app package on "
                "PYTHONPATH (run from backend/'s virtualenv). Original error: "
                f"{exc}"
            ) from exc

        self._db = db_session
        self._AgentOrchestrator = AgentOrchestrator
        self._Holding = Holding
        self._Instrument = Instrument
        self._Portfolio = Portfolio
        self._RiskProfile = RiskProfile
        self._User = User
        # session_id -> user_id, so send()/get_state() can resolve back to the
        # fixture this adapter provisioned in new_session().
        self._sessions: dict[str, uuid.UUID] = {}

    async def new_session(self, persona_name: str, setup: dict) -> str:
        user = self._User(
            id=uuid.uuid4(),
            email=f"redteam-{uuid.uuid4().hex[:10]}@asaas.test",
            full_name=f"Redteam {persona_name}",
        )
        self._db.add(user)
        await self._db.flush()

        if setup.get("has_profile") or setup.get("has_confirmed_portfolio") or setup.get(
            "has_draft_portfolio"
        ):
            profile = self._RiskProfile(
                user_id=user.id,
                risk_tolerance=setup.get("risk_tolerance", "moderate"),
                horizon=setup.get("horizon", "medium"),
                investor_mode=setup.get("investor_mode", "long_term"),
                goal=setup.get("goal", "growth"),
            )
            self._db.add(profile)

        if setup.get("has_confirmed_portfolio"):
            portfolio = self._Portfolio(
                user_id=user.id, name="Redteam Portfolio", status="confirmed"
            )
            self._db.add(portfolio)
        elif setup.get("has_draft_portfolio"):
            portfolio = self._Portfolio(
                user_id=user.id, name="Redteam Draft", status="draft"
            )
            self._db.add(portfolio)

        await self._db.commit()

        session_id = str(user.id)
        self._sessions[session_id] = user.id
        return session_id

    async def send(self, session_id: str, message: str) -> str:
        user_id = self._sessions.get(session_id) or uuid.UUID(session_id)
        orchestrator = self._AgentOrchestrator(self._db)
        response_text, _agent_role = await orchestrator.process_message(user_id, message)
        return response_text

    async def get_state(self, session_id: str) -> dict:
        from sqlalchemy import select

        from app.models.chat_message import ChatMessage

        user_id = self._sessions.get(session_id) or uuid.UUID(session_id)
        res = await self._db.execute(
            select(self._Portfolio)
            .where(self._Portfolio.user_id == user_id)
            .order_by(self._Portfolio.created_at.desc())
        )
        portfolios = res.scalars().all()

        # Audit-trail ground truth: what did the last assistant turn actually
        # persist in tool_calls? (Used by the broken_audit_trail detector —
        # today this is only ever {"agent_role": ...}, see chat.py.)
        msg_res = await self._db.execute(
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id, ChatMessage.role == "assistant")
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        )
        last_msg = msg_res.scalar_one_or_none()
        tool_calls_keys = (
            sorted(last_msg.tool_calls.keys()) if last_msg and last_msg.tool_calls else []
        )

        return {
            "portfolio_count": len(portfolios),
            "portfolio_statuses": [p.status for p in portfolios],
            "confirmed_count": sum(1 for p in portfolios if p.status == "confirmed"),
            "draft_count": sum(1 for p in portfolios if p.status == "draft"),
            "last_tool_calls_keys": tool_calls_keys,
        }
