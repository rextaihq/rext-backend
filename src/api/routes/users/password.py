from fastapi import APIRouter, Depends, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import uuid
import os
from datetime import datetime

from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.schema.user_schema import (
    ResetPassword,
    ForgotPasswordRequest,
    ChangePasswordRequest
)
from src.api.security.token_utils import (
    hash_password,
    create_reset_token,
    verify_token
)
from src.api.models.user_models.users import Users
from src.api.tasks.send_mail import send_email
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

        # Update user with reset token (direct DB update for now)
        # TODO: Could add set_reset_token() to UserService
        result = await db.execute(
            select(Users).where(Users.id == user.id)
        )
        db_user = result.scalar_one()
        db_user.reset_token = reset_token
        await db.flush()

        # Get frontend URL and create reset link
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        reset_link = f"{frontend_url}/reset-password?token={reset_token}"

        # Send email in background
        background_tasks.add_task(
            send_email,
            to=user.email,
            subject="Reset Your Password",
            body=f"<p>Click the link to reset your password: <a href='{reset_link}'>Reset Password</a></p>"
        )

        logger.info(f"Password reset email sent to: {user.email}")
        return success(
            data={"message": "Password reset link has been sent to your email."},
            request=request,
            message="Forgot password initiated successfully"
        )

    except Exception as e:
        logger.error(f"Forgot password error: {str(e)}")
        return error(
            message="Failed to initiate forgot password",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


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
        # Find user by reset token
        result = await db.execute(
            select(Users).where(Users.reset_token == payload.token)
        )
        user = result.scalar_one_or_none()

        if not user:
            return error(
                message="Invalid or expired reset token",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Verify token validity
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

        # Update password (direct DB update for reset flow)
        # Different from change_password which requires current password
        user.password_hash = hash_password(payload.new_password)
        user.reset_token = None
        user.password_changed_at = datetime.utcnow()
        await db.flush()

        logger.info(f"Password reset successfully for user: {user.id}")
        return success(
            data={"user_id": str(user.id)},
            request=request,
            message="Password updated successfully"
        )

    except Exception as e:
        logger.error(f"Password reset error: {str(e)}")
        return error(
            message="Failed to reset password",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


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

        logger.info(f"Password changed successfully for user: {user_id}")
        return success(
            data={
                "user_id": str(user.id),
                "password_changed_at": user.password_changed_at.isoformat()
            },
            request=request,
            message="Password changed successfully"
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
        return error(
            message="Failed to change password",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )
