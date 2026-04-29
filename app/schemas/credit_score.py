"""
app/schemas/credit_score.py — Request/response schemas for the
credit scoring engine output.
"""

from pydantic import BaseModel, Field, computed_field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class RiskLevel(str, Enum):
    trusted  = "trusted"    # score >= 700
    moderate = "moderate"   # score >= 500
    risky    = "risky"      # score < 500


class DataQuality(str, Enum):
    good         = "good"           # >= MIN_TRANSACTIONS months of data
    low_data     = "low_data"       # some data but below ideal threshold
    insufficient = "insufficient"   # too few transactions to score reliably


# ---------------------------------------------------------------------------
# Signals sub-schema
# ---------------------------------------------------------------------------
class SignalResponse(BaseModel):
    """
    The five normalised signals (0–100) that feed the scoring engine.
    Higher is always better except for `burden` (lower burden = healthier).
    """
    income_level:     Optional[float] = Field(None, ge=0, le=100, description="Total income normalised 0–100")
    income_stability: Optional[float] = Field(None, ge=0, le=100, description="Inverse of income variance 0–100")
    savings_rate:     Optional[float] = Field(None, description="(income - expenses) / income × 100")
    activity:         Optional[float] = Field(None, ge=0, le=100, description="Transaction frequency 0–100")
    burden:           Optional[float] = Field(None, ge=0,          description="Expense ratio % (lower = better)")


# ---------------------------------------------------------------------------
# Transactions summary sub-schema
# ---------------------------------------------------------------------------
class TransactionsSummary(BaseModel):
    total_income:    float
    total_expenses:  float
    net:             float
    transaction_count: int
    top_categories:  Dict[str, float] = Field(
        default_factory=dict,
        description="Category → total amount (top 5)",
    )


# ---------------------------------------------------------------------------
# Main credit score response
# ---------------------------------------------------------------------------
class CreditScoreResponse(BaseModel):
    id:                   int
    user_id:              int
    score:                int    = Field(..., ge=300, le=850)
    risk_level:           RiskLevel
    signals:              SignalResponse
    insights:             List[str]
    transactions_summary: TransactionsSummary
    data_quality:         DataQuality
    transaction_count:    Optional[int]    = None
    upload_id:            Optional[str]    = None
    computed_at:          datetime

    @computed_field
    @property
    def score_band(self) -> str:
        """Human-readable score band label."""
        if self.score >= 750:
            return "Excellent"
        if self.score >= 700:
            return "Good"
        if self.score >= 600:
            return "Fair"
        if self.score >= 500:
            return "Poor"
        return "Very Poor"

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Upload response — wraps score + upload metadata
# ---------------------------------------------------------------------------
class UploadStatementResponse(BaseModel):
    upload_id:          str
    row_count:          int    = Field(..., description="Total transaction rows extracted")
    needs_review_count: int    = Field(..., description="Rows flagged for human review")
    score:              CreditScoreResponse
