"""
app/api/v1/routes/admin_credit.py — Admin-only credit scoring management.

GET  /admin/credit/list                          — all users' scores (paginated)
GET  /admin/credit/users/{user_id}/transactions  — any user's transactions
POST /admin/credit/users/{user_id}/rescore       — force recompute from existing data
GET  /admin/credit/review-queue                  — all needs_review rows (all users)
POST /admin/credit/transactions/{id}/resolve     — admin resolves a flagged row
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func as sqlfunc, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.admin import require_admin
from app.dependencies.db import get_db
from app.models.credit_score import CreditScore
from app.models.parsed_transaction import ParsedTransaction, ParsedTransactionType, ParsedTransactionSource
from app.models.user import User
from app.schemas.credit_score import CreditScoreResponse
from app.schemas.transaction_parsed import ParsedTransactionListResponse, ParsedTransactionResponse
from app.services.signal_service import compute_signals
from app.services.scoring_service import (
    compute_score, get_risk_level, generate_insights, build_transactions_summary
)
from app.api.v1.routes.credit import _build_score_response

router = APIRouter()


# ---------------------------------------------------------------------------
# Helper — reuse the shared builder from credit.py
# ---------------------------------------------------------------------------
# _build_score_response is imported above


# ---------------------------------------------------------------------------
# GET /admin/credit/list
# ---------------------------------------------------------------------------
@router.get(
    "/list",
    summary="List All Credit Scores (Admin)",
    description="Paginated list of all users' active credit scores. Filter by risk_level.",
)
async def list_all_scores(
    risk_level: Optional[str] = Query(None, description="trusted | moderate | risky"),
    page:       int           = Query(1,    ge=1),
    page_size:  int           = Query(20,   ge=1, le=100),
    admin:      User          = Depends(require_admin),
    db:         AsyncSession  = Depends(get_db),
) -> dict:
    stmt = select(CreditScore).where(CreditScore.is_active == True)
    if risk_level:
        stmt = stmt.where(CreditScore.risk_level == risk_level.lower())

    total_result = await db.execute(select(sqlfunc.count()).select_from(stmt.subquery()))
    total        = total_result.scalar() or 0

    rows_result = await db.execute(
        stmt.order_by(CreditScore.computed_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = rows_result.scalars().all()

    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "items":     [_build_score_response(cs) for cs in items],
    }


# ---------------------------------------------------------------------------
# GET /admin/credit/users/{user_id}/transactions
# ---------------------------------------------------------------------------
@router.get(
    "/users/{user_id}/transactions",
    response_model=ParsedTransactionListResponse,
    summary="View Any User's Parsed Transactions (Admin)",
)
async def get_user_transactions(
    user_id:   int,
    page:      int           = Query(1,  ge=1),
    page_size: int           = Query(20, ge=1, le=100),
    admin:     User          = Depends(require_admin),
    db:        AsyncSession  = Depends(get_db),
) -> ParsedTransactionListResponse:
    stmt = select(ParsedTransaction).where(ParsedTransaction.user_id == user_id)

    total_result = await db.execute(select(sqlfunc.count()).select_from(stmt.subquery()))
    total        = total_result.scalar() or 0

    rows_result = await db.execute(
        stmt.order_by(ParsedTransaction.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = rows_result.scalars().all()

    return ParsedTransactionListResponse(
        total=total, page=page, page_size=page_size, items=items
    )


# ---------------------------------------------------------------------------
# POST /admin/credit/users/{user_id}/rescore
# ---------------------------------------------------------------------------
@router.post(
    "/users/{user_id}/rescore",
    response_model=CreditScoreResponse,
    summary="Force Recompute Credit Score (Admin)",
    description="Recomputes the credit score from all existing parsed transactions.",
)
async def rescore_user(
    user_id: int,
    admin:   User         = Depends(require_admin),
    db:      AsyncSession = Depends(get_db),
) -> CreditScoreResponse:
    rows_result = await db.execute(
        select(ParsedTransaction).where(ParsedTransaction.user_id == user_id)
    )
    all_rows = rows_result.scalars().all()

    if not all_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No parsed transactions found for this user.",
        )

    signal_input = [
        {
            "normalized_usd":   r.normalized_amount,
            "type":             r.type.value.lower() if hasattr(r.type, "value") else str(r.type).lower(),
            "transaction_date": r.transaction_date,
            "created_at":       r.created_at,
            "category":         r.category or "other",
        }
        for r in all_rows
    ]

    signals    = compute_signals(signal_input)
    score      = compute_score(signals)
    risk_level = get_risk_level(score)
    insights   = generate_insights(signals, score)
    tx_summary = build_transactions_summary(signal_input)

    # Archive old
    await db.execute(
        update(CreditScore)
        .where(CreditScore.user_id == user_id, CreditScore.is_active == True)
        .values(is_active=False)
    )

    new_cs = CreditScore(
        user_id              = user_id,
        score                = score,
        risk_level           = risk_level,
        income_level         = signals.income_level,
        income_stability     = signals.income_stability,
        savings_rate         = signals.savings_rate,
        activity             = signals.activity,
        burden               = signals.burden,
        insights             = insights,
        transactions_summary = tx_summary,
        transaction_count    = signals.transaction_count,
        data_quality         = signals.data_quality,
        is_active            = True,
    )
    db.add(new_cs)
    await db.commit()
    await db.refresh(new_cs)

    return _build_score_response(new_cs)


# ---------------------------------------------------------------------------
# GET /admin/credit/review-queue
# ---------------------------------------------------------------------------
@router.get(
    "/review-queue",
    response_model=ParsedTransactionListResponse,
    summary="Global Review Queue (Admin)",
    description="All needs_review=True rows across all users.",
)
async def global_review_queue(
    page:      int          = Query(1,  ge=1),
    page_size: int          = Query(20, ge=1, le=100),
    admin:     User         = Depends(require_admin),
    db:        AsyncSession = Depends(get_db),
) -> ParsedTransactionListResponse:
    stmt = select(ParsedTransaction).where(ParsedTransaction.needs_review == True)

    total_result = await db.execute(select(sqlfunc.count()).select_from(stmt.subquery()))
    total        = total_result.scalar() or 0

    rows_result = await db.execute(
        stmt.order_by(ParsedTransaction.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = rows_result.scalars().all()

    return ParsedTransactionListResponse(
        total=total, page=page, page_size=page_size, items=items
    )


# ---------------------------------------------------------------------------
# POST /admin/credit/transactions/{id}/resolve
# ---------------------------------------------------------------------------
@router.post(
    "/transactions/{transaction_id}/resolve",
    response_model=ParsedTransactionResponse,
    summary="Resolve a Flagged Transaction (Admin)",
    description="Mark a needs_review row as resolved. Optionally correct type/category.",
)
async def resolve_transaction(
    transaction_id: int,
    correct_type:     Optional[str] = Query(None, description="income | expense | unknown"),
    correct_category: Optional[str] = Query(None),
    admin: User         = Depends(require_admin),
    db:    AsyncSession = Depends(get_db),
) -> ParsedTransactionResponse:
    result = await db.execute(
        select(ParsedTransaction).where(ParsedTransaction.id == transaction_id)
    )
    tx = result.scalar_one_or_none()
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")

    type_map = {
        "income":  ParsedTransactionType.INCOME,
        "expense": ParsedTransactionType.EXPENSE,
        "unknown": ParsedTransactionType.UNKNOWN,
    }
    if correct_type and correct_type.lower() in type_map:
        tx.type = type_map[correct_type.lower()]
    if correct_category:
        tx.category = correct_category

    tx.needs_review = False
    tx.source       = ParsedTransactionSource.MANUAL
    await db.commit()
    await db.refresh(tx)

    return tx
