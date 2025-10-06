from fastapi import APIRouter, Depends, Request, BackgroundTasks, Header
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.schema.user_schema import LoginUser, RegisterUser
from src.api.security.token_utils import (
    hash_password,
    create_access_token,
    verify_password,
    create_refresh_token,
    verify_token,
    create_verification_token,
    verify_refresh_token,
    is_token_blacklisted
)
from sqlalchemy.orm import Session
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.user_sessions import UserSession
from src.api.tasks.send_mail import send_email
from src.api.database.database import get_db
from src.utils.response_utils import success, error, created
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextAuthenticationException
)
from datetime import datetime, timedelta
from user_agents import parse as parse_user_agent
import os
from src.api.middleware.rate_limiter import (
    login_rate_limit,
    registration_rate_limit
)

router = APIRouter()


@router.post("/register")
def create_user(
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
        # Check if user already exists with this email
        logger.info(f"Checking for existing user with email: {user.email}")
        existing_user = db.query(Users).filter(
            (Users.email == user.email) | (Users.username == user.username)
        ).first()

        if existing_user:
            if existing_user.email == user.email:
                raise DuplicateResourceException(
                    message="A user with this email already exists",
                    resource_type="user",
                    conflicting_field="email",
                    conflicting_value=user.email
                )
            else:
                raise DuplicateResourceException(
                    message="A user with this username already exists",
                    resource_type="user",
                    conflicting_field="username",
                    conflicting_value=user.username
                )

        # Hash password and create user
        logger.info("Creating new user")
        hashed_pwd = hash_password(user.password)
        new_user = Users(
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            email=user.email,
            password_hash=hashed_pwd
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        # Generate email verification token
        verification_token = create_verification_token({"user_id": str(new_user.id)})

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

        logger.info(f"Verification email sent to {new_user.email}")

        # Assign default role
        logger.info("Assigning default role to new user")
        default_role = db.query(Role).filter(Role.name == "user").first()
        if not default_role:
            logger.info("Creating default user role")
            default_role = Role(
                name="user",
                display_name="User",
                description="Default role for regular users",
                hierarchy_level=1,
                is_system_role=True
            )
            db.add(default_role)
            db.commit()
            db.refresh(default_role)

        logger.info(f"Assigning role {default_role.name} to user {new_user.username}")
        user_role = UserRole(
            user_id=new_user.id,
            role_id=default_role.id,
            workspace_id=None,
            is_primary=True,
            assigned_at=datetime.utcnow(),
            assigned_by_user_id=new_user.id
        )
        db.add(user_role)
        db.commit()
        db.refresh(user_role)

        logger.info(f"User {new_user.username} created successfully with ID {new_user.id}")

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
            "roles": [default_role.to_dict()],
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
def login_user(
    user: LoginUser,
    request: Request,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(login_rate_limit())
):
    """
    Endpoint to log in a user with table updates.
    """
    try:
        # Find user by email
        db_user = db.query(Users).filter(Users.email == user.email).first()

        if not db_user:
            raise WrextAuthenticationException(
                message="Invalid email or password",
                context={"login_attempt": user.email}
            )
        # Check if account is locked
        if db_user.locked_until and db_user.locked_until > datetime.utcnow():
            raise WrextAuthenticationException(
                message="Account is temporarily locked due to multiple failed login attempts. Please try again later.",
                context={"locked_until": db_user.locked_until.isoformat()}
            )

        # Verify password
        is_match = verify_password(password=user.password, hashed_password=db_user.password_hash)
        if not is_match:
            # increment failed login attempts
            db_user.failed_login_attempts = (db_user.failed_login_attempts or 0) + 1

            # lock account if too many failures
            if db_user.failed_login_attempts >= 3:
                db_user.locked_until = datetime.utcnow() + timedelta(hours=1)

            db.commit()
            raise WrextAuthenticationException(
                message="Invalid email or password",
                context={"login_attempt": user.email}
            )

        # login
        db_user.failed_login_attempts = 0
        db_user.last_login_at = datetime.utcnow()
        db_user.login_count = (db_user.login_count or 0) + 1
        db.commit()
        db.refresh(db_user)

        # get all the roles of the user
        role_names = [ur.role.name for ur in db_user.user_roles if ur.is_primary]

        # Get user's permissions via roles
        permission_names = (
            db.query(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .filter(UserRole.user_id == db_user.id)
            .filter(UserRole.workspace_id == None)  # Global permissions only for login
            .distinct()
            .all()
        )
        permissions = [p.name for p in permission_names]

        # Prepare JWT payload
        token_data = {
            "id": str(db_user.id),
            "username": db_user.username,
            "email": db_user.email,
            "roles": role_names,
            "permissions": permissions
        }

        # Generate tokens
        access_token = create_access_token(data=token_data)
        refresh_token = create_refresh_token(data=token_data)

        # Parse user agent for device information
        user_agent_string = request.headers.get("user-agent", "Unknown")
        user_agent = parse_user_agent(user_agent_string)
        device_type = "mobile" if user_agent.is_mobile else ("tablet" if user_agent.is_tablet else "desktop")
        device_name = f"{user_agent.browser.family} on {user_agent.os.family}"

        # Get client IP address
        client_ip = request.client.host if request.client else "Unknown"

        # Decode access token to get JTI and expiration
        access_payload = verify_token(access_token)
        jti = access_payload.get("jti")
        exp_timestamp = access_payload.get("exp")
        expires_at = datetime.utcfromtimestamp(exp_timestamp) if exp_timestamp else datetime.utcnow() + timedelta(hours=24)

        # Create session record
        new_session = UserSession(
            user_id=db_user.id,
            jti=jti,
            device_name=device_name,
            device_type=device_type,
            user_agent=user_agent_string,
            ip_address=client_ip,
            is_active=True,
            created_at=datetime.utcnow(),
            last_activity_at=datetime.utcnow(),
            expires_at=expires_at
        )
        db.add(new_session)
        db.commit()

        logger.info(f"Created session {new_session.id} for user {db_user.id} from {client_ip}")

        # Return successful login response
        return success(
            data={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
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
def refresh_access_token(
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

    Args:
        request: FastAPI request object
        refresh_token: The refresh token to use
        db: Database session

    Returns:
        New access token and refresh token pair

    Raises:
        401: If token is expired, invalid, or blacklisted
        403: If user account is not active
        404: If user not found
    """
    try:
        # Verify refresh token
        payload = verify_refresh_token(refresh_token)

        # Check if token is blacklisted
        jti = payload.get("jti")
        if not jti:
            raise WrextAuthenticationException(
                message="Token missing JTI",
                context={"note": "Old token format not supported"}
            )

        if is_token_blacklisted(jti, db):
            raise WrextAuthenticationException(
                message="Refresh token has been revoked",
                context={"reason": "Token blacklisted"}
            )

        # Get user from database
        user_id = payload.get("id")
        db_user = db.query(Users).filter(Users.id == user_id).first()

        if not db_user:
            raise WrextAuthenticationException(
                message="User not found",
                context={"user_id": user_id}
            )

        # Check if user is active
        if db_user.status != "active":
            raise WrextAuthenticationException(
                message="User account is not active",
                context={"status": db_user.status}
            )

        # Get user's current roles
        role_names = [ur.role.name for ur in db_user.user_roles if ur.is_primary]

        # Get user's permissions via roles
        permission_names = (
            db.query(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .filter(UserRole.user_id == db_user.id)
            .filter(UserRole.workspace_id == None)  # Global permissions only
            .distinct()
            .all()
        )
        permissions = [p.name for p in permission_names]

        # Create new token pair
        token_data = {
            "id": str(db_user.id),
            "username": db_user.username,
            "email": db_user.email,
            "roles": role_names,
            "permissions": permissions
        }
        new_access_token = create_access_token(data=token_data)
        new_refresh_token = create_refresh_token(data=token_data)

        # Blacklist old refresh token (token rotation)
        blacklist_entry = TokenBlacklist(
            jti=jti,
            token_type="refresh",
            user_id=db_user.id,
            revoked_at=datetime.utcnow(),
            expires_at=datetime.utcfromtimestamp(payload.get("exp")),
            reason="refresh"
        )
        db.add(blacklist_entry)
        db.commit()

        logger.info(f"Access token refreshed for user {db_user.id}")

        return success(
            data={
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "token_type": "bearer"
            },
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
def logout_user(
    request: Request,
    current_user: dict = Depends(get_current_user),
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    """
    Logout user by blacklisting their access token.

    The client should also delete stored refresh tokens locally.
    This prevents the access token from being reused after logout.

    Args:
        request: FastAPI request object
        current_user: Current authenticated user (from get_current_user dependency)
        authorization: Authorization header with Bearer token
        db: Database session

    Returns:
        Success message

    Raises:
        401: If token is invalid, missing JTI, or already blacklisted
        500: If logout process fails
    """
    try:
        # Extract token from authorization header
        scheme, token = authorization.split()

        # Decode token to get JTI and expiration
        payload = verify_token(token)
        jti = payload.get("jti")
        exp = payload.get("exp")
        user_id = current_user.get("identity")

        if not jti:
            raise WrextAuthenticationException(
                message="Token missing JTI",
                context={"note": "Old token format not supported"}
            )

        # Check if already blacklisted
        if is_token_blacklisted(jti, db):
            logger.info(f"Token already blacklisted for user {user_id}")
            return success(
                data={"message": "Already logged out"},
                request=request,
                message="Logout successful"
            )

        # Blacklist the access token
        blacklist_entry = TokenBlacklist(
            jti=jti,
            token_type="access",
            user_id=user_id,
            revoked_at=datetime.utcnow(),
            expires_at=datetime.utcfromtimestamp(exp),
            reason="logout"
        )
        db.add(blacklist_entry)
        db.commit()

        # Deactivate the session
        session = db.query(UserSession).filter(
            UserSession.jti == jti,
            UserSession.is_active == True
        ).first()

        if session:
            session.is_active = False
            session.revoked_at = datetime.utcnow()
            db.commit()
            logger.info(f"Deactivated session {session.id} for user {user_id}")

        logger.info(f"User {user_id} logged out successfully")

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
def verify_email(token: str, request: Request, db: Session = Depends(get_db)):
    """
    Verify user's email using the provided token
    """
    try:
        logger.info("Verifying email with token")
        payload = verify_token(token)
        user_id = payload.get("user_id")  # Use consistent key with token creation
        if not user_id:
            return error(message="Invalid token payload", request=request)

        user = db.query(Users).filter(Users.id == user_id).first()
        if not user:
            return error(message="User not found", request=request)

        if user.email_verified:
            return success(data={"id": str(user.id)}, request=request, message="Email already verified")

        user.email_verified = True
        user.email_verified_at = datetime.utcnow()
        db.commit()
        db.refresh(user)

        return success(data={"id": str(user.id)}, request=request, message="Email verified successfully")

    except Exception as e:
        return error(
            message="Failed to verify email",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )
