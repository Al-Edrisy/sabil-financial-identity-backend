"""
app/services/signal_service.py — Compute financial health signals from a
user's parsed transaction history using pandas.

Five signals, all normalised to 0–100 (higher = healthier),
except `burden` where lower is better:

  income_level      — total income normalised against CREDIT_SCORE_INCOME_CAP
  income_stability  — 100 minus normalised std-dev of monthly income
  savings_rate      — (income - expenses) / income × 100
  activity          — transaction count per month normalised 0–100
  burden            — expenses / income × 100
"""

import dataclasses
from typing import Optional

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_ACTIVITY_CAP = 100.0


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class SignalResult:
    income_level:      float = 0.0
    income_stability:  float = 0.0
    savings_rate:      float = 0.0
    activity:          float = 0.0
    burden:            float = 0.0
    data_quality:      str   = "insufficient"
    total_income:      float = 0.0
    total_expenses:    float = 0.0
    transaction_count: int   = 0
    months_of_data:    int   = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _normalise(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    return _clamp((value / cap) * 100.0)


def _to_type_string(val) -> str:
    """
    Normalise a type value to a plain string "income" | "expense" | "unknown".

    Handles:
      - str:                    "income", "INCOME", "ParsedTransactionType.INCOME"
      - ParsedTransactionType:  ParsedTransactionType.INCOME
      - anything else:          "unknown"
    """
    if val is None:
        return "unknown"
    # Already a plain string
    if isinstance(val, str):
        s = val.lower()
        # Strip enum class prefix if present (e.g. "parsedtransactiontype.income")
        if "." in s:
            s = s.split(".")[-1]
        if s in ("income", "expense", "unknown"):
            return s
        return "unknown"
    # SQLAlchemy enum object — has .value attribute
    if hasattr(val, "value"):
        return _to_type_string(val.value)
    return "unknown"


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------
def compute_signals(rows: list[dict]) -> SignalResult:
    """
    Compute financial signals from a list of parsed transaction dicts.

    Each dict must have at minimum:
        normalized_usd:   float | None
        type:             str | ParsedTransactionType  ("income"/"expense"/"unknown")
        transaction_date: date | None
        created_at:       datetime

    Returns:
        SignalResult dataclass.
    """
    try:
        import pandas as pd
    except ImportError:
        logger.error("pandas not installed — cannot compute signals")
        return SignalResult()

    result = SignalResult()

    if not rows:
        return result

    # ── Build DataFrame ───────────────────────────────────────────────────────
    df = pd.DataFrame(rows)

    for col in ("normalized_usd", "type", "transaction_date", "created_at"):
        if col not in df.columns:
            df[col] = None

    # Normalise type to plain string — handles both str and enum values
    df["type"] = df["type"].apply(_to_type_string)

    # Use transaction_date if available, else fall back to created_at date
    # Build the date column in one pass to avoid dtype mismatch in pandas 3.x
    def _safe_date(row):
        td = row.get("transaction_date")
        if td is not None:
            try:
                return pd.Timestamp(td)
            except Exception:
                pass
        ca = row.get("created_at")
        if ca is not None:
            try:
                return pd.Timestamp(ca)
            except Exception:
                pass
        return pd.NaT

    df["_date"] = pd.to_datetime(
        [_safe_date(r) for r in rows],
        errors="coerce",
        utc=True,          # normalise all to UTC — avoids mixed-tz dtype errors
    )
    df["_month"] = df["_date"].dt.tz_localize(None).dt.to_period("M")

    # Drop rows with no usable amount
    df = df.dropna(subset=["normalized_usd"])
    df["normalized_usd"] = pd.to_numeric(df["normalized_usd"], errors="coerce").fillna(0.0)
    # Drop zero-amount rows — they don't contribute to signals
    df = df[df["normalized_usd"] > 0]

    result.transaction_count = len(df)

    if result.transaction_count == 0:
        return result

    # ── Split income / expense ────────────────────────────────────────────────
    income_df  = df[df["type"] == "income"]
    expense_df = df[df["type"] == "expense"]

    total_income   = float(income_df["normalized_usd"].sum())
    total_expenses = float(expense_df["normalized_usd"].sum())

    result.total_income   = round(total_income, 2)
    result.total_expenses = round(total_expenses, 2)

    # ── Data quality ──────────────────────────────────────────────────────────
    unknown_count = len(df[df["type"] == "unknown"])
    unknown_ratio = unknown_count / len(df)
    months        = df["_month"].nunique()
    result.months_of_data = int(months)

    if unknown_ratio > 0.95 or result.transaction_count < settings.CREDIT_SCORE_MIN_TRANSACTIONS:
        result.data_quality = "insufficient"
        # Still compute basic signals even for insufficient data
        # so the response isn't completely empty
        if total_income > 0:
            result.income_level = _normalise(total_income, settings.CREDIT_SCORE_INCOME_CAP)
        if total_income > 0:
            result.savings_rate = _clamp(
                ((total_income - total_expenses) / total_income) * 100.0,
                lo=-100.0, hi=100.0,
            )
            result.burden = _clamp((total_expenses / total_income) * 100.0, lo=0.0, hi=200.0)
        elif total_expenses > 0:
            result.burden = 100.0
        avg_tx_per_month = result.transaction_count / max(months, 1)
        result.activity = _normalise(avg_tx_per_month, _ACTIVITY_CAP)
        return result
    elif months < 2 or result.transaction_count < 5:
        result.data_quality = "low_data"
    else:
        result.data_quality = "good"

    # ── Signal 1: income_level ────────────────────────────────────────────────
    result.income_level = _normalise(total_income, settings.CREDIT_SCORE_INCOME_CAP)

    # ── Signal 2: income_stability ────────────────────────────────────────────
    if months >= 2 and not income_df.empty:
        monthly_income = income_df.groupby("_month")["normalized_usd"].sum()
        std_dev        = float(monthly_income.std(ddof=0))
        mean_income    = float(monthly_income.mean())
        if mean_income > 0:
            cv = std_dev / mean_income
            result.income_stability = _clamp(100.0 - (cv * 100.0))
        else:
            result.income_stability = 0.0
    else:
        result.income_stability = 50.0 if result.data_quality == "low_data" else 0.0

    # ── Signal 3: savings_rate ────────────────────────────────────────────────
    if total_income > 0:
        result.savings_rate = _clamp(
            ((total_income - total_expenses) / total_income) * 100.0,
            lo=-100.0,
            hi=100.0,
        )
    else:
        result.savings_rate = 0.0

    # ── Signal 4: activity ────────────────────────────────────────────────────
    avg_tx_per_month = result.transaction_count / max(months, 1)
    result.activity  = _normalise(avg_tx_per_month, _ACTIVITY_CAP)

    # ── Signal 5: burden ─────────────────────────────────────────────────────
    if total_income > 0:
        result.burden = _clamp((total_expenses / total_income) * 100.0, lo=0.0, hi=200.0)
    else:
        result.burden = 100.0

    logger.info(
        f"signal_service: income={total_income:.2f} expenses={total_expenses:.2f} "
        f"months={months} quality={result.data_quality} "
        f"signals=(income_level={result.income_level:.1f}, "
        f"stability={result.income_stability:.1f}, "
        f"savings={result.savings_rate:.1f}, "
        f"activity={result.activity:.1f}, "
        f"burden={result.burden:.1f})"
    )

    return result
