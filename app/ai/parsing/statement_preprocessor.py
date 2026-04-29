"""
app/ai/parsing/statement_preprocessor.py — Image preprocessing tuned for
bank statements and receipts (not ID cards).

Key differences vs KYC preprocessing (ocr_image.py):
  - No perspective correction  — statements are flat A4/letter pages
  - No portrait rotation       — statements are landscape or portrait but not tilted
  - Table line removal         — erases horizontal/vertical grid lines that confuse OCR
  - Column boundary detection  — returns x-ranges for Date | Description | Amount columns
  - Stronger upscaling floor   — statements need ≥ 1500px width for reliable OCR

Reuses:
  - deskew()       from ocr_image.py
  - CLAHE enhance  from ocr_image.py (inline)
"""

import cv2
import numpy as np
from typing import Optional
from app.core.logger import get_logger
from app.ai.ocr_image import deskew

logger = get_logger(__name__)

# Minimum width for reliable OCR on statement text (smaller than ID card threshold)
_MIN_WIDTH = 1500


def _remove_table_lines(gray: np.ndarray) -> np.ndarray:
    """
    Erase horizontal and vertical ruling lines from a bank statement image.
    Uses morphological operations to detect and subtract line structures.
    """
    # Horizontal lines: long, thin structures
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (gray.shape[1] // 10, 1))
    h_lines  = cv2.morphologyEx(gray, cv2.MORPH_OPEN, h_kernel, iterations=2)

    # Vertical lines: tall, thin structures
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, gray.shape[0] // 10))
    v_lines  = cv2.morphologyEx(gray, cv2.MORPH_OPEN, v_kernel, iterations=2)

    # Combine and subtract from original
    lines_mask = cv2.add(h_lines, v_lines)
    cleaned    = cv2.subtract(gray, lines_mask)

    return cleaned


def _detect_column_boundaries(gray: np.ndarray) -> list[tuple[int, int]]:
    """
    Detect vertical column boundaries by finding low-density vertical strips.
    Returns a list of (x_start, x_end) tuples for each detected column.

    Used as a hint to the transaction parser — not required for parsing to work.
    Falls back to [] if detection is unreliable.
    """
    try:
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        # Sum pixel density per column
        col_density = thresh.sum(axis=0).astype(float)
        col_density /= (thresh.shape[0] * 255)  # normalise to 0–1

        # Find gaps (columns with < 2% ink density)
        gap_threshold = 0.02
        in_gap = col_density < gap_threshold

        # Extract gap ranges
        boundaries: list[tuple[int, int]] = []
        col_start = 0
        prev_gap  = False

        for x, is_gap in enumerate(in_gap):
            if is_gap and not prev_gap:
                if x > col_start + 20:  # ignore tiny columns
                    boundaries.append((col_start, x))
                col_start = x
            elif not is_gap and prev_gap:
                col_start = x
            prev_gap = is_gap

        if col_start < gray.shape[1] - 20:
            boundaries.append((col_start, gray.shape[1]))

        return boundaries if len(boundaries) >= 2 else []
    except Exception as e:
        logger.debug(f"Column detection failed (non-critical): {e}")
        return []


def preprocess_statement(image_bytes: bytes) -> Optional[dict]:
    """
    Preprocess a bank statement / receipt image for OCR.

    Args:
        image_bytes: Raw bytes of the uploaded image.

    Returns:
        {
            "processed":  np.ndarray,          # preprocessed grayscale image
            "columns":    list[tuple[int,int]], # detected column x-ranges (may be [])
            "original_shape": tuple[int,int],  # (h, w) before scaling
        }
        or None if the image cannot be decoded.
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        logger.error("statement_preprocessor: failed to decode image bytes")
        return None

    original_shape = img.shape[:2]  # (h, w)

    # ── 1. Deskew (reuse from ocr_image) ─────────────────────────────────────
    img = deskew(img)

    # ── 2. Upscale if too small ───────────────────────────────────────────────
    h, w = img.shape[:2]
    if w < _MIN_WIDTH:
        scale = _MIN_WIDTH / w
        img   = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        logger.debug(f"statement_preprocessor: upscaled {w}→{int(w*scale)}px")

    # ── 3. Convert to grayscale ───────────────────────────────────────────────
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img.copy()

    # ── 4. Remove table lines ─────────────────────────────────────────────────
    gray = _remove_table_lines(gray)

    # ── 5. Detect column boundaries (before binarisation) ────────────────────
    columns = _detect_column_boundaries(gray)

    # ── 6. Denoise ────────────────────────────────────────────────────────────
    gray = cv2.medianBlur(gray, 3)

    # ── 7. CLAHE contrast enhancement ────────────────────────────────────────
    clahe   = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray    = clahe.apply(gray)

    # ── 8. Adaptive threshold (binarise) ─────────────────────────────────────
    processed = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        15, 4,   # larger block size than ID cards — statement text is smaller
    )

    logger.debug(
        f"statement_preprocessor: done — shape={processed.shape} "
        f"columns={len(columns)}"
    )

    return {
        "processed":      processed,
        "columns":        columns,
        "original_shape": original_shape,
    }
