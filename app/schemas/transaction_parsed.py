"""
app/schemas/transaction_parsed.py — Request/response schemas for the
parsed transaction layer (credit scoring pipeline).
"""

from pydantic import BaseModel, Field, computed_field
from typing import Optional, List
from datetime import date, datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Enums (mirrors model enums — keeps SQLAlchemy out of schema layer)
# ---------------------------------------------------------------------------
class ParsedTransactionTypeSchema(str, Enum):
    income  = "income"
    expense = "expense"
    unknown = "unknown"


class ParsedTransactionSourceSchema(str, Enum):
    ocr_upload = "ocr_upload"
    manual     = "manual"


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------
class ParsedTransactionResponse(BaseModel):
    id:               int
    user_id:          int
    upload_id:        str
    raw_line:         Optional[str]                       = None
    description:      str
    amount:           float
    currency:         str
    normalized_amount: Optional[float]                    = None
    type:             ParsedTransactionTypeSchema
    category:         Optional[str]                       = None
    transaction_date: Optional[date]                      = None
    confidence:       float
    needs_review:     bool
    source:           ParsedTransactionSourceSchema
    created_at:       datetime
    updated_at:       Optional[datetime]                  = None

    @computed_field
    @property
    def is_income(self) -> bool:
        return self.type == ParsedTransactionTypeSchema.income

    class Config:
        from_attributes = True


class ParsedTransactionListResponse(BaseModel):
    total:     int
    page:      int
    page_size: int
    items:     List[ParsedTransactionResponse]


# ---------------------------------------------------------------------------
# User correction request
# ---------------------------------------------------------------------------
class ParsedTransactionCorrection(BaseModel):
    """
    Allows a user to correct a misparse. All fields optional —
    only provided fields are updated. Triggers score recomputation.
    """
    description:      Optional[str]                       = Field(None, min_length=1, max_length=255)
    amount:           Optional[float]                     = Field(None, gt=0)
    currency:         Optional[str]                       = Field(None, min_length=3, max_length=3)
    type:             Optional[ParsedTransactionTypeSchema] = None
    category:         Optional[str]                       = None
    transaction_date: Optional[date]                      = None
