"""
app/ai/parsing/transaction_parser.py — Convert raw OCR text lines from a
bank statement or receipt into structured transaction rows.

Supports English, Arabic, and Turkish text.

Three parsing strategies, tried in order of reliability:
  A — Structured table (column-aligned with dates)
  B — Line-by-line (one transaction per line)
  C — Multi-line merge (description and amount on adjacent lines)
"""

import re
import dataclasses
from datetime import date, datetime
from typing import Optional
from app.ai.parsing.currency_normalizer import extract_amount_and_currency
from app.core.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class ParsedRow:
    raw_line:         str
    description:      str
    amount:           float
    currency:         str
    normalized_usd:   Optional[float]
    type:             str               # "income" | "expense" | "unknown"
    transaction_date: Optional[date]
    confidence:       float             # 0.0–1.0
    needs_review:     bool


# ---------------------------------------------------------------------------
# Income / expense keyword sets — English + Arabic + Turkish
# ---------------------------------------------------------------------------
_INCOME_KEYWORDS: frozenset[str] = frozenset({
    # English
    "payment", "salary", "deposit", "credit", "received", "refund",
    "transfer in", "incoming", "upwork", "freelance", "revenue",
    "commission", "bonus", "dividend", "interest", "cashback",
    "reimbursement", "grant", "award", "prize", "income",
    # Arabic
    "راتب", "إيداع", "تحويل وارد", "مكافأة", "عمولة", "فائدة",
    "استرداد", "دخل", "أرباح", "مكسب",
    # Turkish
    "maaş", "maas", "yatırım", "yatirim", "alacak", "gelir",
    "ücret", "ucret", "prim", "ikramiye", "faiz", "temettü", "temettu",
    "iade", "geri ödeme", "geri odeme", "havale alındı", "havale alindi",
    "maaş ödemesi", "maas odemesi",
})

_EXPENSE_KEYWORDS: frozenset[str] = frozenset({
    # English
    "rent", "subscription", "bill", "fee", "charge", "debit",
    "purchase", "withdrawal", "payment to", "transfer out",
    "outgoing", "adobe", "netflix", "amazon", "spotify", "apple",
    "google", "microsoft", "electricity", "water", "internet",
    "phone", "insurance", "mortgage", "loan", "tax", "fine",
    "penalty", "grocery", "supermarket", "restaurant", "cafe",
    "fuel", "petrol", "gas", "maintenance", "repair",
    # Arabic
    "إيجار", "فاتورة", "اشتراك", "سحب", "مصروف", "دفع",
    "كهرباء", "ماء", "هاتف", "تأمين", "قرض", "ضريبة",
    "غرامة", "بقالة", "مطعم", "وقود",
    # Turkish
    "kira", "fatura", "abonelik", "çekim", "cekim", "ödeme", "odeme",
    "elektrik", "su", "telefon", "sigorta", "kredi", "vergi",
    "para çekme", "para cekme", "market", "restoran", "yakıt", "yakit",
    "borç", "borc", "gider", "masraf", "aidat",
})


# ---------------------------------------------------------------------------
# Date patterns — English, Arabic context, Turkish month names
# ---------------------------------------------------------------------------
_TR_MONTHS = (
    r"Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|"
    r"Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık|"
    r"Subat|Mayis|Agustos|Eylul|Kasim|Aralik"   # unaccented variants
)
_EN_MONTHS = r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"

_DATE_PATTERNS = [
    # DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    (re.compile(r'\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b'), "%d/%m/%Y"),
    # YYYY/MM/DD or YYYY-MM-DD
    (re.compile(r'\b(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})\b'), "%Y/%m/%d"),
    # DD Mon YYYY — English months
    (re.compile(rf'\b(\d{{1,2}})\s+({_EN_MONTHS})\s+(\d{{4}})\b', re.IGNORECASE), "%d %b %Y"),
    # DD Ay YYYY — Turkish months
    (re.compile(rf'\b(\d{{1,2}})\s+({_TR_MONTHS})\s+(\d{{4}})\b', re.IGNORECASE), "%d %B %Y"),
    # DD/MM (no year)
    (re.compile(r'\b(\d{1,2})[/\-](\d{1,2})\b'), "%d/%m"),
]

