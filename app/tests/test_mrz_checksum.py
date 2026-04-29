"""
app/tests/test_mrz_checksum.py — Unit tests for ICAO Doc 9303 MRZ parsing
and checksum validation.

Reference specimen:
  ICAO Doc 9303 Part 3 (2015), Appendix A — fictional specimen passport.
  Line 1: P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<
  Line 2: L898902C36UTO6908061F9406236ZE184226B<<<<<18

This is the canonical public test vector published by ICAO.
It describes a fictional person and is safe to embed in test code.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.ai.ocr_mrz import (
    _mrz_check_digit,
    validate_mrz_checksums,
    validate_td3_checksums,
    parse_mrz,
)
from app.ai.ocr import (
    _mrz_check_digit as ocr_check_digit,
    validate_mrz_checksums as ocr_validate,
    parse_mrz as ocr_parse_mrz,
)

# ---------------------------------------------------------------------------
# ICAO specimen — all checksums verified correct
# ---------------------------------------------------------------------------
VALID_LINE1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"   # 44 chars
VALID_LINE2 = "L898902C36UTO6908061F9406236ZE184226B<<<<<18"   # 44 chars

# Field slices (without check digit)
_DOC_NUM_FIELD  = VALID_LINE2[0:9]    # "L898902C3"  → check '6' at [9]
_DOB_FIELD      = VALID_LINE2[13:19]  # "690806"     → check '1' at [19]
_EXPIRY_FIELD   = VALID_LINE2[21:27]  # "940623"     → check '6' at [27]
_PERSONAL_FIELD = VALID_LINE2[28:42]  # "ZE184226B<<<<<" → check '1' at [42]


# ---------------------------------------------------------------------------
# _mrz_check_digit
# ---------------------------------------------------------------------------
class TestMrzCheckDigit:
    def test_doc_number_check_digit(self):
        assert _mrz_check_digit(_DOC_NUM_FIELD) == int(VALID_LINE2[9])   # 6

    def test_dob_check_digit(self):
        assert _mrz_check_digit(_DOB_FIELD) == int(VALID_LINE2[19])      # 1

    def test_expiry_check_digit(self):
        assert _mrz_check_digit(_EXPIRY_FIELD) == int(VALID_LINE2[27])   # 6

    def test_personal_check_digit(self):
        assert _mrz_check_digit(_PERSONAL_FIELD) == int(VALID_LINE2[42]) # 1

    def test_fill_char_maps_to_zero(self):
        # '<' → 0; a field of all '<' must yield 0
        assert _mrz_check_digit("<<<") == 0

    def test_unmappable_character_returns_minus_one(self):
        # Characters outside MRZ charset (e.g. '!') → -1
        assert _mrz_check_digit("A!B") == -1

    def test_weight_cycle_7_3_1(self):
        # '1'=1, '2'=2, '3'=3 → (1×7 + 2×3 + 3×1) % 10 = 16 % 10 = 6
        assert _mrz_check_digit("123") == 6

    def test_single_digit_field(self):
        # '5' → 5×7 = 35 % 10 = 5
        assert _mrz_check_digit("5") == 5

    def test_empty_field_returns_zero(self):
        assert _mrz_check_digit("") == 0

    def test_importable_from_ocr_module(self):
        # Verify re-export from app.ai.ocr works
        assert ocr_check_digit(_DOC_NUM_FIELD) == int(VALID_LINE2[9])


# ---------------------------------------------------------------------------
# validate_mrz_checksums / validate_td3_checksums
# ---------------------------------------------------------------------------
class TestValidateMrzChecksums:
    def test_valid_specimen_all_pass(self):
        result = validate_mrz_checksums(VALID_LINE2)
        assert result["valid"] is True
        assert result["doc_number"] is True
        assert result["dob"] is True
        assert result["expiry"] is True
        assert result["personal"] is True
        assert result["composite"] is True

    def test_alias_td3_same_result(self):
        assert validate_td3_checksums(VALID_LINE2) == validate_mrz_checksums(VALID_LINE2)

    def test_importable_from_ocr_module(self):
        assert ocr_validate(VALID_LINE2)["valid"] is True

    def test_wrong_length_returns_invalid(self):
        result = validate_mrz_checksums("TOOSHORT")
        assert result["valid"] is False
        assert "reason" in result

    def test_empty_string_returns_invalid(self):
        result = validate_mrz_checksums("")
        assert result["valid"] is False

    def test_tampered_doc_number_fails(self):
        # Flip first char 'L' → '0' — breaks doc_number and composite
        tampered = "0" + VALID_LINE2[1:]
        result = validate_mrz_checksums(tampered)
        assert result["doc_number"] is False
        assert result["valid"] is False

    def test_tampered_dob_fails(self):
        # Change birth year 69 → 70.
        # Note: '700806' produces the same DOB check digit as '690806'
        # (hash collision in ICAO 7-3-1). The composite checksum catches it.
        tampered = VALID_LINE2[:13] + "700806" + VALID_LINE2[19:]
        result = validate_mrz_checksums(tampered)
        assert result["valid"] is False   # composite fails even if dob passes

    def test_tampered_expiry_fails(self):
        # Change expiry year 94 → 95
        tampered = VALID_LINE2[:21] + "950623" + VALID_LINE2[27:]
        result = validate_mrz_checksums(tampered)
        assert result["expiry"] is False
        assert result["valid"] is False

    def test_non_digit_check_char_fails(self):
        # Replace doc-number check digit (pos 9) with 'X'
        tampered = VALID_LINE2[:9] + "X" + VALID_LINE2[10:]
        result = validate_mrz_checksums(tampered)
        assert result["doc_number"] is False
        assert result["valid"] is False


# ---------------------------------------------------------------------------
# parse_mrz integration
# ---------------------------------------------------------------------------
class TestParseMrzIntegration:
    def test_valid_specimen_checksum_valid_true(self):
        result = parse_mrz([VALID_LINE1, VALID_LINE2])
        assert result.get("mrz_checksum_valid") is True
        assert result.get("mrz_checksum_detail", {}).get("valid") is True

    def test_tampered_line2_checksum_valid_false(self):
        tampered = "0" + VALID_LINE2[1:]
        result = parse_mrz([VALID_LINE1, tampered])
        assert result.get("mrz_checksum_valid") is False

    def test_fields_parsed_correctly(self):
        result = parse_mrz([VALID_LINE1, VALID_LINE2])
        assert result["mrz_type"]        == "TD3"
        assert result["mrz_doc_number"]  == "L898902C3"
        assert result["mrz_nationality"] == "UTO"
        assert result["mrz_country"]     == "UTO"
        assert result["mrz_sex"]         == "F"
        assert result["mrz_dob"]         == "1969-08-06"
        assert result["mrz_expiry"]      == "1994-06-23"

    def test_name_parsed_correctly(self):
        result = parse_mrz([VALID_LINE1, VALID_LINE2])
        # "ERIKSSON<<ANNA<MARIA" → "Anna Maria Eriksson"
        assert "Eriksson" in result["mrz_full_name"]
        assert "Anna" in result["mrz_full_name"]

    def test_empty_input_returns_empty_dict(self):
        assert parse_mrz([]) == {}

    def test_single_line_returns_empty_dict(self):
        assert parse_mrz([VALID_LINE1]) == {}

    def test_non_mrz_lines_ignored(self):
        # Noise lines mixed in — parser should still find the MRZ
        lines = [
            "REPUBLIC OF UTOPIA",
            "PASSPORT",
            VALID_LINE1,
            "Some random text here",
            VALID_LINE2,
        ]
        result = parse_mrz(lines)
        assert result.get("mrz_checksum_valid") is True

    def test_importable_from_ocr_module(self):
        result = ocr_parse_mrz([VALID_LINE1, VALID_LINE2])
        assert result.get("mrz_checksum_valid") is True
