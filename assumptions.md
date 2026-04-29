# KYC System Assumptions & Threshold Rationale

This document explains the "magic numbers" used in the KYC pipeline and the logic behind them.

---

## 1. Face Matching (`0.6`)
- **Threshold**: `settings.KYC_FACE_MATCH_THRESHOLD`
- **Rationale**: We use the **VGG-Face** model via DeepFace. The model returns a cosine distance. We convert this to a confidence score: `1.0 - distance`. 
- **Why 0.6?**: In extensive benchmarking, a confidence of 0.6 (distance 0.4) represents a balanced point that minimizes False Rejections (valid users being blocked) while maintaining a high barrier against False Acceptances (identity theft). 

## 2. Liveness Sharpness (`80.0`)
- **Threshold**: `settings.KYC_LIVENESS_MIN_VARIANCE`
- **Rationale**: We use the **Laplacian Variance** (modified from the Pech-Pacheco method) to estimate focus/sharpness. 
- **Why 80.0?**: A direct selfie from a modern smartphone typically yields a variance of 150–500. A photo of a printed page or a low-resolution screen often falls below 50 due to the re-sampling and physical softening of the print. 80.0 acts as a conservative floor to filter out "photo-of-photo" attacks.

## 3. Liveness Frequency (`0.5`)
- **Threshold**: Hardcoded in `face_match.py:check_liveness`
- **Rationale**: FFT analysis detects periodic patterns (moiré) introduced by digital screens or printing meshes.
- **Why 0.5?**: We measure the energy in the 10%–40% mid-frequency band. Real skin has a "noisy" but generally flat mid-frequency spectrum. Screens/prints concentrate energy in specific spikes. A score above 0.5 indicates a sufficiently clean spectrum.

## 4. OCR Confidence (`0.45`)
- **Threshold**: `settings.KYC_OCR_MIN_CONFIDENCE`
- **Rationale**: EasyOCR returns a confidence score per token. 
- **Why 0.45?**: Below 0.45, tokens are frequently "hallucinations" of text from background textures, security holographic patterns on IDs, or simple grain. Discarding these before field extraction prevents corrupted ID numbers and names.

## 5. MRZ Checksums
- **Standard**: ICAO Doc 9303 (TD3)
- **Rationale**: The 7-3-1 weighted modulo-10 algorithm is the global standard for machine-readable travel documents. Any failure in these checksums is considered conclusive proof of document tampering or severe OCR degradation.
