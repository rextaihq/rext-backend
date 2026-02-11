from fastapi import APIRouter, Depends, Request, BackgroundTasks, Header
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.schema.user_schema import (
    LoginUser, 
    RegisterUser, 
    RegisterWithInvitation, 
    LoginWithInvitation,
    RefreshTokenRequest,  # Added
    ResendVerificationRequest,  # Added
    OAuthLoginRequest,  # Added
    OAuthLinkRequest  # Added
)
from src.api.security.token_utils import decode_and_verify_token
from src.api.config import get_settings
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.email_service import EmailService
from src.api.database.async_database import get_async_db
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    RextAuthenticationException,
    ResourceNotFoundException,
    BusinessRuleViolationException,
    RextValidationException
)
from datetime import datetime
from src.services.notification_helper import schedule_if_allowed
from user_agents import parse as parse_user_agent
from src.api.models.user_models.notification_preferences import NotificationPreferences
import os
from src.api.middleware.rate_limiter import (
    login_rate_limit,
    registration_rate_limit,
    oauth_rate_limit
)
from src.services.auth_service import AuthService
from src.services.invitation_service import InvitationService
from src.services.user_service import UserService
from src.utils.invitation_utils import is_invitation_expired
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
@db_transaction_handler("user registration", auto_commit=True)
async def create_user(
    user: RegisterUser,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(registration_rate_limit())
):
    """
    Endpoint to create a new user.
    """
    # Use auth service
    auth_service = AuthService(db)
    new_user, verification_token = await auth_service.register_user(
        email=user.email,
        password=user.password,
        full_name=user.full_name
    )

    # notification preference for the user
    notification_preference = NotificationPreferences(
        user_id=new_user.id,
        email_notifications=True,
        in_app_notifications=True,
        ws_invite_received=True,
        ws_invite_accepted=True,
        ws_role_changed=True,
        ws_member_removed=True,
        gen_started=True,
        gen_completed=True,
        gen_failed=True,
        gen_published=True,
        billing_payment_success=True,
        billing_payment_failed=True,
        billing_subscription_cancelled=True,
        billing_subscription_expiring=True,
        billing_trial_ending=True,
        billing_usage_limit_warning=True,
        billing_usage_limit_exceeded=True,
        kb_processing_completed=True,
        kb_processing_failed=True,
        digest_enabled=True,
        digest_frequency="daily",
        marketing_updates=False
    )
    db.add(notification_preference)
    
    # Commit here to ensure user exists before background task
    await db.commit()
    await db.refresh(new_user)

    # Get frontend URL from environment
    frontend_url = settings.FRONTEND_URL

    # Send verification email in background
    background_tasks.add_task(
        send_verification_email_task,
        email=new_user.email,
        first_name=new_user.full_name or new_user.display_name,
        verification_token=verification_token,
        user_id=str(new_user.id),
        frontend_url=frontend_url
    )
    
    return {
        "user": {
            "id": str(new_user.id),
            "email": new_user.email,
            "full_name": new_user.full_name,
            "display_name": new_user.display_name,
            "language": new_user.language,
            "timezone": new_user.timezone,
            "status": new_user.status,
            "roles": [{"name": "user", "display_name": "User"}],
            "created_at": new_user.created_at.isoformat() if hasattr(new_user, 'created_at') else None,
        }
    }


