"""
app/api/v1/routes/credit.py — Credit scoring pipeline endpoints.

Step 3 of the user flow:
  POST /credit/upload        — upload one or more financial documents
  POST /credit/upload-batch  — explicit multi-file upload
  GET  /credit/score         — get latest credit score
  GET  /credit/transactions  — list parsed transactions
  GET  /credit/currencies    — list all supported currencies
"""

from typing import Optional, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.dependencies.rate_limit import rate_limiter
from app.models.credit_score import CreditScore
from app.models.user import User
from app.schemas.credit_score import (
    CreditScoreResponse, SignalResponse, TransactionsSummary, UploadStatementResponse
)
from app.schemas.transaction_parsed import (
    ParsedTransactionCorrection,
    ParsedTransactionListResponse,
    ParsedTransactionResponse,
)
from app.services.statement_service import StatementService
from app.utils.fx import list_supported_currencies, get_currency_for_country

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /credit/debug-ocr  — inspect what the pipeline sees (no DB writes)
# ---------------------------------------------------------------------------
@router.post(
    "/debug-ocr",
    summary="Debug: Inspect OCR + Parser Output",
    description=(
        "Upload a statement image and see exactly what OCR extracted and "
        "how the parser classified each line. No data is saved to the DB. "
        "Use this to diagnose why transactions are showing as 'unknown'."
    ),
)
async def debug_ocr(
    statement:    UploadFile   = File(...),
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
) -> dict:
    from app.ai.parsing.statement_preprocessor import preprocess_statement
    from app.ai.parsing.transaction_parser import parse_transactions
    from app.ai.ocr import get_statement_ocr_reader
    from app.services.categorizer_service import categorize_many
    from app.utils.image_validation import validate_image_bytes
    from app.core.config import settings

    image_bytes = await statement.read()
    validate_image_bytes(image_bytes, "statement", statement.content_type)

    preprocessed = preprocess_statement(image_bytes)
    if preprocessed is None:
        raise HTTPException(status_code=422, detail="Could not decode image.")

    reader_latin, reader_arabic = get_statement_ocr_reader()
    min_conf = settings.KYC_OCR_MIN_CONFIDENCE

    ocr_results_by_reader = {}
    best_lines: list[str] = []
    best_score = -1.0

    for reader_name, reader in [("latin(en+tr)", reader_latin), ("arabic(en+ar)", reader_arabic)]:
        if reader is None:
            continue
        try:
            raw = reader.readtext(preprocessed["processed"], detail=1, paragraph=False)
            all_tokens = [{"text": r[1], "confidence": round(r[2], 3)} for r in raw]
            accepted   = [r[1] for r in raw if r[2] >= min_conf]
            score      = sum(r[2] * len(r[1]) for r in raw if r[2] >= min_conf and r[1].strip())
            ocr_results_by_reader[reader_name] = {
                "all_tokens":     all_tokens,
                "accepted_lines": accepted,
                "accepted_count": len(accepted),
                "score":          round(score, 2),
            }
            if score > best_score:
                best_score = score
                best_lines = accepted
        except Exception as e:
            ocr_results_by_reader[reader_name] = {"error": str(e)}

    parsed_rows = parse_transactions(best_lines)
    categories  = categorize_many([r.description for r in parsed_rows])

    parsed_output = [
        {
            "raw_line":    r.raw_line,
            "description": r.description,
            "amount":      r.amount,
            "currency":    r.currency,
            "normalized_usd": r.normalized_usd,
            "type":        r.type,
            "category":    cat,
            "cat_score":   round(cat_score, 1),
            "date":        str(r.transaction_date) if r.transaction_date else None,
            "confidence":  round(r.confidence, 2),
            "needs_review": r.needs_review,
        }
        for r, (cat, cat_score) in zip(parsed_rows, categories)
    ]

    type_counts = {}
    for r in parsed_rows:
        type_counts[r.type] = type_counts.get(r.type, 0) + 1

    return {
        "image_shape":        preprocessed["original_shape"],
        "columns_detected":   len(preprocessed["columns"]),
        "ocr_confidence_gate": min_conf,
        "ocr_by_reader":      ocr_results_by_reader,
        "best_reader_lines":  best_lines,
        "parsed_rows":        parsed_output,
        "summary": {
            "total_rows":    len(parsed_rows),
            "type_breakdown": type_counts,
            "problem": (
                "All rows are 'unknown' — OCR text doesn't contain recognisable "
                "income/expense keywords. Check 'best_reader_lines' to see raw OCR output."
                if all(r.type == "unknown" for r in parsed_rows) and parsed_rows
                else None
            ),
        },
    }


# ---------------------------------------------------------------------------
# Helper — build CreditScoreResponse from ORM CreditScore object
# ---------------------------------------------------------------------------
def _build_score_response(cs: CreditScore) -> CreditScoreResponse:
    """
    Convert a CreditScore ORM object to a CreditScoreResponse schema.
    Handles None values and type coercion safely.
    """
    tx_summary_raw = cs.transactions_summary or {}
    tx_summary = TransactionsSummary(
        total_income     = float(tx_summary_raw.get("total_income", 0.0)),
        total_expenses   = float(tx_summary_raw.get("total_expenses", 0.0)),
        net              = float(tx_summary_raw.get("net", 0.0)),
        transaction_count= int(tx_summary_raw.get("transaction_count", 0)),
        top_categories   = {
            str(k): float(v)
            for k, v in (tx_summary_raw.get("top_categories") or {}).items()
        },
    )

    signals = SignalResponse(
        income_level     = cs.income_level,
        income_stability = cs.income_stability,
        savings_rate     = cs.savings_rate,
        activity         = cs.activity,
        burden           = cs.burden,
    )

    return CreditScoreResponse(
        id                   = cs.id,
        user_id              = cs.user_id,
        score                = cs.score,
        risk_level           = cs.risk_level,
        signals              = signals,
        insights             = cs.insights or [],
        transactions_summary = tx_summary,
        data_quality         = cs.data_quality or "insufficient",
        transaction_count    = cs.transaction_count,
        upload_id            = cs.upload_id,
        computed_at          = cs.computed_at,
    )


