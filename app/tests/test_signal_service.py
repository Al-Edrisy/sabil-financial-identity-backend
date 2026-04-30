"""
app/tests/test_signal_service.py — Unit tests for signal computation and scoring.
Run with: python3 -m pytest app/tests/test_signal_service.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from datetime import date, datetime
import pytest
from app.services.signal_service import compute_signals, SignalResult
from app.services.scoring_service import compute_score, get_risk_level, generate_insights


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_row(amount: float, tx_type: str, month: int = 1, year: int = 2024) -> dict:
    return {
        "normalized_usd":   amount,
        "type":             tx_type,
        "transaction_date": date(year, month, 15),
        "created_at":       datetime(year, month, 15),
        "category":         "other",
    }


def _income_rows(amounts: list[float], months: list[int] = None) -> list[dict]:
    months = months or list(range(1, len(amounts) + 1))
    return [_make_row(a, "income", m) for a, m in zip(amounts, months)]


def _expense_rows(amounts: list[float], months: list[int] = None) -> list[dict]:
    months = months or list(range(1, len(amounts) + 1))
    return [_make_row(a, "expense", m) for a, m in zip(amounts, months)]


# ---------------------------------------------------------------------------
# Signal computation tests
# ---------------------------------------------------------------------------
class TestSignalService:
    def test_empty_input_returns_insufficient(self):
        result = compute_signals([])
        assert result.data_quality == "insufficient"
        assert result.income_level == 0.0

    def test_zero_income(self):
        rows = _expense_rows([500, 300, 200], [1, 2, 3])
        result = compute_signals(rows)
        assert result.savings_rate == 0.0
        assert result.burden == 100.0
        assert result.income_level == 0.0

    def test_income_level_normalisation(self):
        # 50000 USD income = 100% of cap
        rows = _income_rows([50000], [1])
        result = compute_signals(rows)
        assert result.income_level == 100.0

    def test_income_level_partial(self):
        # 25000 USD = 50% of 50000 cap
        rows = _income_rows([25000], [1])
        result = compute_signals(rows)
        assert abs(result.income_level - 50.0) < 1.0

    def test_savings_rate_positive(self):
        rows = _income_rows([1000, 1000, 1000], [1, 2, 3])
        rows += _expense_rows([500, 500, 500], [1, 2, 3])
        result = compute_signals(rows)
        # savings = (3000 - 1500) / 3000 * 100 = 50%
        assert abs(result.savings_rate - 50.0) < 1.0

    def test_savings_rate_negative(self):
        rows = _income_rows([500], [1])
        rows += _expense_rows([1000], [1])
        result = compute_signals(rows)
        assert result.savings_rate < 0

    def test_burden_calculation(self):
        rows = _income_rows([1000], [1])
        rows += _expense_rows([700], [1])
        result = compute_signals(rows)
        # burden = 700/1000 * 100 = 70%
        assert abs(result.burden - 70.0) < 1.0

    def test_income_stability_perfect(self):
        # Same income every month = perfect stability
        rows = _income_rows([1000, 1000, 1000, 1000], [1, 2, 3, 4])
        result = compute_signals(rows)
        assert result.income_stability == 100.0

    def test_income_stability_volatile(self):
        # Wildly varying income = low stability
        rows = _income_rows([100, 5000, 50, 4000], [1, 2, 3, 4])
        result = compute_signals(rows)
        assert result.income_stability < 50.0

    def test_single_month_low_data(self):
        rows = _income_rows([2000], [1])
        rows += _expense_rows([800], [1])
        result = compute_signals(rows)
        assert result.data_quality == "low_data"

    def test_all_unknown_type_insufficient(self):
        rows = [_make_row(500, "unknown", m) for m in range(1, 6)]
        result = compute_signals(rows)
        assert result.data_quality == "insufficient"

    def test_activity_signal(self):
        # 10 transactions in 1 month = 10/100 * 100 = 10
        rows = [_make_row(100, "income", 1) for _ in range(10)]
        result = compute_signals(rows)
        assert result.activity > 0

    def test_signals_clamped_to_valid_range(self):
        rows = _income_rows([100000], [1])  # way above cap
        result = compute_signals(rows)
        assert 0 <= result.income_level <= 100


# ---------------------------------------------------------------------------
# Scoring engine tests
# ---------------------------------------------------------------------------
class TestScoringEngine:
    def test_score_always_in_range(self):
        for _ in range(10):
            rows = _income_rows([1000, 1200, 900], [1, 2, 3])
            rows += _expense_rows([400, 500, 350], [1, 2, 3])
            signals = compute_signals(rows)
            score = compute_score(signals)
            assert 300 <= score <= 850

    def test_insufficient_data_returns_floor(self):
        signals = SignalResult(data_quality="insufficient")
        score = compute_score(signals)
        assert 300 <= score <= 550

    def test_high_income_stable_low_burden_scores_high(self):
        rows = _income_rows([5000, 5000, 5000, 5000], [1, 2, 3, 4])
        rows += _expense_rows([500, 500, 500, 500], [1, 2, 3, 4])
        signals = compute_signals(rows)
        score = compute_score(signals)
        assert score >= 600   # should be well above floor

    def test_zero_income_scores_low(self):
        rows = _expense_rows([500, 500, 500], [1, 2, 3])
        signals = compute_signals(rows)
        score = compute_score(signals)
        assert score <= 500

    def test_risk_level_trusted(self):
        assert get_risk_level(750) == "trusted"
        assert get_risk_level(700) == "trusted"

    def test_risk_level_moderate(self):
        assert get_risk_level(699) == "moderate"
        assert get_risk_level(500) == "moderate"

    def test_risk_level_risky(self):
        assert get_risk_level(499) == "risky"
        assert get_risk_level(300) == "risky"

    def test_insights_not_empty(self):
        rows = _income_rows([2000, 2000, 2000], [1, 2, 3])
        rows += _expense_rows([800, 800, 800], [1, 2, 3])
        signals = compute_signals(rows)
        score = compute_score(signals)
        insights = generate_insights(signals, score)
        assert len(insights) >= 1
        assert isinstance(insights[0], str)

    def test_insufficient_insight_message(self):
        signals = SignalResult(data_quality="insufficient")
        insights = generate_insights(signals, 300)
        # Message should mention limited/partial data
        first = insights[0].lower()
        assert any(word in first for word in ("limited", "insufficient", "partial", "upload"))
