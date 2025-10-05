from fastapi import APIRouter, Depends, Request, BackgroundTasks
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.schema.user_schema import (
    ResetPassword,
    ForgotPasswordRequest,
    ChangePasswordRequest
)
from src.api.security.token_utils import (
    hash_password,
    verify_password,
    create_reset_token,
    verify_token
)
from sqlalchemy.orm import Session
from src.api.models.user_models.users import Users
from src.api.tasks.send_mail import send_email
from src.api.database.database import get_db
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from datetime import datetime
import uuid
import os
from src.api.middleware.rate_limiter import password_reset_rate_limit

router = APIRouter()


@router.post("/forgot-password")
def forgot_password(
    request: Request,
    forgot_request: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(password_reset_rate_limit())
):
    """
    Initiate forgot password process
    """
    try:
        logger.info(f"Initiating forgot password for email: {forgot_request.email}")
        db_user = db.query(Users).filter(Users.email == forgot_request.email).first()
        if not db_user:
            return error(
                message="User with this email does not exist",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Generate reset token and expiry
        reset_data = {
            "user_id": str(db_user.id),
            "email": db_user.email,
            "jti": str(uuid.uuid4())
        }
        reset_token = create_reset_token(data=reset_data)
        db_user.reset_token = reset_token
        db.commit()
        db.refresh(db_user)

        # Get frontend URL from environment
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        reset_link = f"{frontend_url}/reset-password?token={reset_token}"

        # Send email in background
        background_tasks.add_task(
            send_email,
            to=db_user.email,
            subject="Reset Your Password",
            body=f"<p>Click the link to reset your password: <a href='{reset_link}'>Reset Password</a></p>"
        )

        return success(
            data={"message": "Password reset link has been sent to your email."},
            request=request,
            message="Forgot password initiated successfully"
        )
    except Exception as e:
        return error(
            message="Failed to initiate forgot password",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.post("/reset-password")
def reset_password(
    payload: ResetPassword,
    request: Request,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(password_reset_rate_limit())
):
    """
    Reset user password
    """
    try:
        user = db.query(Users).filter(Users.reset_token == payload.token).first()
        if not user:
            return error(message="Invalid token", request=request)

    #    verify token
        logger.info("Verifying reset token")
        _ = verify_token(payload.token)


        # Update password
        user.password_hash = hash_password(payload.new_password)
        user.reset_token = None
        user.password_changed_at = datetime.utcnow()
        db.commit()
        db.refresh(user)

        return success(data={"id": str(user.id)}, request=request, message="Password updated successfully")

    except Exception as e:
        return error(
            message="Failed to reset password",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.post("/change-password")
def change_password(
    request: Request,
    password_data: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Change user password (requires authentication)

    - **current_password**: Current password for verification
    - **new_password**: New password (min 8 characters)
    - **confirm_password**: Confirmation of new password
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"Password change requested for user: {user_id}")

        # Get user from database
        db_user = db.query(Users).filter(Users.id == user_id).first()
        if not db_user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Verify current password
        if not verify_password(password_data.current_password, db_user.password_hash):
            logger.warning(f"Failed password change attempt for user {user_id}: incorrect current password")
            return error(
                message="Current password is incorrect",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Check if new password is same as current (optional security measure)
        if verify_password(password_data.new_password, db_user.password_hash):
            return error(
                message="New password must be different from current password",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Update password
        db_user.password_hash = hash_password(password_data.new_password)
        db_user.password_changed_at = datetime.utcnow()
        db.commit()
        db.refresh(db_user)

        logger.info(f"Password changed successfully for user: {user_id}")
        return success(
            data={
                "user_id": str(db_user.id),
                "password_changed_at": db_user.password_changed_at.isoformat()
            },
            request=request,
            message="Password changed successfully"
        )

    except Exception as e:
        logger.error(f"Error changing password for user {current_user.get('identity')}: {str(e)}")
        db.rollback()
        return error(
            message="Failed to change password",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )
