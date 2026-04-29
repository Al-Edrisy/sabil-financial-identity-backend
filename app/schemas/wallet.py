"""
app/schemas/wallet.py — Pydantic schemas for wallet and transaction endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Enums (mirrors models — avoids importing SQLAlchemy enums into schemas)
# ---------------------------------------------------------------------------
class TransactionTypeSchema(str, Enum):
    transfer = "transfer"
    topup    = "topup"
    withdraw = "withdraw"


class TransactionStatusSchema(str, Enum):
    pending   = "pending"
    completed = "completed"
    failed    = "failed"


# ---------------------------------------------------------------------------
# Wallet
# ---------------------------------------------------------------------------
class WalletResponse(BaseModel):
    id:         int
    user_id:    int
    balance:    float
    currency:   str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Transaction
# ---------------------------------------------------------------------------
class TransactionResponse(BaseModel):
    id:               int
    sender_id:        Optional[int]   = None
    receiver_id:      Optional[int]   = None
    amount:           float
    currency:         str
    fx_rate:          float
    converted_amount: float
    target_currency:  str
    type:             TransactionTypeSchema
    status:           TransactionStatusSchema
    reference:        Optional[str]   = None
    description:      Optional[str]   = None
    created_at:       datetime
    updated_at:       Optional[datetime] = None

    class Config:
        from_attributes = True


class TransactionListResponse(BaseModel):
    total:     int
    page:      int
    page_size: int
    items:     List[TransactionResponse]


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class WalletTransferRequest(BaseModel):
    to_user_id:  int
    amount:      float = Field(..., gt=0, description="Amount to transfer (must be positive)")
    description: Optional[str] = None


class WalletTopUpRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount to add to wallet")


class WalletWithdrawRequest(BaseModel):
    amount:      float = Field(..., gt=0, description="Amount to withdraw")
    description: Optional[str] = "Wallet Withdrawal"