# Amount-only line (pure monetary value, no description)
_AMOUNT_ONLY_RE = re.compile(
    r"^\s*[+\-]?\s*[\d,،٠-٩]+(?:[.,]\d{1,3})*(?:[.,]\d{2})?\s*"
    r"(?:USD|SAR|AED|TRY|EUR|GBP|EGP|KWD|BHD|QAR|OMR|"
    r"\$|£|€|₺|ريال|درهم|دينار|TL|lira)?\s*$",
    re.IGNORECASE | re.UNICODE,
)

# Header / footer lines to skip — English + Arabic + Turkish
_SKIP_RE = re.compile(
    r"^\s*("
    # English
    r"date|description|amount|balance|debit|credit|transaction|"
    r"statement|account|page|total|opening|closing|ref|reference|"
    # Arabic
    r"التاريخ|الوصف|المبلغ|الرصيد|المعاملة|الحساب|الصفحة|الإجمالي|"
    # Turkish
    r"tarih|açıklama|aciklama|tutar|bakiye|işlem|islem|hesap|sayfa|"
    r"toplam|borç|alacak|borc|referans|dekont|ekstre|"
    # Turkish bank receipt fields (should not be parsed as transactions)
    r"sube|şube|iban|numarasi|numarası|vergi|kimlik|komisyon|"
    r"alacakli|alacaklı|hesabinizdan|hesabınızdan|valor|"
    r"taraflar|merkez|internet|mobil|www\."
    r")\b",
    re.IGNORECASE | re.UNICODE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_date(text: str) -> Optional[date]:
    """Extract the first date found in a text string."""
    for pattern, fmt in _DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            try:
                raw = m.group(0)
                if "%Y" not in fmt:
                    raw = f"{raw}/{datetime.now().year}"
                    fmt = fmt + "/%Y"
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
    return None


def _clean_description(text: str, amount_token: str = "") -> str:
    """Remove amount, currency, date, and noise tokens from a line."""
    cleaned = text

    if amount_token:
        cleaned = cleaned.replace(amount_token, "", 1)

    for pattern, _ in _DATE_PATTERNS:
        cleaned = pattern.sub("", cleaned)

    # Remove currency codes and symbols (English + Turkish)
    cleaned = re.sub(
        r'\b(USD|SAR|AED|TRY|EUR|GBP|EGP|KWD|BHD|QAR|OMR|TL)\b',
        "", cleaned, flags=re.IGNORECASE,
    )
    cleaned = re.sub(r'[$£€₺]', "", cleaned)

    # Remove standalone numbers
    cleaned = re.sub(r'\b\d[\d,.,]*\d\b', "", cleaned)

    # Remove CR/DR and Turkish equivalents
    cleaned = re.sub(
        r'\b(cr|dr|credit|debit|alacak|borç|borc)\b',
        "", cleaned, flags=re.IGNORECASE | re.UNICODE,
    )

    # Remove sign prefixes left over after amount removal
    cleaned = re.sub(r'(?<!\w)[+\-](?!\w)', "", cleaned)

    cleaned = re.sub(r'\s+', " ", cleaned).strip(" -|/\\.,+")
    return cleaned if len(cleaned) >= 2 else ""


def _classify_type(description: str, sign_from_text: Optional[str], raw_line: str = "") -> str:
    """
    Determine income / expense from:
    1. CR/DR / Alacak/Borç sign (highest priority)
    2. +/- sign prefix in the raw line
    3. Strong expense noun keywords
    4. Keyword score comparison
    5. Default: expense (most transactions are outflows)
    """
    if sign_from_text == "credit":
        return "income"
    if sign_from_text == "debit":
        return "expense"

    # Check for explicit +/- sign in the raw line (bank statement convention)
    # Look for patterns like "+5000", "+ 5000", "5,000.00 CR", "-1500"
    raw_stripped = raw_line.strip()
    if raw_stripped:
        # Positive sign anywhere before the first digit cluster
        if re.search(r'(?<!\d)\+\s*[\d,]', raw_stripped):
            return "income"
        # Negative sign anywhere before the first digit cluster
        if re.search(r'(?<!\d)-\s*[\d,]', raw_stripped):
            return "expense"
        # CR at end of line (common in bank statements)
        if re.search(r'\bCR\b', raw_stripped, re.IGNORECASE):
            return "income"
        # DR at end of line
        if re.search(r'\bDR\b', raw_stripped, re.IGNORECASE):
            return "expense"

    desc_lower = description.lower()

    # Strong expense indicators — these override ambiguous income words
    _STRONG_EXPENSE = frozenset({
        "rent", "bill", "fee", "charge", "subscription", "insurance",
        "mortgage", "loan", "tax", "fine", "penalty", "utility",
        "electricity", "water", "internet", "phone", "gas", "fuel",
        "petrol", "grocery", "supermarket", "restaurant", "cafe",
        "maintenance", "repair", "purchase", "withdrawal",
        # Arabic
        "إيجار", "فاتورة", "اشتراك", "كهرباء", "ماء", "هاتف",
        "تأمين", "قرض", "ضريبة", "بقالة", "مطعم",
        # Turkish
        "kira", "fatura", "abonelik", "elektrik", "sigorta",
        "kredi", "vergi", "market", "restoran",
    })

    if any(kw in desc_lower for kw in _STRONG_EXPENSE):
        return "expense"

    income_score  = sum(1 for kw in _INCOME_KEYWORDS  if kw in desc_lower)
    expense_score = sum(1 for kw in _EXPENSE_KEYWORDS if kw in desc_lower)

    if income_score > expense_score:
        return "income"
    if expense_score > income_score:
        return "expense"

    # Default to expense — most transactions in a bank statement are outflows
    # This is better than "unknown" which breaks the scoring engine
    return "unknown"


def _score_confidence(
    description: str,
    amount: Optional[float],
    currency_confidence: float,
    has_date: bool,
) -> float:
    score = 0.0
    if amount and amount > 0:
        score += 0.4
    # Description quality: require at least 4 chars and at least one real word
    # (not just noise like "xyz" or "abc")
    if description and len(description) >= 4 and re.search(r'[a-zA-Z\u0600-\u06FF]{3,}', description):
        score += 0.3
    elif description and len(description) >= 2:
        score += 0.1   # partial credit for very short descriptions
    score += currency_confidence * 0.2
    if has_date:
        score += 0.1
    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Strategy A — Structured table
# ---------------------------------------------------------------------------
def _strategy_a(lines: list[str]) -> Optional[list[ParsedRow]]:
    date_amount_count = sum(
        1 for line in lines
        if _parse_date(line) and extract_amount_and_currency(line)["amount"]
    )
    if len(lines) < 2 or date_amount_count / len(lines) < 0.4:
        return None

    rows: list[ParsedRow] = []
    for line in lines:
        if _SKIP_RE.match(line):
            continue
        parsed = extract_amount_and_currency(line)
        if not parsed["amount"]:
            continue
        tx_date     = _parse_date(line)
        description = _clean_description(line)
        tx_type     = _classify_type(description, parsed.get("sign_from_text"), line)
        confidence  = _score_confidence(description, parsed["amount"], parsed["confidence"], tx_date is not None)
        rows.append(ParsedRow(
            raw_line=line, description=description or "Unknown",
            amount=parsed["amount"], currency=parsed["currency"],
            normalized_usd=parsed["normalized_usd"], type=tx_type,
            transaction_date=tx_date, confidence=confidence,
            needs_review=confidence < 0.65,
        ))
    return rows if rows else None


# ---------------------------------------------------------------------------
# Strategy B — Line-by-line
# ---------------------------------------------------------------------------
def _strategy_b(lines: list[str]) -> list[ParsedRow]:
    rows: list[ParsedRow] = []
    for line in lines:
        line = line.strip()
        if not line or _SKIP_RE.match(line):
            continue
        parsed = extract_amount_and_currency(line)
        if not parsed["amount"]:
            continue
        tx_date     = _parse_date(line)
        description = _clean_description(line)
        tx_type     = _classify_type(description, parsed.get("sign_from_text"), line)
        confidence  = _score_confidence(description, parsed["amount"], parsed["confidence"], tx_date is not None)
        rows.append(ParsedRow(
            raw_line=line, description=description or "Unknown",
            amount=parsed["amount"], currency=parsed["currency"],
            normalized_usd=parsed["normalized_usd"], type=tx_type,
            transaction_date=tx_date, confidence=confidence,
            needs_review=confidence < 0.65,
        ))
    return rows


# ---------------------------------------------------------------------------
# Strategy C — Multi-line merge
# ---------------------------------------------------------------------------
def _strategy_c(lines: list[str]) -> list[ParsedRow]:
    rows: list[ParsedRow] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or _SKIP_RE.match(line):
            i += 1
            continue

        parsed = extract_amount_and_currency(line)
        if parsed["amount"]:
            tx_date     = _parse_date(line)
            description = _clean_description(line)
            tx_type     = _classify_type(description, parsed.get("sign_from_text"), line)
            confidence  = _score_confidence(description, parsed["amount"], parsed["confidence"], tx_date is not None)
            rows.append(ParsedRow(
                raw_line=line, description=description or "Unknown",
                amount=parsed["amount"], currency=parsed["currency"],
                normalized_usd=parsed["normalized_usd"], type=tx_type,
                transaction_date=tx_date, confidence=confidence,
                needs_review=confidence < 0.65,
            ))
            i += 1
        elif i + 1 < len(lines) and _AMOUNT_ONLY_RE.match(lines[i + 1]):
            merged = f"{line} {lines[i + 1].strip()}"
            parsed = extract_amount_and_currency(merged)
            if parsed["amount"]:
                tx_date     = _parse_date(line)
                description = _clean_description(line)
                tx_type     = _classify_type(description, parsed.get("sign_from_text"), line)
                confidence  = min(_score_confidence(description, parsed["amount"], parsed["confidence"] + 0.1, tx_date is not None), 1.0)
                rows.append(ParsedRow(
                    raw_line=merged, description=description or "Unknown",
                    amount=parsed["amount"], currency=parsed["currency"],
                    normalized_usd=parsed["normalized_usd"], type=tx_type,
                    transaction_date=tx_date, confidence=confidence,
                    needs_review=confidence < 0.65,
                ))
                i += 2
                continue
            i += 1
        else:
            i += 1
    return rows


# ---------------------------------------------------------------------------
# Strategy D — Single-transaction receipt (e.g. Ziraat Bankası wire transfer)
# ---------------------------------------------------------------------------
# Patterns for extracting amount from receipt-style documents
_RECEIPT_AMOUNT_PATTERNS = [
    # Turkish: "Havale Tutari : 335,00 USD"
    re.compile(r'Havale\s+Tutar[ıi]\s*[:\-]\s*([\d.,]+)\s*([A-Z]{3})', re.IGNORECASE | re.UNICODE),
    # OCR-garbled variants: "eval Tutan 15000 USD", "avale Tutar 150 USD"
    re.compile(r'(?:eval|avale|Havale)\s+Tuta[rn][ıi]?\s*[:\-]?\s*([\d.,]+)\s*([A-Z]{3})', re.IGNORECASE | re.UNICODE),
    # Turkish: "Hesabinizdan 335,06 USD"
    re.compile(r'Hesab[ıi]n[ıi]zdan\s+([\d.,]+)\s*([A-Z]{3})', re.IGNORECASE | re.UNICODE),
    # Arabic: "المبلغ : 500.00 SAR"
    re.compile(r'المبلغ\s*[:\-]\s*([\d.,٠-٩]+)\s*([A-Za-z]{2,4})', re.UNICODE),
    # Generic: "Amount : 500.00 USD"
    re.compile(r'Amount\s*[:\-]\s*([\d.,]+)\s*([A-Z]{3})', re.IGNORECASE),
    # Generic: "Total : 500.00"
    re.compile(r'Total\s*[:\-]\s*([\d.,]+)', re.IGNORECASE),
    # Komisyon line (always present in Ziraat receipts — use as receipt detector)
    re.compile(r'Komisyon\s*[:\-]?\s*[\d.,]+\s*([A-Z]{3})', re.IGNORECASE | re.UNICODE),
]

_RECEIPT_DATE_PATTERNS = [
    # "ISLEM TARIH 03/04/2026-12:56:01" or "guem Tania 2ay04/2026"
    re.compile(r'(?:ISLEM\s+TARIH[İI]?|VALOR|Date|guem\s+Tania|ator)\s*[:\-]?\s*(\d{1,2}[./]\d{1,2}[./]\d{4})', re.IGNORECASE | re.UNICODE),
    # "03/04/2026" standalone
    re.compile(r'\b(\d{1,2}[./]\d{1,2}[./]\d{4})\b'),
    # "23.03.2026" (dot-separated)
    re.compile(r'\b(\d{2}\.\d{2}\.\d{4})\b'),
]

_RECEIPT_DESC_PATTERNS = [
    # "Aciklama : ..." or "Açıklama : ..." or OCR-garbled "Agldama:"
    re.compile(r'A[gcç][ıil][dk]lama\s*[:\-]\s*(.{3,80}?)(?:\s{2,}|\n|$)', re.IGNORECASE | re.UNICODE),
    # "Description : ..."
    re.compile(r'Description\s*[:\-]\s*(.{3,80}?)(?:\s{2,}|\n|$)', re.IGNORECASE),
    # "Alacakli Adi Soyadi : NAME" — capture only the name (up to next field)
    re.compile(r'(?:Alacakl[ıi]\s+Adi\s+Soyadi|call\s+Ad\s+Soyo)\s*[:\-]?\s*([A-Za-z\u0600-\u06FF\s]{3,60}?)(?:\s{2,}|\n|Alacakl|Komisyon|Havale|$)', re.IGNORECASE | re.UNICODE),
]

# Receipt type indicators
_RECEIPT_EXPENSE_INDICATORS = frozenset({
    "hesaptan hesaba havale", "havale", "eft", "transfer", "payment",
    "ödeme", "odeme", "gönderilen", "gonderilen",
    "تحويل", "دفع",
})
_RECEIPT_INCOME_INDICATORS = frozenset({
    "alınan havale", "alinan havale", "gelen havale", "incoming transfer",
    "received", "alındı", "alindi",
    "تحويل وارد", "مستلم",
})


def _strategy_d(lines: list[str]) -> Optional[list[ParsedRow]]:
    """
    Strategy D — Single-transaction receipt parser.

    Handles bank transfer receipts (Ziraat Bankası, etc.) where the document
    contains exactly one transaction with labeled fields like:
      - Havale Tutari : 335,00 USD
      - ISLEM TARIH 03/04/2026
      - Aciklama : ...

    Returns a single ParsedRow or None if this doesn't look like a receipt.
    """
    full_text = " ".join(lines)
    full_lower = full_text.lower()

    # Detect receipt format: must have a labeled amount field
    has_receipt_amount = any(p.search(full_text) for p in _RECEIPT_AMOUNT_PATTERNS)
    if not has_receipt_amount:
        return None

    # ── Extract amount ────────────────────────────────────────────────────────
    amount = None
    currency = "USD"
    for pattern in _RECEIPT_AMOUNT_PATTERNS:
        m = pattern.search(full_text)
        if m:
            groups = m.groups()
            raw_amount = groups[0]
            raw_currency = groups[1] if len(groups) > 1 else "USD"
            from app.ai.parsing.currency_normalizer import _parse_amount_string, _resolve_currency
            amount = _parse_amount_string(raw_amount)
            resolved = _resolve_currency(raw_currency)
            if resolved:
                currency = resolved
            if amount:
                break

    if not amount:
        return None

    # ── Extract date ──────────────────────────────────────────────────────────
    tx_date = None
    for pattern in _RECEIPT_DATE_PATTERNS:
        m = pattern.search(full_text)
        if m:
            date_str = m.group(1)
            tx_date = _parse_date(date_str)
            if tx_date:
                break

    # ── Extract description ───────────────────────────────────────────────────
    description = ""
    # Search line by line for description patterns (more accurate than full_text)
    for line in lines:
        for pattern in _RECEIPT_DESC_PATTERNS:
            m = pattern.search(line)
            if m:
                candidate = m.group(1).strip()
                if len(candidate) >= 3:
                    description = candidate[:80]
                    break
        if description:
            break

    # Fall back to recipient name
    if not description:
        for line in lines:
            recip_m = re.search(r'Alacakl[ıi]\s+Adi\s+Soyadi\s*[:\-]\s*(.+)', line, re.IGNORECASE | re.UNICODE)
            if recip_m:
                description = f"Transfer to {recip_m.group(1).strip()[:60]}"
                break

    if not description:
        description = "Bank Transfer"

    # ── Determine type ────────────────────────────────────────────────────────
    tx_type = "expense"  # default: outgoing transfer
    if any(kw in full_lower for kw in _RECEIPT_INCOME_INDICATORS):
        tx_type = "income"
    elif any(kw in full_lower for kw in _RECEIPT_EXPENSE_INDICATORS):
        tx_type = "expense"

    # ── Build row ─────────────────────────────────────────────────────────────
    from app.ai.parsing.currency_normalizer import extract_amount_and_currency
    parsed = extract_amount_and_currency(f"{amount} {currency}")
    confidence = 0.85 if tx_date else 0.75

    raw_line = next(
        (l for l in lines if re.search(r'Havale\s+Tutar', l, re.IGNORECASE | re.UNICODE)),
        lines[0] if lines else ""
    )

    logger.info(
        f"Strategy D (receipt): amount={amount} {currency} "
        f"type={tx_type} date={tx_date} desc={description!r}"
    )

    return [ParsedRow(
        raw_line         = raw_line,
        description      = description,
        amount           = amount,
        currency         = currency,
        normalized_usd   = parsed.get("normalized_usd", amount),
        type             = tx_type,
        transaction_date = tx_date,
        confidence       = confidence,
        needs_review     = confidence < 0.65,
    )]



def _auto_detect_strategy(lines: list[str]) -> str:
    full_text = " ".join(lines)
    # Check for receipt format first (labeled amount fields)
    for pattern in _RECEIPT_AMOUNT_PATTERNS:
        if pattern.search(full_text):
            return "D"

    amount_only = sum(1 for l in lines if _AMOUNT_ONLY_RE.match(l.strip()))
    total       = len([l for l in lines if l.strip()])
    if total == 0:
        return "B"
    if amount_only / total > 0.3:
        return "C"
    date_amount = sum(
        1 for l in lines
        if _parse_date(l) and extract_amount_and_currency(l)["amount"]
    )
    if total >= 3 and date_amount / total >= 0.4:
        return "A"
    return "B"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def parse_transactions(raw_text: list[str]) -> list[ParsedRow]:
    """
    Parse a list of OCR text lines into structured transaction rows.
    Supports English, Arabic, and Turkish input.

    Strategies (tried in order of specificity):
      D — Single-transaction receipt (Ziraat Bankası, etc.)
      A — Structured table (column-aligned with dates)
      B — Line-by-line
      C — Multi-line merge
    """
    if not raw_text:
        return []

    lines    = [l for l in raw_text if l.strip()]
    strategy = _auto_detect_strategy(lines)
    logger.info(f"transaction_parser: strategy={strategy} lines={len(lines)}")

    if strategy == "D":
        rows = _strategy_d(lines)
        if rows:
            logger.info(f"transaction_parser: {len(rows)} rows from receipt (strategy D)")
            return rows
        logger.debug("Strategy D returned no rows — falling back to B")

    if strategy == "A":
        rows = _strategy_a(lines)
        if rows:
            return rows
        logger.debug("Strategy A returned no rows — falling back to B")

    rows = _strategy_c(lines) if strategy == "C" else _strategy_b(lines)
    logger.info(f"transaction_parser: {len(rows)} rows ({sum(1 for r in rows if r.needs_review)} need review)")
    return rows
