import uuid
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import get_settings
from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.middleware.rate_limiter import password_reset_rate_limit
from src.api.schema.response.password_responses import (
    ChangePasswordResponse,
    ResetPasswordResponse,
    VerifyPasswordResponse,
)
from src.api.schema.response_schemas import (
    ErrorCode,
    ErrorSeverity,
    GenericResponse,
    SuccessResponse,
)
from src.api.schema.user_schema import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPassword,
    VerifyPasswordRequest,
)
from src.api.security.dependencies import get_current_user
from src.api.security.token_utils import create_reset_token, decode_and_verify_token
from src.services.user_service import UserService
from src.utils.logger import logger
from src.utils.response_utils import error, success
from src.utils.route_decorators import db_transaction_handler

# No permission gates in this module: every route manages the caller's own
# password, so authentication (get_current_user) is sufficient. The former
# user.read/user.update gates were redundant — every account held them via
# the platform-floor 'user' role, which has been removed.
router = APIRouter()


# Get settings instance
settings = get_settings()


async def send_password_reset_email_task(
    email: str, user_name: str, reset_token: str, user_id: str, frontend_url: str
):
    """
    Background task to send password reset email using professional template.

    Args:
        email: Recipient email address
        user_name: User's name for personalization
        reset_token: Password reset token (not full URL)
        user_id: User ID for email tracking
        frontend_url: Frontend URL for constructing reset link
    """
    from src.api.database.async_database import get_async_db_context
    from src.services.email_helpers import send_auth_email

    try:
        async with get_async_db_context() as async_db:
            await send_auth_email(
                db=async_db,
                email_type="password_reset",
                recipient_email=email,
                user_name=user_name,
                user_id=UUID(user_id),
                token=reset_token,
                frontend_url=frontend_url,
            )
            logger.info(f"Password reset email sent successfully to {email}")
    except Exception as e:
        logger.error(f"Failed to send password reset email to {email}: {str(e)}", exc_info=True)


@router.post("/forgot-password", response_model=SuccessResponse[GenericResponse])
@db_transaction_handler("forgot password", auto_commit=True)
async def forgot_password(
    request: Request,
    forgot_request: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(password_reset_rate_limit()),
):
    """
    Initiate forgot password process.
    Sends password reset email with token.

    SECURITY: Always returns the same response regardless of whether the email
    exists to prevent user enumeration attacks (OWASP A07:2025).
    """
    # Use a generic message for all responses
    generic_message = "If an account with this email exists, a password reset link has been sent."

    # Log at debug level only — do not log the email at info level
    logger.debug("Forgot password request received")

    service = UserService(db)
    user = await service.get_user_by_email(forgot_request.email)

    if user:
        # Generate reset token
        reset_data = {"user_id": str(user.id), "email": user.email, "jti": str(uuid.uuid4())}
        reset_token = create_reset_token(data=reset_data)

        # Set reset token via service
        await service.set_reset_token(user.id, reset_token)

        # Get frontend URL
        frontend_url = settings.FRONTEND_URL

        # Send email in background
        background_tasks.add_task(
            send_password_reset_email_task,
            email=user.email,
            user_name=user.full_name or user.display_name or user.email,
            reset_token=reset_token,
            user_id=str(user.id),
            frontend_url=frontend_url,
        )
        logger.info(f"Password reset initiated for user: {user.id}")

    # Always return the same generic message
    return success(data={"message": generic_message}, request=request, message=generic_message)


@router.post("/reset-password", response_model=SuccessResponse[ResetPasswordResponse])
@db_transaction_handler("reset password", auto_commit=True)
async def reset_password(
    payload: ResetPassword,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(password_reset_rate_limit()),
):
    """
    Reset user password using token from email.
    """
    # Verify token validity first
    # Verify token validity first
    try:
        decode_and_verify_token(payload.token)
    except Exception as e:
        logger.warning(f"Invalid reset token: {str(e)}")
        return error(
            message="Invalid or expired reset token",
            code=ErrorCode.INVALID_VALUE,
            status_code=400,
            severity=ErrorSeverity.MEDIUM,
            request=request,
        )

    # Reset password via service
    service = UserService(db)
    try:
        user = await service.reset_password_with_token(
            reset_token=payload.token, new_password=payload.new_password
        )

    except ResourceNotFoundException:
        return error(
            message="Invalid or expired reset token",
            code=ErrorCode.INVALID_VALUE,
            status_code=400,
            severity=ErrorSeverity.MEDIUM,
            request=request,
        )

    # SECURITY: Revoke all sessions after password reset
    from src.services.session_service import SessionService

    session_service = SessionService(db)
    await session_service.revoke_all_sessions(user.id)

    from src.utils.audit_helper import create_audit_log_async

    await create_audit_log_async(
        db=db,
        user_id=user.id,
        action="auth.password_reset",
        resource_type="user",
        resource_id=str(user.id),
        request=request,
        status="success",
    )

    logger.info(f"Password reset successfully for user: {user.id}, all sessions revoked")
    return success(
        data={"user_id": str(user.id), "sessions_revoked": True},
        request=request,
        message="Password updated successfully. Please login with your new password.",
    )


@router.post("/change-password", response_model=SuccessResponse[ChangePasswordResponse])
@db_transaction_handler("change password", auto_commit=True)
async def change_password(
    request: Request,
    password_data: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(password_reset_rate_limit()),
):
    """
    Change user password (requires authentication).
    """
    try:
        user_id = UUID(current_user.get("identity"))
        service = UserService(db)

        # Change password via service
        user = await service.change_password(
            user_id=user_id,
            current_password=password_data.current_password,
            new_password=password_data.new_password,
        )

        # SECURITY: Revoke all other sessions
        from src.services.session_service import SessionService

        session_service = SessionService(db)
        await session_service.revoke_all_sessions(user_id)

        from src.utils.audit_helper import create_audit_log_async

        await create_audit_log_async(
            db=db,
            user_id=user_id,
            action="auth.password_change",
            resource_type="user",
            resource_id=str(user_id),
            request=request,
            status="success",
        )

        # Send confirmation email
        from src.services.email_helpers import send_auth_email

        try:
            await send_auth_email(
                db=db,
                email_type="password_changed",
                recipient_email=user.email,
                user_name=user.full_name or user.display_name or user.email.split("@")[0],
                user_id=user_id,
                frontend_url=settings.FRONTEND_URL,
                changed_at=user.password_changed_at.strftime("%b %d, %Y %I:%M %p UTC"),
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            logger.info(f"Password changed email sent to {user.email}")
        except Exception as e:
            logger.error(f"Failed to send password changed email: {str(e)}")

        logger.info(f"Password changed successfully for user: {user_id}, all sessions revoked")
        return success(
            data={
                "user_id": str(user.id),
                "password_changed_at": user.password_changed_at.isoformat(),
                "sessions_revoked": True,
            },
            request=request,
            message="Password changed successfully. Please login again on all devices.",
        )

    except ResourceNotFoundException:
        return error(
            message="User not found",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request,
        )
    except RextValidationException as e:
        logger.warning(
            f"Password change validation error for user {current_user.get('identity')}: {e.message}"
        )
        return error(
            message=e.message,
            code=ErrorCode.INVALID_VALUE,
            status_code=400,
            severity=ErrorSeverity.LOW,
            context={"details": e.details} if e.details else None,
            request=request,
        )


# -------------------------
# Verify Password
# -------------------------
@router.post("/verify-password", response_model=SuccessResponse[VerifyPasswordResponse])
@db_transaction_handler("verify password", auto_commit=False)
async def verify_password(
    password_data: VerifyPasswordRequest,  # CHANGED: Added Pydantic schema parameter
    request: Request,  # CHANGED: Moved to second position
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(password_reset_rate_limit()),
):
    """
    Verify user's current password.
    """
    try:
        user_id = UUID(current_user.get("identity"))
        password = password_data.password

        if not password:
            return error(
                message="Password is required",
                request=request,
                code=ErrorCode.VALIDATION_FAILED,
                status_code=400,
                severity=ErrorSeverity.MEDIUM,
            )

        # Verify password via service
        service = UserService(db)
        is_valid = await service.verify_user_password(user_id, password)

        if not is_valid:
            return error(
                message="Invalid password",
                request=request,
                code=ErrorCode.UNAUTHORIZED,
                status_code=401,
                severity=ErrorSeverity.MEDIUM,
            )

        return success(
            data={"verified": True}, request=request, message="Password verified successfully"
        )

    except ResourceNotFoundException:
        return error(
            message="User not found",
            request=request,
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.HIGH,
        )
    except Exception as e:
        logger.error(f"Error verifying password: {str(e)}")
        raise
