"""
Asaas (اثاثہ) — Profile API Router

Endpoints for managing risk profiles and the lean 8-question onboarding questionnaire.
Submitting the questionnaire also auto-generates an IPS and portfolio recommendation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.risk_profile import RiskProfile
from app.models.ips import InvestmentPolicyStatement
from app.models.portfolio_recommendation import PortfolioRecommendation
from app.schemas.profile import ProfileResponse, ProfileUpdate
from app.schemas.questionnaire import (
    QuestionDefinition,
    QuestionnaireRequest,
    QuestionnaireResponse,
)
from app.schemas.ips import IPSResponse, PortfolioRecommendationResponse
from app.services.questionnaire import QUESTIONS, evaluate_questionnaire
from app.services.ips import generate_ips, generate_portfolio_recommendation

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve the current user's risk profile."""
    result = await db.execute(
        select(RiskProfile).where(RiskProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Risk profile not found. Complete the questionnaire at POST /profile/questionnaire.",
        )
    return profile


@router.put("", response_model=ProfileResponse)
async def update_profile(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Directly create or update the current user's risk profile (bypasses questionnaire)."""
    result = await db.execute(
        select(RiskProfile).where(RiskProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        profile = RiskProfile(
            user_id=current_user.id,
            goal=payload.goal or "growth",
            horizon=payload.horizon or "medium",
            risk_tolerance=payload.risk_tolerance or "moderate",
            investor_mode=payload.investor_mode or "long_term",
            initial_capital=payload.initial_capital or Decimal("100000"),
            constraints=payload.constraints or {},
        )
        db.add(profile)
    else:
        for field in (
            "goal", "horizon", "risk_tolerance", "investor_mode",
            "initial_capital", "monthly_contribution", "investment_frequency",
            "risk_willingness", "loss_tolerance", "experience",
            "investment_preferences", "constraints",
            "investor_persona", "risk_score", "agent_remarks", "recommendations",
        ):
            val = getattr(payload, field, None)
            if val is not None:
                setattr(profile, field, val)

    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/questionnaire", response_model=List[QuestionDefinition])
async def get_questionnaire():
    """Return the onboarding question set. No auth required."""
    return QUESTIONS


@router.post("/questionnaire", response_model=QuestionnaireResponse, status_code=status.HTTP_200_OK)
async def submit_questionnaire(
    payload: QuestionnaireRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Evaluate 8-question answers, upsert risk profile, then auto-generate
    an IPS and portfolio recommendation record.
    initial_capital is stored in the DB but never returned to LLMs (RULES.md A1.2).
    """
    # Build answer dict; asset preferences may come from payload directly
    answers: Dict[str, Any] = {}
    for qa in payload.answers:
        answers[qa.question_id] = qa.answer

    # Fold explicit payload fields into answers for the scorer
    answers["initial_capital"] = float(payload.initial_capital)
    answers["monthly_contribution"] = float(payload.monthly_contribution)
    answers["investment_frequency"] = payload.investment_frequency

    # Merge investment_preferences from payload (preferences screen)
    if payload.investment_preferences:
        for key in ("asset_classes", "psx_sectors", "crypto_assets", "fixed_income_products"):
            if key in payload.investment_preferences:
                answers[key] = payload.investment_preferences[key]
        if "shariah" in payload.investment_preferences:
            if payload.investment_preferences["shariah"] and "shariah" not in answers.get("asset_classes", []):
                answers.setdefault("asset_classes", [])
                answers["asset_classes"] = list(answers["asset_classes"]) + ["shariah"]

    evaluated = evaluate_questionnaire(answers)

    result = await db.execute(
        select(RiskProfile).where(RiskProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    # Sanitised raw answers — exclude capital amounts (RULES.md A1.2)
    _safe_answers = {
        k: v for k, v in answers.items()
        if k not in ("initial_capital", "monthly_contribution")
    }

    profile_fields = {
        "goal":                   evaluated["goal"],
        "horizon":                evaluated["horizon"],
        "risk_tolerance":         evaluated["risk_tolerance"],
        "investor_mode":          evaluated["investor_mode"],
        "constraints":            evaluated["constraints"],
        "investor_persona":       evaluated.get("investor_persona"),
        "risk_score":             evaluated.get("risk_score"),
        "investment_preferences": evaluated.get("investment_preferences"),
        "agent_remarks":          evaluated.get("agent_remarks"),
        "recommendations":        evaluated.get("recommendations"),
        "risk_willingness":       answers.get("risk_willingness"),
        "loss_tolerance":         answers.get("loss_tolerance"),
        "experience":             answers.get("experience"),
        "investment_frequency":   payload.investment_frequency,
        "monthly_contribution":   payload.monthly_contribution,
        "questionnaire_answers":  _safe_answers,
    }

    if not profile:
        profile = RiskProfile(
            user_id=current_user.id,
            initial_capital=payload.initial_capital,
            **profile_fields,
        )
        db.add(profile)
    else:
        profile.initial_capital = payload.initial_capital
        for k, v in profile_fields.items():
            setattr(profile, k, v)

    await db.commit()
    await db.refresh(profile)

    # ── Auto-generate IPS ─────────────────────────────────────────────────────
    ips_data = generate_ips(profile)
    ips_result = await db.execute(
        select(InvestmentPolicyStatement).where(
            InvestmentPolicyStatement.risk_profile_id == profile.id
        )
    )
    ips = ips_result.scalar_one_or_none()
    if not ips:
        ips = InvestmentPolicyStatement(
            user_id=current_user.id,
            risk_profile_id=profile.id,
            **ips_data,
        )
        db.add(ips)
    else:
        for k, v in ips_data.items():
            setattr(ips, k, v)

    # ── Auto-generate portfolio recommendation ────────────────────────────────
    rec_data = generate_portfolio_recommendation(profile)
    rec_result = await db.execute(
        select(PortfolioRecommendation).where(
            PortfolioRecommendation.risk_profile_id == profile.id
        )
    )
    rec = rec_result.scalar_one_or_none()
    if not rec:
        rec = PortfolioRecommendation(
            user_id=current_user.id,
            risk_profile_id=profile.id,
            **rec_data,
        )
        db.add(rec)
    else:
        for k, v in rec_data.items():
            setattr(rec, k, v)

    await db.commit()

    return QuestionnaireResponse(
        profile_id=profile.id,
        risk_score=profile.risk_score or 50,
        investor_persona=profile.investor_persona or "Balanced Investor",
        risk_tolerance=profile.risk_tolerance,
        horizon=profile.horizon,
        investor_mode=profile.investor_mode,
        goal=profile.goal,
        constraints=profile.constraints or {},
        investment_preferences=profile.investment_preferences,
        monthly_contribution=profile.monthly_contribution,
        investment_frequency=profile.investment_frequency,
        agent_remarks=profile.agent_remarks,
        recommendations=profile.recommendations,
    )


@router.get("/ips", response_model=IPSResponse)
async def get_ips(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current user's Investment Policy Statement."""
    result = await db.execute(
        select(InvestmentPolicyStatement).where(
            InvestmentPolicyStatement.user_id == current_user.id
        )
    )
    ips = result.scalar_one_or_none()
    if not ips:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="IPS not found. Complete the onboarding questionnaire first.",
        )
    return ips


@router.get("/recommendation", response_model=PortfolioRecommendationResponse)
async def get_recommendation(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current user's portfolio recommendation."""
    result = await db.execute(
        select(PortfolioRecommendation).where(
            PortfolioRecommendation.user_id == current_user.id
        )
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No portfolio recommendation found. Complete the onboarding questionnaire first.",
        )
    return rec
