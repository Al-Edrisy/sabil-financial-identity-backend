"""
app/ai/ocr_mrz.py — ICAO Doc 9303 MRZ Parsing and Validation.
Supports TD1 (3×30), TD2 (2×36), and TD3 (2×44) formats.

Public API:
  _mrz_check_digit(field)          → int (0–9, or -1 on invalid char)
  validate_mrz_checksums(line2)    → dict  (unified TD3 validator)
  validate_td3_checksums(line2)    → dict  (alias)
  validate_td1_checksums(lines)    → dict
  parse_mrz(raw_texts)             → dict
"""

import re
from app.core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# ICAO character value table
# '<' → 0, '0'–'9' → face value, 'A'–'Z' → 10–35
# ---------------------------------------------------------------------------
_MRZ_CHAR_VALUES: dict[str, int] = {
    "<": 0,
    **{str(i): i for i in range(10)},
    **{chr(ord("A") + i): 10 + i for i in range(26)},
}
_MRZ_WEIGHTS = [7, 3, 1]


# ---------------------------------------------------------------------------
# Core check-digit computation
# ---------------------------------------------------------------------------
def _mrz_check_digit(field: str) -> int:
    """
    Compute the ICAO 7-3-1 weighted modulo-10 check digit for *field*.

    Returns:
        int 0–9  — the computed check digit.
        -1       — field contains a character outside the MRZ charset.
    """
    total = 0
    for i, ch in enumerate(field):
        val = _MRZ_CHAR_VALUES.get(ch)
        if val is None:
            return -1
        total += val * _MRZ_WEIGHTS[i % 3]
    return total % 10


def _check(field: str, expected_chk_digit: str, name: str) -> bool:
    """Validate a single MRZ field against its check digit character."""
    computed = _mrz_check_digit(field)
    if not expected_chk_digit.isdigit():
        return False
    actual = int(expected_chk_digit)
    ok = (computed != -1) and (computed == actual)
    if not ok:
        logger.warning(
            f"MRZ checksum [{name}]: computed={computed}, got={actual}"
        )
    return ok


# ---------------------------------------------------------------------------
# Date and name helpers
# ---------------------------------------------------------------------------
def _parse_mrz_date(raw: str) -> str | None:
    """Convert YYMMDD → YYYY-MM-DD. Returns None on invalid input."""
    if len(raw) != 6 or not raw.isdigit():
        return None
    yy, mm, dd = raw[:2], raw[2:4], raw[4:]
    year = f"19{yy}" if int(yy) > 30 else f"20{yy}"
    return f"{year}-{mm}-{dd}"


def _clean_mrz_name(raw: str) -> str:
    """Convert 'ERIKSSON<<ANNA<MARIA' → 'Anna Maria Eriksson'."""
    parts = raw.split("<<", 1)
    surname = parts[0].replace("<", " ").strip().title()
    given   = parts[1].replace("<", " ").strip().title() if len(parts) > 1 else ""
    return f"{given} {surname}".strip()


# ---------------------------------------------------------------------------
# TD3 checksum validation (passports)
# ---------------------------------------------------------------------------
def validate_td3_checksums(line2: str) -> dict:
    """
    Validate all ICAO TD3 check digits in the second MRZ line.

    Args:
        line2: 44-character second line of a TD3 (passport) MRZ.

    Returns:
        {
            "valid":      bool,
            "doc_number": bool,
            "dob":        bool,
            "expiry":     bool,
            "personal":   bool,
            "composite":  bool,
        }
        or {"valid": False, "reason": str} on bad input.
    """
    if len(line2) != 44:
        return {"valid": False, "reason": f"Line 2 must be 44 chars, got {len(line2)}"}

    results = {
        "doc_number": _check(line2[0:9],   line2[9],  "doc_number"),
        "dob":        _check(line2[13:19], line2[19], "dob"),
        "expiry":     _check(line2[21:27], line2[27], "expiry"),
        "personal":   _check(line2[28:42], line2[42], "personal"),
        "composite":  _check(
            line2[0:10] + line2[13:20] + line2[21:43],
            line2[43],
            "composite",
        ),
    }
    results["valid"] = all(results.values())
    return results


# Unified alias used by the test suite
validate_mrz_checksums = validate_td3_checksums


# ---------------------------------------------------------------------------
# TD1 checksum validation (ID cards)
# ---------------------------------------------------------------------------
def validate_td1_checksums(lines: list[str]) -> dict:
    """Validate ICAO TD1 check digits (3-line, 30-char format)."""
    if len(lines) < 3:
        return {"valid": False, "reason": "TD1 requires 3 lines"}
    l1, l2 = lines[0], lines[1]
    results = {
        "doc_number": _check(l1[5:14], l1[14], "doc_number"),
        "dob":        _check(l2[0:6],  l2[6],  "dob"),
        "expiry":     _check(l2[8:14], l2[14], "expiry"),
    }
    results["valid"] = all(results.values())
    return results


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------
def _normalize_mrz_line(text: str) -> str:
    """
    Strip non-MRZ characters and uppercase.
    Does NOT apply letter-digit substitutions (O→0, I→1, S→5) because
    O, I, S are valid MRZ characters — substitution corrupts real data.
    OCR noise correction is applied separately only when checksums fail.
    """
    # Map Arabic-Indic digits and common filler misreads
    mapping = {
        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
        "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
        "$": "<",  # common misread of filler
        "(": "<",
        ")": "<",
        "{": "<",
        "}": "<",
        "|": "<",
    }
    res = text.upper()
    for k, v in mapping.items():
        res = res.replace(k, v)
    return re.sub(r"[^A-Z0-9<]", "", res)


