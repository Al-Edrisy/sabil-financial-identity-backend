"""
app/tests/test_transaction_parser.py — Unit tests for the transaction parser.
Run with: python3 -m pytest app/tests/test_transaction_parser.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
from app.ai.parsing.transaction_parser import parse_transactions, _auto_detect_strategy
from app.ai.parsing.currency_normalizer import extract_amount_and_currency


# ---------------------------------------------------------------------------
# Currency normalizer tests
# ---------------------------------------------------------------------------
class TestCurrencyNormalizer:
    def test_basic_usd(self):
        r = extract_amount_and_currency("Upwork Payment 500 USD")
        assert r["amount"] == 500.0
        assert r["currency"] == "USD"

    def test_symbol_prefix(self):
        r = extract_amount_and_currency("$1,500.00")
        assert r["amount"] == 1500.0
        assert r["currency"] == "USD"

    def test_arabic_indic_digits(self):
        r = extract_amount_and_currency("٥٠٠ ريال")
        assert r["amount"] == 500.0
        assert r["currency"] == "SAR"

    def test_european_decimal(self):
        r = extract_amount_and_currency("1.500,00 EUR")
        assert r["amount"] == 1500.0
        assert r["currency"] == "EUR"

    def test_negative_amount(self):
        r = extract_amount_and_currency("-300 USD")
        # Parser takes abs value; sign handled by type detector
        assert r["amount"] == 300.0

    def test_no_amount(self):
        r = extract_amount_and_currency("Date Description Balance")
        assert r["amount"] is None

    def test_sanity_cap(self):
        r = extract_amount_and_currency("99999999 USD")
        assert r["amount"] is None   # exceeds 10M cap

    def test_cr_dr_detection(self):
        r = extract_amount_and_currency("CR 500 USD")
        assert r["sign_from_text"] == "credit"
        r2 = extract_amount_and_currency("DR 300 SAR")
        assert r2["sign_from_text"] == "debit"


# ---------------------------------------------------------------------------
# Strategy detection tests
# ---------------------------------------------------------------------------
class TestStrategyDetection:
    def test_detects_strategy_b_for_simple_lines(self):
        lines = [
            "Upwork Payment 500 USD",
            "Rent April 300 USD",
            "Adobe Subscription 20 USD",
        ]
        assert _auto_detect_strategy(lines) == "B"

    def test_detects_strategy_a_for_dated_table(self):
        lines = [
            "01/04/2024  Upwork Payment    500.00 USD",
            "02/04/2024  Rent April        300.00 USD",
            "03/04/2024  Adobe             20.00 USD",
            "04/04/2024  Salary            2000.00 USD",
        ]
        assert _auto_detect_strategy(lines) == "A"

    def test_detects_strategy_c_for_split_lines(self):
        lines = [
            "Upwork Payment",
            "500 USD",
            "Rent April",
            "300 USD",
            "Adobe",
            "20 USD",
        ]
        assert _auto_detect_strategy(lines) == "C"


# ---------------------------------------------------------------------------
# Strategy B — line-by-line
# ---------------------------------------------------------------------------
class TestStrategyB:
    def test_basic_parsing(self):
        lines = [
            "Upwork Payment 500 USD",
            "Rent April 300 USD",
            "Adobe Subscription 20 USD",
        ]
        rows = parse_transactions(lines)
        assert len(rows) == 3
        assert rows[0].description == "Upwork Payment"
        assert rows[0].amount == 500.0
        assert rows[0].currency == "USD"

    def test_income_classification(self):
        rows = parse_transactions(["Salary Payment 3000 USD"])
        assert rows[0].type == "income"

    def test_expense_classification(self):
        rows = parse_transactions(["Netflix Subscription 15 USD"])
        assert rows[0].type == "expense"

    def test_unknown_classification(self):
        rows = parse_transactions(["XYZ Corp 100 USD"])
        assert rows[0].type == "unknown"

    def test_skips_header_lines(self):
        lines = [
            "Date Description Amount",
            "Upwork Payment 500 USD",
        ]
        rows = parse_transactions(lines)
        assert len(rows) == 1

    def test_skips_empty_lines(self):
        lines = ["", "  ", "Upwork Payment 500 USD", ""]
        rows = parse_transactions(lines)
        assert len(rows) == 1

    def test_arabic_description(self):
        rows = parse_transactions(["راتب شهري 5000 SAR"])
        assert len(rows) == 1
        assert rows[0].amount == 5000.0
        assert rows[0].currency == "SAR"

    def test_low_confidence_flagged(self):
        # Line with no currency and ambiguous description
        rows = parse_transactions(["xyz 50"])
        if rows:
            # If parsed, should be flagged for review
            assert rows[0].needs_review is True or rows[0].confidence < 0.5


# ---------------------------------------------------------------------------
# Strategy C — multi-line merge
# ---------------------------------------------------------------------------
class TestStrategyC:
    def test_merges_description_and_amount(self):
        lines = [
            "Upwork Payment",
            "500 USD",
            "Rent April",
            "300 USD",
        ]
        rows = parse_transactions(lines)
        assert len(rows) == 2
        assert rows[0].amount == 500.0
        assert rows[1].amount == 300.0

    def test_description_preserved_after_merge(self):
        lines = ["Adobe Creative Cloud", "20 USD"]
        rows = parse_transactions(lines)
        assert len(rows) == 1
        assert "Adobe" in rows[0].description


# ---------------------------------------------------------------------------
# Strategy A — structured table
# ---------------------------------------------------------------------------
class TestStrategyA:
    def test_parses_dated_table(self):
        lines = [
            "01/04/2024  Upwork Payment    500.00 USD",
            "02/04/2024  Rent April        300.00 USD",
            "03/04/2024  Adobe             20.00 USD",
            "04/04/2024  Salary            2000.00 USD",
        ]
        rows = parse_transactions(lines)
        assert len(rows) == 4
        assert rows[0].transaction_date is not None

    def test_date_extracted(self):
        lines = [
            "01/04/2024  Salary 3000 USD",
            "15/04/2024  Rent 1000 USD",
            "20/04/2024  Grocery 200 USD",
        ]
        rows = parse_transactions(lines)
        for row in rows:
            assert row.transaction_date is not None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_empty_input(self):
        assert parse_transactions([]) == []

    def test_all_headers(self):
        lines = ["Date", "Description", "Amount", "Balance"]
        rows = parse_transactions(lines)
        assert len(rows) == 0

    def test_mixed_currencies(self):
        lines = [
            "Upwork 500 USD",
            "Rent 1500 SAR",
            "Netflix 15 EUR",
        ]
        rows = parse_transactions(lines)
        assert len(rows) == 3
        currencies = {r.currency for r in rows}
        assert "USD" in currencies
        assert "SAR" in currencies
        assert "EUR" in currencies

    def test_normalized_usd_populated(self):
        rows = parse_transactions(["Salary 3750 SAR"])
        assert len(rows) == 1
        # 3750 SAR ≈ 1000 USD (rate 3.75)
        assert rows[0].normalized_usd is not None
        assert rows[0].normalized_usd > 0
