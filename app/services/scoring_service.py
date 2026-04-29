"""
app/services/scoring_service.py — Weighted credit score engine and
rule-based explanation generator.

Score range: 300–850 (mirrors credit bureau convention).
Risk levels: trusted (≥700) | moderate (≥500) | risky (<500)

Weights (must sum to 1.0):
  income_level      30%
  income_stability  25%
  savings_rate      20%
  activity          15%
  burden            10%  (inverted: lower burden → higher contribution)
"""

from app.services.signal_service import SignalResult
from app.core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------
WEIGHTS: dict[str, float] = {
    "income_level":     0.30,
    "income_stability": 0.25,
    "savings_rate":     0.20,
    "activity":         0.15,
    "burden":           0.10,   # inverted below
}

# Score band boundaries
_SCORE_MIN = 300
_SCORE_MAX = 850
_SCORE_RANGE = _SCORE_MAX - _SCORE_MIN   # 550

# ---------------------------------------------------------------------------
# Explanation rules
# Each rule is (condition_fn, insight_string)
# ---------------------------------------------------------------------------
_RULES: list[tuple] = [
    # Income
    (lambda s: s.income_level >= 80,
     "Strong income level — well above average for this scoring model."),
    (lambda s: 40 <= s.income_level < 80,
     "Moderate income level detected."),
    (lambda s: s.income_level < 40,
     "Low income level — consider diversifying income sources."),

    # Stability
    (lambda s: s.income_stability >= 75,
     "Income is highly stable across months — a strong positive signal."),
    (lambda s: 40 <= s.income_stability < 75,
     "Income shows some variability month-to-month."),
    (lambda s: s.income_stability < 40,
     "High income volatility detected — irregular earnings reduce score."),

    # Savings
    (lambda s: s.savings_rate >= 30,
     "Excellent savings rate — you retain more than 30% of your income."),
    (lambda s: 10 <= s.savings_rate < 30,
     "Positive savings rate — you are spending less than you earn."),
    (lambda s: 0 <= s.savings_rate < 10,
     "Savings rate is low — consider reducing discretionary expenses."),
    (lambda s: s.savings_rate < 0,
     "Spending exceeds income — this is a significant risk flag."),

    # Burden
    (lambda s: s.burden <= 40,
     "Low expense burden — expenses are well within income."),
    (lambda s: 40 < s.burden <= 70,
     "Moderate expense burden — manageable but watch for increases."),
    (lambda s: s.burden > 70,
     "High expense burden — expenses consume most of your income."),

    # Activity
    (lambda s: s.activity >= 60,
     "Active transaction history provides a reliable data foundation."),
    (lambda s: s.activity < 20,
     "Low transaction activity — limited history may reduce score accuracy."),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_score(signals: SignalResult) -> int:
    """
    Compute a credit score (300–850) from a SignalResult.

    The burden signal is inverted (lower burden = higher contribution)
    before applying weights.
    """
    if signals.data_quality == "insufficient":
        # Not enough data to score — return floor
        return _SCORE_MIN

    # Clamp all signals to [0, 100]
    def _c(v: float) -> float:
        return max(0.0, min(100.0, v))

    # Invert burden: 0 burden → 100 contribution, 100 burden → 0 contribution
    burden_inverted = max(0.0, 100.0 - _c(signals.burden))

    raw = (
        WEIGHTS["income_level"]     * _c(signals.income_level)
        + WEIGHTS["income_stability"] * _c(signals.income_stability)
        + WEIGHTS["savings_rate"]     * _c(signals.savings_rate)
        + WEIGHTS["activity"]         * _c(signals.activity)
        + WEIGHTS["burden"]           * burden_inverted
    )  # raw is 0–100

    score = int(_SCORE_MIN + (raw / 100.0) * _SCORE_RANGE)
    score = max(_SCORE_MIN, min(_SCORE_MAX, score))

    logger.info(f"scoring_service: raw={raw:.2f} → score={score}")
    return score


def get_risk_level(score: int) -> str:
    """Map a score to a risk level string."""
    if score >= 700:
        return "trusted"
    if score >= 500:
        return "moderate"
    return "risky"


def generate_insights(signals: SignalResult, score: int) -> list[str]:
    """
    Apply rule-based explanation rules and return a list of insight strings.
    Always returns at least one insight.
    """
    if signals.data_quality == "insufficient":
        return [
            "Insufficient transaction data to generate a reliable score. "
            "Upload more statements to improve accuracy."
        ]

    insights: list[str] = []
    for condition, message in _RULES:
        try:
            if condition(signals):
                insights.append(message)
        except Exception:
            pass

    # Score-level summary always first
    risk = get_risk_level(score)
    summary = {
        "trusted":  f"Overall credit score of {score} — classified as Trusted.",
        "moderate": f"Overall credit score of {score} — classified as Moderate risk.",
        "risky":    f"Overall credit score of {score} — classified as High risk.",
    }[risk]
    insights.insert(0, summary)

    return insights[:6]   # cap at 6 insights for readability


def build_transactions_summary(rows: list[dict]) -> dict:
    """
    Build a summary dict from parsed transaction rows.
    Handles both string and enum type values.
    """
    from app.services.signal_service import _to_type_string

    total_income   = 0.0
    total_expenses = 0.0
    category_totals: dict[str, float] = {}

    for row in rows:
        amount   = float(row.get("normalized_usd") or 0.0)
        tx_type  = _to_type_string(row.get("type", "unknown"))
        category = str(row.get("category") or "other")

        if tx_type == "income":
            total_income += amount
        elif tx_type == "expense":
            total_expenses += amount

        category_totals[category] = category_totals.get(category, 0.0) + amount

    top_categories = dict(
        sorted(category_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    )

    return {
        "total_income":      round(total_income, 2),
        "total_expenses":    round(total_expenses, 2),
        "net":               round(total_income - total_expenses, 2),
        "transaction_count": len(rows),
        "top_categories":    {k: round(v, 2) for k, v in top_categories.items()},
    }