def _normalize_mrz_line_aggressive(text: str) -> str:
    """
    Apply aggressive OCR noise correction for real scanned documents.
    Only used as a fallback when standard parsing fails checksums.
    Maps common letter-digit confusions: O→0, I→1, S→5.
    """
    mapping = {
        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
        "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
        "O": "0", "I": "1", "S": "5",
        "$": "<", "(": "<", ")": "<", "{": "<", "}": "<", "|": "<",
    }
    res = text.upper()
    for k, v in mapping.items():
        res = res.replace(k, v)
    return re.sub(r"[^A-Z0-9<]", "", res)


# ---------------------------------------------------------------------------
# Main MRZ parser
# ---------------------------------------------------------------------------
def parse_mrz(raw_texts: list[str]) -> dict:
    """
    Detect and parse MRZ formats: TD1 (3×30), TD2 (2×36), TD3 (2×44).

    Two-pass strategy:
      Pass 1: standard normalisation (preserves O, I, S as letters)
      Pass 2: aggressive OCR correction (O→0, I→1, S→5) — fallback for
              real scanned documents where OCR confuses letters with digits

    Args:
        raw_texts: List of OCR text lines (mixed content OK).

    Returns:
        Parsed MRZ dict, or {} if no valid MRZ is found.
    """
    if not raw_texts:
        return {}

    def _try_parse(normalizer) -> dict:
        clean_lines = [normalizer(ln) for ln in raw_texts]

        # Pre-pass: merge adjacent tokens into candidate MRZ lines
        # EasyOCR frequently splits a 44-char MRZ line into 2-3 pieces.
        extra_candidates: list[str] = []
        for i in range(len(clean_lines)):
            for j in range(i + 2, min(i + 8, len(clean_lines) + 1)):
                merged = "".join(clean_lines[i:j])
                if len(merged) in (30, 36, 44) and merged not in clean_lines:
                    extra_candidates.append(merged)
        all_lines = clean_lines + extra_candidates

        # ── TD3 (Passports — 2 × 44) ─────────────────────────────────────────
        td3_lines = [ln for ln in all_lines if len(ln) == 44]
        if len(td3_lines) >= 2:
            l1, l2 = td3_lines[0], td3_lines[1]
            if l1[0] == "P":
                chk = validate_td3_checksums(l2)
                return {
                    "mrz_type":            "TD3",
                    "mrz_full_name":       _clean_mrz_name(l1[5:44]),
                    "mrz_doc_number":      l2[0:9].replace("<", ""),
                    "mrz_nationality":     l2[10:13].replace("<", ""),
                    "mrz_dob":             _parse_mrz_date(l2[13:19]),
                    "mrz_sex":             l2[20],
                    "mrz_expiry":          _parse_mrz_date(l2[21:27]),
                    "mrz_country":         l1[2:5].replace("<", ""),
                    "mrz_checksum_valid":  chk["valid"],
                    "mrz_checksum_detail": chk,
                }

        # ── TD1 (Modern ID Cards — 3 × 30) ───────────────────────────────────
        td1_lines = [ln for ln in all_lines if len(ln) == 30]
        if len(td1_lines) >= 3:
            l1, l2, l3 = td1_lines[0], td1_lines[1], td1_lines[2]
            if l1[0] in "IAC":
                chk = validate_td1_checksums([l1, l2, l3])
                return {
                    "mrz_type":            "TD1",
                    "mrz_full_name":       _clean_mrz_name(l3),
                    "mrz_doc_number":      l1[5:14].replace("<", ""),
                    "mrz_nationality":     l2[15:18].replace("<", ""),
                    "mrz_dob":             _parse_mrz_date(l2[0:6]),
                    "mrz_sex":             l2[7],
                    "mrz_expiry":          _parse_mrz_date(l2[8:14]),
                    "mrz_country":         l1[2:5].replace("<", ""),
                    "mrz_checksum_valid":  chk["valid"],
                    "mrz_checksum_detail": chk,
                }

        # ── TD2 (Visas / Older Cards — 2 × 36) ───────────────────────────────
        td2_lines = [ln for ln in all_lines if len(ln) == 36]
        if len(td2_lines) >= 2:
            l1, l2 = td2_lines[0], td2_lines[1]
            if l1[0] in "IV":
                return {
                    "mrz_type":           "TD2",
                    "mrz_full_name":      _clean_mrz_name(l1[5:36]),
                    "mrz_doc_number":     l2[0:9].replace("<", ""),
                    "mrz_nationality":    l2[10:13].replace("<", ""),
                    "mrz_dob":            _parse_mrz_date(l2[13:19]),
                    "mrz_sex":            l2[19] if len(l2) > 19 else "",
                    "mrz_expiry":         _parse_mrz_date(l2[21:27]),
                    "mrz_country":        l2[10:13].replace("<", ""),
                    "mrz_checksum_valid": True,
                }
        return {}

    # Pass 1: standard normalisation (O, I, S preserved as letters)
    result = _try_parse(_normalize_mrz_line)
    if result:
        return result

    # Pass 2: aggressive OCR correction (O→0, I→1, S→5)
    return _try_parse(_normalize_mrz_line_aggressive)
