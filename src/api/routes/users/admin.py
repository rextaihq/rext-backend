from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.permissions import is_admin
from src.api.schema.response.admin_responses import CleanupResponse, PendingDeletionsResponse
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.user_service import UserService
from src.utils.logger import logger
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler

router = APIRouter()


@router.post("/admin/cleanup-deactivated-accounts", response_model=SuccessResponse[CleanupResponse])
@db_transaction_handler("cleanup deactivated accounts", auto_commit=True)
async def cleanup_deactivated_accounts_endpoint(
    request: Request,
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """Admin endpoint to trigger cleanup of deactivated accounts."""
    service = UserService(db)
    deleted_count = await service.cleanup_deactivated_accounts()

    logger.info(
        "Deactivated account cleanup executed",
        extra={"admin_user_id": current_user.get("identity"), "deleted_count": deleted_count},
    )

    return success(
        data={
            "deleted_count": deleted_count,
            "message": f"Successfully deleted {deleted_count} deactivated account(s)",
        },
        request=request,
        message="Deactivated account cleanup successful",
    )


@router.get("/admin/pending-deletions", response_model=SuccessResponse[PendingDeletionsResponse])
@db_transaction_handler("get pending account deletions", auto_commit=False)
async def get_pending_deletions_endpoint(
    request: Request,
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """Return accounts scheduled for deletion."""
    service = UserService(db)
    pending = await service.get_pending_deletions()

    logger.info(
        "Pending account deletions viewed",
        extra={"admin_user_id": current_user.get("identity"), "count": len(pending)},
    )

    return success(
        data={"pending_deletions": pending, "count": len(pending)},
        request=request,
        message="Pending account deletions retrieved successfully",
    )


@router.post("/admin/cleanup-tokens", response_model=SuccessResponse[CleanupResponse])
@db_transaction_handler("cleanup expired tokens", auto_commit=True)
async def cleanup_tokens_endpoint(
    request: Request,
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """Admin endpoint to remove expired tokens from the blacklist."""
    service = UserService(db)
    deleted_count = await service.cleanup_expired_tokens()

    logger.info(
        "Expired token cleanup executed",
        extra={"admin_user_id": current_user.get("identity"), "deleted_count": deleted_count},
    )

    return success(
        data={
            "deleted_count": deleted_count,
            "message": f"Successfully cleaned up {deleted_count} expired tokens",
        },
        request=request,
        message="Expired token cleanup successful",
    )
