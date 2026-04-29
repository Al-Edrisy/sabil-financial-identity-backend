"""
app/dependencies/admin.py — Admin-only access guard.

Usage:
    from app.dependencies.admin import require_admin

    @router.get("/admin/something")
    async def admin_endpoint(admin: User = Depends(require_admin)):
        ...

Admin status is controlled by the User.is_admin boolean column.
To promote a user to admin, set is_admin = True directly in the database
(or via a dedicated internal tool — never expose a public "make me admin" route).
"""

from fastapi import Depends, HTTPException, status
from app.dependencies.auth import get_current_user
from app.models.user import User


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    FastAPI dependency that enforces admin access.
    Returns the current user if they are an admin; raises HTTP 403 otherwise.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )
    return current_user
