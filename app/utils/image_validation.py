"""
Image validation utilities for KYC uploads.

Checks are performed in order of cost (cheapest first):
  1. Content-type MIME check (zero cost)
  2. File size limit (zero cost)
  3. OpenCV decode check (cheap — ensures the bytes form a real image)

All checks raise HTTPException so callers don't need extra try/except.
"""

from fastapi import HTTPException, UploadFile, status
import cv2
import numpy as np

# Allowed MIME types — extend if you need HEIC / TIFF later
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}

# Maximum upload size: 10 MB
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


def validate_image_bytes(
    image_bytes: bytes,
    field_name: str,
    content_type: str | None,
) -> None:
    """
    Validate that *image_bytes* represent an acceptable image.

    Args:
        image_bytes:  Raw bytes already read from the UploadFile.
        field_name:   Human-readable field label used in error messages.
        content_type: The content-type header reported by the client.

    Raises:
        HTTPException 415 – unsupported media type.
        HTTPException 413 – payload too large.
        HTTPException 422 – bytes cannot be decoded as an image.
    """
    # 1. MIME type check -------------------------------------------------------
    normalised_ct = (content_type or "").lower().split(";")[0].strip()
    if normalised_ct not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"'{field_name}' must be a JPEG, PNG, or WebP image. "
                f"Received content-type: '{normalised_ct or 'unknown'}'."
            ),
        )

    # 2. Size check ------------------------------------------------------------
    if len(image_bytes) > MAX_IMAGE_BYTES:
        limit_mb = MAX_IMAGE_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"'{field_name}' exceeds the {limit_mb} MB size limit.",
        )

    # 3. Decodability check ----------------------------------------------------
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"'{field_name}' could not be decoded as a valid image. "
                "The file may be corrupt or truncated."
            ),
        )