@router.post("/register-with-invitation")
@db_transaction_handler("registration with invitation", auto_commit=True)
async def register_with_invitation(
    user_data: RegisterWithInvitation,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(registration_rate_limit())
):
    """
    Create a new user account via workspace invitation OR accept invitation for existing user.
    """
    # Step 1: Validate invitation token
    invitation_service = InvitationService(db)
    invitation = await invitation_service.get_invitation_by_token(user_data.invitation_token)

    logger.info(
        "Processing invitation registration",
        extra={
            "invitation_id": str(invitation.id),
            "invitation_status": invitation.status,
            "invitation_email": invitation.email,
            "registration_email": user_data.email
        }
    )

    # Check invitation status
    if invitation.status != "pending":
        if invitation.status == "accepted":
            raise BusinessRuleViolationException(
                message="This invitation has already been accepted.",
                rule_name="invitation_already_accepted"
            )
        elif invitation.status == "expired":
            raise BusinessRuleViolationException(
                message="This invitation has expired.",
                rule_name="invitation_expired"
            )
        else:
            raise BusinessRuleViolationException(
                message=f"Invitation is {invitation.status} and cannot be used",
                rule_name="invitation_invalid"
            )

    # Check if invitation expired
    if is_invitation_expired(invitation):
        invitation.status = "expired"
        await db.flush()
        raise BusinessRuleViolationException(
            message="Invitation has expired",
            rule_name="invitation_not_expired"
        )

    # Step 2: Verify email matches invitation
    if user_data.email.lower() != invitation.email.lower():
        raise BusinessRuleViolationException(
            message=f"Email must match invitation email: {invitation.email}",
            rule_name="email_must_match_invitation"
        )

    # Step 3: Check if user already exists
    user_service = UserService(db)
    existing_user = await user_service.get_user_by_email(user_data.email)
    user_exists = existing_user is not None
    current_user = existing_user

    # Step 4: Create user account if doesn't exist
    if not user_exists:
        auth_service = AuthService(db)
        new_user, _ = await auth_service.register_user(
            email=user_data.email,
            password=user_data.password,
            full_name=user_data.full_name
        )
        new_user.email_verified = True
        new_user.email_verified_at = datetime.utcnow()
        await db.flush()
        current_user = new_user

    # Step 5: Auto-accept invitation
    acceptance_result = await invitation_service.accept_invitation(
        invitation_id=invitation.id,
        user_id=current_user.id
    )

    # Handle notification preferences for new users
    if not user_exists:
        notification_preference = NotificationPreferences(
            user_id=current_user.id,
            email_notifications=True,
            in_app_notifications=True,
            ws_invite_received=True,
            ws_invite_accepted=True,
            ws_role_changed=True,
            ws_member_removed=True,
            gen_started=True,
            gen_completed=True,
            gen_failed=True,
            gen_published=True,
            billing_payment_success=True,
            billing_payment_failed=True,
            billing_subscription_cancelled=True,
            billing_subscription_expiring=True,
            billing_trial_ending=True,
            billing_usage_limit_warning=True,
            billing_usage_limit_exceeded=True,
            kb_processing_completed=True,
            kb_processing_failed=True,
            digest_enabled=True,
            digest_frequency="daily",
            marketing_updates=False
        )
        db.add(notification_preference)

    await db.commit()
    await db.refresh(current_user)

    # Step 6: Send welcome email for new users
    if not user_exists:
        background_tasks.add_task(
            send_welcome_email_task,
            email=current_user.email,
            first_name=current_user.full_name or current_user.display_name,
            user_id=str(current_user.id),
            frontend_url=settings.FRONTEND_URL
        )

    # Step 7: Response details
    from src.services.workspace_service import WorkspaceService
    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace(invitation.workspace_id)

    from src.api.models.user_models.roles import Role
    from sqlalchemy import select
    result = await db.execute(select(Role).where(Role.id == invitation.role_id))
    assigned_role = result.scalar_one_or_none()

    # Schedule notification
    await schedule_if_allowed(
        db=db,
        user_id=str(invitation.invited_by_user_id),
        background_tasks=background_tasks,
        pref_flag="ws_invite_accepted",
        message=f"{current_user.email} has accepted an invitation to join a workspace.",
        payload={
            "user_id": str(current_user.id),
            "workspace_id": str(workspace.id),
            "invitation_id": str(invitation.id)
        }
    )

    return {
        "user": {
            "id": str(current_user.id),
            "email": current_user.email,
            "full_name": current_user.full_name,
            "display_name": current_user.display_name,
            "email_verified": current_user.email_verified,
            "roles": [{"name": assigned_role.name, "display_name": assigned_role.display_name}] if assigned_role else [{"name": "user", "display_name": "User"}]
        },
        "workspace": {
            "id": str(workspace.id),
            "slug": workspace.slug,
            "name": workspace.name,
            "membership_id": acceptance_result["membership_id"]
        },
        "invitation_accepted": True,
        "message": f"Welcome! You've joined {workspace.name}"
    }


