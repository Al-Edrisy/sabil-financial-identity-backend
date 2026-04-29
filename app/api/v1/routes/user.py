"""
app/api/v1/routes/user.py — User profile and management endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.dependencies.db import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.admin import require_admin
from app.dependencies.rate_limit import rate_limiter
from app.services.user_service import UserService
from app.schemas.user import User as UserSchema, UserUpdate, OnboardingStatus
from app.models.user import User

router = APIRouter()


@router.get(
    "/me",
    response_model=UserSchema,
    summary="Get Current User Profile",
)
async def get_me(current_user: User = Depends(get_current_user)):
    """Returns the profile of the currently authenticated user."""
    return current_user


@router.get(
    "/me/onboarding-status",
    response_model=OnboardingStatus,
    summary="Get Onboarding Progress",
    description="Returns the current onboarding step and what the user needs to do next.",
)
async def get_onboarding_status(
    current_user: User = Depends(get_current_user),
) -> OnboardingStatus:
    """Returns the user's onboarding progress and next action."""
    step     = getattr(current_user, "onboarding_step", 0)
    kyc_st   = getattr(current_user, "kyc_status", "not_started") or "not_started"
    cr_score = getattr(current_user, "credit_score", None)

    credit_status = "not_started" if cr_score is None else "scored"

    # Determine next step
    if step == 0 or not getattr(current_user, "phone_verified", False):
        next_step     = "Verify your phone number"
        next_step_url = "/api/v1/auth/send-otp"
    elif kyc_st in ("not_started", "rejected"):
        next_step     = "Complete identity verification"
        next_step_url = "/api/v1/kyc/verify"
    elif kyc_st == "pending":
        next_step     = "Identity verification under review"
        next_step_url = "/api/v1/kyc/status"
    elif credit_status == "not_started":
        next_step     = "Upload financial documents"
        next_step_url = "/api/v1/credit/upload"
    else:
        next_step     = "All steps complete"
        next_step_url = "/api/v1/credit/score"

    return OnboardingStatus(
        onboarding_step = step,
        phone_verified  = getattr(current_user, "phone_verified", False),
        kyc_status      = kyc_st,
        credit_status   = credit_status,
        next_step       = next_step,
        next_step_url   = next_step_url,
    )


@router.patch(
    "/me",
    response_model=UserSchema,
    summary="Update User Profile",
    dependencies=[Depends(rate_limiter(requests_per_minute=5))],
)
async def update_me(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Updates non-sensitive profile information for the current user."""
    service = UserService(db)
    updated = await service.update_user(current_user.id, update_data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return updated


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Own Account",
    dependencies=[Depends(rate_limiter(requests_per_minute=1))],
)
async def delete_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently deletes the authenticated user's account and all associated data."""
    service = UserService(db)
    await service.delete_user(current_user.id)


@router.get(
    "",
    response_model=list[UserSchema],
    summary="List All Users (Admin Only)",
)
async def list_users(
    skip:      int = 0,
    limit:     int = 100,
    email:     Optional[str]  = None,
    phone:     Optional[str]  = None,
    is_active: Optional[bool] = None,
    admin:     User = Depends(require_admin),
    db:        AsyncSession = Depends(get_db),
):
    """Allows an administrator to retrieve a paginated and filtered list of all users."""
    service = UserService(db)
    return await service.get_users(
        skip=skip,
        limit=limit,
        email=email,
        phone=phone,
        is_active=is_active,
    )


@router.get(
    "/{user_id}",
    response_model=UserSchema,
    summary="Get User by ID (Admin Only)",
)
async def get_user_by_id(
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Allows an administrator to retrieve any user's profile by their internal ID."""
    service = UserService(db)
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch(
    "/{user_id}",
    response_model=UserSchema,
    summary="Update Any User (Admin Only)",
)
async def admin_update_user(
    user_id: int,
    update_data: UserUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Allows an administrator to update any user's profile or status."""
    service = UserService(db)
    updated = await service.update_user(user_id, update_data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return updated
