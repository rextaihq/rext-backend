from fastapi import APIRouter, Depends, Request, BackgroundTasks, Header, Body, HTTPException, status
from typing import Optional
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.schema.user_schema import (
    LoginUser,
    RegisterUser,
    RegisterWithInvitation,
    RefreshTokenRequest,
    LogoutRequest,
    ResendVerificationRequest,
    OAuthLoginRequest,
    OAuthLinkRequest,
    UserResponse,
)
from src.api.security.token_utils import decode_and_verify_token, verify_refresh_token
from src.api.config import get_settings
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.database.async_database import get_async_db
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.response_utils import success
from src.api.middleware.exceptions import (
    RextAuthenticationException,
    BusinessRuleViolationException,
    DuplicateResourceException,
)
from datetime import datetime, timezone
from src.services.notification_helper import schedule_if_allowed
from src.services.notification_preferences_service import NotificationPreferencesService
from user_agents import parse as parse_user_agent
from src.api.middleware.rate_limiter import (
    login_rate_limit,
    registration_rate_limit,
    oauth_rate_limit,
    get_device_fingerprint
)
from src.utils.email_domain_validator import is_disposable_email
from src.services.account_creation_allowlist_service import AccountCreationAllowlistService
from src.services.auth_service import AuthService
from src.services.subscription_service import SubscriptionService
from src.services.invitation_service import InvitationService
from src.services.user_service import UserService
from src.utils.invitation_utils import is_invitation_expired
from uuid import UUID
from src.api.schema.response_schemas import SuccessResponse, GenericResponse
from src.api.schema.response.auth_responses import (
    RegisterResponse,
    AuthTokenResponse,
    VerifyEmailResponse,
    RegisterWithInvitationResponse,
    UnlinkOAuthResponse,
    OAuthAccountResponse,
    OAuthAccountsResponse
)

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


MAX_NON_PAID_ACCOUNTS_PER_DEVICE = 5


async def check_disposable_email(
    user: RegisterUser,
) -> None:
    """
    Block registration from known temporary / disposable email providers.

    Runs as a FastAPI dependency before any DB writes, keeping resource usage
    minimal. Raises HTTP 422 so the frontend treats it as a validation error
    (consistent with Pydantic field errors).
    """
    if is_disposable_email(user.email):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Registrations from temporary or disposable email addresses are not "
                   "allowed. Please use a permanent email address."
        )


async def check_device_account_limit(
    request: Request,
    device_fingerprint: str = Depends(get_device_fingerprint),
    db: AsyncSession = Depends(get_async_db),
) -> None:
    """
    Permanently caps the number of accounts without an active paid subscription
    that a single device (IP + User-Agent fingerprint) may create.

    Unlike a rate limiter, this never resets on a timer: the count is computed
    live from current subscription state, so an account stops counting the
    moment it upgrades to a paid plan, freeing a slot for a new registration.

    Internal public IPs on the admin-managed allowlist (see
    AccountCreationAllowlistService and /api/v1/admin/account-creation-allowlist)
    are exempt from this cap so shared office / CI egress addresses can create
    multiple accounts. The IP is taken from request.client.host, which uvicorn's
    ProxyHeadersMiddleware only derives from X-Forwarded-For for trusted proxies
    (TRUSTED_PROXY_IPS); it is never taken from a raw client header.
    """
    client_ip = request.client.host if request.client else None
    if await AccountCreationAllowlistService(db).is_ip_allowlisted(client_ip):
        logger.info(f"Account-creation device cap bypassed for allowlisted IP {client_ip}")
        return

    count = await SubscriptionService(db).count_non_paid_accounts_for_device(device_fingerprint)
    if count >= MAX_NON_PAID_ACCOUNTS_PER_DEVICE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This device has reached the maximum number of free accounts allowed. "
                   "Upgrade an existing account to a paid plan to create another."
        )


