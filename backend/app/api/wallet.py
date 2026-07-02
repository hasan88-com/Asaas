"""
Asaas (اثاثہ) — Wallet API Router

Virtual PKR cash wallet: manual (paper-money) deposits and withdrawals plus a
read-only transaction ledger. Buys/sells move cash through the same service
helpers from the portfolio router; this router never touches holdings.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import get_current_user
from app.models.cash_transaction import CashTransaction
from app.models.user import User
from app.schemas.wallet import (
    CashMovementRequest,
    TransactionListResponse,
    WalletResponse,
)
from app.services.wallet import (
    InsufficientFundsError,
    credit_cash,
    debit_cash,
    get_or_create_account,
)

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("", response_model=WalletResponse)
async def get_wallet(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Current cash balance; lazily creates the account at ₨0 on first call."""
    return await get_or_create_account(user.id, db)


@router.post("/deposit", response_model=WalletResponse)
async def deposit(
    payload: CashMovementRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Virtual deposit — paper money, no payment gateway."""
    await credit_cash(db, user.id, payload.amount, txn_type="deposit", note=payload.note)
    await db.commit()
    return await get_or_create_account(user.id, db)


@router.post("/withdraw", response_model=WalletResponse)
async def withdraw(
    payload: CashMovementRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await debit_cash(db, user.id, payload.amount, txn_type="withdrawal", note=payload.note)
    except InsufficientFundsError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Insufficient funds: your cash balance is ₨{e.balance:,.2f}.",
        )
    await db.commit()
    return await get_or_create_account(user.id, db)


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    total = (
        await db.execute(
            select(func.count()).select_from(CashTransaction).where(CashTransaction.user_id == user.id)
        )
    ).scalar_one()
    res = await db.execute(
        select(CashTransaction)
        .where(CashTransaction.user_id == user.id)
        .order_by(CashTransaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return {"items": res.scalars().all(), "total": total}
