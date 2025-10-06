from fastapi import APIRouter, Depends, Request
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from sqlalchemy.orm import Session
from src.api.database.database import get_db
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.utils.token_cleanup import cleanup_expired_tokens
from src.utils.account_cleanup import delete_deactivated_accounts, get_pending_deletions
from src.api.middleware.permissions import is_admin

router = APIRouter()


@router.post("/admin/cleanup-deactivated-accounts")
def cleanup_deactivated_accounts_endpoint(
    request: Request,
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to manually trigger cleanup of deactivated accounts.

    Permanently deletes accounts that have been deactivated for 14+ days.
    Only accessible to users with admin or super_admin role.

    Returns:
        Number of accounts deleted

    Note:
        This should ideally be run as a scheduled job (cron/celery)
        but can be triggered manually via this endpoint.
    """
    try:
        deleted_count = delete_deactivated_accounts(db)

        logger.info(
            f"Admin {current_user.get('identity')} triggered deactivated account cleanup - "
            f"deleted {deleted_count} account(s)"
        )

        return success(
            data={
                "deleted_count": deleted_count,
                "message": f"Successfully deleted {deleted_count} deactivated account(s)"
            },
            request=request,
            message=f"Cleaned up {deleted_count} deactivated account(s)"
        )

    except Exception as e:
        logger.error(f"Deactivated account cleanup failed: {str(e)}")
        return error(
            message="Account cleanup failed",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.get("/admin/pending-deletions")
def get_pending_deletions_endpoint(
    request: Request,
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to view accounts scheduled for deletion.

    Returns list of deactivated accounts with their scheduled deletion dates.
    Only accessible to users with admin or super_admin role.
    """
    try:
        pending = get_pending_deletions(db)

        logger.info(f"Admin {current_user.get('identity')} viewed pending account deletions")

        return success(
            data={
                "pending_deletions": pending,
                "count": len(pending)
            },
            request=request,
            message=f"Retrieved {len(pending)} account(s) pending deletion"
        )

    except Exception as e:
        logger.error(f"Failed to retrieve pending deletions: {str(e)}")
        return error(
            message="Failed to retrieve pending deletions",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.post("/admin/cleanup-tokens")
def cleanup_tokens_endpoint(
    request: Request,
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to manually trigger token cleanup.

    Removes expired tokens from blacklist to prevent table growth.
    Only accessible to users with admin or super_admin role.

    Args:
        request: FastAPI request object
        current_user: Current authenticated user (must be admin)
        _: Admin check dependency (enforces admin role)
        db: Database session

    Returns:
        Number of tokens deleted

    Raises:
        403: If user is not an admin
        500: If cleanup process fails
    """
    try:
        deleted_count = cleanup_expired_tokens(db)

        logger.info(f"Admin {current_user.get('identity')} triggered token cleanup - deleted {deleted_count} tokens")

        return success(
            data={
                "deleted_count": deleted_count,
                "message": f"Successfully cleaned up {deleted_count} expired tokens"
            },
            request=request,
            message=f"Cleaned up {deleted_count} expired tokens"
        )
    except Exception as e:
        logger.error(f"Manual token cleanup failed: {str(e)}")
        return error(
            message="Token cleanup failed",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )
