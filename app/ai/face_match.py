"""
app/ai/face_match.py — Face detection, liveness check, and face comparison.

Detection:  Haar cascade (fast) with DeepFace opencv fallback.
Matching:   DeepFace.verify (VGG-Face model).
Liveness:   Heuristic — Laplacian variance + FFT mid-frequency analysis.

⚠️  Static-image liveness is inherently limited.  A production-grade
    anti-spoofing system requires video frames or depth data.  These checks
    raise the bar against naive photo-of-photo attacks but should be
    complemented by a dedicated anti-spoofing model for high-risk flows.
"""

import cv2
import numpy as np
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _bytes_to_bgr(b: bytes) -> np.ndarray | None:
    nparr = np.frombuffer(b, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)


def normalize_orientation(img_bgr: np.ndarray) -> np.ndarray:
    """
    Rotate an image to portrait ONLY if it is clearly landscape
    (width significantly greater than height, ratio > 1.3).

    A selfie at 941×863 (ratio 1.09) is essentially square — don't rotate.
    A passport photo at 2032×1428 (ratio 1.42) is landscape — rotate.

    Threshold 1.3 avoids rotating near-square selfies while still
    correcting genuinely sideways ID card photos.
    """
    h, w = img_bgr.shape[:2]
    ratio = w / h if h > 0 else 1.0
    if ratio > 1.3:
        logger.debug(f"normalize_orientation: rotating {w}x{h} (ratio={ratio:.2f}) → portrait")
        return cv2.rotate(img_bgr, cv2.ROTATE_90_CLOCKWISE)
    return img_bgr


def _upscale_face(crop: np.ndarray, target: int = 224) -> np.ndarray:
    """
    Upscale a face crop to at least target×target pixels.
    VGG-Face and most DeepFace models expect ≥ 224×224 input.
    Small crops (e.g. 134×134 from a passport photo) produce poor match scores.
    """
    h, w = crop.shape[:2]
    if h < target or w < target:
        scale = max(target / h, target / w)
        crop  = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        logger.debug(f"_upscale_face: {w}x{h} → {crop.shape[1]}x{crop.shape[0]}")
    return crop


# ---------------------------------------------------------------------------
# ID face crop — isolate the photo region before comparison
# ---------------------------------------------------------------------------
def crop_id_face(img_bgr: np.ndarray) -> np.ndarray:
    """
    Detect and crop the face region from an ID / passport image.

    Strategy (in order — fastest first):
      1. Haar cascade       — fast, reliable for clear passport photos
      2. DeepFace opencv    — slower but handles more face orientations
      3. Full image fallback — last resort

    The largest detected face is always preferred to avoid false positives
    from MRZ text patterns and background noise.

    The returned crop is upscaled to ≥ 224×224 for VGG-Face compatibility.
    """
    img_bgr = normalize_orientation(img_bgr)

    # ── Attempt 1: Haar cascade (fast, permissive for passport photos) ────────
    try:
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        # Use permissive settings — passport photos are small and low-contrast
        detected = cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=3, minSize=(20, 20)
        )
        if len(detected) > 0:
            # Use the largest face (most likely the real passport photo)
            x, y, w, h = max(detected, key=lambda r: r[2] * r[3])
            # Add 20% padding around the face for better matching
            pad_x = int(w * 0.2)
            pad_y = int(h * 0.2)
            h_img, w_img = img_bgr.shape[:2]
            x1 = max(0, x - pad_x)
            y1 = max(0, y - pad_y)
            x2 = min(w_img, x + w + pad_x)
            y2 = min(h_img, y + h + pad_y)
            crop = img_bgr[y1:y2, x1:x2]
            crop = _upscale_face(crop)
            logger.debug(f"crop_id_face: Haar {w}x{h} at ({x},{y}) → crop {crop.shape[1]}x{crop.shape[0]}")
            return crop
    except Exception as exc:
        logger.warning(f"crop_id_face Haar error: {exc}")

    # ── Attempt 2: DeepFace opencv (fallback) ─────────────────────────────────
    try:
        from deepface import DeepFace
        faces = DeepFace.extract_faces(
            img_path=img_bgr,
            detector_backend="opencv",
            enforce_detection=False,
            align=False,
        )
        # Filter out the whole-image fallback (confidence=0, covers full image)
        h_img, w_img = img_bgr.shape[:2]
        valid = [
            f for f in faces
            if f.get("confidence", 0.0) >= 0.50
            and f.get("facial_area", {}).get("w", w_img) < w_img * 0.9
        ]
        if valid:
            best = max(valid, key=lambda f: (
                f.get("facial_area", {}).get("w", 0) *
                f.get("facial_area", {}).get("h", 0)
            ))
            area = best.get("facial_area", {})
            x, y, fw, fh = area.get("x", 0), area.get("y", 0), area.get("w", 0), area.get("h", 0)
            if fw > 0 and fh > 0:
                crop = img_bgr[y:y+fh, x:x+fw]
                crop = _upscale_face(crop)
                logger.debug(f"crop_id_face: DeepFace opencv {fw}x{fh} → {crop.shape[1]}x{crop.shape[0]}")
                return crop
    except Exception as exc:
        logger.debug(f"crop_id_face DeepFace opencv: {exc}")

    logger.warning("crop_id_face: no face found — using full image (match accuracy reduced)")
    return img_bgr


