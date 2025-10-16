from fastapi import APIRouter, Depends, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
import uuid
import os

from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.config import get_settings
from src.api.schema.user_schema import (
    ResetPassword,
    ForgotPasswordRequest,
    ChangePasswordRequest
)
from src.api.security.token_utils import create_reset_token, verify_token
from src.api.database.async_database import get_async_db
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    WrextValidationException
)
from src.services.user_service import UserService
from src.api.middleware.rate_limiter import password_reset_rate_limit

router = APIRouter()


# Get settings instance
settings = get_settings()

async def send_password_reset_email_task(
    email: str,
    user_name: str,
    reset_token: str,
    user_id: str,
    frontend_url: str
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
                frontend_url=frontend_url
            )
            logger.info(f"Password reset email sent successfully to {email}")
    except Exception as e:
        logger.error(f"Failed to send password reset email to {email}: {str(e)}", exc_info=True)


@router.post("/forgot-password")
async def forgot_password(
    request: Request,
    forgot_request: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(password_reset_rate_limit())
):
    """
    Initiate forgot password process.
    Sends password reset email with token.
    """
    try:
        logger.info(f"Forgot password request for: {forgot_request.email}")
        service = UserService(db)

        # Get user by email
        user = await service.get_user_by_email(forgot_request.email)
        if not user:
            return error(
                message="User with this email does not exist",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Generate reset token
        reset_data = {
            "user_id": str(user.id),
            "email": user.email,
            "jti": str(uuid.uuid4())
        }
        reset_token = create_reset_token(data=reset_data)

        # Set reset token via service
        await service.set_reset_token(user.id, reset_token)

        # Get frontend URL
        frontend_url = settings.FRONTEND_URL

        # Send email in background using professional template
        background_tasks.add_task(
            send_password_reset_email_task,
            email=user.email,
            user_name=user.first_name or user.username,
            reset_token=reset_token,
            user_id=str(user.id),
            frontend_url=frontend_url
        )

        logger.info(f"Password reset email sent to: {user.email}")
        return success(
            data={"message": "Password reset link has been sent to your email."},
            request=request,
            message="Forgot password initiated successfully"
        )

    except Exception as e:
        logger.error(f"Forgot password error: {str(e)}")
        raise


@router.post("/reset-password")
async def reset_password(
    payload: ResetPassword,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(password_reset_rate_limit())
):
    """
    Reset user password using token from email.
    """
    try:
        # Verify token validity first
        try:
            verify_token(payload.token)
        except Exception as e:
            logger.warning(f"Invalid reset token: {str(e)}")
            return error(
                message="Invalid or expired reset token",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Reset password via service
        service = UserService(db)
        user = await service.reset_password_with_token(
            reset_token=payload.token,
            new_password=payload.new_password
        )

        # SECURITY: Revoke all sessions after password reset
        # This prevents attackers from maintaining access if they had stolen sessions
        from src.services.session_service import SessionService
        session_service = SessionService(db)
        await session_service.revoke_all_sessions(user.id)

        logger.info(f"Password reset successfully for user: {user.id}, all sessions revoked")
        return success(
            data={
                "user_id": str(user.id),
                "sessions_revoked": True
            },
            request=request,
            message="Password updated successfully. Please login with your new password."
        )

    except ResourceNotFoundException as e:
        return error(
            message=str(e),
            code=ErrorCode.INVALID_INPUT,
            status_code=400,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        logger.error(f"Password reset error: {str(e)}")
        raise


@router.post("/change-password")
async def change_password(
    request: Request,
    password_data: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Change user password (requires authentication).
    Thin controller - uses UserService for all business logic.

    - **current_password**: Current password for verification
    - **new_password**: New password (min 8 characters)
    - **confirm_password**: Confirmation of new password
    """
    try:
        user_id = UUID(current_user.get("identity"))
        service = UserService(db)

        # Change password via service (handles all validation)
        user = await service.change_password(
            user_id=user_id,
            current_password=password_data.current_password,
            new_password=password_data.new_password
        )

        # SECURITY: Revoke all other sessions when password changes
        # This forces users to re-login on all devices, preventing stolen sessions
        from src.services.session_service import SessionService
        session_service = SessionService(db)
        await session_service.revoke_all_sessions(user_id)

        # Send password changed confirmation email
        from src.services.email_helpers import send_auth_email
        from datetime import datetime

        try:
            await send_auth_email(
                db=db,
                email_type="password_changed",
                recipient_email=user.email,
                user_name=user.first_name or user.email.split('@')[0],
                user_id=user_id,
                frontend_url=settings.FRONTEND_URL,
                changed_at=user.password_changed_at.strftime("%b %d, %Y %I:%M %p UTC"),
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent")
            )
            logger.info(f"Password changed email sent to {user.email}")
        except Exception as e:
            # Don't fail the password change if email fails
            logger.error(f"Failed to send password changed email: {str(e)}", exc_info=True)

        logger.info(f"Password changed successfully for user: {user_id}, all sessions revoked")
        return success(
            data={
                "user_id": str(user.id),
                "password_changed_at": user.password_changed_at.isoformat(),
                "sessions_revoked": True  # Inform frontend that re-login is needed
            },
            request=request,
            message="Password changed successfully. Please login again on all devices."
        )

    except ResourceNotFoundException:
        return error(
            message="User not found",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except WrextValidationException as e:
        # Service returns validation errors for incorrect password
        logger.warning(f"Password change validation error for user {current_user.get('identity')}: {e.message}")
        return error(
            message=e.message,
            code=ErrorCode.INVALID_INPUT,
            status_code=400,
            severity=ErrorSeverity.LOW,
            context={"details": e.details} if e.details else None,
            request=request
        )
    except Exception as e:
        logger.error(f"Error changing password: {str(e)}")
        raise


# -------------------------
# Verify Password
# -------------------------
@router.post("/verify-password")
async def verify_password(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Verify user's current password.
    
    Used for confirming sensitive operations like workspace deletion.
    
    Body:
        {
          "password": "user's current password"
        }
    
    Returns:
        200: Password is correct
        400: Password is incorrect
    """
    try:
        user_id = UUID(current_user.get("identity"))
        body = await request.json()
        password = body.get("password")

        if not password:
            return error(
                message="Password is required",
                request=request,
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
                severity=ErrorSeverity.MEDIUM
            )

        # Verify password via service
        service = UserService(db)
        is_valid = await service.verify_user_password(user_id, password)

        if not is_valid:
            return error(
                message="Invalid password",
                request=request,
                code=ErrorCode.AUTHENTICATION_FAILED,
                status_code=401,
                severity=ErrorSeverity.MEDIUM
            )

        return success(
            data={"verified": True},
            request=request,
            message="Password verified successfully"
        )

    except ResourceNotFoundException:
        return error(
            message="User not found",
            request=request,
            code=ErrorCode.NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.HIGH
        )
    except Exception as e:
        logger.error(f"Error verifying password: {str(e)}")
        raise
