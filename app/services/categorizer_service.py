"""
app/services/categorizer_service.py — Fuzzy-match transaction descriptions
to a predefined category taxonomy using rapidfuzz.

Supports English, Arabic, and Turkish keywords.

Categories:
  freelance, salary, subscription, rent, utilities, food,
  transfer, refund, investment, healthcare, education, transport, other
"""

from rapidfuzz import process, fuzz
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Category → keyword list (English + Arabic + Turkish)
# ---------------------------------------------------------------------------
CATEGORY_MAP: dict[str, list[str]] = {
    "freelance": [
        # English
        "upwork", "fiverr", "toptal", "freelancer", "freelance",
        "consulting", "contract", "project payment", "client payment",
        "99designs", "guru", "people per hour", "bionluk",
        # Arabic
        "مستقل", "عمل حر", "مشروع",
        # Turkish
        "serbest çalışma", "serbest calısma", "danışmanlık", "danismanlik",
        "proje ödemesi", "proje odemesi",
    ],
    "salary": [
        # English
        "salary", "payroll", "wage", "wages", "employer", "paycheck",
        "monthly salary", "bi-weekly", "payslip",
        # Arabic
        "راتب", "أجر", "مرتب", "رواتب",
        # Turkish
        "maaş", "maas", "ücret", "ucret", "bordro", "aylık", "aylik",
        "maaş ödemesi", "maas odemesi",
    ],
    "subscription": [
        # English
        "adobe", "netflix", "spotify", "amazon prime", "apple",
        "google", "microsoft", "dropbox", "slack", "zoom",
        "github", "notion", "figma", "canva", "subscription",
        "monthly plan", "annual plan", "youtube premium",
        "disney plus", "hbo", "paramount",
        # Arabic
        "اشتراك", "اشتراكات",
        # Turkish
        "abonelik", "aylık plan", "yıllık plan", "yillik plan",
        "üyelik", "uyelik",
    ],
    "rent": [
        # English
        "rent", "lease", "housing", "apartment", "flat",
        "landlord", "property", "accommodation",
        # Arabic
        "إيجار", "سكن", "شقة", "عقار",
        # Turkish
        "kira", "kiralık", "kiralik", "konut", "daire", "ev kirası",
        "ev kirasi",
    ],
    "utilities": [
        # English
        "electricity", "water", "internet", "phone bill", "gas",
        "utility", "sewage", "cable", "broadband", "mobile bill",
        # Arabic
        "كهرباء", "ماء", "إنترنت", "هاتف", "غاز", "مياه",
        # Turkish
        "elektrik", "su faturası", "su faturasi", "internet faturası",
        "internet faturasi", "telefon faturası", "telefon faturasi",
        "doğalgaz", "dogalgaz", "ttnet", "turkcell", "vodafone",
        "türk telekom", "turk telekom",
    ],
    "food": [
        # English
        "restaurant", "cafe", "coffee", "grocery", "supermarket",
        "food", "dining", "lunch", "dinner", "breakfast",
        "takeaway", "delivery", "starbucks", "mcdonalds", "kfc",
        # Arabic
        "مطعم", "بقالة", "طعام", "قهوة", "وجبة", "سوبرماركت",
        # Turkish
        "restoran", "kafe", "kahve", "market", "süpermarket",
        "supermarket", "yemek", "migros", "carrefour", "bim",
        "a101", "şok", "sok", "getir", "yemeksepeti",
    ],
    "transfer": [
        # English
        "transfer", "wire", "remittance", "send money", "bank transfer",
        "international transfer", "western union", "moneygram",
        # Arabic
        "تحويل", "حوالة", "إرسال",
        # Turkish
        "havale", "eft", "swift", "para transferi", "para gönderme",
        "para gonderme",
    ],
    "refund": [
        # English
        "refund", "cashback", "return", "reversal", "chargeback",
        # Arabic
        "استرداد", "إعادة", "رد",
        # Turkish
        "iade", "geri ödeme", "geri odeme", "para iadesi",
    ],
    "investment": [
        # English
        "investment", "stock", "shares", "dividend", "crypto",
        "bitcoin", "trading", "brokerage", "fund", "etf",
        # Arabic
        "استثمار", "أسهم", "توزيعات", "صندوق",
        # Turkish
        "yatırım", "yatirim", "hisse", "temettü", "temettu",
        "borsa", "fon", "kripto",
    ],
    "healthcare": [
        # English
        "hospital", "clinic", "pharmacy", "doctor", "medical",
        "health", "dental", "vision", "insurance",
        # Arabic
        "مستشفى", "صيدلية", "طبيب", "تأمين صحي", "عيادة",
        # Turkish
        "hastane", "eczane", "doktor", "sağlık", "saglik",
        "sigorta", "diş", "dis", "göz", "goz", "muayene",
    ],
    "education": [
        # English
        "university", "school", "tuition", "course", "training",
        "udemy", "coursera", "books", "education",
        # Arabic
        "جامعة", "مدرسة", "تعليم", "دورة", "كتب",
        # Turkish
        "üniversite", "universite", "okul", "eğitim", "egitim",
        "kurs", "udemy", "kitap", "öğrenim", "ogrenim",
    ],
    "transport": [
        # English
        "uber", "taxi", "bus", "metro", "train", "flight",
        "airline", "fuel", "petrol", "gas station", "parking",
        # Arabic
        "أوبر", "تاكسي", "حافلة", "مترو", "قطار", "طيران", "وقود",
        # Turkish
        "uber", "taksi", "otobüs", "otobus", "metro", "tren",
        "uçak", "ucak", "yakıt", "yakit", "benzin", "otopark",
        "iett", "marmaray",
    ],
    "other": [],  # fallback — never matched directly
}

# Flatten to (keyword, category) pairs for rapidfuzz lookup
_KEYWORD_CATEGORY: list[tuple[str, str]] = [
    (kw, cat)
    for cat, keywords in CATEGORY_MAP.items()
    for kw in keywords
]
_ALL_KEYWORDS: list[str] = [kw for kw, _ in _KEYWORD_CATEGORY]
_KEYWORD_TO_CATEGORY: dict[str, str] = {kw: cat for kw, cat in _KEYWORD_CATEGORY}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def categorize(description: str) -> tuple[str, float]:
    """
    Categorize a single transaction description.
    Supports English, Arabic, and Turkish input.

    Returns:
        (category: str, score: float 0–100)
        Falls back to ("other", 0.0) when below threshold.
    """
    if not description or not description.strip():
        return "other", 0.0

    threshold = settings.CREDIT_CATEGORIZER_THRESHOLD

    result = process.extractOne(
        description.lower(),
        _ALL_KEYWORDS,
        scorer=fuzz.partial_ratio,
        score_cutoff=threshold,
    )

    if result is None:
        return "other", 0.0

    matched_keyword, score, _ = result
    category = _KEYWORD_TO_CATEGORY.get(matched_keyword, "other")

    logger.debug(
        f"categorizer: '{description[:40]}' → '{category}' "
        f"(kw='{matched_keyword}' score={score:.0f})"
    )
    return category, float(score)


def categorize_many(descriptions: list[str]) -> list[tuple[str, float]]:
    """Batch categorize. Returns (category, score) tuples in the same order."""
    return [categorize(d) for d in descriptions]