# ---------------------------------------------------------------------------
# Face count validation
# ---------------------------------------------------------------------------
def count_faces(image_bytes: bytes, label: str = "image") -> int:
    """
    Return the number of faces detected in *image_bytes*.

    For KYC purposes:
    - Selfie: must have exactly 1 face
    - ID card: must have at least 1 face

    We use the LARGEST detected face as the primary signal — Haar cascades
    produce false positives on document backgrounds. The largest face is
    almost always the real one.

    Returns:
        int >= 0  — number of plausible faces (using largest-face heuristic)
        -1        — detector error (caller should treat as "unknown")
    """
    img = _bytes_to_bgr(image_bytes)
    if img is None:
        logger.error(f"count_faces: could not decode image [{label}]")
        return -1

    # Normalize orientation first — landscape photos of portrait documents
    # confuse face detectors
    img = normalize_orientation(img)

    # ── Attempt 1: DeepFace (opencv backend) ─────────────────────────────────
    try:
        from deepface import DeepFace
        faces = DeepFace.extract_faces(
            img_path=img,
            detector_backend="opencv",
            enforce_detection=False,
        )
        # Filter to plausible detections
        threshold = 0.50
        valid = [f for f in faces if f.get("confidence", 1.0) >= threshold]

        if valid:
            # For ID cards: if multiple faces detected, count only the largest
            # (passport photo + background noise is common)
            if len(valid) > 1 and label == "id_card":
                largest = max(valid, key=lambda f: (
                    f.get("facial_area", {}).get("w", 0) *
                    f.get("facial_area", {}).get("h", 0)
                ))
                count = 1 if largest.get("confidence", 0) >= threshold else 0
            else:
                count = len(valid)
            logger.debug(f"count_faces [{label}]: {count} face(s) via DeepFace (from {len(faces)} detections)")
            return count
        # DeepFace returned 0 valid faces — fall through to Haar
        logger.debug(f"count_faces [{label}]: DeepFace found no confident faces, trying Haar")
    except ImportError:
        pass
    except Exception as exc:
        logger.warning(f"count_faces DeepFace error [{label}]: {exc}")

    # ── Attempt 2: OpenCV Haar cascade fallback ───────────────────────────────
    try:
        cascade  = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        gray     = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Use lower minNeighbors for ID cards — passport photos are small
        # and low-contrast, requiring a more permissive detector
        min_neighbors = 3 if label == "id_card" else 5
        detected = cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=min_neighbors, minSize=(20, 20)
        )

        if len(detected) == 0:
            logger.debug(f"count_faces [{label}]: 0 faces via Haar")
            return 0

        # For ID cards: use only the largest face to avoid false positives
        if label == "id_card" and len(detected) > 1:
            largest = max(detected, key=lambda r: r[2] * r[3])
            count = 1
            logger.debug(f"count_faces [{label}]: using largest of {len(detected)} Haar faces ({largest[2]}x{largest[3]}px)")
        else:
            count = len(detected)
            logger.debug(f"count_faces [{label}]: {count} face(s) via Haar")

        return count
    except Exception as exc:
        logger.error(f"count_faces Haar error [{label}]: {exc}")
        return -1


# ---------------------------------------------------------------------------
# Liveness / anti-spoofing (heuristic, static-image only)
# ---------------------------------------------------------------------------
def check_liveness(image_bytes: bytes) -> dict:
    """
    Heuristic liveness estimation from a single static selfie image.

    Two signals are combined:

    Signal 1 — Sharpness (Laplacian variance)
        A photo of a printed page or a screen is often softer than a directly
        captured real-face selfie.  Threshold is configurable via
        settings.KYC_LIVENESS_MIN_VARIANCE (default 80).

    Signal 2 — Frequency regularity (FFT mid-band ratio)
        Printed/screen surfaces introduce periodic moiré patterns.  We measure
        the fraction of DFT energy in the 10–40 % mid-frequency ring; a high
        ratio (> 0.55) suggests a repeating screen/print artefact.

    Returns:
        {
          "passed":          bool,
          "score":           float,   # Laplacian variance (main signal)
          "sharpness_score": float,
          "frequency_score": float,   # 0–1; higher = cleaner spectrum
          "reason":          str | None,
        }
    """
    img = _bytes_to_bgr(image_bytes)
    if img is None:
        return {
            "passed": False, "score": 0.0,
            "sharpness_score": 0.0, "frequency_score": 0.0,
            "reason": "Image decode failed",
        }

    # ── Normalize and Crop to Face ────────────────────────────────────────────
    # We crop to the face region because background textures (walls, fabric)
    # can pollute both the sharpness (Laplacian) and frequency (FFT) signals.
    img = normalize_orientation(img)
    
    # Lightweight face detection for liveness crop
    face_img = img
    try:
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        gray_full = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray_full, 1.3, 5)
        if len(faces) > 0:
            x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
            face_img = img[y:y+h, x:x+w]
            logger.debug(f"check_liveness: Isolated face region ({w}x{h})")
    except Exception as e:
        logger.warning(f"check_liveness crop failed: {e}")

    gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)

    # ── Signal 1: Laplacian variance ──────────────────────────────────────────
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # ── Signal 2: FFT mid-frequency energy ratio ──────────────────────────────
    dft       = np.fft.fft2(gray.astype(np.float32))
    magnitude = np.log1p(np.abs(np.fft.fftshift(dft)))
    h, w      = magnitude.shape
    cy, cx    = h // 2, w // 2
    Y, X      = np.ogrid[:h, :w]
    dist      = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    r_max     = min(cx, cy)
    mid_mask  = (dist >= 0.10 * r_max) & (dist <= 0.40 * r_max)

    total_energy   = magnitude.sum() or 1.0
    mid_ratio      = float(magnitude[mid_mask].sum() / total_energy)
    # A real photo has mid_ratio ≈ 0.25–0.45; screen/print pushes it above 0.55.
    # Score inversely: 1.0 = perfectly clean, 0.0 = strong artefact.
    frequency_score = max(0.0, 1.0 - max(0.0, mid_ratio - 0.45) / 0.20)

    # ── Decision ──────────────────────────────────────────────────────────────
    min_var = settings.KYC_LIVENESS_MIN_VARIANCE
    min_freq = getattr(settings, "KYC_LIVENESS_FREQ_THRESHOLD", 0.5)
    
    sharp_ok = lap_var >= min_var
    freq_ok  = frequency_score >= min_freq
    passed   = sharp_ok and freq_ok

    reason = None
    if not sharp_ok:
        reason = f"Image too blurry (sharpness={lap_var:.1f}, required≥{min_var})"
    elif not freq_ok:
        reason = f"Possible screen/print artefact (frequency_score={frequency_score:.2f})"

    logger.debug(
        f"Liveness: passed={passed}  sharpness={lap_var:.1f}  freq={frequency_score:.2f}"
    )
    return {
        "passed":          passed,
        "score":           lap_var,
        "sharpness_score": lap_var,
        "frequency_score": frequency_score,
        "reason":          reason,
    }


# ---------------------------------------------------------------------------
# Face comparison
# ---------------------------------------------------------------------------
def _face_similarity_opencv(face1: np.ndarray, face2: np.ndarray) -> float:
    """
    Compute face similarity using multiple OpenCV-only signals.
    Returns a confidence score 0.0–1.0.

    Methods combined (weighted ensemble):
      1. Normalized Cross-Correlation on grayscale face crops (structural)
      2. Histogram correlation on YCrCb color space (skin tone / color)
      3. SIFT feature matching (local keypoint descriptors)
      4. LBP (Local Binary Pattern) texture histogram similarity

    This is a best-effort approach when DeepFace/face_recognition is
    unavailable. For production, install deepface or face-recognition.
    """
    SIZE = (128, 128)
    f1 = cv2.resize(face1, SIZE)
    f2 = cv2.resize(face2, SIZE)

    scores = []

    # ── 1. Normalized Cross-Correlation (grayscale structural similarity) ─────
    try:
        g1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY).astype(np.float32)
        g2 = cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY).astype(np.float32)
        g1 -= g1.mean(); g2 -= g2.mean()
        n1, n2 = np.linalg.norm(g1), np.linalg.norm(g2)
        if n1 > 0 and n2 > 0:
            ncc = float(np.dot(g1.flatten(), g2.flatten()) / (n1 * n2))
            # NCC range: -1 to 1 → map to 0–1
            scores.append(("ncc", (ncc + 1.0) / 2.0, 0.35))
    except Exception:
        pass

    # ── 2. YCrCb histogram correlation (skin tone / color distribution) ───────
    try:
        y1 = cv2.cvtColor(f1, cv2.COLOR_BGR2YCrCb)
        y2 = cv2.cvtColor(f2, cv2.COLOR_BGR2YCrCb)
        # Use Cr and Cb channels (skin-tone invariant to lighting)
        hist_scores = []
        for ch in [1, 2]:
            h1 = cv2.calcHist([y1], [ch], None, [32], [0, 256])
            h2 = cv2.calcHist([y2], [ch], None, [32], [0, 256])
            cv2.normalize(h1, h1); cv2.normalize(h2, h2)
            corr = cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL)
            hist_scores.append(max(0.0, float(corr)))
        scores.append(("hist_ycrcb", sum(hist_scores) / len(hist_scores), 0.30))
    except Exception:
        pass

    # ── 3. SIFT feature matching ──────────────────────────────────────────────
    # Note: SIFT is unreliable on upscaled low-res passport photos.
    # Use a lower weight and only include if meaningful keypoints found.
    try:
        sift = cv2.SIFT_create(nfeatures=300)
        g1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
        g2 = cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY)
        kp1, des1 = sift.detectAndCompute(g1, None)
        kp2, des2 = sift.detectAndCompute(g2, None)
        # Only use SIFT if both images have enough keypoints to be meaningful
        if (des1 is not None and des2 is not None
                and len(des1) >= 10 and len(des2) >= 10):
            bf = cv2.BFMatcher(cv2.NORM_L2)
            matches = bf.knnMatch(des1, des2, k=2)
            good = [m for m, n in matches if m.distance < 0.75 * n.distance]
            max_possible = min(len(kp1), len(kp2))
            sift_score = min(1.0, len(good) / max(max_possible * 0.10, 1))
            scores.append(("sift", sift_score, 0.15))   # reduced weight
        # If too few keypoints (upscaled low-res), skip SIFT entirely
    except Exception:
        pass

    # ── 4. LBP texture histogram ──────────────────────────────────────────────
    try:
        def _lbp_hist(img_gray):
            """Simplified LBP using pixel comparisons."""
            h, w = img_gray.shape
            lbp = np.zeros_like(img_gray, dtype=np.uint8)
            for dy, dx in [(-1,-1),(-1,0),(-1,1),(0,1),(1,1),(1,0),(1,-1),(0,-1)]:
                shifted = np.roll(np.roll(img_gray, dy, axis=0), dx, axis=1)
                lbp = (lbp << 1) | (img_gray >= shifted).astype(np.uint8)
            hist, _ = np.histogram(lbp, bins=32, range=(0, 256))
            hist = hist.astype(np.float32)
            hist /= (hist.sum() + 1e-8)
            return hist

        g1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
        g2 = cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY)
        lbp1 = _lbp_hist(g1)
        lbp2 = _lbp_hist(g2)
        # Chi-squared distance → similarity
        chi2 = float(np.sum((lbp1 - lbp2) ** 2 / (lbp1 + lbp2 + 1e-8)))
        lbp_sim = max(0.0, 1.0 - chi2 / 2.0)
        scores.append(("lbp", lbp_sim, 0.20))
    except Exception:
        pass

    if not scores:
        return 0.0

    # Weighted average
    total_weight = sum(w for _, _, w in scores)
    weighted_sum = sum(s * w for _, s, w in scores)
    result = weighted_sum / total_weight if total_weight > 0 else 0.0

    logger.debug(
        "face_similarity_opencv: " +
        " | ".join(f"{name}={score:.3f}(w={w})" for name, score, w in scores) +
        f" → combined={result:.3f}"
    )
    return round(float(result), 4)


def match_faces(id_image_bytes: bytes, selfie_image_bytes: bytes) -> float:
    """
    Compare the face on the ID card with the selfie.

    Pipeline:
      1. Normalize orientation of both images
      2. Crop the ID face (Haar cascade)
      3. Crop the selfie face (Haar cascade)
      4. Try DeepFace.verify() if available (best accuracy)
      5. Fall back to multi-method OpenCV similarity if DeepFace unavailable

    Returns a confidence score 0.0–1.0. Never returns None.
    """
    img1 = _bytes_to_bgr(id_image_bytes)
    img2 = _bytes_to_bgr(selfie_image_bytes)
    if img1 is None or img2 is None:
        logger.error("match_faces: failed to decode one or both images")
        return 0.0

    # ── Normalize orientation ─────────────────────────────────────────────────
    img1 = normalize_orientation(img1)
    img2 = normalize_orientation(img2)

    # ── Crop ID face ──────────────────────────────────────────────────────────
    id_face = crop_id_face(img1)
    id_is_full = (id_face.shape == img1.shape and np.array_equal(id_face, img1))
    if id_is_full:
        logger.warning("match_faces: ID face crop failed — using full image")
    else:
        logger.debug(f"match_faces: ID face crop {id_face.shape[1]}x{id_face.shape[0]}px")

    # ── Crop selfie face ──────────────────────────────────────────────────────
    # Don't use the full selfie — crop to the face region for fair comparison
    selfie_face = crop_id_face(img2)   # reuses same Haar logic
    selfie_is_full = (selfie_face.shape == img2.shape and np.array_equal(selfie_face, img2))
    if selfie_is_full:
        logger.debug("match_faces: selfie face crop failed — using full selfie")
    else:
        logger.debug(f"match_faces: selfie face crop {selfie_face.shape[1]}x{selfie_face.shape[0]}px")

    # ── Upscale both to ≥ 224×224 ─────────────────────────────────────────────
    id_face     = _upscale_face(id_face,     target=224)
    selfie_face = _upscale_face(selfie_face, target=224)

    # ── Attempt 1: DeepFace (best accuracy, optional dependency) ─────────────
    try:
        from deepface import DeepFace
        result = DeepFace.verify(
            img1_path=id_face,
            img2_path=selfie_face,
            model_name="VGG-Face",
            enforce_detection=False,
            detector_backend="opencv",
        )
        verified = result.get("verified", False)
        distance = float(result.get("distance", 1.0))
        raw_conf   = max(0.0, 1.0 - distance)
        confidence = raw_conf if not verified else max(raw_conf, 0.65)
        logger.info(
            f"match_faces [DeepFace]: verified={verified} distance={distance:.3f} "
            f"confidence={confidence:.3f}"
        )
        return round(confidence, 4)
    except ImportError:
        logger.info("match_faces: DeepFace not installed — using OpenCV multi-method fallback")
    except Exception as exc:
        logger.warning(f"match_faces: DeepFace failed ({exc}) — falling back to OpenCV")

    # ── Attempt 2: face_recognition library (dlib-based, very accurate) ───────
    try:
        import face_recognition
        enc1 = face_recognition.face_encodings(
            face_recognition.load_image_file(
                __import__("io").BytesIO(
                    cv2.imencode(".jpg", id_face)[1].tobytes()
                )
            )
        )
        enc2 = face_recognition.face_encodings(
            face_recognition.load_image_file(
                __import__("io").BytesIO(
                    cv2.imencode(".jpg", selfie_face)[1].tobytes()
                )
            )
        )
        if enc1 and enc2:
            distance = float(face_recognition.face_distance([enc1[0]], enc2[0])[0])
            # dlib distance: 0=identical, 0.6=threshold, >1=different
            confidence = max(0.0, 1.0 - distance / 0.6)
            logger.info(f"match_faces [face_recognition]: distance={distance:.3f} confidence={confidence:.3f}")
            return round(min(confidence, 1.0), 4)
        else:
            logger.warning("match_faces [face_recognition]: no encodings found in one or both images")
    except ImportError:
        logger.info("match_faces: face_recognition not installed — using OpenCV fallback")
    except Exception as exc:
        logger.warning(f"match_faces: face_recognition failed ({exc}) — using OpenCV fallback")

    # ── Attempt 3: OpenCV multi-method similarity (always available) ──────────
    confidence = _face_similarity_opencv(id_face, selfie_face)
    logger.info(f"match_faces [OpenCV]: confidence={confidence:.3f}")
    return confidence