@router.post("/login")
@db_transaction_handler("user login", auto_commit=True)
async def login_user(
    user: LoginUser,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(login_rate_limit())
):
    """
    Endpoint to log in a user with table updates.
    """
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
    
    # We wrap the service call in a local try/except ONLY for login to handle
    # the specific requirement of committing failed login attempts for account locking.
    try:
        db_user, tokens = await auth_service.login_user(
            email=user.email,
            password=user.password,
            device_info=device_info,
            background_tasks=background_tasks,
            db=db
        )
        
        # Explicit commit here for login context tracking
        await db.commit()
        
        return {
            **tokens,
            "user": {
                "id": str(db_user.id),
                "email": db_user.email,
                "full_name": db_user.full_name,
                "display_name": db_user.display_name,
                "avatar_url": db_user.avatar_url,
                "last_login_at": db_user.last_login_at,
                "login_count": db_user.login_count,
                "roles": tokens.get("roles", []),
                "permissions": tokens.get("permissions", [])
            }
        }
    except RextAuthenticationException as auth_error:
        # Commit transaction to persist failed login attempts for security
        await db.commit()
        raise auth_error


@router.post("/refresh")
@db_transaction_handler("token refresh", auto_commit=True)
async def refresh_access_token(
    token_data: RefreshTokenRequest,  # CHANGED: Added Pydantic schema
    request: Request,  # CHANGED: Moved to second position
    db: AsyncSession = Depends(get_async_db)
):
    """
    Refresh access token using refresh token.
    """
    try:
        # CHANGED: Access refresh_token from Pydantic model
        refresh_token = token_data.refresh_token

        if not refresh_token:
            return error(
                message="Refresh token is required",
                code=ErrorCode.INVALID_VALUE,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Use auth service
        auth_service = AuthService(db)
        tokens = await auth_service.refresh_token(refresh_token)

    if not refresh_token:
        raise RextValidationException(
            message="Refresh token is required"
        )

    # Use auth service
    auth_service = AuthService(db)
    tokens = await auth_service.refresh_token(refresh_token)

    return tokens


@router.post("/logout")
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("user logout", auto_commit=True)
async def logout_user(
    request: Request,
    current_user: dict = Depends(get_current_user),
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Logout user by blacklisting their access token.
    """
    # Extract token from authorization header
    scheme, token = authorization.split()

    # Decode token to get JTI and expiration
    payload = decode_and_verify_token(token, expected_type="access")
    jti = payload.get("jti")
    exp = payload.get("exp")
    user_id = current_user.get("identity")

    # Use auth service
    auth_service = AuthService(db)
    await auth_service.logout_user(user_id, jti, exp)

    return {"message": "Logged out successfully"}


@router.get("/verify-email")
@db_transaction_handler("email verification", auto_commit=True)
async def verify_email(
    token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Verify user's email using the provided token and send welcome email
    """
    # Use auth service
    auth_service = AuthService(db)
    user = await auth_service.verify_email(token)

    # Send welcome email after first-time verification
    if user.email_verified:
        frontend_url = settings.FRONTEND_URL
        background_tasks.add_task(
            send_welcome_email_task,
            email=user.email,
            first_name=user.full_name or user.display_name,
            user_id=str(user.id),
            frontend_url=frontend_url
        )

    return {
        "id": str(user.id),
        "message": "Email verified successfully" if user.email_verified else "Email already verified"
    }


@router.post("/resend-verification")
@db_transaction_handler("resend verification", auto_commit=True)
async def resend_verification(
    email_data: ResendVerificationRequest,  # CHANGED: Added Pydantic schema
    request: Request,  # CHANGED: Moved to second position
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(registration_rate_limit())
):
    """
    Resend email verification link.
    """
    try:
        # CHANGED: Access email from Pydantic model
        email = email_data.email

        if not email:
            return error(
                message="Email is required",
                code=ErrorCode.INVALID_VALUE,
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
            first_name=user.full_name or user.display_name,
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

    except (RextAuthenticationException, ResourceNotFoundException):
        raise
    except Exception as e:
        logger.error(f"Resend verification error: {str(e)}")
        return error(
            message="Failed to resend verification email",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


@router.post("/oauth/login")
@db_transaction_handler("oauth login", auto_commit=True)
async def oauth_login(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(oauth_rate_limit())
):
    """
    Login or register user via OAuth provider.
    """
    from src.services.oauth_service import OAuthService
    from datetime import datetime

    try:
        # CHANGED: Access data from Pydantic model instead of request.json()
        # Parse token_expires_at from ISO string to datetime (if provided)
        # Database uses TIMESTAMP WITHOUT TIME ZONE, so we need timezone-naive datetimes
        token_expires_at = None
        if oauth_data.token_expires_at:
            try:
                expires_str = oauth_data.token_expires_at
                # Handle ISO format with 'Z' suffix (e.g., '2025-01-01T00:00:00Z')
                if expires_str.endswith('Z'):
                    expires_str = expires_str[:-1]  # Remove 'Z' to get naive datetime
                parsed_dt = datetime.fromisoformat(expires_str)
                # If parsed datetime has timezone info, convert to naive UTC
                if parsed_dt.tzinfo is not None:
                    parsed_dt = parsed_dt.replace(tzinfo=None)
                token_expires_at = parsed_dt
            except (ValueError, AttributeError) as e:
                logger.warning(f"Failed to parse token_expires_at: {oauth_data.token_expires_at}, error: {e}")

        oauth_service = OAuthService(db)
        new_user, tokens = await oauth_service.oauth_login_or_register(
            provider=oauth_data.provider,
            provider_account_id=oauth_data.provider_account_id,
            provider_email=oauth_data.provider_email,
            provider_name=oauth_data.provider_name,
            provider_avatar_url=oauth_data.provider_avatar_url,
            provider_username=oauth_data.provider_username,
            access_token=oauth_data.access_token,
            refresh_token=oauth_data.refresh_token,
            token_expires_at=token_expires_at
        )

        # Check if notification preferences already exist for this user
        # (OAuth can return existing users, so we should only create prefs for new users)
        from sqlalchemy import select
        existing_prefs_result = await db.execute(
            select(NotificationPreferences).where(NotificationPreferences.user_id == new_user.id)
        )
        existing_prefs = existing_prefs_result.scalar_one_or_none()
        
        if not existing_prefs:
            # Create notification preferences only for new users
            notification_preference = NotificationPreferences(
                user_id=new_user.id,
                email_notifications=True,
                in_app_notifications=True,
                ws_invite_received=True,
                ws_invite_accepted=True,
                ws_role_changed=True,
                ws_member_removed=True,
                gen_started=True,
                gen_completed=True,
                gen_failed=True,
                gen_published=True,
                billing_payment_success=True,
                billing_payment_failed=True,
                billing_subscription_cancelled=True,
                billing_subscription_expiring=True,
                billing_trial_ending=True,
                billing_usage_limit_warning=True,
                billing_usage_limit_exceeded=True,
                kb_processing_completed=True,
                kb_processing_failed=True,
                digest_enabled=True,
                digest_frequency="daily",
                marketing_updates=False
            )
            db.add(notification_preference)
            await db.commit()
            logger.info(f"Created notification preferences for new OAuth user: {new_user.id}")
        
        await db.refresh(new_user)
        # Extract roles and permissions from service response (same pattern as login)
        role_names = tokens.get("roles", [])
        permissions = tokens.get("permissions", [])

        return success(
            data={
                **tokens,
                "user": {
                    "id": str(new_user.id),
                    "email": new_user.email,
                    "full_name": new_user.full_name,
                    "display_name": new_user.display_name,
                    "avatar_url": new_user.avatar_url,
                    "last_login_at": new_user.last_login_at,
                    "login_count": new_user.login_count,
                    "roles": role_names,
                    "permissions": permissions
                }
            },
            request=request,
            message="OAuth login successful"
        )

    except RextAuthenticationException:
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
            request=request
        )
        db.add(notification_preference)
        await db.flush()
        logger.info(f"Created notification preferences for new OAuth user: {new_user.id}")
    
    await db.refresh(new_user)

    return {
        **tokens,
        "user": {
            "id": str(new_user.id),
            "email": new_user.email,
            "full_name": new_user.full_name,
            "display_name": new_user.display_name,
            "avatar_url": new_user.avatar_url,
            "last_login_at": new_user.last_login_at,
            "login_count": new_user.login_count,
            "roles": tokens.get("roles", []),
            "permissions": tokens.get("permissions", [])
        }
    }


@router.post("/oauth/link")
@db_transaction_handler("link oauth", auto_commit=True)
async def link_oauth(
    oauth_data: OAuthLinkRequest,  # CHANGED: Added Pydantic schema
    request: Request,  # CHANGED: Moved to second position
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(oauth_rate_limit())

):
    """
    Link an OAuth account to the current user.
    """
    from src.services.oauth_service import OAuthService
    from datetime import datetime

    try:
        # CHANGED: Access data from Pydantic model instead of request.json()
        user_id = UUID(current_user.get("identity"))

        # Parse token_expires_at from ISO string to datetime (if provided)
        # Database uses TIMESTAMP WITHOUT TIME ZONE, so we need timezone-naive datetimes
        token_expires_at = None
        if oauth_data.token_expires_at:
            try:
                expires_str = oauth_data.token_expires_at
                # Handle ISO format with 'Z' suffix (e.g., '2025-01-01T00:00:00Z')
                if expires_str.endswith('Z'):
                    expires_str = expires_str[:-1]  # Remove 'Z' to get naive datetime
                parsed_dt = datetime.fromisoformat(expires_str)
                # If parsed datetime has timezone info, convert to naive UTC
                if parsed_dt.tzinfo is not None:
                    parsed_dt = parsed_dt.replace(tzinfo=None)
                token_expires_at = parsed_dt
            except (ValueError, AttributeError) as e:
                logger.warning(f"Failed to parse token_expires_at: {oauth_data.token_expires_at}, error: {e}")

        oauth_service = OAuthService(db)
        oauth_account = await oauth_service.link_oauth_account(
            user_id=user_id,
            provider=oauth_data.provider,
            provider_account_id=oauth_data.provider_account_id,
            provider_email=oauth_data.provider_email,
            provider_username=oauth_data.provider_username,
            provider_avatar_url=oauth_data.provider_avatar_url,
            access_token=oauth_data.access_token,
            refresh_token=oauth_data.refresh_token,
            token_expires_at=token_expires_at
        )

        return success(
            data=oauth_account.to_dict(),
            request=request,
            message=f"{oauth_data.provider.capitalize()} account linked successfully"
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
            request=request
        )


@router.delete("/oauth/{provider}")
@db_transaction_handler("unlink oauth", auto_commit=True)
async def unlink_oauth(
    provider: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(oauth_rate_limit())

):
    """
    Unlink an OAuth account from the current user.
    """
    from src.services.oauth_service import OAuthService

    user_id = UUID(current_user.get("identity"))
    oauth_service = OAuthService(db)
    await oauth_service.unlink_oauth_account(user_id, provider)

    return {
        "provider": provider,
        "message": f"{provider.capitalize()} account unlinked successfully"
    }
