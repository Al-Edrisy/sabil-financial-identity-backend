"""
app/api/v1/routes/kyc.py — End-user KYC submission and history endpoints.
"""

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.dependencies.db import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rate_limit import rate_limiter
from app.services.kyc_service import KYCService
from app.schemas.kyc import KYCResponse, IDType
from app.models.kyc import KYCStatus
from app.models.user import User

router = APIRouter()


@router.post(
    "/verify",
    response_model=KYCResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Step 2 — Submit KYC Verification",
    description=(
        "Upload a government-issued ID photo and a live selfie. "
        "Optionally provide manual fields (full_name, id_number, issue_date, etc.) "
        "which override OCR extraction when provided. "
        "The system performs OCR, liveness detection, and face matching."
    ),
    dependencies=[Depends(rate_limiter(requests_per_minute=3))],
)
async def verify_kyc(
    id_card:             UploadFile      = File(..., description="Clear photo of government-issued ID (JPEG/PNG/WebP, max 10MB)"),
    selfie:              UploadFile      = File(..., description="Live selfie — face must be clearly visible"),
    id_type:             IDType          = Form(IDType.national_id, description="Document type"),
    # ── Manual override fields — all optional, override OCR when provided ──
    full_name:           Optional[str]   = Form(None, description="Full name as on document"),
    id_number:           Optional[str]   = Form(None, description="Passport/ID number"),
    issue_date:          Optional[str]   = Form(None, description="Document issue date (YYYY-MM-DD)"),
    expiry_date:         Optional[str]   = Form(None, description="Document expiry date (YYYY-MM-DD)"),
    country:             Optional[str]   = Form(None, description="Country of document (e.g. YE, SA)"),
    nationality:         Optional[str]   = Form(None, description="Nationality (e.g. Yemeni, Saudi)"),
    current_user: User   = Depends(get_current_user),
    db: AsyncSession     = Depends(get_db),
) -> KYCResponse:
    service = KYCService(db)
    return await service.process_kyc(
        user_id             = current_user.id,
        id_card             = id_card,
        selfie              = selfie,
        id_type             = id_type.value,
        manual_full_name    = full_name,
        manual_id_number    = id_number,
        manual_issue_date   = issue_date,
        manual_expiry_date  = expiry_date,
        manual_country      = country,
        manual_nationality  = nationality,
    )


@router.post(
    "/resubmit",
    response_model=KYCResponse,
    summary="Resubmit KYC After Rejection",
    description=(
        "Re-attempt verification after a REJECTED status. "
        "Capped by KYC_MAX_RESUBMISSIONS setting."
    ),
    dependencies=[Depends(rate_limiter(requests_per_minute=2))],
)
async def resubmit_kyc(
    id_card: UploadFile = File(..., description="Updated photo of identity document"),
    selfie:  UploadFile = File(..., description="New live selfie"),
    id_type: IDType     = Form(IDType.national_id, description="Document type"),
    current_user: User  = Depends(get_current_user),
    db: AsyncSession    = Depends(get_db),
) -> KYCResponse:
    service = KYCService(db)
    kyc_record = await service.get_kyc_status(current_user.id)

    if kyc_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No previous KYC record found. Use POST /kyc/verify for first-time submission.",
        )

    current_status = kyc_record.get("status") if isinstance(kyc_record, dict) else kyc_record.status
    if current_status not in (KYCStatus.REJECTED, KYCStatus.RESUBMITTED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Resubmission not allowed. Current status: {current_status.value}",
        )

    return await service.process_kyc(current_user.id, id_card, selfie, id_type.value)


@router.get(
    "/status",
    response_model=KYCResponse,
    summary="Get Current Verification Status",
    description="Returns the most recent active KYC record with full verification details.",
)
async def get_current_kyc_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_db),
) -> KYCResponse:
    service = KYCService(db)
    record = await service.get_kyc_status(current_user.id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No KYC record found. Submit via POST /kyc/verify.",
        )
    return record


@router.get(
    "/history",
    response_model=List[KYCResponse],
    summary="View Full Verification History",
    description="Returns all past KYC attempts including rejections.",
)
async def get_kyc_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_db),
) -> List[KYCResponse]:
    service = KYCService(db)
    return await service.get_kyc_history(current_user.id)


@router.post(
    "/debug-ocr",
    summary="Debug: Inspect OCR Output from ID Image",
    description=(
        "Upload an ID image and see exactly what OCR extracted — "
        "raw tokens, field extraction results, MRZ parsing. "
        "No data is saved. Use to diagnose OCR quality issues."
    ),
)
async def debug_kyc_ocr(
    id_card: UploadFile = File(..., description="ID card image to inspect"),
    id_type: IDType     = Form(IDType.national_id),
    current_user: User  = Depends(get_current_user),
    db: AsyncSession    = Depends(get_db),
) -> dict:
    from app.ai.ocr import extract_text_from_id, _run_ocr_best_variant, get_ocr_reader, OCR_MIN_CONFIDENCE
    from app.ai.ocr_image import preprocess_image_variants
    from app.utils.image_validation import validate_image_bytes

    image_bytes = await id_card.read()
    validate_image_bytes(image_bytes, "id_card", id_card.content_type)

    reader = get_ocr_reader()
    if not reader:
        raise HTTPException(status_code=503, detail="OCR engine not available.")

    # Run all variants and show scores
    variants = preprocess_image_variants(image_bytes)
    variant_scores = []
    for i, variant in enumerate(variants):
        try:
            results = reader.readtext(variant, detail=1, paragraph=False)
            score   = sum(r[2] * len(r[1]) for r in results if r[2] >= OCR_MIN_CONFIDENCE and r[1].strip())
            accepted = [{"text": r[1], "confidence": round(r[2], 3)} for r in results if r[2] >= OCR_MIN_CONFIDENCE]
            variant_scores.append({"variant": i, "score": round(score, 2), "accepted_tokens": accepted})
        except Exception as e:
            variant_scores.append({"variant": i, "error": str(e)})

    # Full extraction
    ocr_result = extract_text_from_id(image_bytes, id_type=id_type.value)

    return {
        "id_type":        id_type.value,
        "variant_scores": variant_scores,
        "best_variant":   max((v for v in variant_scores if "score" in v), key=lambda x: x["score"], default=None),
        "raw_text":       ocr_result.get("raw_text", []),
        "extracted_fields": {
            "full_name":   ocr_result.get("full_name"),
            "id_number":   ocr_result.get("id_number"),
            "dob":         ocr_result.get("dob"),
            "expiry_date": ocr_result.get("expiry_date"),
            "nationality": ocr_result.get("nationality"),
            "country":     ocr_result.get("country"),
            "gender":      ocr_result.get("gender"),
        },
        "mrz":            ocr_result.get("mrz"),
        "ocr_tokens":     ocr_result.get("ocr_tokens", []),
        "error":          ocr_result.get("error"),
    }
