from fastapi import APIRouter, Depends, Request, BackgroundTasks, Header
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.schema.user_schema import LoginUser, RegisterUser
from src.api.security.token_utils import verify_token
from src.api.config import get_settings
from sqlalchemy.orm import Session
from src.services.email_service import EmailService
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
from uuid import UUID

router = APIRouter()


# Get settings instance
settings = get_settings()

async def send_verification_email_task(
    email: str,
    first_name: str,
    verification_token: str,
    user_id: str,
    frontend_url: str
):
    """
    Background task to send email verification email using professional template.

    Args:
        email: Recipient email address
        first_name: User's first name for personalization
        verification_token: Verification token (not full URL)
        user_id: User ID for email tracking
        frontend_url: Frontend URL for constructing verification link
    """
    from src.api.database.async_database import get_async_db_context
    from src.services.email_helpers import send_auth_email

    try:
        async with get_async_db_context() as async_db:
            await send_auth_email(
                db=async_db,
                email_type="verification",
                recipient_email=email,
                user_name=first_name,
                user_id=UUID(user_id),
                token=verification_token,
                frontend_url=frontend_url
            )
            logger.info(f"Verification email sent successfully to {email}")
    except Exception as e:
        logger.error(f"Failed to send verification email to {email}: {str(e)}", exc_info=True)


async def send_welcome_email_task(
    email: str,
    first_name: str,
    user_id: str,
    frontend_url: str
):
    """
    Background task to send welcome email after email verification.

    Args:
        email: Recipient email address
        first_name: User's first name for personalization
        user_id: User ID for email tracking
        frontend_url: Frontend URL
    """
    from src.api.database.async_database import get_async_db_context
    from src.services.email_helpers import send_auth_email

    try:
        async with get_async_db_context() as async_db:
            await send_auth_email(
                db=async_db,
                email_type="welcome",
                recipient_email=email,
                user_name=first_name,
                user_id=UUID(user_id),
                frontend_url=frontend_url
            )
            logger.info(f"Welcome email sent successfully to {email}")
    except Exception as e:
        logger.error(f"Failed to send welcome email to {email}: {str(e)}", exc_info=True)


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
        frontend_url = settings.FRONTEND_URL

        # Send verification email in background using professional template
        background_tasks.add_task(
            send_verification_email_task,
            email=new_user.email,
            first_name=new_user.first_name,
            verification_token=verification_token,
            user_id=str(new_user.id),
            frontend_url=frontend_url
        )

        # Return user data (excluding password)
        # Note: Transaction will be committed by transaction decorator (Task 2.2)
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
        # Re-raise to be handled by middleware (transaction will be rolled back automatically)
        logger.error(f"User registration failed: {str(e)}", exc_info=True)
        raise


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

        # Extract roles and permissions from service response
        role_names = tokens.get("roles", [])
        permissions = tokens.get("permissions", [])

        # Return successful login response
        return success(
            data={
                **tokens,
                "user": {
                    "id": str(db_user.id),
                    "username": db_user.username,
                    "email": db_user.email,
                    "first_name": db_user.first_name,
                    "last_name": db_user.last_name,
                    "avatar_url": db_user.avatar_url,
                    "last_login_at": db_user.last_login_at,
                    "login_count": db_user.login_count,
                    "roles": role_names,
                    "permissions": permissions
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
    db: Session = Depends(get_db)
):
    """
    Refresh access token using refresh token.

    This endpoint allows clients to obtain a new access token
    without requiring the user to log in again. Implements refresh
    token rotation for better security - old refresh token is
    blacklisted and a new pair is issued.

    Request Body:
    {
        "refresh_token": "your-refresh-token-here"
    }

    Security Note: Refresh token is now sent in POST body instead of URL
    to prevent token exposure in server logs and browser history.
    """
    try:
        # Extract refresh token from request body
        body = await request.json()
        refresh_token = body.get("refresh_token")

        if not refresh_token:
            return error(
                message="Refresh token is required",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Use auth service
        auth_service = AuthService(db)
        tokens = await auth_service.refresh_token(refresh_token)

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
async def verify_email(
    token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Verify user's email using the provided token and send welcome email
    """
    try:
        # Use auth service
        auth_service = AuthService(db)
        user = await auth_service.verify_email(token)

        # Send welcome email after first-time verification
        if user.email_verified:
            frontend_url = settings.FRONTEND_URL
            background_tasks.add_task(
                send_welcome_email_task,
                email=user.email,
                first_name=user.first_name or user.username,
                user_id=str(user.id),
                frontend_url=frontend_url
            )

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


@router.post("/resend-verification")
async def resend_verification(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(registration_rate_limit())
):
    """
    Resend email verification link.

    Request Body:
    {
        "email": "user@example.com"
    }
    """
    try:
        body = await request.json()
        email = body.get("email")

        if not email:
            return error(
                message="Email is required",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Use auth service
        auth_service = AuthService(db)
        user, verification_token = await auth_service.resend_verification_email(email)

        # Get frontend URL
        frontend_url = settings.FRONTEND_URL

        # Send verification email in background
        background_tasks.add_task(
            send_verification_email_task,
            email=user.email,
            first_name=user.first_name or user.username,
            verification_token=verification_token,
            user_id=str(user.id),
            frontend_url=frontend_url
        )

        logger.info(f"Verification email resent to: {user.email}")
        return success(
            data={"message": "Verification email has been resent"},
            request=request,
            message="Verification email sent successfully"
        )

    except (WrextAuthenticationException, ResourceNotFoundException):
        raise
    except Exception as e:
        logger.error(f"Resend verification error: {str(e)}")
        return error(
            message="Failed to resend verification email",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.post("/oauth/login")
async def oauth_login(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Login or register user via OAuth provider.

    This endpoint handles the OAuth callback from the frontend.
    It automatically creates a new user if one doesn't exist,
    or links the OAuth account to an existing user with the same email.

    Request Body:
    {
        "provider": "google" | "github",
        "provider_account_id": "123456789",
        "provider_email": "user@example.com",
        "provider_name": "John Doe",
        "provider_avatar_url": "https://...",  // optional
        "provider_username": "johndoe",  // optional
        "access_token": "...",  // optional
        "refresh_token": "...",  // optional
        "token_expires_at": "2024-..."  // optional
    }
    """
    from src.services.oauth_service import OAuthService

    try:
        body = await request.json()

        oauth_service = OAuthService(db)
        user, tokens = await oauth_service.oauth_login_or_register(
            provider=body.get("provider"),
            provider_account_id=body.get("provider_account_id"),
            provider_email=body.get("provider_email"),
            provider_name=body.get("provider_name", ""),
            provider_avatar_url=body.get("provider_avatar_url"),
            provider_username=body.get("provider_username"),
            access_token=body.get("access_token"),
            refresh_token=body.get("refresh_token"),
            token_expires_at=body.get("token_expires_at")
        )

        # Extract roles and permissions from service response (same pattern as login)
        role_names = tokens.get("roles", [])
        permissions = tokens.get("permissions", [])

        return success(
            data={
                **tokens,
                "user": {
                    "id": str(user.id),
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "avatar_url": user.avatar_url,
                    "last_login_at": user.last_login_at,
                    "login_count": user.login_count,
                    "roles": role_names,
                    "permissions": permissions
                }
            },
            request=request,
            message="OAuth login successful"
        )

    except WrextAuthenticationException:
        raise
    except DuplicateResourceException:
        raise
    except Exception as e:
        logger.error(f"OAuth login failed: {str(e)}", exc_info=True)
        return error(
            message="OAuth login failed",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.post("/oauth/link")
async def link_oauth(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Link an OAuth account to the current user.

    This allows users to add OAuth providers to their existing account
    for alternative login methods.

    Request Body:
    {
        "provider": "google" | "github",
        "provider_account_id": "123456789",
        "provider_email": "user@example.com",
        "provider_username": "johndoe",  // optional
        "provider_avatar_url": "https://...",  // optional
        "access_token": "...",  // optional
        "refresh_token": "...",  // optional
        "token_expires_at": "2024-..."  // optional
    }
    """
    from src.services.oauth_service import OAuthService

    try:
        body = await request.json()
        user_id = UUID(current_user.get("identity"))

        oauth_service = OAuthService(db)
        oauth_account = await oauth_service.link_oauth_account(
            user_id=user_id,
            provider=body.get("provider"),
            provider_account_id=body.get("provider_account_id"),
            provider_email=body.get("provider_email"),
            provider_username=body.get("provider_username"),
            provider_avatar_url=body.get("provider_avatar_url"),
            access_token=body.get("access_token"),
            refresh_token=body.get("refresh_token"),
            token_expires_at=body.get("token_expires_at")
        )

        return success(
            data=oauth_account.to_dict(),
            request=request,
            message=f"{body.get('provider').capitalize()} account linked successfully"
        )

    except (DuplicateResourceException, ResourceNotFoundException):
        raise
    except Exception as e:
        logger.error(f"OAuth link failed: {str(e)}", exc_info=True)
        return error(
            message="Failed to link OAuth account",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.delete("/oauth/{provider}")
async def unlink_oauth(
    provider: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Unlink an OAuth account from the current user.

    Path Parameters:
        provider: OAuth provider to unlink (google, github, etc.)
    """
    from src.services.oauth_service import OAuthService

    try:
        user_id = UUID(current_user.get("identity"))

        oauth_service = OAuthService(db)
        await oauth_service.unlink_oauth_account(user_id, provider)

        return success(
            data={"provider": provider},
            request=request,
            message=f"{provider.capitalize()} account unlinked successfully"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.error(f"OAuth unlink failed: {str(e)}", exc_info=True)
        return error(
            message="Failed to unlink OAuth account",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )
