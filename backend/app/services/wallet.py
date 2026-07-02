"""
Asaas (اثاثہ) — Wallet Service

Virtual PKR cash balance per user. All balance mutations go through the
atomic conditional-UPDATE helpers here so a debit can never race past the
`balance >= amount` guard, even through the PgBouncer transaction pooler.
Helpers never commit — the caller's session (FastAPI `get_db`) commits, so a
cash movement and its companion holding mutation land in one transaction.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cash_account import CashAccount
from app.models.cash_transaction import CashTransaction

TWO_DP = Decimal("0.01")


class InsufficientFundsError(Exception):
    """Debit rejected: the account balance is below the requested amount."""

    def __init__(self, balance: Decimal):
        self.balance = balance
        super().__init__(f"Insufficient funds: balance is {balance}")


async def get_or_create_account(user_id: uuid.UUID, db: AsyncSession) -> CashAccount:
    """Fetch the user's cash account, creating it at ₨0 on first touch.
    Race-safe via INSERT ... ON CONFLICT DO NOTHING."""
    stmt = (
        pg_insert(CashAccount)
        .values(user_id=user_id)
        .on_conflict_do_nothing(index_elements=["user_id"])
    )
    await db.execute(stmt)
    result = await db.execute(select(CashAccount).where(CashAccount.user_id == user_id))
    return result.scalar_one()


def _ledger_row(
    account: CashAccount,
    user_id: uuid.UUID,
    txn_type: str,
    amount: Decimal,
    balance_after: Decimal,
    *,
    holding_id: Optional[uuid.UUID] = None,
    symbol: Optional[str] = None,
    quantity: Optional[Decimal] = None,
    price: Optional[Decimal] = None,
    note: Optional[str] = None,
) -> CashTransaction:
    return CashTransaction(
        account_id=account.id,
        user_id=user_id,
        type=txn_type,
        amount=amount,
        balance_after=balance_after,
        holding_id=holding_id,
        symbol=symbol,
        quantity=quantity,
        price=price,
        note=note,
    )


async def credit_cash(
    db: AsyncSession,
    user_id: uuid.UUID,
    amount: Decimal,
    *,
    txn_type: str,
    holding_id: Optional[uuid.UUID] = None,
    symbol: Optional[str] = None,
    quantity: Optional[Decimal] = None,
    price: Optional[Decimal] = None,
    note: Optional[str] = None,
) -> CashTransaction:
    """Add `amount` to the user's balance and append a ledger row. No commit."""
    amount = amount.quantize(TWO_DP)
    account = await get_or_create_account(user_id, db)
    result = await db.execute(
        update(CashAccount)
        .where(CashAccount.id == account.id)
        .values(balance=CashAccount.balance + amount)
        .returning(CashAccount.balance)
    )
    balance_after = result.scalar_one()
    txn = _ledger_row(
        account, user_id, txn_type, amount, balance_after,
        holding_id=holding_id, symbol=symbol, quantity=quantity, price=price, note=note,
    )
    db.add(txn)
    await db.flush()
    return txn


async def debit_cash(
    db: AsyncSession,
    user_id: uuid.UUID,
    amount: Decimal,
    *,
    txn_type: str,
    holding_id: Optional[uuid.UUID] = None,
    symbol: Optional[str] = None,
    quantity: Optional[Decimal] = None,
    price: Optional[Decimal] = None,
    note: Optional[str] = None,
) -> CashTransaction:
    """Subtract `amount` from the user's balance if it covers the amount,
    else raise InsufficientFundsError(current_balance). No commit."""
    amount = amount.quantize(TWO_DP)
    account = await get_or_create_account(user_id, db)
    result = await db.execute(
        update(CashAccount)
        .where(CashAccount.id == account.id, CashAccount.balance >= amount)
        .values(balance=CashAccount.balance - amount)
        .returning(CashAccount.balance)
    )
    balance_after = result.scalar_one_or_none()
    if balance_after is None:
        fresh = await db.execute(
            select(CashAccount.balance).where(CashAccount.id == account.id)
        )
        raise InsufficientFundsError(fresh.scalar_one())
    txn = _ledger_row(
        account, user_id, txn_type, amount, balance_after,
        holding_id=holding_id, symbol=symbol, quantity=quantity, price=price, note=note,
    )
    db.add(txn)
    await db.flush()
    return txn
