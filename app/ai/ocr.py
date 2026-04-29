"""
app/ai/ocr.py — OCR pipeline entry point.

Multi-variant strategy:
  1. Generate 5 preprocessed variants of the image
  2. Run EasyOCR on each variant
  3. Pick the variant with the highest total confidence × token count score
  4. Extract structured fields from the winning token set

This is significantly more robust than a single fixed preprocessing pipeline,
especially for Arabic text, varied lighting, and different ID card types.

Confidence threshold is lowered to 0.35 for Arabic (EasyOCR scores Arabic
lower than Latin even when the recognition is correct).
"""

from app.core.logger import get_logger
from app.core.config import settings
from app.ai.ocr_image import preprocess_image, preprocess_image_variants
from app.ai.ocr_mrz import (
    parse_mrz,
    _mrz_check_digit,
    validate_mrz_checksums,
    validate_td3_checksums,
    validate_td1_checksums,
)
from app.ai.ocr_fields import extract_fields

# Re-export so tests can import from app.ai.ocr directly
__all__ = [
    "get_ocr_reader",
    "get_statement_ocr_reader",
    "extract_text_from_id",
    "parse_mrz",
    "_mrz_check_digit",
    "validate_mrz_checksums",
    "validate_td3_checksums",
    "validate_td1_checksums",
]

logger = get_logger(__name__)

# Confidence gate — lowered from 0.45 to 0.35 to capture Arabic tokens
# EasyOCR systematically scores Arabic lower than Latin even when correct
OCR_MIN_CONFIDENCE: float = float(getattr(settings, "KYC_OCR_MIN_CONFIDENCE", 0.35))

_reader = None
_statement_reader_latin = None   # en + tr  (Latin-script backbone)
_statement_reader_arabic = None  # en + ar  (Arabic-script backbone)


def get_ocr_reader():
    """KYC reader: English + Arabic."""
    global _reader
    if _reader is None:
        try:
            import easyocr
            _reader = easyocr.Reader(["en", "ar"], gpu=False)
            logger.info("EasyOCR KYC reader initialised (en + ar).")
        except ImportError:
            logger.error("EasyOCR not installed. Run: pip install easyocr")
            return None
    return _reader


def get_statement_ocr_reader():
    """
    Statement readers: returns (latin_reader, arabic_reader).

    EasyOCR constraint: Arabic cannot be combined with Turkish in one reader
    because they use different recognition backbones.

    Solution: two readers, both run on every image, results merged by score.
      - latin_reader:  ["en", "tr"]  — handles English + Turkish
      - arabic_reader: ["en", "ar"]  — handles English + Arabic
    """
    global _statement_reader_latin, _statement_reader_arabic
    try:
        import easyocr
        if _statement_reader_latin is None:
            _statement_reader_latin = easyocr.Reader(["en", "tr"], gpu=False)
            logger.info("EasyOCR statement reader (en + tr) initialised.")
        if _statement_reader_arabic is None:
            _statement_reader_arabic = easyocr.Reader(["en", "ar"], gpu=False)
            logger.info("EasyOCR statement reader (en + ar) initialised.")
    except ImportError:
        logger.error("EasyOCR not installed. Run: pip install easyocr")
        return None, None
    return _statement_reader_latin, _statement_reader_arabic


def _score_results(results: list) -> float:
    """
    Score a set of OCR results: sum of (confidence × text_length) for all
    tokens above the minimum threshold. Higher = better variant.
    """
    return sum(
        res[2] * len(res[1])
        for res in results
        if res[2] >= OCR_MIN_CONFIDENCE and res[1].strip()
    )


def _run_ocr_best_variant(reader, image_bytes: bytes) -> list:
    """
    Run OCR on all preprocessing variants and return the token list from
    the variant that scores highest.
    """
    variants = preprocess_image_variants(image_bytes)
    if not variants:
        return []

    best_results = []
    best_score   = -1.0

    for i, variant in enumerate(variants):
        try:
            results = reader.readtext(variant, detail=1, paragraph=False)
            score   = _score_results(results)
            logger.debug(
                f"OCR variant {i}: {len(results)} tokens, "
                f"score={score:.1f}, "
                f"accepted={sum(1 for r in results if r[2] >= OCR_MIN_CONFIDENCE)}"
            )
            if score > best_score:
                best_score   = score
                best_results = results
        except Exception as exc:
            logger.warning(f"OCR variant {i} failed: {exc}")
            continue

    logger.info(
        f"OCR best variant score={best_score:.1f}, "
        f"total_tokens={len(best_results)}, "
        f"accepted={sum(1 for r in best_results if r[2] >= OCR_MIN_CONFIDENCE)}"
    )
    return best_results


def extract_text_from_id(image_bytes: bytes, id_type: str = "national_id") -> dict:
    """
    Full OCR pipeline for a KYC identity document.
    Uses multi-variant preprocessing to maximise extraction quality.
    """
    reader = get_ocr_reader()
    if not reader:
        return {"error": "OCR engine not available"}

    try:
        all_results = _run_ocr_best_variant(reader, image_bytes)

        if not all_results:
            return {"error": "Failed to decode or process image"}

        accepted   = [res for res in all_results if res[2] >= OCR_MIN_CONFIDENCE]
        raw_texts  = [res[1] for res in accepted]

        ocr_tokens = [
            {
                "text":       res[1],
                "confidence": float(res[2]),
                "bbox":       [[int(p[0]), int(p[1])] for p in res[0]],
            }
            for res in accepted
        ]

        extracted = {
            "raw_text":   raw_texts,
            "ocr_tokens": ocr_tokens,
            **extract_fields(raw_texts, id_type),
        }

        # ── MRZ overlay ───────────────────────────────────────────────────────
        mrz = parse_mrz(raw_texts)
        if mrz:
            extracted["mrz"]         = mrz
            extracted["full_name"]   = mrz.get("mrz_full_name")   or extracted.get("full_name")
            extracted["id_number"]   = mrz.get("mrz_doc_number")  or extracted.get("id_number")
            extracted["dob"]         = mrz.get("mrz_dob")         or extracted.get("dob")
            extracted["expiry_date"] = mrz.get("mrz_expiry")      or extracted.get("expiry_date")
            extracted["nationality"] = mrz.get("mrz_nationality") or extracted.get("nationality")
            extracted["country"]     = mrz.get("mrz_country")     or extracted.get("country")
            extracted["gender"]      = mrz.get("mrz_sex")         or extracted.get("gender")

        logger.info(
            f"OCR complete [id_type={id_type}]: "
            f"tokens={len(accepted)} "
            f"name={'✓' if extracted.get('full_name')   else '✗'} "
            f"id={'✓'   if extracted.get('id_number')   else '✗'} "
            f"dob={'✓'  if extracted.get('dob')         else '✗'} "
            f"expiry={'✓' if extracted.get('expiry_date') else '✗'}"
        )
        return extracted

    except Exception as exc:
        logger.error(f"OCR processing failed: {exc}", exc_info=True)
        return {"error": str(exc)}
