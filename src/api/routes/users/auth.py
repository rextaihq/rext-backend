from fastapi import APIRouter, Depends, Request, BackgroundTasks, Header
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.schema.user_schema import (
    LoginUser, 
    RegisterUser, 
    RegisterWithInvitation, 
    RefreshTokenRequest,
    ResendVerificationRequest,
    OAuthLoginRequest,
    OAuthLinkRequest,
    UserResponse,
    LoginResponse
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
from datetime import datetime, timezone
from src.services.notification_helper import schedule_if_allowed
from src.services.notification_preferences_service import NotificationPreferencesService
from user_agents import parse as parse_user_agent
from src.api.models.user_models.notification_preferences import NotificationPreferences
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
from src.utils.response_utils import success, error, created
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity

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
@db_transaction_handler("user registration", auto_commit=False)
async def create_user(
    user: RegisterUser,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """
    Endpoint to create a new user.
    """
    from src.utils.password_utils import validate_password_strength
    
    # 1. Validate password before rate limiting so weak password mistakes do not consume limits
    validate_password_strength(user.password)

    # 2. Enforce registration rate limits explicitly
    limiter = registration_rate_limit()
    await limiter(request)

    # Use auth service
    auth_service = AuthService(db)
    new_user, verification_token = await auth_service.register_user(
        email=user.email,
        password=user.password,
        full_name=user.full_name
    )

    # Create notification preferences using standardized service
    pref_service = NotificationPreferencesService(db)
    await pref_service.get_or_create(new_user.id)
    
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
        "user": UserResponse.model_validate(new_user).model_dump()
    }




@router.post("/login")
@db_transaction_handler("user login", auto_commit=False)
async def login_user(
    user: LoginUser,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(login_rate_limit())
) -> dict:
    """
    Endpoint to log in a user with device tracking and security persistence.
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
    
    try:
        db_user, tokens = await auth_service.login_user(
            email=user.email,
            password=user.password,
            device_info=device_info,
            background_tasks=background_tasks,
            db=db
        )
        
        # PERSIST: We must commit here to save login sessions/logins counts
        await db.commit()
        
        # Build response using standardized schema
        return {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": tokens.get("token_type", "bearer"),
            "expires_in": tokens.get("expires_in", 3600),
            "user": {
                **UserResponse.model_validate(db_user).model_dump(),
                "roles": tokens.get("roles", []),
                "permissions": tokens.get("permissions", [])
            }
        }

    except RextAuthenticationException as auth_error:
        # CRITICAL: Commit transaction to persist failed login attempts for account locking
        await db.commit()
        raise auth_error


@router.post("/refresh")
@db_transaction_handler("token refresh", auto_commit=True)
async def refresh_access_token(
    request: Request,
    token_data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """
    Refresh access token using refresh token.
    """
    # Use auth service
    auth_service = AuthService(db)
    tokens = await auth_service.refresh_token(token_data.refresh_token)

    return tokens


@router.post("/logout")
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("user logout", auto_commit=True)
async def logout_user(
    request: Request,
    current_user: dict = Depends(get_current_user),
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_async_db)
) -> dict:
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
) -> dict:
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
    request: Request,
    verification_data: ResendVerificationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(registration_rate_limit())
) -> dict:
    """
    Resend email verification link.
    """
    # Use auth service
    auth_service = AuthService(db)
    user, verification_token = await auth_service.resend_verification_email(verification_data.email)

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
    return {
        "message": "Verification email has been resent"
    }


@router.post("/oauth/login")
@db_transaction_handler("oauth login", auto_commit=True)
async def oauth_login(
    oauth_data: OAuthLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(oauth_rate_limit())
) -> dict:
    """
    Login or register user via OAuth provider.
    """
    from src.services.oauth_service import OAuthService

    oauth_service = OAuthService(db)
    # Parse expires_at if provided
    token_expires_at = None
    if oauth_data.token_expires_at:
        try:
            expires_str = oauth_data.token_expires_at
            if expires_str.endswith('Z'):
                expires_str = expires_str[:-1]
            token_expires_at = datetime.fromisoformat(expires_str)
        except Exception:
            pass

    new_user, tokens = await oauth_service.oauth_login_or_register(
        provider=oauth_data.provider,
        provider_account_id=oauth_data.provider_account_id,
        provider_email=oauth_data.provider_email,
        provider_name=oauth_data.provider_name or "",
        provider_avatar_url=oauth_data.provider_avatar_url,
        provider_username=oauth_data.provider_username,
        access_token=oauth_data.access_token,
        refresh_token=oauth_data.refresh_token,
        token_expires_at=token_expires_at
    )

    # Guarantee notification preferences exist using service
    pref_service = NotificationPreferencesService(db)
    await pref_service.get_or_create(new_user.id)

    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": tokens.get("token_type", "bearer"),
        "expires_in": tokens.get("expires_in", 3600),
        "user": UserResponse.model_validate(new_user).model_dump(),
        "roles": tokens.get("roles", []),
        "permissions": tokens.get("permissions", [])
    }


@router.post("/register-with-invitation")
@db_transaction_handler("register with invitation", auto_commit=False)
async def register_with_invitation(
    user_data: RegisterWithInvitation,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """
    Create or use account via workspace invitation.
    """
    from src.utils.password_utils import validate_password_strength
    
    # 1. Validate password before rate limiting so weak password mistakes do not consume limits
    validate_password_strength(user_data.password)

    # 2. Enforce registration rate limits explicitly
    limiter = registration_rate_limit()
    await limiter(request)
    invitation_service = InvitationService(db)
    invitation = await invitation_service.get_invitation_by_token(user_data.invitation_token)

    if invitation.status != "pending" or is_invitation_expired(invitation):
        raise BusinessRuleViolationException("Invitation is invalid or expired")

    if user_data.email.lower() != invitation.email.lower():
        raise BusinessRuleViolationException("Email must match invitation")

    user_service = UserService(db)
    existing_user = await user_service.get_user_by_email(user_data.email)

    if not existing_user:
        auth_service = AuthService(db)
        existing_user, _ = await auth_service.register_user(
            email=user_data.email,
            password=user_data.password,
            full_name=user_data.full_name
        )
        existing_user.email_verified = True
        existing_user.email_verified_at = datetime.now(timezone.utc)
        
        # Add notification preference using service
        pref_service = NotificationPreferencesService(db)
        await pref_service.get_or_create(existing_user.id)
        
        background_tasks.add_task(
            send_welcome_email_task,
            email=existing_user.email,
            first_name=existing_user.full_name or existing_user.display_name,
            user_id=str(existing_user.id),
            frontend_url=settings.FRONTEND_URL
        )

    # Accept invitation
    acceptance_result = await invitation_service.accept_invitation(
        invitation_id=invitation.id,
        user_id=existing_user.id
    )

    await db.commit()
    
    # Notify inviter
    await schedule_if_allowed(
        db=db,
        user_id=str(invitation.invited_by_user_id),
        background_tasks=background_tasks,
        pref_flag="ws_invite_accepted",
        message=f"{existing_user.email} joined your workspace.",
        payload={"user_id": str(existing_user.id), "workspace_id": str(invitation.workspace_id)}
    )

    return {
        "user": UserResponse.model_validate(existing_user).model_dump(),
        "invitation_accepted": True
    }


@router.post("/oauth/link")
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("link oauth account", auto_commit=True)
async def link_oauth(
    oauth_data: OAuthLinkRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """
    Link OAuth account to current user.
    """
    from src.services.oauth_service import OAuthService
    user_id = UUID(current_user.get("identity"))
    oauth_service = OAuthService(db)
    
    token_expires_at = None
    if oauth_data.token_expires_at:
        try:
            token_expires_at = datetime.fromisoformat(oauth_data.token_expires_at.replace('Z', ''))
        except Exception:
            pass

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

    return oauth_account.to_dict()


@router.delete("/oauth/{provider}")
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("unlink oauth account", auto_commit=True)
async def unlink_oauth(
    provider: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """
    Unlink OAuth account from current user.
    """
    from src.services.oauth_service import OAuthService
    user_id = UUID(current_user.get("identity"))
    oauth_service = OAuthService(db)
    
    await oauth_service.unlink_oauth_account(user_id, provider)
    return {"provider": provider, "status": "unlinked"}
