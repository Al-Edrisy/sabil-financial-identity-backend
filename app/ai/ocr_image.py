"""
app/ai/ocr_image.py — Image preprocessing for OCR.

Strategy: generate multiple preprocessed variants and let the OCR caller
pick the one that yields the best results. This is more robust than a
single fixed pipeline, especially for Arabic text and varied lighting.

Variants produced by preprocess_image_variants():
  0 — grayscale + CLAHE only (minimal processing, best for clean scans)
  1 — grayscale + CLAHE + mild threshold (good for printed text)
  2 — grayscale + denoise + CLAHE + adaptive threshold (original pipeline)
  3 — original colour image (EasyOCR handles colour natively)
  4 — deskewed + CLAHE (for tilted documents)

The legacy preprocess_image() still works for backward compatibility —
it now returns variant 0 (CLAHE only) which is gentler on Arabic script.
"""

import cv2
import numpy as np
from typing import Optional
from app.core.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _order_points(pts: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype="float32")
    s    = pts.sum(axis=1)
    rect[0], rect[2] = pts[np.argmin(s)], pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1], rect[3] = pts[np.argmin(diff)], pts[np.argmax(diff)]
    return rect


def _four_point_transform(image: np.ndarray, pts: np.ndarray) -> np.ndarray:
    rect = _order_points(pts)
    tl, tr, br, bl = rect
    mw = max(int(np.linalg.norm(br - bl)), int(np.linalg.norm(tr - tl)))
    mh = max(int(np.linalg.norm(tr - br)), int(np.linalg.norm(tl - bl)))
    if mw <= 0 or mh <= 0:
        return image
    dst = np.array([[0, 0], [mw - 1, 0], [mw - 1, mh - 1], [0, mh - 1]], dtype="float32")
    M   = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, M, (mw, mh))


def correct_perspective(image: np.ndarray) -> np.ndarray:
    """
    Attempt to isolate the document boundary and warp it to a rectangle.
    Falls back to the original image if no clear 4-point contour is found.
    """
    gray    = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged   = cv2.Canny(blurred, 75, 200)
    contours, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) == 4:
            return _four_point_transform(image, approx.reshape(4, 2))
    return image


def deskew(image: np.ndarray) -> np.ndarray:
    """Correct small rotation angles (< 45°) using minAreaRect."""
    gray   = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 5))
    dilated = cv2.dilate(gray, kernel, iterations=2)
    _, thresh = cv2.threshold(dilated, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) == 0:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    if abs(angle) < 0.5:
        return image
    h, w = image.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def normalize_orientation(img_bgr: np.ndarray) -> np.ndarray:
    """
    Rotate landscape images to portrait.

    Most ID documents (passports, national IDs) are portrait-oriented.
    Photos taken of them are often landscape. We rotate any image where
    width > height so the document is upright for face detection and OCR.

    Exception: very wide images (> 2:1) are likely already correct landscape
    documents (e.g. some driver's licenses) — don't rotate those.
    """
    h, w = img_bgr.shape[:2]
    ratio = w / h if h > 0 else 1.0
    # Rotate if landscape (w > h) but not extremely wide (which would be a
    # genuine landscape document like a wide-format bank card)
    if w > h and ratio < 2.0:
        logger.debug(f"normalize_orientation: rotating {w}x{h} (ratio={ratio:.2f}) → portrait")
        return cv2.rotate(img_bgr, cv2.ROTATE_90_CLOCKWISE)
    return img_bgr


# ---------------------------------------------------------------------------
# Scale helper — upscale small images, downscale huge ones
# ---------------------------------------------------------------------------
def _scale_for_ocr(img: np.ndarray, min_width: int = 1200, max_width: int = 1600) -> np.ndarray:
    """
    Ensure image width is in [min_width, max_width].
    - Upscale if too small (poor OCR quality)
    - Downscale if too large (CPU OCR timeout on 2000+ px images)
    """
    h, w = img.shape[:2]
    if w < min_width:
        scale = min_width / w
        img   = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    elif w > max_width:
        scale = max_width / w
        img   = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return img


# Backward-compatible alias
def _upscale(img: np.ndarray, min_width: int = 1200) -> np.ndarray:
    return _scale_for_ocr(img, min_width=min_width, max_width=1600)


# ---------------------------------------------------------------------------
# Multi-variant preprocessing
# ---------------------------------------------------------------------------
def preprocess_image_variants(image_bytes: bytes) -> list[np.ndarray]:
    """
    Return a list of preprocessed image variants for the OCR caller to try.
    The caller should run OCR on each and pick the one with the most/best tokens.

    Variants:
      [0] Grayscale + CLAHE only          — gentlest, best for Arabic
      [1] Grayscale + CLAHE + Otsu        — good for high-contrast printed text
      [2] Grayscale + denoise + adaptive  — original pipeline (aggressive)
      [3] Original colour (upscaled)      — EasyOCR handles colour natively
      [4] Deskewed + CLAHE                — for tilted documents
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return []

    img = _upscale(img, min_width=1200)

    # Variant 3: colour (upscaled only)
    v3 = img.copy()

    # Convert to grayscale for the rest
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Variant 0: CLAHE only
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    v0    = clahe.apply(gray)

    # Variant 1: CLAHE + Otsu threshold
    _, v1 = cv2.threshold(v0, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Variant 2: denoise + CLAHE + adaptive threshold (original pipeline)
    denoised = cv2.medianBlur(gray, 3)
    enhanced = clahe.apply(denoised)
    v2       = cv2.adaptiveThreshold(
        enhanced, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11, 2,
    )

    # Variant 4: deskew + CLAHE
    deskewed = deskew(img)
    gray_d   = cv2.cvtColor(deskewed, cv2.COLOR_BGR2GRAY)
    v4       = clahe.apply(gray_d)

    return [v0, v1, v2, v3, v4]


# ---------------------------------------------------------------------------
# Legacy single-image preprocessor (backward compatible)
# ---------------------------------------------------------------------------
def preprocess_image(image_bytes: bytes) -> Optional[np.ndarray]:
    """
    Legacy entry point used by extract_text_from_id().
    Now returns variant 0 (CLAHE only) — gentler on Arabic script.
    The multi-variant path is used by the new extract_text_from_id_robust().
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    img  = _upscale(img, min_width=1200)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)