@router.post("/register", response_model=SuccessResponse[RegisterResponse])
@db_transaction_handler("user registration", auto_commit=False)
async def create_user(
    user: RegisterUser,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    device_fingerprint: str = Depends(get_device_fingerprint),
    _rate_limit: None = Depends(registration_rate_limit()),
    _email_check: None = Depends(check_disposable_email),
    _account_limit: None = Depends(check_device_account_limit)
):
    """
    Endpoint to create a new user.
    """
    from src.utils.password_utils import validate_password_strength

    # 1. Validate password before rate limiting so weak password mistakes do not consume limits
    validate_password_strength(user.password)

    # Use auth service
    auth_service = AuthService(db)
    new_user, verification_token = await auth_service.register_user(
        email=user.email,
        password=user.password,
        full_name=user.full_name,
        device_fingerprint=device_fingerprint
    )

    # Create notification preferences using standardized service
    pref_service = NotificationPreferencesService(db)
    await pref_service.get_or_create(new_user.id)

    from src.utils.audit_helper import create_audit_log_async
    await create_audit_log_async(
        db=db,
        user_id=new_user.id,
        action="user.create",
        resource_type="user",
        resource_id=str(new_user.id),
        new_values={"email": new_user.email},
        request=request,
    )

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

    return success(
        data={
            "user": UserResponse.model_validate(new_user).model_dump()
        },
        request=request,
        message="User registered successfully. Please check your email for verification link."
    )




@router.post("/login", response_model=SuccessResponse[AuthTokenResponse])
@db_transaction_handler("user login", auto_commit=False)
async def login_user(
    user: LoginUser,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(login_rate_limit())
):
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
            confirm_reactivation=user.confirm_reactivation,
        )

        # PERSIST: We must commit here to save login sessions/logins counts
        await db.commit()
        
        # Build response using standardized schema
        return success(
            data={
                "access_token": tokens["access_token"],
                "refresh_token": tokens["refresh_token"],
                "token_type": tokens.get("token_type", "bearer"),
                "expires_in": tokens.get("expires_in", 3600),
                "user": {
                    **UserResponse.model_validate(db_user).model_dump(),
                    "roles": tokens.get("roles", []),
                    "permissions": tokens.get("permissions", [])
                }
            },
            request=request,
            message="Login successful"
        )

    except RextAuthenticationException as auth_error:
        # CRITICAL: Commit transaction to persist failed login attempts for account locking
        await db.commit()
        raise auth_error


@router.post("/refresh", response_model=SuccessResponse[AuthTokenResponse])
@db_transaction_handler("token refresh", auto_commit=False)
async def refresh_access_token(
    request: Request,
    token_data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Refresh access token using refresh token.
    """
    from src.api.security.token_utils import blacklist_token_in_cache

    auth_service = AuthService(db)
    tokens, old_jti, old_exp = await auth_service.refresh_token(token_data.refresh_token)

    # This commit is required on both the initial rotation and replay paths:
    # it persists the session update and promptly releases transaction-scoped
    # advisory locks. Redis remains an optional post-commit accelerator.
    await db.commit()

    await blacklist_token_in_cache(old_jti, old_exp)

    return success(
        data=tokens,
        request=request,
        message="Token refreshed successfully"
    )


@router.post("/logout", response_model=SuccessResponse[GenericResponse])
@db_transaction_handler("user logout", auto_commit=False)
async def logout_user(
    request: Request,
    body: Optional[LogoutRequest] = Body(None),
    current_user: dict = Depends(get_current_user),
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Logout user by blacklisting their access token (and optionally their refresh token).
    Pass refresh_token in the request body to also invalidate the refresh token.
    """
    from src.api.security.token_utils import blacklist_token_in_cache

    parts = authorization.split(maxsplit=1)
    if len(parts) != 2:
        raise RextAuthenticationException(message="Invalid Authorization header format")
    scheme, token = parts
    payload = decode_and_verify_token(token, expected_type="access")
    jti = payload.get("jti")
    exp = payload.get("exp")
    user_id = current_user.get("identity")
    session_id = payload.get("session_id")
    strict_user_session = payload.get("session_kind") == "user"

    # Decode refresh token if provided
    refresh_jti = None
    refresh_exp = None
    if body and body.refresh_token:
        try:
            refresh_payload = verify_refresh_token(body.refresh_token)
            refresh_matches_user = (
                str(refresh_payload.get("id")) == str(user_id)
            )
            refresh_matches_session = (
                not strict_user_session
                or (
                    refresh_payload.get("session_kind") == "user"
                    and str(refresh_payload.get("session_id"))
                    == str(session_id)
                )
            )
            if refresh_matches_user and refresh_matches_session:
                refresh_jti = refresh_payload.get("jti")
                refresh_exp = refresh_payload.get("exp")
        except Exception:
            # Invalid refresh token — still proceed with access token logout
            pass

    auth_service = AuthService(db)
    logout_result = await auth_service.logout_user(
        user_id,
        jti,
        exp,
        refresh_jti,
        refresh_exp,
        session_id=session_id,
        strict_user_session=strict_user_session,
    )

    from src.utils.audit_helper import create_audit_log_async
    await create_audit_log_async(
        db=db,
        user_id=UUID(user_id),
        action="auth.logout",
        resource_type="user",
        resource_id=str(user_id),
        request=request,
        status="success",
    )

    await db.commit()
    await blacklist_token_in_cache(
        logout_result.revoked_access_jti,
        logout_result.revoked_access_exp,
    )
    if (
        logout_result.revoked_refresh_jti
        and logout_result.revoked_refresh_exp
    ):
        await blacklist_token_in_cache(
            logout_result.revoked_refresh_jti,
            logout_result.revoked_refresh_exp,
        )

    return success(
        data={"message": "Logged out successfully"},
        request=request,
        message="Logout successful"
    )


@router.get("/verify-email", response_model=SuccessResponse[VerifyEmailResponse])
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

    return success(
        data={
            "id": str(user.id),
            "message": "Email verified successfully" if user.email_verified else "Email already verified"
        },
        request=request,
        message="Email verification result"
    )


@router.post("/resend-verification", response_model=SuccessResponse[GenericResponse])
@db_transaction_handler("resend verification", auto_commit=True)
async def resend_verification(
    request: Request,
    verification_data: ResendVerificationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(registration_rate_limit())
):
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
    return success(
        data={
            "message": "Verification email has been resent"
        },
        request=request,
        message="Verification email resent"
    )


@router.post("/oauth/login", response_model=SuccessResponse[AuthTokenResponse])
@db_transaction_handler("oauth login", auto_commit=True)
async def oauth_login(
    oauth_data: OAuthLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(oauth_rate_limit())
):
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

    return success(
        data={
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": tokens.get("token_type", "bearer"),
            "expires_in": tokens.get("expires_in", 3600),
            "user": UserResponse.model_validate(new_user).model_dump(),
            "roles": tokens.get("roles", []),
            "permissions": tokens.get("permissions", [])
        },
        request=request,
        message="OAuth login successful"
    )


@router.post("/register-with-invitation", response_model=SuccessResponse[RegisterWithInvitationResponse])
@db_transaction_handler("register with invitation", auto_commit=False)
async def register_with_invitation(
    user_data: RegisterWithInvitation,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(registration_rate_limit())
):
    """
    Create or use account via workspace invitation.
    """
    from src.utils.password_utils import validate_password_strength
    
    # 1. Validate password before rate limiting so weak password mistakes do not consume limits
    validate_password_strength(user_data.password)

    invitation_service = InvitationService(db)
    invitation = await invitation_service.get_invitation_by_token(user_data.invitation_token)

    if invitation.status != "pending" or is_invitation_expired(invitation):
        raise BusinessRuleViolationException("Invitation is invalid or expired")

    if user_data.email.lower() != invitation.email.lower():
        raise BusinessRuleViolationException("Email must match invitation")

    # Block disposable/temporary email providers even on invitation paths
    if is_disposable_email(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Registrations from temporary or disposable email addresses are not "
                   "allowed. Please use a permanent email address."
        )

    user_service = UserService(db)
    existing_user = await user_service.get_user_by_email(user_data.email)

    from src.utils.audit_helper import create_audit_log_async

    if existing_user:
        raise DuplicateResourceException(
            message="User already registered",
            resource_type="user",
            conflicting_field="email"
        )

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

    await create_audit_log_async(
        db=db,
        user_id=existing_user.id,
        action="user.create",
        resource_type="user",
        resource_id=str(existing_user.id),
        new_values={"email": existing_user.email},
        request=request,
    )

    background_tasks.add_task(
        send_welcome_email_task,
        email=existing_user.email,
        first_name=existing_user.full_name or existing_user.display_name,
        user_id=str(existing_user.id),
        frontend_url=settings.FRONTEND_URL
    )

    # Accept invitation
    await invitation_service.accept_invitation(
        invitation_id=invitation.id,
        user_id=existing_user.id
    )

    await create_audit_log_async(
        db=db,
        user_id=existing_user.id,
        action="invitation.accept",
        resource_type="invitation",
        resource_id=str(invitation.id),
        workspace_id=invitation.workspace_id,
        request=request,
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

    return success(
        data={
            "user": UserResponse.model_validate(existing_user).model_dump(),
            "invitation_accepted": True
        },
        request=request,
        message="Registration with invitation successful"
    )


async def send_recovery_email_task(
    email: str,
    first_name: str,
    recovery_token: str,
    user_id: str,
    frontend_url: str,
    retention_days: int = 14
):
    """
    Background task to send account recovery email.
    """
    from src.api.database.async_database import get_async_db_context
    from src.services.email_helpers import send_auth_email

    try:
        async with get_async_db_context() as async_db:
            await send_auth_email(
                db=async_db,
                email_type="account_recovery",
                recipient_email=email,
                user_name=first_name,
                user_id=UUID(user_id),
                token=recovery_token,
                frontend_url=frontend_url,
                retention_days=retention_days
            )
            logger.info(f"Account recovery email sent successfully to {email}")
    except Exception as e:
        logger.error(f"Failed to send recovery email to {email}: {str(e)}", exc_info=True)


@router.post("/account-recovery/request", response_model=SuccessResponse[GenericResponse])
@db_transaction_handler("account recovery request", auto_commit=False)
async def request_account_recovery(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(login_rate_limit())
):
    """
    Request account recovery for a soft-deleted account.
    Sends a recovery email if the account is within the retention period.
    Always returns success to prevent email enumeration attacks.
    """
    user_service = UserService(db)
    try:
        user, recovery_token = await user_service.request_account_recovery(email)
        frontend_url = settings.FRONTEND_URL
        background_tasks.add_task(
            send_recovery_email_task,
            email=user.email,
            first_name=user.full_name or user.display_name or "User",
            recovery_token=recovery_token,
            user_id=str(user.id),
            frontend_url=frontend_url,
            retention_days=settings.USER_DELETION_RETENTION_DAYS
        )
        logger.info(f"Account recovery email queued for: {email}")
    except Exception:
        # Response stays identical either way to prevent email enumeration, but
        # the cause must reach the logs — a silent except here hid a broken
        # template lookup that stopped every recovery email from being sent.
        logger.info(
            f"Account recovery request received for email (result suppressed): {email}",
            exc_info=True
        )

    return success(
        data={"message": "If your account is eligible for recovery, you will receive an email with instructions."},
        request=request,
        message="Recovery request processed"
    )


@router.post("/account-recovery/verify", response_model=SuccessResponse[GenericResponse])
@db_transaction_handler("account recovery verify", auto_commit=True)
async def verify_account_recovery(
    request: Request,
    token: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Verify recovery token and restore the soft-deleted account.
    Token is single-use and cryptographically verified.
    """
    user_service = UserService(db)
    user = await user_service.verify_account_recovery(token)

    from src.utils.audit_helper import create_audit_log_async
    await create_audit_log_async(
        db=db,
        user_id=user.id,
        action="user.account_recovered",
        resource_type="user",
        resource_id=str(user.id),
        request=request,
        status="success",
    )

    return success(
        data={"message": "Your account has been successfully restored. You may now log in."},
        request=request,
        message="Account restored successfully"
    )


@router.post("/oauth/link", response_model=SuccessResponse[OAuthAccountResponse])
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("link oauth account", auto_commit=True)
async def link_oauth(
    oauth_data: OAuthLinkRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
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

    return success(
        data=oauth_account.to_dict(),
        request=request,
        message="OAuth account linked successfully"
    )


@router.delete("/oauth/{provider}", response_model=SuccessResponse[UnlinkOAuthResponse])
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("unlink oauth account", auto_commit=True)
async def unlink_oauth(
    provider: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Unlink OAuth account from current user.
    """
    from src.services.oauth_service import OAuthService
    user_id = UUID(current_user.get("identity"))
    oauth_service = OAuthService(db)
    
    await oauth_service.unlink_oauth_account(user_id, provider)
    return success(
        data={"provider": provider, "status": "unlinked"},
        request=request,
        message=f"Successfully unlinked {provider} account"
    )

@router.get("/oauth/accounts", response_model=SuccessResponse[OAuthAccountsResponse])
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("get oauth accounts", auto_commit=False)
async def get_oauth_accounts(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get all OAuth accounts linked to the current user.
    """
    from src.services.oauth_service import OAuthService
    user_id = UUID(current_user.get("identity"))
    oauth_service = OAuthService(db)
    
    accounts = await oauth_service.get_user_oauth_accounts(user_id)
    return success(
        data={
            "accounts": [a.to_dict() for a in accounts],
            "total_count": len(accounts)
        },
        request=request,
        message="OAuth accounts retrieved successfully"
    )
