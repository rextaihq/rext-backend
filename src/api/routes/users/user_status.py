from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import datetime, timedelta, timezone

from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import require_permissions
from src.api.schema.user_schema import (
    UserStatusRequest,
    UserStatusResponse,
    DeactivateAccountRequest,
    DeactivateAccountResponse
)
from src.api.models.user_models.users import Users
from src.api.database.async_database import get_async_db
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.utils.audit_helper import create_audit_log_async
from src.api.middleware.permissions import is_admin
from src.services.user_service import UserService
from src.api.middleware.exceptions import ResourceNotFoundException
from sqlalchemy import select

router = APIRouter()


@router.post("/{user_id}/suspend", response_model=UserStatusResponse)
@require_permissions("user.update")
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
                code=ErrorCode.PERMISSION_DENIED,
                status_code=403,
                severity=ErrorSeverity.HIGH,
                request=request
            )

        service = UserService(db)

        # Get target user
        target_user = await service.get_user_by_id(UUID(user_id))
        old_status = target_user.status

        # Update status directly (could be extracted to service method)
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
            message=f"User {target_user.full_name or target_user.email} suspended successfully"
        )

    except ResourceNotFoundException:
        return error(
            message="User not found or access denied",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        logger.error(f"Error suspending user {user_id}: {str(e)}")
        return error(
            message="Failed to suspend user",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


@router.post("/{user_id}/activate", response_model=UserStatusResponse)
@require_permissions("user.update")
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
                code=ErrorCode.PERMISSION_DENIED,
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
            message=f"User {target_user.full_name or target_user.email} activated successfully"
        )

    except ResourceNotFoundException:
        return error(
            message="User not found or access denied",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        logger.error(f"Error activating user {user_id}: {str(e)}")
        return error(
            message="Failed to activate user",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


@router.post("/{user_id}/ban", response_model=UserStatusResponse)
@require_permissions("user.update")
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
                code=ErrorCode.PERMISSION_DENIED,
                status_code=403,
                severity=ErrorSeverity.HIGH,
                request=request
            )

        service = UserService(db)

        # Get target user
        target_user = await service.get_user_by_id(UUID(user_id))
        old_status = target_user.status

        # Update status directly (could be extracted to service method)
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
            message=f"User {target_user.full_name or target_user.email} banned successfully"
        )

    except ResourceNotFoundException:
        return error(
            message="User not found or access denied",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        logger.error(f"Error banning user {user_id}: {str(e)}")
        return error(
            message="Failed to ban user",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


@router.post("/deactivate", response_model=DeactivateAccountResponse)
@require_permissions("user.update")
async def deactivate_account(
    request: Request,
    deactivation_data: DeactivateAccountRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Deactivate user's own account.
    Thin controller - uses UserService.deactivate_account().

    Account will be marked as inactive and scheduled for permanent deletion after 14 days.
    User will be logged out immediately.

    - **reason**: Optional reason for deactivation
    - **confirm**: Must be true to proceed

    Returns deactivation confirmation with scheduled deletion date.
    """
    try:
        user_id = UUID(current_user.get("identity"))
        logger.info(f"Account deactivation requested for user: {user_id}")

        service = UserService(db)

        # Get user and check status
        db_user = await service.get_user_by_id(user_id)

        # Check if already deactivated
        if db_user.status == "inactive":
            return error(
                message="Account is already deactivated",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Store old status for audit
        old_status = db_user.status

        # Check for active subscriptions
        from src.api.models.subscription_models.subscriptions import UserSubscription
        from src.services.subscription_service import SubscriptionService

        subscriptions_result = await db.execute(
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user_id,
                UserSubscription.status.in_(["active", "trialing"])
            )
        )
        active_subs = subscriptions_result.scalars().all()

        if active_subs and not deactivation_data.cancel_subscriptions:
            # Return error with subscription details
            subscription_details = [
                {
                    "subscription_id": str(sub.id),
                    "plan_name": sub.plan.name if sub.plan else "Unknown",
                    "status": sub.status,
                    "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None
                }
                for sub in active_subs
            ]

            return error(
                message="You have active subscriptions. Please cancel them first or enable automatic cancellation.",
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Auto-cancel subscriptions if requested
        if active_subs and deactivation_data.cancel_subscriptions:
            subscription_service = SubscriptionService(db)
            canceled_count = 0
            for sub in active_subs:
                try:
                    await subscription_service.cancel(
                        user_id=user_id,
                        reason="Account deactivation"
                    )
                    canceled_count += 1
                    logger.info(f"Canceled subscription {sub.id} for user {user_id} during account deactivation")
                except Exception as e:
                    logger.error(f"Failed to cancel subscription {sub.id}: {e}")
                    # Continue with other subscriptions

            logger.info(f"Canceled {canceled_count} subscriptions for user {user_id} during deactivation")

        # Deactivate via service
        db_user = await service.deactivate_account(user_id)

        # Calculate scheduled deletion date (14 days from now)
        scheduled_deletion = db_user.deactivated_at + timedelta(days=14)

        # Create audit log
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
                "scheduled_deletion": scheduled_deletion.isoformat(),
                "reason": deactivation_data.reason
            },
            request=request,
            full_name=db_user.full_name,
            user_email=db_user.email
        )

        logger.info(f"User {user_id} deactivated successfully. Scheduled deletion: {scheduled_deletion}")

        response_data = DeactivateAccountResponse(
            user_id=str(db_user.id),
            email=db_user.email,
            status="inactive",
            deactivated_at=db_user.deactivated_at.isoformat(),
            scheduled_deletion_at=scheduled_deletion.isoformat(),
            message=f"Account deactivated successfully. Your account will be permanently deleted on {scheduled_deletion.strftime('%B %d, %Y')}."
        )

        return success(
            data=response_data.model_dump(),
            request=request,
            message="Account deactivated successfully"
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
        logger.error(f"Error deactivating account for user {current_user.get('identity')}: {str(e)}")
        return error(
            message="Failed to deactivate account",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )