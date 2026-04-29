"""
app/ai/document_check.py — Lightweight heuristic ID document authenticity checks.

These checks are a fast, cheap first pass to catch obviously invalid submissions.
They are NOT a substitute for a forensic document-analysis model.

Checks performed:
  1. Resolution     — image must be large enough for reliable OCR (≥ 200×200 px)
  2. Aspect ratio   — must fall within the expected range for the claimed id_type
  3. Field presence — id_number must be present in OCR output
  4. Name presence  — full_name is a soft check (warns, does not hard-fail)
  5. MRZ checksum   — passports only; hard-fails on a present-but-invalid checksum

Future improvements:
  - Integrate a fine-tuned ResNet/EfficientNet classifier for forgery detection.
  - Add expected field-position heatmaps per document template.
"""

import cv2
import numpy as np
from datetime import datetime, timezone
from app.core.logger import get_logger
from app.ai.ocr_image import correct_perspective

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Expected aspect ratios (width / height) per document type
# ---------------------------------------------------------------------------
# ID-1 (credit-card format): 85.6 mm × 54 mm ≈ 1.585
# Passport bio-data page:    portrait, roughly 0.65–0.85
# Driver's licence:          same as ID-1
_ASPECT_RANGES: dict[str, tuple[float, float]] = {
    "national_id":      (1.35, 1.80),
    "drivers_license":  (1.35, 1.80),
    "residence_permit": (1.35, 1.80),
    "passport":         (0.60, 0.90),   # portrait orientation
}

# Minimum pixel count — anything smaller won't OCR reliably
_MIN_PIXELS = 200 * 200   # 200 × 200


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def check_document_authenticity(
    image_bytes: bytes,
    ocr_result: dict,
    id_type: str = "national_id",
) -> dict:
    """
    Run heuristic authenticity checks on a KYC document image.

    Args:
        image_bytes: Raw bytes of the uploaded document image.
        ocr_result:  Dict returned by extract_text_from_id().
        id_type:     Claimed document type (mirrors IDType enum).

    Returns:
        {
          "passed":  bool,    # False only on hard failures (resolution / missing ID)
          "score":   float,   # 0.0–1.0 composite (equal weight per check)
          "checks":  dict,    # per-check boolean results
          "reason":  str | None,
        }
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    checks:  dict[str, bool] = {}
    reasons: list[str]       = []

    # ── 1. Decodability ───────────────────────────────────────────────────────
    if img is None:
        return {
            "passed": False, "score": 0.0,
            "checks": {"decodable": False},
            "reason": "Document image could not be decoded",
        }
    checks["decodable"] = True

    # ── Normalize orientation before aspect ratio check ───────────────────────
    # A landscape photo of a portrait passport should be rotated first.
    from app.ai.ocr_image import normalize_orientation as _norm_orient
    img = _norm_orient(img)

    h, w = img.shape[:2]

    # ── 2. Resolution ─────────────────────────────────────────────────────────
    checks["resolution"] = (h * w) >= _MIN_PIXELS
    if not checks["resolution"]:
        reasons.append(f"Image too small ({w}×{h} px); expected ≥ 200×200")

    # ── 3. Aspect ratio (on perspective-corrected crop) ───────────────────────
    img_rect   = correct_perspective(img)
    h_c, w_c   = img_rect.shape[:2]
    aspect     = (w_c / h_c) if h_c > 0 else 0.0
    lo, hi     = _ASPECT_RANGES.get(id_type, (0.5, 2.5))
    checks["aspect_ratio"] = lo <= aspect <= hi
    if not checks["aspect_ratio"]:
        # Soft warning only — don't hard-fail on aspect ratio alone
        # (photos taken at an angle or with background will fail this)
        reasons.append(
            f"Document aspect ratio {aspect:.2f} unexpected for '{id_type}' "
            f"(expected {lo:.2f}–{hi:.2f}) — soft warning"
        )

    # ── 4. ID number extracted ────────────────────────────────────────────────
    checks["id_number_found"] = bool(ocr_result.get("id_number"))
    if not checks["id_number_found"]:
        reasons.append("No ID number could be extracted by OCR")

    # ── 5. Name extracted (soft) ──────────────────────────────────────────────
    checks["name_found"] = bool(ocr_result.get("full_name"))
    if not checks["name_found"]:
        reasons.append("No name could be extracted by OCR (soft warning)")

    # ── 6. Passport: MRZ checksum validation (hard failure on forgery) ─────────
    mrz_checksum_failed = False  # tracks an explicit failure (not just absence)
    if id_type == "passport":
        mrz = ocr_result.get("mrz")  # populated by parse_mrz() in ocr.py
        if mrz is not None:
            # mrz_checksum_valid is set by the updated parse_mrz(); it is
            # True only when ALL five ICAO TD3 check digits match.
            checksum_valid = mrz.get("mrz_checksum_valid")
            if checksum_valid is True:
                checks["mrz_checksum"] = True
                logger.info("doc_check [passport]: MRZ checksum PASSED")
            elif checksum_valid is False:
                checks["mrz_checksum"] = False
                mrz_checksum_failed    = True  # definitive evidence of tampering
                reasons.append(
                    "MRZ checksum FAILED — document may be forged or tampered; "
                    f"detail={mrz.get('mrz_checksum_detail', {})}"
                )
                logger.warning(
                    "doc_check [passport]: MRZ checksum FAILED — hard-failing document"
                )
            else:
                # mrz_checksum_valid key missing (old-format dict); treat as absent
                logger.debug("doc_check [passport]: mrz_checksum_valid not present in MRZ dict")
        else:
            # MRZ sub-dict absent — OCR likely missed it; soft warning only
            logger.debug("doc_check [passport]: MRZ not found in OCR result (soft)")

    # ── 7. id_type validation (cross-check against content) ───────────────────
    # If user claims 'passport' but no MRZ was found, it's a high-risk mismatch.
    has_mrz = bool(ocr_result.get("mrz"))
    checks["id_type_match"] = True  # default

    if id_type == "passport" and not has_mrz:
        if checks.get("id_number_found"):
            reasons.append("Claimed 'passport' but no MRZ found (soft warning, ID number extracted)")
            logger.warning(f"[user] expected passport MRZ but none found (ID number was extracted, passing)")
        else:
            checks["id_type_match"] = False
            reasons.append("Claimed 'passport' but no Machine Readable Zone (MRZ) found")
            logger.warning(f"[user] id_type mismatch: expected passport MRZ but none found")
    elif id_type != "passport" and has_mrz:
        # Some modern NIDs and Residence Permits have MRZs. We log it but
        # do NOT hard-fail, as it's not a definitive mismatch.
        logger.debug(f"doc_check: id_type is '{id_type}' and MRZ was detected (permissible)")

    # ── 8. Expiry Validation ──────────────────────────────────────────────────
    expiry_raw = ocr_result.get("expiry_date")
    checks["not_expired"] = True
    if expiry_raw:
        try:
            # Handle YYYY-MM-DD (MRZ) or DD/MM/YYYY (Regex) or YYYY/MM/DD
            exp_date = None
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%d.%m.%Y"):
                try:
                    exp_date = datetime.strptime(expiry_raw, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            
            if exp_date and exp_date < datetime.now(timezone.utc):
                checks["not_expired"] = False
                reasons.append(f"Document expired on {exp_date.date()}")
                logger.warning(f"doc_check: document is expired (expiry={expiry_raw})")
        except Exception as e:
            logger.debug(f"doc_check: could not parse expiry date '{expiry_raw}': {e}")


    # ── Composite score ───────────────────────────────────────────────────────
    scored = ["resolution", "aspect_ratio", "id_number_found", "name_found", "id_type_match", "not_expired"]
    if "mrz_checksum" in checks:
        scored.append("mrz_checksum")
    score  = sum(1 for k in scored if checks.get(k, False)) / len(scored)

    # Hard-fail: resolution, ID number, type-match, expiry, and MRZ checksum.
    # Aspect ratio is a soft check — photos taken at angles will fail it.
    passed = (
        checks["resolution"]
        and checks["id_number_found"]
        and checks["id_type_match"]
        and checks["not_expired"]
        and not mrz_checksum_failed
    )

    logger.debug(
        f"doc_check [{id_type}]: passed={passed}  score={score:.2f}  "
        f"aspect={aspect:.2f}  id_found={checks['id_number_found']}"
        + (f"  mrz_checksum={checks.get('mrz_checksum', 'n/a')}" if id_type == "passport" else "")
    )

    return {
        "passed": passed,
        "score":  round(score, 3),
        "checks": checks,
        "reason": "; ".join(reasons) if reasons else None,
    }
