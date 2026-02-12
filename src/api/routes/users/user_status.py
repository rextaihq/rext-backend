from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import datetime, timezone, timedelta, timezone

from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import require_permissions, db_transaction_handler
from src.api.schema.user_schema import (
    UserStatusRequest,
    UserStatusResponse,
    DeactivateAccountRequest,
    DeactivateAccountResponse
)
from src.api.models.user_models.users import Users
from src.api.database.async_database import get_async_db
from src.utils.audit_helper import create_audit_log_async
from src.api.middleware.permissions import is_admin
from sqlalchemy import select
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import ResourceNotFoundException, RextAuthorizationException, RextAuthenticationException, RextValidationException
from src.services.user_service import UserService
from src.services.subscription_service import SubscriptionService

router = APIRouter()


@router.post("/{user_id}/suspend", response_model=UserStatusResponse)
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("suspend user", auto_commit=True)
async def suspend_user(
    user_id: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Suspend a user account (admin only).
    Thin controller - business logic should be in service.

    - **user_id**: ID of the user to suspend
    - **reason**: Optional reason for suspension

    Requires admin privileges.
    """
    try:
        # Check if current user is admin
        if not is_admin(current_user):
            return error(
                message="Insufficient permissions. Admin role required.",
                code=ErrorCode.FORBIDDEN,
                status_code=403,
                severity=ErrorSeverity.HIGH,
                request=request
            )

        service = UserService(db)

        # Get target user
        target_user = await service.get_user_by_id(UUID(user_id))
        old_status = target_user.status

        # Update status directly
        target_user.status = "suspended"
        target_user.updated_at = datetime.now(timezone.utc)
        await db.flush()

        # Get admin user for audit log
        admin_user_id = UUID(current_user.get("identity"))
        admin_user = await service.get_user_by_id(admin_user_id)

        # Create audit log
        await create_audit_log_async(
            db=db,
            user_id=str(admin_user_id),
            action="user.suspend",
            resource_type="user",
            resource_id=str(user_id),
            old_values={"status": old_status},
            new_values={"status": "suspended", "reason": status_data.reason},
            request=request,
            full_name=admin_user.full_name if admin_user else None,
            user_email=admin_user.email if admin_user else None
        )

        logger.info(f"User {user_id} suspended by admin {admin_user_id}")

        response_data = UserStatusResponse(
            user_id=str(target_user.id),
            full_name=target_user.full_name or target_user.display_name or target_user.email,
            email=target_user.email,
            old_status=old_status,
            new_status="suspended",
            changed_by=admin_user.full_name or admin_user.display_name or admin_user.email if admin_user else "unknown",
            reason=status_data.reason,
            changed_at=target_user.updated_at.isoformat()
        )

        return success(
            data=response_data.model_dump(),
            request=request,
            message="User suspended successfully"
        )

    except ResourceNotFoundException:
        return error(
            message="User not found",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        logger.error(f"Error suspending user {user_id}: {str(e)}")
        raise


@router.post("/{user_id}/activate", response_model=UserStatusResponse)
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("activate user", auto_commit=True)
async def activate_user(
    user_id: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Activate a suspended or banned user account (admin only).
    Thin controller - uses UserService.reactivate_account().

    - **user_id**: ID of the user to activate
    - **reason**: Optional reason for activation

    Requires admin privileges.
    """
    try:
        # Check if current user is admin
        if not is_admin(current_user):
            return error(
                message="Insufficient permissions. Admin role required.",
                code=ErrorCode.FORBIDDEN,
                status_code=403,
                severity=ErrorSeverity.HIGH,
                request=request
            )

        service = UserService(db)

        # Get target user to record old status
        target_user = await service.get_user_by_id(UUID(user_id))
        old_status = target_user.status

        # Reactivate via service
        target_user = await service.reactivate_account(UUID(user_id))

        # Get admin user for audit log
        admin_user_id = UUID(current_user.get("identity"))
        admin_user = await service.get_user_by_id(admin_user_id)

        # Create audit log
        await create_audit_log_async(
            db=db,
            user_id=str(admin_user_id),
            action="user.activate",
            resource_type="user",
            resource_id=str(user_id),
            old_values={"status": old_status},
            new_values={"status": "active", "reason": status_data.reason},
            request=request,
            full_name=admin_user.full_name if admin_user else None,
            user_email=admin_user.email if admin_user else None
        )

        logger.info(f"User {user_id} activated by admin {admin_user_id}")

        response_data = UserStatusResponse(
            user_id=str(target_user.id),
            full_name=target_user.full_name or target_user.display_name or target_user.email,
            email=target_user.email,
            old_status=old_status,
            new_status="active",
            changed_by=admin_user.full_name or admin_user.display_name or admin_user.email if admin_user else "unknown",
            reason=status_data.reason,
            changed_at=target_user.updated_at.isoformat()
        )

        return success(
            data=response_data.model_dump(),
            request=request,
            message="User activated successfully"
        )

    except ResourceNotFoundException:
        return error(
            message="User not found",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        logger.error(f"Error activating user {user_id}: {str(e)}")
        raise


@router.post("/{user_id}/ban", response_model=UserStatusResponse)
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("ban user", auto_commit=True)
async def ban_user(
    user_id: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Ban a user account (admin only).
    Thin controller - business logic could be extracted to service.

    - **user_id**: ID of the user to ban
    - **reason**: Optional reason for ban

    Requires admin privileges.
    """
    try:
        # Check if current user is admin
        if not is_admin(current_user):
            return error(
                message="Insufficient permissions. Admin role required.",
                code=ErrorCode.FORBIDDEN,
                status_code=403,
                severity=ErrorSeverity.HIGH,
                request=request
            )

        service = UserService(db)

        # Get target user
        target_user = await service.get_user_by_id(UUID(user_id))
        old_status = target_user.status

        # Update status directly
        target_user.status = "banned"
        target_user.updated_at = datetime.now(timezone.utc)
        await db.flush()

        # Get admin user for audit log
        admin_user_id = UUID(current_user.get("identity"))
        admin_user = await service.get_user_by_id(admin_user_id)

        # Create audit log
        await create_audit_log_async(
            db=db,
            user_id=str(admin_user_id),
            action="user.ban",
            resource_type="user",
            resource_id=str(user_id),
            old_values={"status": old_status},
            new_values={"status": "banned", "reason": status_data.reason},
            request=request,
            full_name=admin_user.full_name if admin_user else None,
            user_email=admin_user.email if admin_user else None
        )

        logger.info(f"User {user_id} banned by admin {admin_user_id}")

        response_data = UserStatusResponse(
            user_id=str(target_user.id),
            full_name=target_user.full_name or target_user.display_name or target_user.email,
            email=target_user.email,
            old_status=old_status,
            new_status="banned",
            changed_by=admin_user.full_name or admin_user.display_name or admin_user.email if admin_user else "unknown",
            reason=status_data.reason,
            changed_at=target_user.updated_at.isoformat()
        )

        return success(
            data=response_data.model_dump(),
            request=request,
            message="User banned successfully"
        )

    except ResourceNotFoundException:
        return error(
            message="User not found",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        logger.error(f"Error banning user {user_id}: {str(e)}")
        raise


