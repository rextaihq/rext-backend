from fastapi import APIRouter, Depends, Request, BackgroundTasks, Header
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.schema.user_schema import LoginUser, RegisterUser
from src.api.security.token_utils import verify_token
from sqlalchemy.orm import Session
from src.api.tasks.send_mail import send_email
from src.api.database.database import get_db
from src.utils.response_utils import success, error, created
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextAuthenticationException
)
from datetime import datetime
from user_agents import parse as parse_user_agent
import os
from src.api.middleware.rate_limiter import (
    login_rate_limit,
    registration_rate_limit
)
from src.services.auth_service import AuthService

router = APIRouter()


@router.post("/register")
async def create_user(
    user: RegisterUser,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(registration_rate_limit())
):
    """
    Endpoint to create a new user.
    """
    try:
        # Use auth service
        auth_service = AuthService(db)
        new_user, verification_token = await auth_service.register_user(
            email=user.email,
            username=user.username,
            password=user.password,
            first_name=user.first_name,
            last_name=user.last_name
        )

        # Get frontend URL from environment
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        verification_link = f"{frontend_url}/verify-email?token={verification_token}"

        # Send verification email in background
        background_tasks.add_task(
            send_email,
            to=new_user.email,
            subject="Verify Your Email Address",
            body=f"<p>Welcome {new_user.first_name}!</p><p>Click the link to verify your email: <a href='{verification_link}'>Verify Email</a></p><p>This link will expire in 24 hours.</p>"
        )

        # Commit transaction
        db.commit()
        db.refresh(new_user)

        # Return user data (excluding password)
        user_data = {
            "id": str(new_user.id),
            "username": new_user.username,
            "email": new_user.email,
            "first_name": new_user.first_name,
            "last_name": new_user.last_name,
            "display_name": new_user.display_name,
            "language": new_user.language,
            "timezone": new_user.timezone,
            "status": new_user.status,
            "roles": [{"name": "user", "display_name": "User"}],
            "created_at": new_user.created_at.isoformat() if hasattr(new_user, 'created_at') else None,
        }

        return created(
            data={"user": user_data},
            request=request,
            message="User created successfully"
        )

    except DuplicateResourceException:
        # Re-raise to be handled by middleware
        raise
    except Exception as e:
        db.rollback()
        return error(
            message="Failed to create user",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.post("/login")
async def login_user(
    user: LoginUser,
    request: Request,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(login_rate_limit())
):
    """
    Endpoint to log in a user with table updates.
    """
    try:
        # Parse user agent for device information
        user_agent_string = request.headers.get("user-agent", "Unknown")
        user_agent = parse_user_agent(user_agent_string)
        device_type = "mobile" if user_agent.is_mobile else ("tablet" if user_agent.is_tablet else "desktop")
        device_name = f"{user_agent.browser.family} on {user_agent.os.family}"
        client_ip = request.client.host if request.client else "Unknown"

        device_info = {
            "device_name": device_name,
            "device_type": device_type,
            "user_agent": user_agent_string,
            "ip_address": client_ip
        }

        # Use auth service
        auth_service = AuthService(db)
        db_user, tokens = await auth_service.login_user(
            email=user.email,
            password=user.password,
            device_info=device_info
        )

        # Commit transaction
        db.commit()
        db.refresh(db_user)

        # Get role names for response
        role_names = [ur.role.name for ur in db_user.user_roles if ur.is_primary]

        # Return successful login response
        return success(
            data={
                **tokens,
                "user": {
                    "id": str(db_user.id),
                    "username": db_user.username,
                    "email": db_user.email,
                    "last_login_at": db_user.last_login_at,
                    "login_count": db_user.login_count,
                    "roles": role_names
                }
            },
            request=request,
            message="User logged in successfully"
        )

    except WrextAuthenticationException:
        # Re-raise to be handled by middleware
        raise
    except Exception as e:
        return error(
            message="Login failed due to server error",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.post("/refresh")
async def refresh_access_token(
    request: Request,
    refresh_token: str,
    db: Session = Depends(get_db)
):
    """
    Refresh access token using refresh token.

    This endpoint allows clients to obtain a new access token
    without requiring the user to log in again. Implements refresh
    token rotation for better security - old refresh token is
    blacklisted and a new pair is issued.
    """
    try:
        # Use auth service
        auth_service = AuthService(db)
        tokens = await auth_service.refresh_token(refresh_token)

        # Commit transaction
        db.commit()

        return success(
            data=tokens,
            request=request,
            message="Token refreshed successfully"
        )

    except WrextAuthenticationException:
        # Re-raise to be handled by middleware
        raise
    except Exception as e:
        logger.error(f"Token refresh failed: {str(e)}")
        return error(
            message="Failed to refresh token",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.post("/logout")
async def logout_user(
    request: Request,
    current_user: dict = Depends(get_current_user),
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    """
    Logout user by blacklisting their access token.

    The client should also delete stored refresh tokens locally.
    This prevents the access token from being reused after logout.
    """
    try:
        # Extract token from authorization header
        scheme, token = authorization.split()

        # Decode token to get JTI and expiration
        payload = verify_token(token)
        jti = payload.get("jti")
        exp = payload.get("exp")
        user_id = current_user.get("identity")

        # Use auth service
        auth_service = AuthService(db)
        await auth_service.logout_user(user_id, jti, exp)

        # Commit transaction
        db.commit()

        return success(
            data={"message": "Logged out successfully"},
            request=request,
            message="Logout successful"
        )

    except WrextAuthenticationException:
        # Re-raise to be handled by middleware
        raise
    except Exception as e:
        logger.error(f"Logout failed: {str(e)}")
        return error(
            message="Logout failed",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.get("/verify-email")
async def verify_email(token: str, request: Request, db: Session = Depends(get_db)):
    """
    Verify user's email using the provided token
    """
    try:
        # Use auth service
        auth_service = AuthService(db)
        user = await auth_service.verify_email(token)

        # Commit transaction
        db.commit()

        message = "Email verified successfully" if user.email_verified else "Email already verified"

        return success(
            data={"id": str(user.id)},
            request=request,
            message=message
        )

    except (WrextAuthenticationException, ResourceNotFoundException):
        raise
    except Exception as e:
        return error(
            message="Failed to verify email",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )
