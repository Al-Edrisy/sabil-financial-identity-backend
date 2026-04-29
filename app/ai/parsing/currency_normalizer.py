"""
app/ai/parsing/currency_normalizer.py — Extract and normalize monetary amounts
from raw OCR text strings.

Supports English, Arabic, and Turkish text including:
  - Latin digits:          500, 1,500.00, 1.500,00
  - Arabic-Indic digits:   ٥٠٠, ١٬٥٠٠
  - Currency codes:        USD, SAR, AED, TRY, EUR, GBP, EGP, KWD, BHD, QAR, OMR
  - Currency symbols:      $, £, €, ₺, ر.س, ريال, درهم, دينار, TL, lira
  - Sign prefixes:         +500, -300, CR 500, DR 300, Alacak, Borç
  - Inline currency:       "500 TRY", "TRY 500", "₺500", "500₺"
"""

import re
from typing import Optional
from app.utils.fx import convert_currency
from app.core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Arabic-Indic → ASCII digit map
# ---------------------------------------------------------------------------
_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")

# ---------------------------------------------------------------------------
# Currency symbol / keyword → ISO code
# (English, Arabic, Turkish)
# ---------------------------------------------------------------------------
_SYMBOL_MAP: dict[str, str] = {
    # ── USD ──────────────────────────────────────────────────────────────────
    "$":        "USD",
    "usd":      "USD",
    "dollar":   "USD",
    "dollars":  "USD",

    # ── GBP ──────────────────────────────────────────────────────────────────
    "£":        "GBP",
    "gbp":      "GBP",
    "pound":    "GBP",
    "sterling": "GBP",

    # ── EUR ──────────────────────────────────────────────────────────────────
    "€":        "EUR",
    "eur":      "EUR",
    "euro":     "EUR",

    # ── SAR ──────────────────────────────────────────────────────────────────
    "sar":      "SAR",
    "sr":       "SAR",
    "ريال":     "SAR",
    "ر.س":      "SAR",
    "ر.س.":     "SAR",
    "riyal":    "SAR",
    "riyals":   "SAR",

    # ── AED ──────────────────────────────────────────────────────────────────
    "aed":      "AED",
    "dhs":      "AED",
    "dh":       "AED",
    "درهم":     "AED",
    "د.إ":      "AED",
    "dirham":   "AED",
    "dirhams":  "AED",

    # ── TRY (Turkish Lira) ────────────────────────────────────────────────────
    "₺":        "TRY",
    "try":      "TRY",
    "tl":       "TRY",
    "lira":     "TRY",
    "türk lirası": "TRY",
    "turk lirasi": "TRY",

    # ── EGP ──────────────────────────────────────────────────────────────────
    "egp":      "EGP",
    "le":       "EGP",
    "جنيه":     "EGP",

    # ── KWD ──────────────────────────────────────────────────────────────────
    "kwd":      "KWD",
    "kd":       "KWD",
    "دينار":    "KWD",

    # ── BHD ──────────────────────────────────────────────────────────────────
    "bhd":      "BHD",
    "bd":       "BHD",

    # ── QAR ──────────────────────────────────────────────────────────────────
    "qar":      "QAR",
    "qr":       "QAR",

    # ── OMR ──────────────────────────────────────────────────────────────────
    "omr":      "OMR",
    "ro":       "OMR",
}

# Supported ISO codes (for direct uppercase match)
_ISO_CODES = {
    "USD", "SAR", "AED", "TRY", "EUR", "GBP",
    "EGP", "KWD", "BHD", "QAR", "OMR",
}

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
_AMOUNT_RE = re.compile(
    r"(?P<pre_curr>[A-Za-z₺$£€\u0600-\u06FF.]{1,15}\s*)?"
    r"(?P<amount>[+\-]?\s*[\d,،٠-٩]+(?:[.,]\d{1,3})*(?:[.,]\d{1,2})?)"
    r"(?:\s*(?P<post_curr>[A-Za-z₺$£€\u0600-\u06FF.]{1,15}))?",
    re.UNICODE,
)

