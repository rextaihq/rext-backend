from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import get_settings
from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextAuthenticationException,
    RextValidationException,
)
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.schema.response.admin_responses import (
    DeactivateAccountResponseSchema,
    UserStatusActionResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.user_schema import (
    DeactivateAccountRequest,
    DeactivateAccountResponse,
    UserStatusRequest,
)
from src.api.security.dependencies import get_current_user
from src.api.security.token_utils import verify_password
from src.services.session_service import SessionService
from src.services.subscription_service import SubscriptionService
from src.services.user_service import UserService
from src.utils.audit_helper import create_audit_log_async
from src.utils.logger import logger
from src.utils.rbac_utils import assert_target_manageable_by
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions

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
    """
    service = UserService(db)

    # Super Admin accounts are protected from status changes by lesser admins.
    await assert_target_manageable_by(
        db,
        UUID(str(current_user.get("identity"))),
        UUID(user_id),
        action=action_name.split(".")[-1],
    )

    # Delegate status change to service layer
    target_user, old_status = await service.change_user_status(UUID(user_id), new_status)

    # Suspended and banned users must lose access immediately — revoking their
    # sessions blacklists the live access tokens and kills the refresh tokens,
    # so an already-signed-in tab cannot keep working until its token expires.
    if new_status in ("suspended", "banned"):
        await SessionService(db).revoke_all_sessions(UUID(user_id))

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

    # Build response data
    response_data = {
        "user_id": str(target_user.id),
        "full_name": target_user.full_name or target_user.display_name or target_user.email,
        "email": target_user.email,
        "old_status": old_status,
        "new_status": new_status,
        "changed_by": (
            admin_user.full_name or admin_user.display_name or admin_user.email
            if admin_user
            else "unknown"
        ),
        "reason": status_data.reason,
        "changed_at": target_user.updated_at.isoformat(),
    }

    return success(
        data=response_data,
        request=request,
        message=f"User {target_user.full_name or target_user.email} {new_status} successfully",
    )


@router.post("/{user_id}/suspend", response_model=SuccessResponse[UserStatusActionResponse])
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
        db=db,
    )


@router.post("/{user_id}/activate", response_model=SuccessResponse[UserStatusActionResponse])
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("activate user", auto_commit=True)
async def activate_user(
    user_id: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
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
        db=db,
    )


@router.post("/{user_id}/ban", response_model=SuccessResponse[UserStatusActionResponse])
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
        db=db,
    )


async def send_deactivation_email_task(
    email: str, first_name: str, user_id: str, frontend_url: str, retention_days: int = 14
):
    """Background task to send the self-deactivation confirmation email."""
    from src.api.database.async_database import get_async_db_context
    from src.services.email_helpers import send_auth_email

    try:
        async with get_async_db_context() as async_db:
            await send_auth_email(
                db=async_db,
                email_type="account_deactivated",
                recipient_email=email,
                user_name=first_name,
                user_id=UUID(user_id),
                frontend_url=frontend_url,
                retention_days=retention_days,
            )
            logger.info(f"Deactivation email sent successfully to {email}")
    except Exception as e:
        logger.error(f"Failed to send deactivation email to {email}: {str(e)}", exc_info=True)


@router.post("/deactivate", response_model=SuccessResponse[DeactivateAccountResponseSchema])
@db_transaction_handler("deactivate account", auto_commit=True)
async def deactivate_self(
    request: Request,
    deactivate_data: DeactivateAccountRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Self-deactivation of account by the current user.

    Emails a confirmation telling the owner how long they have and that logging
    back in reactivates the account (see AuthService.login's reactivation
    branch) — deactivation leaves deleted_at NULL, so there is no recovery
    token involved.
    """
    user_id = UUID(current_user.get("identity"))
    service = UserService(db)
    user = await service.get_user_by_id(user_id)

    if not user:
        raise ResourceNotFoundException(resource_type="user", resource_id=str(user_id))

    # Verify the password submitted in the confirmation dialog
    if not verify_password(password=deactivate_data.password, hashed_password=user.password_hash):
        raise RextAuthenticationException(
            message="Incorrect password. Please try again.", context={"user_id": str(user_id)}
        )

    old_status = user.status

    # Check active subscriptions
    subscriptions_result = await db.execute(
        select(UserSubscription).where(
            UserSubscription.user_id == user_id,
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
        )
    )
    active_subs = subscriptions_result.scalars().all()

    if active_subs and not deactivate_data.cancel_subscriptions:
        raise RextValidationException(
            message="You have active subscriptions. Please cancel them first or enable automatic cancellation."
        )

    if active_subs:
        sub_service = SubscriptionService(db)
        try:
            await sub_service.cancel(
                user_id=user_id,
                reason="Account deactivation",
                cancel_immediately=True,
            )
        except Exception as e:
            logger.error(f"Failed to cancel subscription during deactivation: {e}")

    # Deactivate: status -> "inactive" with deactivated_at set and deleted_at
    # left NULL, so the 14-day cleanup job can pick the account up
    db_user = await service.deactivate_account(user_id)
    scheduled_deletion = db_user.deactivated_at + timedelta(days=14)

    # Queued, not sent inline, so a mail failure can't roll back the
    # deactivation the user just confirmed.
    background_tasks.add_task(
        send_deactivation_email_task,
        email=db_user.email,
        first_name=db_user.full_name or db_user.display_name or "there",
        user_id=str(db_user.id),
        frontend_url=get_settings().FRONTEND_URL,
        retention_days=get_settings().USER_DELETION_RETENTION_DAYS,
    )

    # Audit log
    await create_audit_log_async(
        db=db,
        user_id=str(user_id),
        action="user.self_deactivate",
        resource_type="user",
        resource_id=str(user_id),
        old_values={"status": old_status},
        new_values={"status": "inactive", "reason": deactivate_data.reason},
        request=request,
    )

    return success(
        data=DeactivateAccountResponse(
            user_id=user_id,
            email=db_user.email,
            status="inactive",
            deactivated_at=db_user.deactivated_at,
            scheduled_deletion_at=scheduled_deletion,
            message="Your account has been deactivated. It will be permanently deleted after 14 days unless you log back in.",
        ).model_dump(mode="json"),
        request=request,
        message="Account deactivated successfully",
    )
