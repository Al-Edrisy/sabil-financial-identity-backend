"""
app/api/v1/routes/wallet.py — Wallet and transaction management endpoints.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.dependencies.db import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rate_limit import rate_limiter
from app.models.user import User
from app.services.transaction_service import TransactionService
from app.services.wallet_service import WalletService
from app.schemas.wallet import (
    WalletResponse,
    TransactionResponse,
    WalletTopUpRequest,
    WalletTransferRequest,
    WalletWithdrawRequest,
)

router = APIRouter()


@router.get(
    "/balance",
    response_model=WalletResponse,
    summary="Get Wallet Balance",
)
async def get_balance(
    current_user: User       = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Returns the current user's wallet balance and currency."""
    service = WalletService(db)
    return await service.get_wallet(current_user.id)


@router.post(
    "/transfer",
    response_model=TransactionResponse,
    summary="Transfer Funds to Another User",
    dependencies=[Depends(rate_limiter(requests_per_minute=10))],
)
async def transfer(
    request:      WalletTransferRequest,
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Transfers funds from the current user's wallet to another user by their ID."""
    service = TransactionService(db)
    return await service.transfer_funds_by_id(
        from_user_id=current_user.id,
        to_user_id=request.to_user_id,
        amount=request.amount,
        description=request.description,
    )


@router.post(
    "/withdraw",
    response_model=TransactionResponse,
    summary="Withdraw Funds",
    dependencies=[Depends(rate_limiter(requests_per_minute=5))],
)
async def withdraw(
    request:      WalletWithdrawRequest,
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Executes a withdrawal from the user's wallet."""
    service = TransactionService(db)
    return await service.withdraw_funds(
        user_id=current_user.id,
        amount=request.amount,
        description=request.description or "Wallet Withdrawal",
    )


@router.get(
    "/history",
    response_model=List[TransactionResponse],
    summary="Get Transaction History",
)
async def get_history(
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Returns the full transaction history for the authenticated user."""
    service = TransactionService(db)
    return await service.get_history(current_user.id)


@router.get(
    "/transactions/{transaction_id}",
    response_model=TransactionResponse,
    summary="Get Transaction Details",
)
async def get_transaction(
    transaction_id: int,
    current_user:   User         = Depends(get_current_user),
    db:             AsyncSession = Depends(get_db),
):
    """Fetches details for a specific transaction by its ID."""
    service = TransactionService(db)
    return await service.get_transaction_by_id(current_user.id, transaction_id)


@router.post(
    "/topup",
    response_model=TransactionResponse,
    summary="Top Up Wallet (Simulated)",
    dependencies=[Depends(rate_limiter(requests_per_minute=5))],
)
async def topup(
    request:      WalletTopUpRequest,
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Simulates a wallet top-up. Replace with real payment gateway in production."""
    service = TransactionService(db)
    return await service.top_up(current_user.id, request.amount)