# ---------------------------------------------------------------------------
# GET /credit/currencies
# ---------------------------------------------------------------------------
@router.get(
    "/currencies",
    summary="List All Supported Currencies",
    description="Returns all currencies supported for financial document processing with their exchange rates.",
)
async def get_currencies() -> list:
    return list_supported_currencies()


# ---------------------------------------------------------------------------
# POST /credit/upload  — single OR multi-file
# ---------------------------------------------------------------------------
@router.post(
    "/upload",
    response_model=UploadStatementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Step 3 — Upload Financial Documents",
    description=(
        "Upload one or more financial documents for credit scoring. "
        "**Supported formats:** JPEG, PNG, WebP (images), PDF, CSV, TXT. "
        "**Multiple files:** send multiple `files` fields in the same request. "
        "All files are processed together and contribute to the same score. "
        "Optionally provide `user_country` (ISO code e.g. 'YE', 'SA') to convert "
        "foreign currency amounts to the user's home currency."
    ),
    dependencies=[Depends(rate_limiter(requests_per_minute=3))],
)
async def upload_statements(
    files:        List[UploadFile] = File(..., description="One or more financial documents (image/PDF/CSV/TXT, max 25MB each)"),
    user_country: Optional[str]    = Form(None, description="ISO country code for currency conversion (e.g. YE, SA, TR)"),
    current_user: User             = Depends(get_current_user),
    db:           AsyncSession     = Depends(get_db),
) -> UploadStatementResponse:
    service = StatementService(db)

    # Resolve user country from profile if not provided
    country = user_country or getattr(current_user, "country_code", None)

    result = await service.upload_statements_batch(
        user_id      = current_user.id,
        files        = files,
        user_country = country,
    )

    return UploadStatementResponse(
        upload_id          = result["upload_id"],
        row_count          = result["row_count"],
        needs_review_count = result["needs_review_count"],
        score              = _build_score_response(result["score"]),
    )


# ---------------------------------------------------------------------------
# GET /credit/score
# ---------------------------------------------------------------------------
@router.get(
    "/score",
    response_model=CreditScoreResponse,
    summary="Get Latest Credit Score",
)
async def get_score(
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
) -> CreditScoreResponse:
    """Returns the most recent active credit score for the authenticated user."""
    service = StatementService(db)
    cs      = await service.get_score(current_user.id)

    if cs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No credit score found. Upload a bank statement to generate one.",
        )

    return _build_score_response(cs)


# ---------------------------------------------------------------------------
# GET /credit/transactions/review
# ---------------------------------------------------------------------------
@router.get(
    "/transactions/review",
    response_model=list[ParsedTransactionResponse],
    summary="Get Transactions Flagged for Review",
)
async def get_review_queue(
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
) -> list[ParsedTransactionResponse]:
    """Returns all parsed transaction rows that need human review."""
    service = StatementService(db)
    return await service.get_review_queue(current_user.id)


# ---------------------------------------------------------------------------
# GET /credit/transactions
# ---------------------------------------------------------------------------
@router.get(
    "/transactions",
    response_model=ParsedTransactionListResponse,
    summary="List Parsed Transactions",
)
async def list_transactions(
    page:         int            = Query(1,    ge=1),
    page_size:    int            = Query(20,   ge=1, le=100),
    type:         Optional[str]  = Query(None, description="Filter: income | expense | unknown"),
    needs_review: Optional[bool] = Query(None, description="Filter by review flag"),
    current_user: User           = Depends(get_current_user),
    db:           AsyncSession   = Depends(get_db),
) -> ParsedTransactionListResponse:
    """Returns a paginated list of parsed transactions for the current user."""
    service = StatementService(db)
    result  = await service.get_transactions(
        user_id      = current_user.id,
        page         = page,
        page_size    = page_size,
        tx_type      = type,
        needs_review = needs_review,
    )
    return ParsedTransactionListResponse(**result)


# ---------------------------------------------------------------------------
# PUT /credit/transactions/{id}/correct
# ---------------------------------------------------------------------------
@router.put(
    "/transactions/{transaction_id}/correct",
    response_model=CreditScoreResponse,
    summary="Correct a Parsed Transaction",
    description=(
        "Fix a misparse (wrong amount, description, or type). "
        "Triggers automatic score recomputation."
    ),
)
async def correct_transaction(
    transaction_id: int,
    correction:     ParsedTransactionCorrection,
    current_user:   User         = Depends(get_current_user),
    db:             AsyncSession = Depends(get_db),
) -> CreditScoreResponse:
    service = StatementService(db)
    cs      = await service.correct_transaction(
        tx_id      = transaction_id,
        user_id    = current_user.id,
        correction = correction.model_dump(exclude_none=True),
    )
    return _build_score_response(cs)