# CR/DR and Turkish equivalents (Alacak = credit, Borç = debit)
_CR_DR_RE = re.compile(
    r"\b(cr|credit|alacak|dr|debit|borç|borc)\b",
    re.IGNORECASE | re.UNICODE,
)


def _normalize_digits(text: str) -> str:
    """Convert Arabic-Indic numerals and separators to ASCII."""
    return text.translate(_ARABIC_INDIC)


def _parse_amount_string(raw: str) -> Optional[float]:
    """
    Parse a raw amount string into a float.
    Handles both comma-as-thousands (1,500.00) and comma-as-decimal (1.500,00).
    """
    raw = _normalize_digits(raw.strip().replace(" ", ""))
    if not raw:
        return None

    sign = -1.0 if raw.startswith("-") else 1.0
    raw  = raw.lstrip("+-").strip()

    comma_pos = raw.rfind(",")
    dot_pos   = raw.rfind(".")

    if comma_pos > dot_pos:
        # European / Turkish format: 1.500,00
        raw = raw.replace(".", "").replace(",", ".")
    else:
        # Standard format: 1,500.00
        raw = raw.replace(",", "")

    try:
        return sign * float(raw)
    except ValueError:
        return None


def _resolve_currency(token: Optional[str]) -> Optional[str]:
    """Map a raw currency token to an ISO code."""
    if not token:
        return None
    t = token.strip().rstrip(".")
    if t.upper() in _ISO_CODES:
        return t.upper()
    return _SYMBOL_MAP.get(t.lower())


def extract_amount_and_currency(text: str) -> dict:
    """
    Extract the first monetary amount and currency from a raw text string.

    Returns:
        {
            "amount":          float | None,
            "currency":        str,           # ISO code, default "USD"
            "normalized_usd":  float | None,
            "confidence":      float,         # 0.0–1.0
            "sign_from_text":  str | None,    # "credit" | "debit" | None
        }
    """
    result: dict = {
        "amount":         None,
        "currency":       "USD",
        "normalized_usd": None,
        "confidence":     0.0,
        "sign_from_text": None,
    }

    if not text:
        return result

    # ── CR / DR / Alacak / Borç detection ────────────────────────────────────
    cr_dr = _CR_DR_RE.search(text)
    if cr_dr:
        token = cr_dr.group(1).lower()
        result["sign_from_text"] = (
            "credit" if token in ("cr", "credit", "alacak") else "debit"
        )

    normalized_text = _normalize_digits(text)

    # Strip date tokens before amount matching — dates like "01.04.2024"
    # confuse the regex (it matches "01.04" as a decimal amount)
    _DATE_STRIP = re.compile(
        r'\b\d{1,2}[./\-]\d{1,2}[./\-]\d{4}\b'
        r'|\b\d{4}[./\-]\d{1,2}[./\-]\d{1,2}\b'
    )
    normalized_text = _DATE_STRIP.sub(" ", normalized_text)

    match = _AMOUNT_RE.search(normalized_text)
    if not match:
        return result

    raw_amount = match.group("amount")
    pre_curr   = match.group("pre_curr")
    post_curr  = match.group("post_curr")

    amount = _parse_amount_string(raw_amount)
    if amount is None or amount == 0:
        return result

    if abs(amount) > 10_000_000:
        logger.debug(f"currency_normalizer: amount {amount} exceeds sanity cap — skipped")
        return result

    result["amount"] = abs(amount)

    resolved_post = _resolve_currency(post_curr)
    resolved_pre  = _resolve_currency(pre_curr)
    currency = resolved_post or resolved_pre or "USD"
    result["currency"] = currency

    try:
        usd_amount, _ = convert_currency(result["amount"], currency, "USD")
        result["normalized_usd"] = usd_amount
    except Exception:
        result["normalized_usd"] = result["amount"]

    confidence = 0.3   # base: amount found but no currency context
    # Only boost confidence if a KNOWN currency was actually resolved
    # (not just any text token that happened to appear before the number)
    if resolved_post or resolved_pre:
        confidence += 0.3
    if result["amount"] > 0:
        confidence += 0.2
    result["confidence"] = min(confidence, 1.0)

    return result
