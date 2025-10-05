from fastapi import APIRouter, Depends, Request, HTTPException, status
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.schema.user_role_schema import AssignUserRoleRequest
from sqlalchemy.orm import Session
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.database.database import get_db
from src.utils.response_utils import success
from datetime import datetime

router = APIRouter()


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
