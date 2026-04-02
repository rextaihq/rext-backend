from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime, timezone, timedelta

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
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import ResourceNotFoundException, RextAuthenticationException, RextValidationException
from src.services.user_service import UserService
from src.services.subscription_service import SubscriptionService

router = APIRouter()


async def _handle_status_change(
    user_id: str,
    new_status: str,
    action_name: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict,
    db: AsyncSession,
):
    """
    Shared logic for admin-initiated user status changes (suspend, ban, etc.).

    Delegates the actual status mutation to UserService.change_user_status(),
    then handles audit logging, response building, and success messaging.

    Args:
        user_id: Target user ID string
        new_status: Status to set (e.g., "suspended", "banned")
        action_name: Audit action name (e.g., "user.suspend", "user.ban")
        request: FastAPI Request object for audit/response context
        status_data: Request body with optional reason
        current_user: Authenticated admin user dict from JWT
        db: Async database session

    Returns:
        Success response dict via success() utility
    """
    service = UserService(db)

    # Delegate status change to service layer
    target_user, old_status = await service.change_user_status(
        UUID(user_id), new_status
    )

    # Get admin user details for audit log
    admin_user_id = UUID(current_user.get("identity"))
    admin_user = await service.get_user_by_id(admin_user_id)

    # Create audit log
    await create_audit_log_async(
        db=db,
        user_id=str(admin_user_id),
        action=action_name,
        resource_type="user",
        resource_id=str(user_id),
        old_values={"status": old_status},
        new_values={"status": new_status, "reason": status_data.reason},
        request=request,
        full_name=admin_user.full_name if admin_user else None,
        user_email=admin_user.email if admin_user else None,
    )

    logger.info(f"User {user_id} {new_status} by admin {admin_user_id}")

    # Build response
    response_data = UserStatusResponse(
        user_id=str(target_user.id),
        full_name=target_user.full_name or target_user.display_name or target_user.email,
        email=target_user.email,
        old_status=old_status,
        new_status=new_status,
        changed_by=(
            admin_user.full_name or admin_user.display_name or admin_user.email
            if admin_user else "unknown"
        ),
        reason=status_data.reason,
        changed_at=target_user.updated_at.isoformat(),
    )

    return success(
        data=response_data.model_dump(),
        request=request,
        message=f"User {target_user.full_name or target_user.email} {new_status} successfully",
    )


@router.post("/{user_id}/suspend", response_model=UserStatusResponse)
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("suspend user", auto_commit=True)
async def suspend_user(
    user_id: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Suspend a user account (admin only).
    """
    return await _handle_status_change(
        user_id=user_id,
        new_status="suspended",
        action_name="user.suspend",
        request=request,
        status_data=status_data,
        current_user=current_user,
        db=db
    )

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
    """
    return await _handle_status_change(
        user_id=user_id,
        new_status="active",
        action_name="user.activate",
        request=request,
        status_data=status_data,
        current_user=current_user,
        db=db
    )

@router.post("/{user_id}/ban", response_model=UserStatusResponse)
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("ban user", auto_commit=True)
async def ban_user(
    user_id: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Ban a user account (admin only).
    """
    return await _handle_status_change(
        user_id=user_id,
        new_status="banned",
        action_name="user.ban",
        request=request,
        status_data=status_data,
        current_user=current_user,
        db=db
    )

@router.post("/deactivate", response_model=DeactivateAccountResponse)
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("deactivate account", auto_commit=True)
async def deactivate_account(
    request: Request,
    deactivation_data: DeactivateAccountRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Deactivate user's own account.
    """
    user_id = UUID(current_user.get("identity"))
    service = UserService(db)

    # Verify password
    if not await service.verify_user_password(user_id, deactivation_data.password):
        raise RextAuthenticationException(
            message="Invalid password. Please enter your current password to deactivate your account."
        )

    # Get user
    db_user = await service.get_user_by_id(user_id)
    if db_user.status == "inactive":
        return error(
            message="Account is already deactivated",
            code=ErrorCode.INVALID_VALUE,
            status_code=400,
            severity=ErrorSeverity.LOW,
            request=request
        )

    old_status = db_user.status

    # Handle subscriptions
    from src.api.models.subscription_models.subscriptions import UserSubscription, SubscriptionStatus
    subscriptions_result = await db.execute(
        select(UserSubscription)
        .where(
            UserSubscription.user_id == user_id,
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
        )
    )
    active_subs = subscriptions_result.scalars().all()

    if active_subs and not deactivation_data.cancel_subscriptions:
        return error(
            message="You have active subscriptions. Please cancel them first or enable automatic cancellation.",
            code=ErrorCode.VALIDATION_FAILED,
            status_code=400,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )

    if active_subs and deactivation_data.cancel_subscriptions:
        sub_service = SubscriptionService(db)
        for sub in active_subs:
            try:
                await sub_service.cancel(user_id=user_id, reason="Account deactivation")
            except Exception as e:
                logger.error(f"Failed to cancel subscription {sub.id}: {e}")

    # Deactivate
    db_user = await service.deactivate_account(user_id)
    scheduled_deletion = db_user.deactivated_at + timedelta(days=14)

    # Audit log
    await create_audit_log_async(
        db=db,
        user_id=str(user_id),
        action="user.deactivate",
        resource_type="user",
        resource_id=str(user_id),
        old_values={"status": old_status},
        new_values={
            "status": "inactive",
            "deactivated_at": db_user.deactivated_at.isoformat(),
            "scheduled_deletion": scheduled_deletion.isoformat()
        },
        request=request,
        full_name=db_user.full_name,
        user_email=db_user.email
    )

    return success(
        data=DeactivateAccountResponse(
            status="inactive",
            deactivated_at=db_user.deactivated_at.isoformat(),
            scheduled_deletion=scheduled_deletion.isoformat(),
            message="Your account has been deactivated. It will be permanently deleted after 14 days unless you log back in."
        ).model_dump(),
        request=request,
        message="Account deactivated successfully"
    )
