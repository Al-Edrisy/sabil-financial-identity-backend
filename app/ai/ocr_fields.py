"""
app/ai/ocr_fields.py — Keyword-aware field extraction from OCR text.

Handles both Latin and Arabic text. Uses proximity heuristics to distinguish
DOB from Expiry from Issue Date.
"""

import re
from app.core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Date patterns — matches DD/MM/YYYY, YYYY/MM/DD, DDMMYYYY, and Arabic variants
# ---------------------------------------------------------------------------
_DATE_RE = re.compile(
    r'\b(?:'
    r'\d{2}[\s\/\-\.]\d{2}[\s\/\-\.]\d{4}'   # DD/MM/YYYY or DD MM YYYY
    r'|\d{4}[\s\/\-\.]\d{2}[\s\/\-\.]\d{2}'  # YYYY/MM/DD or YYYY MM DD
    r'|\d{8}'                                 # DDMMYYYY
    r'|\d{2}[\s\/\-\.]\d{4}'                  # MM/YYYY (partial)
    r')\b'
)

# ---------------------------------------------------------------------------
# ID number patterns per document type
# ---------------------------------------------------------------------------
_ID_PATTERNS: dict[str, list[re.Pattern]] = {
    "national_id": [
        re.compile(r'\b\d{10,14}\b'),           # Saudi / Egyptian NID (10-14 digits)
        re.compile(r'\b[12]\d{9}\b'),            # Saudi NID starts with 1 or 2
        re.compile(r'\b[A-Z]{1,2}\d{6,10}\b'),  # Alphanumeric IDs
    ],
    "passport": [
        re.compile(r'\b[A-Z]{1,2}\d{6,8}\b'),
        re.compile(r'\b[A-Z]\d{7}\b'),                        # Common passport format
        re.compile(r'\b[A-Z][0-9A-Z]*\d[0-9A-Z]{0,7}\b'),   # Mixed alphanumeric with at least one digit
    ],
    "drivers_license": [
        re.compile(r'\b[A-Z0-9]{5,15}\b'),
        re.compile(r'\b\d{8,12}\b'),
    ],
    "residence_permit": [
        re.compile(r'\b\d{8,12}\b'),
        re.compile(r'\b[A-Z]{1,3}\d{6,10}\b'),
        re.compile(r'\b[12]\d{9}\b'),            # Iqama (Saudi residence permit)
    ],
}

# ---------------------------------------------------------------------------
# Date context keywords
# ---------------------------------------------------------------------------
_DATE_KEYWORDS: dict[str, list[str]] = {
    "dob": [
        "birth", "born", "dob", "date of birth", "naissance", "nascimento",
        "ولد", "ميلاد", "تاريخ الميلاد", "تاريخ الولادة",
    ],
    "expiry": [
        "expiry", "expiration", "expires", "valid until", "valid thru",
        "exp", "انتهاء", "صالح", "تاريخ الانتهاء", "تاريخ الصلاحية",
        "صلاحية",
    ],
    "issue": [
        "issue", "issued", "date of issue", "delivre", "emissao",
        "اصدار", "تاريخ الاصدار", "تاريخ الإصدار",
    ],
}

# ---------------------------------------------------------------------------
# Nationality keyword map
# ---------------------------------------------------------------------------
_NATIONALITY_MAP: dict[str, str] = {
    "egypt":    "Egyptian",
    "saudi":    "Saudi",
    "emirat":   "Emirati",
    "qatar":    "Qatari",
    "kuwait":   "Kuwaiti",
    "bahrain":  "Bahraini",
    "oman":     "Omani",
    "jordan":   "Jordanian",
    "leban":    "Lebanese",
    "turk":     "Turkish",
    "british":  "British",
    "american": "American",
    "french":   "French",
    "german":   "German",
    "indian":   "Indian",
    "pakistan": "Pakistani",
    "bangla":   "Bangladeshi",
    "philipp":  "Filipino",
    "libya":    "Libyan",
    "سعودي":    "Saudi",
    "مصري":     "Egyptian",
    "إماراتي":  "Emirati",
    "ليبي":     "Libyan",
}

# ---------------------------------------------------------------------------
# Name character regex — Latin + Arabic + common punctuation
# ---------------------------------------------------------------------------
_NAME_CHAR_RE = re.compile(r'^[A-Za-z\u0600-\u06FF\s\'\-\.]+$')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _extract_id_number(texts: list[str], id_type: str) -> str | None:
    patterns = _ID_PATTERNS.get(id_type, _ID_PATTERNS["national_id"])
    for t in texts:
        # Normalize Arabic digits in candidate strings
        t_norm = t
        arabic_digits = {"٠":"0","١":"1","٢":"2","٣":"3","٤":"4","٥":"5","٦":"6","٧":"7","٨":"8","٩":"9"}
        for k, v in arabic_digits.items():
            t_norm = t_norm.replace(k, v)

        for pat in patterns:
            m = pat.search(t_norm)
            if m:
                candidate = m.group()
                # Sanity: reject if it looks like a date (8 digits that parse as DDMMYYYY)
                if len(candidate) == 8 and candidate.isdigit():
                    continue
                # For passports, avoid picking up common year-like numbers if they are clearly wrong
                if id_type == "passport" and len(candidate) < 6:
                    continue
                return candidate
    return None


def _extract_name(texts: list[str]) -> str | None:
    # Strip common label prefixes before matching
    _LABEL_RE = re.compile(
        r'^(الاسم|name|full name|surname|given names?|first name|last name|'
        r'الاسم الكامل|nom|prénom)\s*[:\-]\s*',
        re.IGNORECASE,
    )
    cleaned_pairs = [(_LABEL_RE.sub("", t).strip(), t.strip()) for t in texts]

    # Prefer lines that had a name label — they are most likely the actual name
    labelled = [
        c for c, orig in cleaned_pairs
        if c != orig and len(c.split()) >= 1 and _NAME_CHAR_RE.match(c)
    ]
    if labelled:
        # Combine surname + given names if both present
        return " ".join(labelled[:2]).strip()

    # Fallback: longest multi-word line that looks like a name
    # Exclude common document labels and short noise
    candidates = [
        c for c, _ in cleaned_pairs
        if len(c.split()) >= 2
        and _NAME_CHAR_RE.match(c)
        and not any(kw in c.lower() for kw in [
            "ministry", "republic", "kingdom", "state", "card", "identity",
            "national", "passport", "وزارة", "مملكة", "جمهورية", "بطاقة",
            "هوية", "جواز", "رخصة", "bearing", "signature", "bearer", "issued",
            "place", "date", "birth", "expiry", "expiration", "توقيع", "صاحب",
        ])
    ]
    # Sort by number of words (desc) then by length (desc)
    candidates.sort(key=lambda x: (len(x.split()), len(x)), reverse=True)
    return candidates[0] if candidates else None


def _extract_keyword_aware_fields(texts: list[str], id_type: str) -> dict:
    """
    Extract DOB, Expiry, Issue Date, Nationality, Country, and Authority
    using keyword proximity heuristics.
    """
    result = {
        "dob":               None,
        "expiry_date":       None,
        "issue_date":        None,
        "nationality":       None,
        "country":           None,
        "issuing_authority": None,
    }
    dates_found: list[str] = []

    # ── 1. Date extraction with context ──────────────────────────────────────
    for i, line in enumerate(texts):
        matches = _DATE_RE.findall(line)
        for m in matches:
            # Build context window (previous + current + next line)
            context_parts = []
            if i > 0:
                context_parts.append(texts[i - 1])
            context_parts.append(line)
            if i < len(texts) - 1:
                context_parts.append(texts[i + 1])
            context = " ".join(context_parts).lower()

            assigned = False
            if any(k in context for k in _DATE_KEYWORDS["dob"]):
                result["dob"] = m
                assigned = True
            elif any(k in context for k in _DATE_KEYWORDS["expiry"]):
                result["expiry_date"] = m
                assigned = True
            elif any(k in context for k in _DATE_KEYWORDS["issue"]):
                result["issue_date"] = m
                assigned = True

            if not assigned:
                dates_found.append(m)

    # Positional fallback: first unassigned date = DOB, second = expiry
    if dates_found:
        if not result["dob"]:
            result["dob"] = dates_found[0]
        if not result["expiry_date"] and len(dates_found) > 1:
            result["expiry_date"] = dates_found[1]
        if not result["issue_date"] and len(dates_found) > 2:
            result["issue_date"] = dates_found[2]

    # ── 2. Nationality, country, authority ───────────────────────────────────
    full_text = " ".join(texts).lower()
    for key, val in _NATIONALITY_MAP.items():
        if key in full_text:
            result["nationality"] = val
            if not result["country"]:
                result["country"] = key.title()
            break

    auth_keywords = [
        "ministry", "interior", "police", "department", "state",
        "government", "authority", "service", "republic", "kingdom",
        "وزارة", "الداخلية", "شرطة", "مملكة", "جمهورية",
    ]
    for line in texts:
        if any(k in line.lower() for k in auth_keywords):
            result["issuing_authority"] = line.strip()
            break

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def extract_fields(raw_texts: list[str], id_type: str) -> dict:
    fields = _extract_keyword_aware_fields(raw_texts, id_type)
    fields["full_name"] = _extract_name(raw_texts)
    fields["id_number"] = _extract_id_number(raw_texts, id_type)
    return fields
