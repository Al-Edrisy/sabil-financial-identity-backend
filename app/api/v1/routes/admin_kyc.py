"""
app/api/v1/routes/admin_kyc.py — Administrative KYC management endpoints.
All routes require is_admin=True.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.db import get_db
from app.dependencies.admin import require_admin
from app.models.kyc import KYCStatus
from app.models.user import User
from app.schemas.kyc import KYCResponse, KYCAdminResponse, KYCAdminReviewRequest, KYCListResponse
from app.services.kyc_service import KYCService

router = APIRouter()


@router.get(
    "/list",
    response_model=KYCListResponse,
    summary="List and Filter KYC Applications (Admin)",
)
async def list_kyc_applications(
    status:       Optional[KYCStatus] = Query(None,  description="Filter by status"),
    expired_only: bool                 = Query(False, description="Only expired VERIFIED records"),
    user_id:      Optional[int]        = Query(None,  description="Filter by user ID"),
    id_number:    Optional[str]        = Query(None,  description="Partial ID number search"),
    page:         int                  = Query(1,     ge=1),
    page_size:    int                  = Query(20,    ge=1, le=100),
    admin:        User                 = Depends(require_admin),
    db:           AsyncSession         = Depends(get_db),
) -> KYCListResponse:
    service = KYCService(db)
    result = await service.list_kyc_records(
        status_filter=status,
        expired_only=expired_only,
        user_id=user_id,
        search_id_number=id_number,
        page=page,
        page_size=page_size,
    )
    return KYCListResponse(**result)


@router.post(
    "/{user_id}/review",
    response_model=KYCAdminResponse,
    summary="Submit Manual KYC Review (Admin)",
)
async def submit_admin_review(
    user_id: int,
    review:  KYCAdminReviewRequest,
    admin:   User          = Depends(require_admin),
    db:      AsyncSession  = Depends(get_db),
) -> KYCResponse:
    service = KYCService(db)
    return await service.admin_review(
        user_id=user_id,
        reviewer_id=admin.id,
        approved=review.approved,
        note=review.note,
    )
