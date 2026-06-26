"""
Tool: analyze_profile

Upserts a risk profile from structured form/chat data.
Returns abstracted profile (no initial_capital).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk_profile import RiskProfile


async def analyze_profile(
    db: AsyncSession,
    user_id: UUID,
    profile_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create or update the user's risk profile from extracted form data.

    profile_data keys:
      risk_tolerance: "conservative" | "moderate" | "aggressive"
      horizon:        "short" | "medium" | "long"
      investor_mode:  "long_term" | "active"
      goal:           "growth" | "income" | "preservation"
      initial_capital: numeric string (stored in DB; NEVER returned to LLM)
      constraints:    dict of exclusions, e.g. {"excluded_sectors": ["tobacco"]}
    """
    valid_tolerances = {"conservative", "moderate", "aggressive"}
    valid_horizons = {"short", "medium", "long"}
    valid_modes = {"long_term", "active"}
    valid_goals = {"growth", "income", "preservation"}

    risk_tolerance = profile_data.get("risk_tolerance", "moderate")
    horizon = profile_data.get("horizon", "medium")
    investor_mode = profile_data.get("investor_mode", "long_term")
    goal = profile_data.get("goal", "growth")
    constraints = profile_data.get("constraints") or {}
    capital_raw = profile_data.get("initial_capital")

    # Validate enums
    if risk_tolerance not in valid_tolerances:
        risk_tolerance = "moderate"
    if horizon not in valid_horizons:
        horizon = "medium"
    if investor_mode not in valid_modes:
        investor_mode = "long_term"
    if goal not in valid_goals:
        goal = "growth"

    # Parse capital if provided (stored as NUMERIC, never returned to LLM)
    initial_capital: Optional[Decimal] = None
    if capital_raw is not None:
        try:
            initial_capital = Decimal(str(capital_raw))
        except Exception:
            initial_capital = None

    # Upsert risk profile
    res = await db.execute(
        select(RiskProfile).where(RiskProfile.user_id == user_id)
    )
    profile = res.scalar_one_or_none()

    # Store sanitised answers for agent personalisation — capital excluded
    safe_answers = {
        k: v for k, v in profile_data.items()
        if k not in ("initial_capital", "monthly_contribution")
    }

    if profile:
        profile.risk_tolerance = risk_tolerance
        profile.horizon = horizon
        profile.investor_mode = investor_mode
        profile.goal = goal
        profile.constraints = constraints
        profile.questionnaire_answers = safe_answers
        if initial_capital is not None:
            profile.initial_capital = initial_capital
    else:
        profile = RiskProfile(
            user_id=user_id,
            risk_tolerance=risk_tolerance,
            horizon=horizon,
            investor_mode=investor_mode,
            goal=goal,
            constraints=constraints,
            questionnaire_answers=safe_answers,
            initial_capital=initial_capital or Decimal("100000"),
        )
        db.add(profile)

    await db.commit()
    await db.refresh(profile)

    # Return abstracted profile — initial_capital deliberately excluded
    return {
        "saved": True,
        "risk_tolerance": profile.risk_tolerance,
        "horizon": profile.horizon,
        "investor_mode": profile.investor_mode,
        "goal": profile.goal,
        "constraints": profile.constraints,
        "risk_score": profile.risk_score,
    }
