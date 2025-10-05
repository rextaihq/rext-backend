from fastapi import APIRouter, Depends, Request
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.schema.impersonation_schema import ImpersonateStartRequest
from src.api.security.token_utils import create_access_token, create_refresh_token
from sqlalchemy.orm import Session
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.database.database import get_db
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.utils.audit_helper import create_audit_log
from src.api.middleware.permissions import is_admin
from src.api.middleware.exceptions import (
    WrextAuthenticationException,
    WrextValidationException
)
from datetime import datetime, timezone

router = APIRouter()


@router.post("/impersonate/start", dependencies=[Depends(is_admin)])
def start_impersonation(
    impersonate_request: ImpersonateStartRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Start impersonating another user.

    - **Requires:** admin role or user.impersonate permission
    - **Creates:** Audit log entry
    - **Returns:** New JWT tokens for the impersonated user with original user stored
    """
    admin_user_id = current_user.get("identity")
    target_user_id = impersonate_request.user_id

    try:
        # Get admin user
        admin_user = db.query(Users).filter(
            Users.id == admin_user_id,
            Users.deleted_at == None
        ).first()

        if not admin_user:
            raise WrextAuthenticationException(
                message="Admin user not found",
                context={"user_id": admin_user_id}
            )

        # Get target user to impersonate
        target_user = db.query(Users).filter(
            Users.id == target_user_id,
            Users.deleted_at == None
        ).first()

        if not target_user:
            raise WrextValidationException(
                message="Target user not found",
                validation_errors={"user_id": "User does not exist"}
            )

        # Prevent impersonating yourself
        if admin_user_id == target_user_id:
            raise WrextValidationException(
                message="Cannot impersonate yourself",
                validation_errors={"user_id": "You cannot impersonate your own account"}
            )

        # Get target user's roles and permissions
        user_roles = db.query(Role.name).join(
            UserRole, UserRole.role_id == Role.id
        ).filter(
            UserRole.user_id == target_user_id,
            UserRole.workspace_id == None  # Global roles only
        ).all()

        roles = [role[0] for role in user_roles]

        # Get target user's permissions
        permissions_query = db.query(Permission.name).join(
            RolePermission, RolePermission.permission_id == Permission.id
        ).join(
            UserRole, UserRole.role_id == RolePermission.role_id
        ).filter(
            UserRole.user_id == target_user_id,
            UserRole.workspace_id == None  # Global permissions only
        ).distinct()

        permissions = [perm[0] for perm in permissions_query.all()]

        # Create JWT tokens with impersonation metadata
        token_data = {
            "identity": str(target_user_id),
            "username": target_user.username,
            "email": target_user.email,
            "roles": roles,
            "permissions": permissions,
            "is_impersonating": True,
            "original_user_id": str(admin_user_id),
            "impersonation_started_at": datetime.now(timezone.utc).isoformat()
        }

        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token({"identity": str(target_user_id)})

        # Create audit log
        create_audit_log(
            db=db,
            user_id=admin_user_id,
            action="user.impersonate.start",
            resource_type="user",
            resource_id=target_user_id,
            details={
                "admin_user_email": admin_user.email,
                "target_user_email": target_user.email,
                "target_user_name": target_user.display_name,
                "ip_address": request.client.host if request.client else None
            }
        )

        logger.info(f"Admin {admin_user.email} started impersonating user {target_user.email}")

        return success(
            data={
                "original_user_id": str(admin_user_id),
                "impersonated_user_id": str(target_user_id),
                "impersonated_user_email": target_user.email,
                "impersonated_user_name": target_user.display_name,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "started_at": datetime.now(timezone.utc).isoformat()
            },
            request=request,
            message=f"Now impersonating {target_user.display_name}"
        )

    except (WrextAuthenticationException, WrextValidationException):
        raise
    except Exception as e:
        logger.error(f"Failed to start impersonation: {str(e)}")
        return error(
            message="Failed to start impersonation",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.post("/impersonate/stop")
def stop_impersonation(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Stop impersonating and return to original user.

    - **Requires:** Currently impersonating
    - **Creates:** Audit log entry
    - **Returns:** New JWT tokens for the original user
    """
    try:
        # Check if currently impersonating
        is_impersonating = current_user.get("is_impersonating", False)
        if not is_impersonating:
            raise WrextValidationException(
                message="Not currently impersonating",
                validation_errors={"impersonation": "You are not impersonating anyone"}
            )

        original_user_id = current_user.get("original_user_id")
        impersonated_user_id = current_user.get("identity")

        if not original_user_id:
            raise WrextValidationException(
                message="Original user ID not found in token",
                validation_errors={"token": "Invalid impersonation token"}
            )

        # Get original user
        original_user = db.query(Users).filter(
            Users.id == original_user_id,
            Users.deleted_at == None
        ).first()

        if not original_user:
            raise WrextAuthenticationException(
                message="Original user not found",
                context={"user_id": original_user_id}
            )

        # Get original user's roles and permissions
        user_roles = db.query(Role.name).join(
            UserRole, UserRole.role_id == Role.id
        ).filter(
            UserRole.user_id == original_user_id,
            UserRole.workspace_id == None  # Global roles only
        ).all()

        roles = [role[0] for role in user_roles]

        # Get original user's permissions
        permissions_query = db.query(Permission.name).join(
            RolePermission, RolePermission.permission_id == Permission.id
        ).join(
            UserRole, UserRole.role_id == RolePermission.role_id
        ).filter(
            UserRole.user_id == original_user_id,
            UserRole.workspace_id == None  # Global permissions only
        ).distinct()

        permissions = [perm[0] for perm in permissions_query.all()]

        # Create JWT tokens for original user (without impersonation)
        token_data = {
            "identity": str(original_user_id),
            "username": original_user.username,
            "email": original_user.email,
            "roles": roles,
            "permissions": permissions,
            "is_impersonating": False
        }

        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token({"identity": str(original_user_id)})

        # Create audit log
        create_audit_log(
            db=db,
            user_id=original_user_id,
            action="user.impersonate.stop",
            resource_type="user",
            resource_id=impersonated_user_id,
            details={
                "admin_user_email": original_user.email,
                "impersonated_user_id": impersonated_user_id,
                "ip_address": request.client.host if request.client else None
            }
        )

        logger.info(f"Admin {original_user.email} stopped impersonating")

        return success(
            data={
                "original_user_id": str(original_user_id),
                "access_token": access_token,
                "refresh_token": refresh_token,
                "stopped_at": datetime.now(timezone.utc).isoformat()
            },
            request=request,
            message="Impersonation stopped"
        )

    except (WrextAuthenticationException, WrextValidationException):
        raise
    except Exception as e:
        logger.error(f"Failed to stop impersonation: {str(e)}")
        return error(
            message="Failed to stop impersonation",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.get("/impersonate/status")
def get_impersonation_status(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Get current impersonation status.

    - **Returns:** Impersonation status and user details if impersonating
    """
    try:
        is_impersonating = current_user.get("is_impersonating", False)

        if not is_impersonating:
            return success(
                data={
                    "is_impersonating": False
                },
                request=request,
                message="Not impersonating"
            )

        # Extract impersonation details from token
        original_user_id = current_user.get("original_user_id")
        impersonated_user_id = current_user.get("identity")
        started_at = current_user.get("impersonation_started_at")

        return success(
            data={
                "is_impersonating": True,
                "original_user_id": original_user_id,
                "impersonated_user_id": impersonated_user_id,
                "impersonated_user_email": current_user.get("email"),
                "impersonated_user_name": current_user.get("username"),
                "started_at": started_at
            },
            request=request,
            message="Impersonation status retrieved"
        )

    except Exception as e:
        logger.error(f"Failed to get impersonation status: {str(e)}")
        return error(
            message="Failed to get impersonation status",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.LOW,
            context={"error_details": str(e)},
            request=request
        )
