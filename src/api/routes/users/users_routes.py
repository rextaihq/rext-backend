from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks, Header, UploadFile, File
from src.utils.logger import logger
from src.api.security.auth import get_current_user
from src.api.schema.user_schema import (LoginUser, RegisterUser,
                                        UpdateUser, ResetPassword,
                                        ForgotPasswordRequest,
                                        ChangePasswordRequest,
                                        UpdateProfileRequest,
                                        ProfileResponse,
                                        UserStatusRequest,
                                        UserStatusResponse,
                                        DeactivateAccountRequest,
                                        DeactivateAccountResponse,
                                        DataExportRequest,
                                        DataExportResponse)
from src.api.schema.user_role_schema import AssignUserRoleRequest, UserRoleResponse
from src.api.security.token_utils import (hash_password, create_access_token,
                              verify_password, create_refresh_token,
                              create_reset_token, verify_token,
                              create_verification_token, verify_refresh_token,
                              is_token_blacklisted
                              )
from sqlalchemy.orm import Session
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.tasks.send_mail import send_email
from src.api.database.database import get_db
from src.utils.response_utils import success, error, created, unauthorized
from src.utils.token_cleanup import cleanup_expired_tokens
from src.utils.audit_helper import create_audit_log
from src.utils.account_cleanup import delete_deactivated_accounts, get_pending_deletions
from src.api.middleware.permissions import is_admin
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextAuthenticationException,
    WrextValidationException
)
from dotenv import load_dotenv
from datetime import datetime, timedelta
from pathlib import Path
import uuid
import os
import time

load_dotenv()

# Avatar upload directory
AVATAR_UPLOAD_DIR = Path("uploads/avatars")
AVATAR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SECRET_KEY= os.getenv("SECRET_KEY")
ALGORITHM= os.getenv("ALGORITHM")
router = APIRouter(
    prefix="/user",
    tags=["user"],
    # dependencies=
)

@router.get("/status")
def get_user_status(request: Request):
    """
    Endpoint to check the user service status.
    """
    return success(
        data={"status": "running", "service": "user_service"},
        request=request,
        message="User service is operational"
    )

