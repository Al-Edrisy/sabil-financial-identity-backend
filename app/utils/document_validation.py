"""
app/utils/document_validation.py — Validate and extract text from financial documents.

Supported formats:
  - Images: JPEG, PNG, WebP  → OpenCV decode check
  - PDF:    application/pdf  → pdfplumber text extraction
  - CSV:    text/csv         → pandas read_csv
  - Text:   text/plain       → direct decode

All validators raise HTTPException on failure.
"""

import io
import csv
from typing import Optional
from fastapi import HTTPException, status
from app.core.logger import get_logger

logger = get_logger(__name__)

# ── MIME type groups ──────────────────────────────────────────────────────────
IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
PDF_TYPES   = {"application/pdf"}
CSV_TYPES   = {"text/csv", "application/csv", "text/comma-separated-values"}
TEXT_TYPES  = {"text/plain"}

ALL_ALLOWED_TYPES = IMAGE_TYPES | PDF_TYPES | CSV_TYPES | TEXT_TYPES

# ── Size limits ───────────────────────────────────────────────────────────────
MAX_IMAGE_BYTES = 10 * 1024 * 1024   # 10 MB
MAX_DOC_BYTES   = 25 * 1024 * 1024   # 25 MB for PDFs/CSVs


def get_file_category(content_type: Optional[str]) -> str:
    """Return 'image' | 'pdf' | 'csv' | 'text' | 'unknown'."""
    ct = (content_type or "").lower().split(";")[0].strip()
    if ct in IMAGE_TYPES:
        return "image"
    if ct in PDF_TYPES:
        return "pdf"
    if ct in CSV_TYPES:
        return "csv"
    if ct in TEXT_TYPES:
        return "text"
    return "unknown"


def validate_financial_document(
    file_bytes:   bytes,
    field_name:   str,
    content_type: Optional[str],
) -> str:
    """
    Validate a financial document upload.

    Returns the file category: 'image' | 'pdf' | 'csv' | 'text'
    Raises HTTPException on invalid type, size, or corrupt content.
    """
    ct       = (content_type or "").lower().split(";")[0].strip()
    category = get_file_category(ct)

    if category == "unknown":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"'{field_name}' has unsupported type '{ct}'. "
                "Accepted: JPEG, PNG, WebP, PDF, CSV, TXT."
            ),
        )

    max_size = MAX_IMAGE_BYTES if category == "image" else MAX_DOC_BYTES
    if len(file_bytes) > max_size:
        limit_mb = max_size // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"'{field_name}' exceeds the {limit_mb} MB size limit.",
        )

    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'{field_name}' is empty.",
        )

    # Content-specific validation
    if category == "image":
        import cv2, numpy as np
        nparr = np.frombuffer(file_bytes, np.uint8)
        img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{field_name}' could not be decoded as a valid image.",
            )

    elif category == "pdf":
        # Check PDF magic bytes
        if not file_bytes.startswith(b"%PDF"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{field_name}' does not appear to be a valid PDF file.",
            )

    elif category == "csv":
        try:
            text = file_bytes.decode("utf-8", errors="replace")
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
            if len(rows) < 2:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"'{field_name}' CSV has fewer than 2 rows — no data to process.",
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{field_name}' could not be parsed as CSV: {e}",
            )

    return category


def extract_text_from_pdf(file_bytes: bytes) -> list[str]:
    """
    Extract text lines from a PDF using pdfplumber.
    Returns a list of non-empty text lines.
    Falls back to empty list if pdfplumber is not installed.
    """
    try:
        import pdfplumber
        lines = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    lines.extend(
                        line.strip()
                        for line in text.split("\n")
                        if line.strip()
                    )
        logger.info(f"PDF extraction: {len(lines)} lines from {len(pdf.pages)} pages")
        return lines
    except ImportError:
        logger.warning("pdfplumber not installed — PDF text extraction unavailable")
        return []
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        return []


def extract_text_from_csv(file_bytes: bytes) -> list[str]:
    """
    Convert CSV rows to text lines for the transaction parser.
    Each row becomes a single space-joined string.
    """
    try:
        text   = file_bytes.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        lines  = []
        for i, row in enumerate(reader):
            if i == 0:
                continue   # skip header row
            line = "  ".join(cell.strip() for cell in row if cell.strip())
            if line:
                lines.append(line)
        logger.info(f"CSV extraction: {len(lines)} data rows")
        return lines
    except Exception as e:
        logger.error(f"CSV extraction failed: {e}")
        return []


def extract_text_from_plain(file_bytes: bytes) -> list[str]:
    """Extract lines from a plain text file."""
    try:
        text  = file_bytes.decode("utf-8", errors="replace")
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        logger.info(f"Text extraction: {len(lines)} lines")
        return lines
    except Exception as e:
        logger.error(f"Text extraction failed: {e}")
        return []
