from fastapi import APIRouter, Depends, Request, BackgroundTasks, Header
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.schema.user_schema import LoginUser, RegisterUser, RegisterWithInvitation, LoginWithInvitation
from src.api.security.token_utils import verify_token
from src.api.config import get_settings
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.email_service import EmailService
from src.api.database.async_database import get_async_db
from src.utils.response_utils import success, error, created
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    RextAuthenticationException,
    ResourceNotFoundException,
    BusinessRuleViolationException
)
from datetime import datetime
from src.services.notification_helper import schedule_if_allowed
from user_agents import parse as parse_user_agent
from src.api.models.user_models.notification_preferences import NotificationPreferences
import os
from src.api.middleware.rate_limiter import (
    login_rate_limit,
    registration_rate_limit
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
    try:
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
        
        # IMPORTANT: Commit all database changes (user + preferences) before adding background tasks
        await db.commit()
        await db.refresh(new_user)

        # Get frontend URL from environment
        frontend_url = settings.FRONTEND_URL

        # Send verification email in background using professional template
        background_tasks.add_task(
            send_verification_email_task,
            email=new_user.email,
            first_name=new_user.full_name or new_user.display_name,
            verification_token=verification_token,
            user_id=str(new_user.id),
            frontend_url=frontend_url
        )
        user_data = {
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


@router.post("/register-with-invitation")
async def register_with_invitation(
    user_data: RegisterWithInvitation,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(registration_rate_limit())
):
    """
    Create a new user account via workspace invitation OR accept invitation for existing user.

    This endpoint handles the complete invitation acceptance flow:
    1. Validates the invitation token
    2. Checks if user already exists:
       a. If user exists: Auto-accepts invitation and adds to workspace
       b. If new user: Creates user account, auto-accepts invitation
    3. Creates workspace membership
    4. Skips email verification (invitation email already validated)
    5. Returns user + workspace context

    This is the recommended flow for users accepting invitation links.

    Args:
        user_data: RegisterWithInvitation schema with user details + invitation token
        request: FastAPI request object
        background_tasks: For sending welcome emails
        db: Database session

    Returns:
        User data + workspace information + authentication tokens

    Raises:
        ResourceNotFoundException: If invitation not found
        BusinessRuleViolationException: If invitation expired or email mismatch
    """
    try:
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
            # Provide helpful error messages based on status
            if invitation.status == "accepted":
                raise BusinessRuleViolationException(
                    message="This invitation has already been accepted. If you need access to this workspace, please contact the workspace administrator for a new invitation.",
                    rule_name="invitation_already_accepted"
                )
            elif invitation.status == "expired":
                raise BusinessRuleViolationException(
                    message="This invitation has expired. Please request a new invitation from the workspace administrator.",
                    rule_name="invitation_expired"
                )
            elif invitation.status == "revoked":
                raise BusinessRuleViolationException(
                    message="This invitation has been revoked. Please contact the workspace administrator if you believe this is an error.",
                    rule_name="invitation_revoked"
                )
            else:
                raise BusinessRuleViolationException(
                    message=f"Invitation is {invitation.status} and cannot be used",
                    rule_name="invitation_must_be_pending"
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
        # This is a critical security check
        if user_data.email.lower() != invitation.email.lower():
            raise BusinessRuleViolationException(
                message=f"Email must match invitation email: {invitation.email}",
                rule_name="email_must_match_invitation"
            )

        # Step 3: Check if user already exists
        user_service = UserService(db)
        existing_user = await user_service.get_user_by_email(user_data.email)

        if existing_user:
            user_exists = True
            current_user = existing_user
            logger.info(
                f"Existing user found for invitation: {user_data.email}",
                extra={
                    "user_id": str(existing_user.id),
                    "invitation_id": str(invitation.id)
                }
            )
        else:
            user_exists = False
            current_user = None
            logger.info(
                f"New user will be created for invitation: {user_data.email}",
                extra={
                    "invitation_id": str(invitation.id)
                }
            )

        # Step 4: Create user account if doesn't exist, otherwise use existing
        if not user_exists:
            auth_service = AuthService(db)
            new_user, verification_token = await auth_service.register_user(
                email=user_data.email,
                password=user_data.password,
                full_name=user_data.full_name
            )

            # Skip email verification for invited users
            # Rationale: Email was already validated by invitation system
            new_user.email_verified = True
            new_user.email_verified_at = datetime.utcnow()
            await db.flush()

            current_user = new_user
            logger.info(
                f"New user created via invitation: {user_data.email}",
                extra={
                    "user_id": str(new_user.id),
                    "invitation_id": str(invitation.id)
                }
            )

        # Step 5: Auto-accept invitation
        acceptance_result = await invitation_service.accept_invitation(
            invitation_id=invitation.id,
            user_id=current_user.id
        )

        # Handle notification preferences for new users
        if not user_exists:
            logger.info("Adding notification preference for user")
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

        # Commit all changes (user creation if new, membership, preferences, invitation status)
        # before starting background tasks
        await db.commit()
        await db.refresh(current_user)

        # Step 6: Send welcome email for new users only
        if not user_exists:
            frontend_url = settings.FRONTEND_URL
            background_tasks.add_task(
                send_welcome_email_task,
                email=current_user.email,
                first_name=current_user.full_name or current_user.display_name,
                user_id=str(current_user.id),
                frontend_url=frontend_url
            )

        # Step 7: Get workspace details for response
        from src.services.workspace_service import WorkspaceService
        workspace_service = WorkspaceService(db)
        workspace = await workspace_service.get_workspace(invitation.workspace_id)

        # Step 7.5: Get the assigned role from invitation
        from src.api.models.user_models.roles import Role
        from sqlalchemy import select
        result = await db.execute(
            select(Role).where(Role.id == invitation.role_id)
        )
        assigned_role = result.scalar_one_or_none()

        # Step 8: Return comprehensive response with workspace context
        user_data_response = {
            "id": str(current_user.id),
            "email": current_user.email,
            "full_name": current_user.full_name,
            "display_name": current_user.display_name,
            "language": current_user.language,
            "timezone": current_user.timezone,
            "status": current_user.status,
            "email_verified": current_user.email_verified,
            "roles": [{"name": assigned_role.name, "display_name": assigned_role.display_name}] if assigned_role else [{"name": "user", "display_name": "User"}],
            "created_at": current_user.created_at.isoformat() if hasattr(current_user, 'created_at') else None,
        }

        workspace_data = {
            "id": str(workspace.id),
            "slug": workspace.slug,
            "name": workspace.name,
            "membership_id": acceptance_result["membership_id"]
        }

        action_message = "Account created and workspace joined" if not user_exists else "Workspace joined"

        logger.info(
            f"User {'registered' if not user_exists else 'accepted invitation'} via invitation: {current_user.email}",
            extra={
                "user_id": str(current_user.id),
                "workspace_id": str(workspace.id),
                "invitation_id": str(invitation.id)
            }
        )
        #  send the notification to user
        await schedule_if_allowed(
            db=db,
            user_id=str(invitation.invited_by_user_id),
            background_tasks=background_tasks,
            pref_flag="ws_invite_accepted",
            message=f"{current_user.email} has accepted an invitation to join a workspace.",
            payload = {
                "user_id": str(current_user.id),
                "workspace_id": str(workspace.id),
                "invitation_id": str(invitation.id)
            }
        )

        return created(
            data={
                "user": user_data_response,
                "workspace": workspace_data,
                "invitation_accepted": True,
                "message": f"Welcome! You've joined {workspace.name}"
            },
            request=request,
            message=f"{action_message} successfully"
        )

    except (ResourceNotFoundException, BusinessRuleViolationException):
        # Re-raise to be handled by middleware
        raise
    except Exception as e:
        logger.error(f"Registration with invitation failed: {str(e)}", exc_info=True)
        raise


@router.post("/login")
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
            device_info=device_info,
            background_tasks=background_tasks,
            db=db
        )

        # Commit transaction to persist auto-accepted invitations
        # (WorkspaceMembers and UserRole records created during login)
        logger.info(
            f"[LOGIN] Committing transaction for user {user.email}",
            extra={"user_id": str(db_user.id), "user_email": user.email}
        )
        await db.commit()
        logger.info(
            f"[LOGIN] Transaction committed successfully",
            extra={"user_id": str(db_user.id), "user_email": user.email}
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
                    "email": db_user.email,
                    "full_name": db_user.full_name,
                    "display_name": db_user.display_name,
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

    except RextAuthenticationException as auth_error:
        # CRITICAL: Commit transaction to persist failed login attempts
        # Without this, account locking after multiple failed attempts won't work
        await db.commit()
        # Re-raise to be handled by middleware
        raise auth_error
    except Exception as e:
        # Rollback transaction on error
        await db.rollback()
        logger.error(f"Login failed: {str(e)}", exc_info=True)
        return error(
            message="Login failed due to server error",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


@router.post("/refresh")
async def refresh_access_token(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
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

    except RextAuthenticationException:
        # Re-raise to be handled by middleware
        raise
    except Exception as e:
        logger.error(f"Token refresh failed: {str(e)}")
        return error(
            message="Failed to refresh token",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


@router.post("/logout")
async def logout_user(
    request: Request,
    current_user: dict = Depends(get_current_user),
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_async_db)
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
        payload = verify_token(token, expected_type="access")
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

    except RextAuthenticationException:
        # Re-raise to be handled by middleware
        raise
    except Exception as e:
        logger.error(f"Logout failed: {str(e)}")
        return error(
            message="Logout failed",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


@router.get("/verify-email")
async def verify_email(
    token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db)
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
                first_name=user.full_name or user.display_name,
                user_id=str(user.id),
                frontend_url=frontend_url
            )

        message = "Email verified successfully" if user.email_verified else "Email already verified"

        return success(
            data={"id": str(user.id)},
            request=request,
            message=message
        )

    except (RextAuthenticationException, ResourceNotFoundException):
        raise
    except Exception as e:
        return error(
            message="Failed to verify email",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


@router.post("/resend-verification")
async def resend_verification(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
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
async def oauth_login(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
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
    from datetime import datetime

    try:
        body = await request.json()

        # Parse token_expires_at from ISO string to datetime (if provided)
        # Database uses TIMESTAMP WITHOUT TIME ZONE, so we need timezone-naive datetimes
        token_expires_at = None
        if body.get("token_expires_at"):
            try:
                expires_str = body.get("token_expires_at")
                # Handle ISO format with 'Z' suffix (e.g., '2025-01-01T00:00:00Z')
                if expires_str.endswith('Z'):
                    expires_str = expires_str[:-1]  # Remove 'Z' to get naive datetime
                parsed_dt = datetime.fromisoformat(expires_str)
                # If parsed datetime has timezone info, convert to naive UTC
                if parsed_dt.tzinfo is not None:
                    parsed_dt = parsed_dt.replace(tzinfo=None)
                token_expires_at = parsed_dt
            except (ValueError, AttributeError) as e:
                logger.warning(f"Failed to parse token_expires_at: {body.get('token_expires_at')}, error: {e}")

        oauth_service = OAuthService(db)
        new_user, tokens = await oauth_service.oauth_login_or_register(
            provider=body.get("provider"),
            provider_account_id=body.get("provider_account_id"),
            provider_email=body.get("provider_email"),
            provider_name=body.get("provider_name", ""),
            provider_avatar_url=body.get("provider_avatar_url"),
            provider_username=body.get("provider_username"),
            access_token=body.get("access_token"),
            refresh_token=body.get("refresh_token"),
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


@router.post("/oauth/link")
async def link_oauth(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
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
    from datetime import datetime

    try:
        body = await request.json()
        user_id = UUID(current_user.get("identity"))

        # Parse token_expires_at from ISO string to datetime (if provided)
        # Database uses TIMESTAMP WITHOUT TIME ZONE, so we need timezone-naive datetimes
        token_expires_at = None
        if body.get("token_expires_at"):
            try:
                expires_str = body.get("token_expires_at")
                # Handle ISO format with 'Z' suffix (e.g., '2025-01-01T00:00:00Z')
                if expires_str.endswith('Z'):
                    expires_str = expires_str[:-1]  # Remove 'Z' to get naive datetime
                parsed_dt = datetime.fromisoformat(expires_str)
                # If parsed datetime has timezone info, convert to naive UTC
                if parsed_dt.tzinfo is not None:
                    parsed_dt = parsed_dt.replace(tzinfo=None)
                token_expires_at = parsed_dt
            except (ValueError, AttributeError) as e:
                logger.warning(f"Failed to parse token_expires_at: {body.get('token_expires_at')}, error: {e}")

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
            token_expires_at=token_expires_at
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
            request=request
        )


@router.delete("/oauth/{provider}")
async def unlink_oauth(
    provider: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
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
            request=request
        )