@router.get("/users")
def get_users(
    request: Request,
    workspace_id: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Endpoint to retrieve users, optionally filtered by workspace.
    Requires authentication.
    """
    try:
        logger.info(f"Fetching users for workspace: {workspace_id or 'all'}")

        # Base query
        query = db.query(Users)

        if workspace_id:
            # Filter by workspace membership
            query = query.join(WorkspaceMembers).filter(
                WorkspaceMembers.workspace_id == workspace_id,
                WorkspaceMembers.status == "active"
            )
            logger.info(f"Filtering users by workspace_id: {workspace_id}")

        users = query.all()

        # Convert users to dict format (excluding passwords)
        user_data = [user.to_dict() for user in users]

        return success(
            data={
                "users": user_data,
                "total_count": len(user_data),
                "workspace_id": workspace_id
            },
            request=request,
            message=f"Retrieved {len(user_data)} users successfully"
        )
    except Exception as e:
        logger.error(f"Failed to retrieve users: {str(e)}")
        return error(
            message="Failed to retrieve users",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.post("/register")
def create_user(
    user: RegisterUser,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
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
        # Prepare JWT payload
        token_data = {
            "id": str(db_user.id),
            "username": db_user.username,
            "email": db_user.email,
            "roles": role_names
        }

        # Generate tokens
        access_token = create_access_token(data=token_data)
        refresh_token = create_refresh_token(data=token_data)

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


# Refresh Access Token
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

        # Create new token pair
        token_data = {
            "id": str(db_user.id),
            "username": db_user.username,
            "email": db_user.email,
            "roles": role_names
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


# Logout User
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


# Admin: Cleanup Deactivated Accounts
@router.post("/admin/cleanup-deactivated-accounts")
def cleanup_deactivated_accounts_endpoint(
    request: Request,
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to manually trigger cleanup of deactivated accounts.

    Permanently deletes accounts that have been deactivated for 14+ days.
    Only accessible to users with admin or super_admin role.

    Returns:
        Number of accounts deleted

    Note:
        This should ideally be run as a scheduled job (cron/celery)
        but can be triggered manually via this endpoint.
    """
    try:
        deleted_count = delete_deactivated_accounts(db)

        logger.info(
            f"Admin {current_user.get('identity')} triggered deactivated account cleanup - "
            f"deleted {deleted_count} account(s)"
        )

        return success(
            data={
                "deleted_count": deleted_count,
                "message": f"Successfully deleted {deleted_count} deactivated account(s)"
            },
            request=request,
            message=f"Cleaned up {deleted_count} deactivated account(s)"
        )

    except Exception as e:
        logger.error(f"Deactivated account cleanup failed: {str(e)}")
        return error(
            message="Account cleanup failed",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.get("/admin/pending-deletions")
def get_pending_deletions_endpoint(
    request: Request,
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to view accounts scheduled for deletion.

    Returns list of deactivated accounts with their scheduled deletion dates.
    Only accessible to users with admin or super_admin role.
    """
    try:
        pending = get_pending_deletions(db)

        logger.info(f"Admin {current_user.get('identity')} viewed pending account deletions")

        return success(
            data={
                "pending_deletions": pending,
                "count": len(pending)
            },
            request=request,
            message=f"Retrieved {len(pending)} account(s) pending deletion"
        )

    except Exception as e:
        logger.error(f"Failed to retrieve pending deletions: {str(e)}")
        return error(
            message="Failed to retrieve pending deletions",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


# Admin: Cleanup Expired Tokens
@router.post("/admin/cleanup-tokens")
def cleanup_tokens_endpoint(
    request: Request,
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to manually trigger token cleanup.

    Removes expired tokens from blacklist to prevent table growth.
    Only accessible to users with admin or super_admin role.

    Args:
        request: FastAPI request object
        current_user: Current authenticated user (must be admin)
        _: Admin check dependency (enforces admin role)
        db: Database session

    Returns:
        Number of tokens deleted

    Raises:
        403: If user is not an admin
        500: If cleanup process fails
    """
    try:
        deleted_count = cleanup_expired_tokens(db)

        logger.info(f"Admin {current_user.get('identity')} triggered token cleanup - deleted {deleted_count} tokens")

        return success(
            data={
                "deleted_count": deleted_count,
                "message": f"Successfully cleaned up {deleted_count} expired tokens"
            },
            request=request,
            message=f"Cleaned up {deleted_count} expired tokens"
        )
    except Exception as e:
        logger.error(f"Manual token cleanup failed: {str(e)}")
        return error(
            message="Token cleanup failed",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


# Delete user
@router.delete("/delete/{user_id}")
def delete_user(user_id: str, request: Request, db: Session = Depends(get_db)):
    """
    Soft delete a user by setting deleted_at timestamp
    """
    try:
        db_user = db.query(Users).filter(Users.id == user_id).first()
        if not db_user:
            return error(
                message="User not found",
                code=ErrorCode.NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )
        
        # Prevent deleting an already deleted user
        if db_user.deleted_at:
            return error(
                message="User already deleted",
                code=ErrorCode.DEPENDENCY_ERROR,
                status_code=400,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )
        
        # Soft delete
        db_user.deleted_at = datetime.utcnow()
        db.commit()

        return success(
            data={"id": str(db_user.id)},
            request=request,
            message="User deleted successfully"
        )

    except Exception as e:
        db.rollback()
        return error(
            message="Failed to delete user",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )

# update user details
@router.put("/update/{user_id}")
def update_user(user_id: str, user: UpdateUser, request: Request, db: Session = Depends(get_db)):
    """
    Update user details
    """
    try:
        db_user = db.query(Users).filter(Users.id == user_id).first()
        if not db_user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )
         # Check for duplicate email
        if user.email and db.query(Users).filter(Users.email == user.email, Users.id != user_id).first():
            return error(
                message="Email already exists",
                code=ErrorCode.DUPLICATE_RESOURCE,
                status_code=400,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )
        # Check for duplicate username
        if user.username and db.query(Users).filter(Users.username == user.username, Users.id != user_id).first():
            return error(
                message="Username already exists",
                code=ErrorCode.DUPLICATE_RESOURCE,
                status_code=400,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )
        
        # Update fields if provided
        if user.email is not None:
            db_user.email = user.email
        if user.username is not None:
            db_user.username = user.username
        if user.first_name is not None:
            db_user.first_name = user.first_name
        if user.last_name is not None:
            db_user.last_name = user.last_name
        if user.display_name is not None:
            db_user.display_name = user.display_name
        if user.language is not None:
            db_user.language = user.language
        if user.timezone is not None:
            db_user.timezone = user.timezone

        db.commit()
        db.refresh(db_user)

        # Return updated user data (excluding password)
        user_data = {
            "id": str(db_user.id),
            "username": db_user.username,
            "email": db_user.email,
            "first_name": db_user.first_name,
            "last_name": db_user.last_name,
            "display_name": db_user.display_name,
            "language": db_user.language,
            "timezone": db_user.timezone,
            "status": db_user.status,
            "updated_at": db_user.updated_at.isoformat() if hasattr(db_user, 'updated_at') else None
        }

        return success(
            data={"user": user_data},
            request=request,
            message="User updated successfully"
        )

    except Exception as e:
        db.rollback()
        return error(
            message="Failed to update user",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )
    
# forget password
@router.post("/forgot-password")
def forgot_password(
    request: Request,
    forgot_request: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
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

# reset user password
@router.post("/reset-password")
def reset_password(payload:ResetPassword, request: Request, db: Session = Depends(get_db)):
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

# Change password (authenticated)
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

# Get current user profile
@router.get("/profile", response_model=dict)
def get_profile(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current authenticated user's profile

    Returns complete profile information for the logged-in user
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"Fetching profile for user: {user_id}")

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

        # Build profile response
        profile_data = {
            "id": str(db_user.id),
            "email": db_user.email,
            "username": db_user.username,
            "first_name": db_user.first_name,
            "last_name": db_user.last_name,
            "display_name": db_user.display_name,
            "language": db_user.language or "en",
            "timezone": db_user.timezone or "UTC",
            "status": db_user.status,
            "email_verified": db_user.email_verified,
            "created_at": db_user.created_at.isoformat() if db_user.created_at else None,
            "updated_at": db_user.updated_at.isoformat() if db_user.updated_at else None
        }

        logger.info(f"Profile fetched successfully for user: {user_id}")
        return success(
            data={"profile": profile_data},
            request=request,
            message="Profile retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Error fetching profile for user {current_user.get('identity')}: {str(e)}")
        return error(
            message="Failed to fetch profile",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )

# Update current user profile
@router.patch("/profile")
def update_profile(
    request: Request,
    profile_data: UpdateProfileRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update current authenticated user's profile

    - **first_name**: First name
    - **last_name**: Last name
    - **display_name**: Display name
    - **language**: Language preference
    - **timezone**: Timezone preference

    Note: Email, username, and password cannot be changed via this endpoint
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"Profile update requested for user: {user_id}")

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

        # Track what was updated
        updated_fields = []

        # Update fields if provided
        if profile_data.first_name is not None:
            db_user.first_name = profile_data.first_name
            updated_fields.append("first_name")

        if profile_data.last_name is not None:
            db_user.last_name = profile_data.last_name
            updated_fields.append("last_name")

        if profile_data.display_name is not None:
            db_user.display_name = profile_data.display_name
            updated_fields.append("display_name")

        if profile_data.language is not None:
            db_user.language = profile_data.language
            updated_fields.append("language")

        if profile_data.timezone is not None:
            db_user.timezone = profile_data.timezone
            updated_fields.append("timezone")

        # Update timestamp
        db_user.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(db_user)

        # Build response
        profile_response = {
            "id": str(db_user.id),
            "email": db_user.email,
            "username": db_user.username,
            "first_name": db_user.first_name,
            "last_name": db_user.last_name,
            "display_name": db_user.display_name,
            "language": db_user.language,
            "timezone": db_user.timezone,
            "status": db_user.status,
            "email_verified": db_user.email_verified,
            "updated_at": db_user.updated_at.isoformat()
        }

        logger.info(f"Profile updated successfully for user {user_id}. Updated fields: {', '.join(updated_fields)}")
        return success(
            data={
                "profile": profile_response,
                "updated_fields": updated_fields
            },
            request=request,
            message="Profile updated successfully"
        )

    except Exception as e:
        logger.error(f"Error updating profile for user {current_user.get('identity')}: {str(e)}")
        db.rollback()
        return error(
            message="Failed to update profile",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )

# Email verification
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


# ============================================================================
# USER-ROLE ASSIGNMENT ENDPOINTS
# ============================================================================


@router.post("/{user_id}/roles")
def assign_role_to_user(
    request: Request,
    user_id: str,
    assignment_data: AssignUserRoleRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Assign a role to a user.

    Requires: user.assign_role permission OR admin role

    Parameters:
    - user_id: UUID of the user

    Request Body:
    - role_id: UUID of the role to assign
    - workspace_id: Optional workspace UUID for workspace-scoped role
    - is_primary: Whether this is the primary role

    Returns:
    - Assignment details
    """
    try:
        assigner_id = current_user.get("identity")

        # Check if admin
        is_user_admin = db.query(UserRole).join(Role).filter(
            UserRole.user_id == assigner_id,
            Role.name.in_(["admin", "super_admin"])
        ).first() is not None

        if not is_user_admin:
            # Check for user.assign_role permission
            has_permission = (
                db.query(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .filter(
                    UserRole.user_id == assigner_id,
                    Permission.name == "user.assign_role"
                )
                .first()
            )

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: user.assign_role or admin role"
                )

        # Verify user exists
        user = db.query(Users).filter(Users.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Verify role exists
        role = db.query(Role).filter(Role.id == assignment_data.role_id).first()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found"
            )

        # Check assigner's hierarchy level (must be >= role's hierarchy to assign it)
        assigner_max_hierarchy = (
            db.query(Role.hierarchy_level)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(UserRole.user_id == assigner_id)
            .order_by(Role.hierarchy_level.desc())
            .first()
        )

        if assigner_max_hierarchy and assigner_max_hierarchy[0] < role.hierarchy_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cannot assign role with hierarchy level {role.hierarchy_level}. Your max level: {assigner_max_hierarchy[0]}"
            )

        # If workspace-scoped, verify workspace and membership
        workspace = None
        if assignment_data.workspace_id:
            workspace = db.query(WorkspaceModel).filter(
                WorkspaceModel.id == assignment_data.workspace_id
            ).first()

            if not workspace:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Workspace not found"
                )

            # Check if user is member of workspace
            is_member = db.query(WorkspaceMembers).filter(
                WorkspaceMembers.workspace_id == assignment_data.workspace_id,
                WorkspaceMembers.user_id == user_id
            ).first()

            if not is_member:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User is not a member of this workspace"
                )

        # Check if already assigned (idempotent)
        existing = db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.role_id == assignment_data.role_id,
            UserRole.workspace_id == assignment_data.workspace_id
        ).first()

        if existing:
            return success(
                data={
                    "assignment": existing.to_dict(),
                    "role_name": role.name,
                    "already_assigned": True
                },
                request=request,
                message=f"Role '{role.display_name}' already assigned to user"
            )

        # Create assignment
        user_role = UserRole(
            user_id=user_id,
            role_id=assignment_data.role_id,
            workspace_id=assignment_data.workspace_id,
            assigned_by_user_id=assigner_id,
            is_primary=assignment_data.is_primary,
            assigned_at=datetime.utcnow()
        )

        db.add(user_role)
        db.commit()
        db.refresh(user_role)

        logger.info(
            f"Role '{role.name}' assigned to user {user_id} "
            f"in workspace {assignment_data.workspace_id or 'global'} by {assigner_id}"
        )

        return success(
            data={
                "assignment": user_role.to_dict(),
                "role_name": role.name,
                "role_display_name": role.display_name,
                "workspace_name": workspace.name if workspace else None
            },
            request=request,
            message=f"Role '{role.display_name}' assigned successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error assigning role to user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign role"
        )


@router.delete("/{user_id}/roles/{role_id}")
def revoke_role_from_user(
    request: Request,
    user_id: str,
    role_id: str,
    workspace_id: str = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Revoke a role from a user.

    Requires: user.revoke_role permission OR admin role

    Parameters:
    - user_id: UUID of the user
    - role_id: UUID of the role to revoke
    - workspace_id: Optional workspace UUID (query param) to specify which assignment

    Returns:
    - Success message
    """
    try:
        assigner_id = current_user.get("identity")

        # Check if admin
        is_user_admin = db.query(UserRole).join(Role).filter(
            UserRole.user_id == assigner_id,
            Role.name.in_(["admin", "super_admin"])
        ).first() is not None

        if not is_user_admin:
            # Check for user.revoke_role permission
            has_permission = (
                db.query(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .filter(
                    UserRole.user_id == assigner_id,
                    Permission.name == "user.revoke_role"
                )
                .first()
            )

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: user.revoke_role or admin role"
                )

        # Find the assignment
        query = db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id
        )

        # Add workspace filter if provided
        if workspace_id:
            query = query.filter(UserRole.workspace_id == workspace_id)
        else:
            query = query.filter(UserRole.workspace_id == None)

        user_role = query.first()

        if not user_role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role assignment not found"
            )

        # Get role and user for logging
        role = db.query(Role).filter(Role.id == role_id).first()
        user = db.query(Users).filter(Users.id == user_id).first()

        db.delete(user_role)
        db.commit()

        logger.info(
            f"Role '{role.name if role else role_id}' revoked from user "
            f"{user.email if user else user_id} by {assigner_id}"
        )

        return success(
            data={
                "user_id": str(user_id),
                "role_id": str(role_id),
                "workspace_id": str(workspace_id) if workspace_id else None,
                "role_name": role.name if role else None
            },
            request=request,
            message=f"Role revoked successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error revoking role from user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke role"
        )


@router.get("/{user_id}/roles")
def list_user_roles(
    request: Request,
    user_id: str,
    workspace_id: str = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all roles assigned to a user.

    Requires: user.read permission OR admin role OR requesting own roles

    Parameters:
    - user_id: UUID of the user
    - workspace_id: Optional workspace UUID to filter roles

    Returns:
    - List of user's roles with details
    """
    try:
        requester_id = current_user.get("identity")

        # Allow if admin, has user.read permission, or requesting own roles
        is_own_user = requester_id == user_id

        if not is_own_user:
            # Check if admin
            is_user_admin = db.query(UserRole).join(Role).filter(
                UserRole.user_id == requester_id,
                Role.name.in_(["admin", "super_admin"])
            ).first() is not None

            if not is_user_admin:
                # Check for user.read permission
                has_permission = (
                    db.query(Permission.name)
                    .join(RolePermission, RolePermission.permission_id == Permission.id)
                    .join(UserRole, UserRole.role_id == RolePermission.role_id)
                    .filter(
                        UserRole.user_id == requester_id,
                        Permission.name == "user.read"
                    )
                    .first()
                )

                if not has_permission:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Insufficient permissions. Required: user.read or admin role"
                    )

        # Query user roles
        query = (
            db.query(UserRole, Role, WorkspaceModel)
            .join(Role, UserRole.role_id == Role.id)
            .outerjoin(WorkspaceModel, UserRole.workspace_id == WorkspaceModel.id)
            .filter(UserRole.user_id == user_id)
        )

        # Filter by workspace if provided
        if workspace_id:
            query = query.filter(UserRole.workspace_id == workspace_id)

        results = query.all()

        roles_data = []
        for user_role, role, workspace in results:
            roles_data.append({
                "id": str(user_role.id),
                "role_id": str(role.id),
                "role_name": role.name,
                "role_display_name": role.display_name,
                "hierarchy_level": role.hierarchy_level,
                "workspace_id": str(user_role.workspace_id) if user_role.workspace_id else None,
                "workspace_name": workspace.name if workspace else None,
                "is_primary": user_role.is_primary,
                "assigned_at": user_role.assigned_at.isoformat() if user_role.assigned_at else None
            })

        return success(
            data={"roles": roles_data, "count": len(roles_data)},
            request=request,
            message=f"Retrieved {len(roles_data)} role(s) for user"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing user roles for {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user roles"
        )


# -------------------------
# User Status Management Endpoints
# -------------------------

@router.post("/{user_id}/suspend", response_model=UserStatusResponse)
def suspend_user(
    user_id: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Suspend a user account (admin only).

    - **user_id**: ID of the user to suspend
    - **reason**: Optional reason for suspension

    Requires admin privileges.
    """
    try:
        # Check if current user is admin
        if not is_admin(current_user):
            return error(
                message="Insufficient permissions. Admin role required.",
                code=ErrorCode.PERMISSION_DENIED,
                status_code=403,
                severity=ErrorSeverity.HIGH,
                request=request
            )

        # Get target user
        target_user = db.query(Users).filter(Users.id == user_id).first()
        if not target_user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Store old status
        old_status = target_user.status

        # Update status
        target_user.status = "suspended"
        target_user.updated_at = datetime.utcnow()

        # Create audit log
        admin_user_id = current_user.get("identity")
        admin_user = db.query(Users).filter(Users.id == admin_user_id).first()

        create_audit_log(
            db=db,
            user_id=admin_user_id,
            action="user.suspend",
            resource_type="user",
            resource_id=str(user_id),
            old_values={"status": old_status},
            new_values={"status": "suspended", "reason": status_data.reason},
            request=request,
            username=admin_user.username if admin_user else None,
            user_email=admin_user.email if admin_user else None
        )

        db.commit()
        db.refresh(target_user)

        logger.info(f"User {user_id} suspended by admin {admin_user_id}")

        response_data = UserStatusResponse(
            user_id=str(target_user.id),
            username=target_user.username,
            email=target_user.email,
            old_status=old_status,
            new_status="suspended",
            changed_by=admin_user.username if admin_user else "unknown",
            reason=status_data.reason,
            changed_at=target_user.updated_at.isoformat()
        )

        return success(
            data=response_data.model_dump(),
            request=request,
            message=f"User {target_user.username} suspended successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error suspending user {user_id}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to suspend user"
        )


@router.post("/{user_id}/activate", response_model=UserStatusResponse)
def activate_user(
    user_id: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Activate a suspended or banned user account (admin only).

    - **user_id**: ID of the user to activate
    - **reason**: Optional reason for activation

    Requires admin privileges.
    """
    try:
        # Check if current user is admin
        if not is_admin(current_user):
            return error(
                message="Insufficient permissions. Admin role required.",
                code=ErrorCode.PERMISSION_DENIED,
                status_code=403,
                severity=ErrorSeverity.HIGH,
                request=request
            )

        # Get target user
        target_user = db.query(Users).filter(Users.id == user_id).first()
        if not target_user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Store old status
        old_status = target_user.status

        # Update status
        target_user.status = "active"
        target_user.updated_at = datetime.utcnow()

        # Create audit log
        admin_user_id = current_user.get("identity")
        admin_user = db.query(Users).filter(Users.id == admin_user_id).first()

        create_audit_log(
            db=db,
            user_id=admin_user_id,
            action="user.activate",
            resource_type="user",
            resource_id=str(user_id),
            old_values={"status": old_status},
            new_values={"status": "active", "reason": status_data.reason},
            request=request,
            username=admin_user.username if admin_user else None,
            user_email=admin_user.email if admin_user else None
        )

        db.commit()
        db.refresh(target_user)

        logger.info(f"User {user_id} activated by admin {admin_user_id}")

        response_data = UserStatusResponse(
            user_id=str(target_user.id),
            username=target_user.username,
            email=target_user.email,
            old_status=old_status,
            new_status="active",
            changed_by=admin_user.username if admin_user else "unknown",
            reason=status_data.reason,
            changed_at=target_user.updated_at.isoformat()
        )

        return success(
            data=response_data.model_dump(),
            request=request,
            message=f"User {target_user.username} activated successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating user {user_id}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate user"
        )


@router.post("/{user_id}/ban", response_model=UserStatusResponse)
def ban_user(
    user_id: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Ban a user account (admin only).

    - **user_id**: ID of the user to ban
    - **reason**: Optional reason for ban

    Requires admin privileges.
    """
    try:
        # Check if current user is admin
        if not is_admin(current_user):
            return error(
                message="Insufficient permissions. Admin role required.",
                code=ErrorCode.PERMISSION_DENIED,
                status_code=403,
                severity=ErrorSeverity.HIGH,
                request=request
            )

        # Get target user
        target_user = db.query(Users).filter(Users.id == user_id).first()
        if not target_user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Store old status
        old_status = target_user.status

        # Update status
        target_user.status = "banned"
        target_user.updated_at = datetime.utcnow()

        # Create audit log
        admin_user_id = current_user.get("identity")
        admin_user = db.query(Users).filter(Users.id == admin_user_id).first()

        create_audit_log(
            db=db,
            user_id=admin_user_id,
            action="user.ban",
            resource_type="user",
            resource_id=str(user_id),
            old_values={"status": old_status},
            new_values={"status": "banned", "reason": status_data.reason},
            request=request,
            username=admin_user.username if admin_user else None,
            user_email=admin_user.email if admin_user else None
        )

        db.commit()
        db.refresh(target_user)

        logger.info(f"User {user_id} banned by admin {admin_user_id}")

        response_data = UserStatusResponse(
            user_id=str(target_user.id),
            username=target_user.username,
            email=target_user.email,
            old_status=old_status,
            new_status="banned",
            changed_by=admin_user.username if admin_user else "unknown",
            reason=status_data.reason,
            changed_at=target_user.updated_at.isoformat()
        )

        return success(
            data=response_data.model_dump(),
            request=request,
            message=f"User {target_user.username} banned successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error banning user {user_id}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to ban user"
        )


# -------------------------
# Account Settings Endpoints
# -------------------------

@router.post("/deactivate", response_model=DeactivateAccountResponse)
def deactivate_account(
    request: Request,
    deactivation_data: DeactivateAccountRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Deactivate user's own account.

    Account will be marked as inactive and scheduled for permanent deletion after 14 days.
    User will be logged out immediately.

    - **reason**: Optional reason for deactivation
    - **confirm**: Must be true to proceed

    Returns deactivation confirmation with scheduled deletion date.
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"Account deactivation requested for user: {user_id}")

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

        # Check if already deactivated
        if db_user.status == "inactive":
            return error(
                message="Account is already deactivated",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Update user status
        old_status = db_user.status
        db_user.status = "inactive"
        db_user.deactivated_at = datetime.utcnow()
        db_user.updated_at = datetime.utcnow()

        # Calculate scheduled deletion date (14 days from now)
        scheduled_deletion = db_user.deactivated_at + timedelta(days=14)

        # Create audit log
        create_audit_log(
            db=db,
            user_id=user_id,
            action="user.deactivate",
            resource_type="user",
            resource_id=str(user_id),
            old_values={"status": old_status},
            new_values={
                "status": "inactive",
                "deactivated_at": db_user.deactivated_at.isoformat(),
                "scheduled_deletion": scheduled_deletion.isoformat(),
                "reason": deactivation_data.reason
            },
            request=request,
            username=db_user.username,
            user_email=db_user.email
        )

        db.commit()
        db.refresh(db_user)

        logger.info(f"User {user_id} deactivated successfully. Scheduled deletion: {scheduled_deletion}")

        response_data = DeactivateAccountResponse(
            user_id=str(db_user.id),
            email=db_user.email,
            status="inactive",
            deactivated_at=db_user.deactivated_at.isoformat(),
            scheduled_deletion_at=scheduled_deletion.isoformat(),
            message=f"Account deactivated successfully. Your account will be permanently deleted on {scheduled_deletion.strftime('%B %d, %Y')}."
        )

        return success(
            data=response_data.model_dump(),
            request=request,
            message="Account deactivated successfully"
        )

    except Exception as e:
        logger.error(f"Error deactivating account for user {current_user.get('identity')}: {str(e)}")
        db.rollback()
        return error(
            message="Failed to deactivate account",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.post("/export-data", response_model=DataExportResponse)
def export_user_data(
    request: Request,
    export_request: DataExportRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Request export of user's data.

    Generates a comprehensive data export including:
    - Profile information
    - Role assignments
    - Workspace memberships
    - Activity logs (if available)

    Export will be generated in the background and sent via email.

    Returns export request confirmation.
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"Data export requested for user: {user_id}")

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

        # Generate export ID
        export_id = str(uuid.uuid4())

        # Collect user data based on request
        export_data = {}

        if export_request.include_profile:
            export_data["profile"] = {
                "id": str(db_user.id),
                "email": db_user.email,
                "username": db_user.username,
                "first_name": db_user.first_name,
                "last_name": db_user.last_name,
                "display_name": db_user.display_name,
                "language": db_user.language,
                "timezone": db_user.timezone,
                "status": db_user.status,
                "email_verified": db_user.email_verified,
                "email_verified_at": db_user.email_verified_at.isoformat() if db_user.email_verified_at else None,
                "created_at": db_user.created_at.isoformat() if db_user.created_at else None,
                "last_login_at": db_user.last_login_at.isoformat() if db_user.last_login_at else None,
                "login_count": db_user.login_count
            }

        if export_request.include_roles:
            roles = []
            for user_role in db_user.user_roles:
                roles.append({
                    "role_name": user_role.role.name if user_role.role else None,
                    "role_display_name": user_role.role.display_name if user_role.role else None,
                    "is_primary": user_role.is_primary,
                    "workspace_id": str(user_role.workspace_id) if user_role.workspace_id else None,
                    "assigned_at": user_role.assigned_at.isoformat() if user_role.assigned_at else None
                })
            export_data["roles"] = roles

        if export_request.include_workspaces:
            workspaces = []
            for membership in db_user.workspace_memberships:
                workspaces.append({
                    "workspace_id": str(membership.workspace_id),
                    "workspace_name": membership.workspace.name if membership.workspace else None,
                    "role": membership.role,
                    "status": membership.status,
                    "joined_at": membership.joined_at.isoformat() if membership.joined_at else None
                })
            export_data["workspaces"] = workspaces

        # Note: Activity logs would require audit_logs table access
        if export_request.include_activity:
            export_data["activity"] = {
                "note": "Activity logs export will be available once audit log system is queried"
            }

        # Convert to JSON for email
        import json
        export_json = json.dumps(export_data, indent=2)

        # Get frontend URL
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

        # Send email with data export in background
        background_tasks.add_task(
            send_email,
            to=db_user.email,
            subject="Your WREXT Data Export",
            body=f"""
            <h2>Your Data Export is Ready</h2>
            <p>Hello {db_user.first_name or db_user.username},</p>
            <p>Your requested data export has been generated.</p>
            <p><strong>Export ID:</strong> {export_id}</p>
            <p><strong>Generated at:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>

            <h3>Export Contents:</h3>
            <ul>
                <li>Profile Information: {'✓' if export_request.include_profile else '✗'}</li>
                <li>Role Assignments: {'✓' if export_request.include_roles else '✗'}</li>
                <li>Workspace Memberships: {'✓' if export_request.include_workspaces else '✗'}</li>
                <li>Activity Logs: {'✓' if export_request.include_activity else '✗'}</li>
            </ul>

            <p>Your data is attached as a JSON file to this email.</p>
            <p><a href="{frontend_url}">Return to WREXT</a></p>

            <hr>
            <pre style="background: #f4f4f4; padding: 15px; border-radius: 5px; overflow-x: auto;">
{export_json}
            </pre>
            """
        )

        logger.info(f"Data export {export_id} generated for user {user_id}")

        response_data = DataExportResponse(
            export_id=export_id,
            user_id=str(user_id),
            status="completed",
            requested_at=datetime.utcnow().isoformat(),
            message="Data export has been sent to your email address"
        )

        return success(
            data=response_data.model_dump(),
            request=request,
            message="Data export request completed successfully"
        )

    except Exception as e:
        logger.error(f"Error exporting data for user {current_user.get('identity')}: {str(e)}")
        return error(
            message="Failed to export user data",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


# -------------------------
# Avatar Upload Endpoints
# -------------------------

@router.post("/avatar/upload")
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload user avatar image.

    - **file**: Image file (JPEG, PNG, GIF, WebP)
    - Max size: 5MB
    - Replaces existing avatar if present
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"User {user_id} uploading avatar")

        # Get user
        user = db.query(Users).filter(Users.id == user_id).first()
        if not user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
        if file.content_type not in allowed_types:
            return error(
                message=f"Invalid file type. Allowed: {', '.join(allowed_types)}",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Read file content
        file_content = await file.read()
        file_size = len(file_content)

        # Validate file size (5MB max)
        max_size = 5 * 1024 * 1024  # 5MB
        if file_size > max_size:
            return error(
                message=f"File too large. Max size: 5MB. Your file: {file_size / (1024 * 1024):.2f}MB",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Create user-specific directory
        user_avatar_dir = AVATAR_UPLOAD_DIR / str(user_id)
        user_avatar_dir.mkdir(parents=True, exist_ok=True)

        # Delete old avatar if exists
        if user.avatar_url:
            old_avatar_path = Path(user.avatar_url.lstrip('/'))
            if old_avatar_path.exists():
                try:
                    old_avatar_path.unlink()
                    logger.info(f"Deleted old avatar: {old_avatar_path}")
                except Exception as e:
                    logger.warning(f"Could not delete old avatar: {str(e)}")

        # Generate unique filename
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        timestamp = int(time.time())
        new_filename = f"{user_id}_{timestamp}.{file_extension}"
        file_path = user_avatar_dir / new_filename

        # Save file
        with open(file_path, "wb") as f:
            f.write(file_content)

        # Update user avatar_url (store relative path)
        relative_path = f"/avatars/{user_id}/{new_filename}"
        user.avatar_url = relative_path
        user.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(user)

        logger.info(f"Avatar uploaded successfully for user {user_id}: {relative_path}")

        return success(
            data={
                "avatar_url": user.avatar_url,
                "file_size": file_size,
                "uploaded_at": user.updated_at.isoformat()
            },
            request=request,
            message="Avatar uploaded successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading avatar for user {current_user.get('identity')}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar"
        )


@router.delete("/avatar")
def delete_avatar(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete user avatar.

    Sets avatar_url to null and removes the file from storage.
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"User {user_id} deleting avatar")

        # Get user
        user = db.query(Users).filter(Users.id == user_id).first()
        if not user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Check if user has avatar
        if not user.avatar_url:
            return error(
                message="No avatar to delete",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Delete file from storage
        avatar_path = Path(user.avatar_url.lstrip('/'))
        if avatar_path.exists():
            try:
                avatar_path.unlink()
                logger.info(f"Deleted avatar file: {avatar_path}")
            except Exception as e:
                logger.warning(f"Could not delete avatar file: {str(e)}")

        # Update user
        old_avatar_url = user.avatar_url
        user.avatar_url = None
        user.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(user)

        logger.info(f"Avatar deleted successfully for user {user_id}")

        return success(
            data={
                "deleted_avatar_url": old_avatar_url,
                "deleted_at": user.updated_at.isoformat()
            },
            request=request,
            message="Avatar deleted successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting avatar for user {current_user.get('identity')}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete avatar"
        )