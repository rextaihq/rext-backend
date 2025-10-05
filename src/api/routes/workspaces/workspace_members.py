from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from uuid import UUID

from src.utils.logger import logger
from src.utils.response_utils import success, error
from src.utils.auth_utils import verify_current_user
from src.utils.workspace_utils import verify_workspace_membership
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    WrextValidationException,
    WrextAuthenticationException
)
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.schema.workspace_schema import ChangeMemberRoleRequest
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole

router = APIRouter()


# -------------------------
# Get workspace members
# -------------------------
@router.get("/{workspace_id}/members")
async def get_workspace_members(workspace_id: str, request: Request, db: AsyncSession = Depends(get_async_db), user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    try:
        workspace, membership = await verify_workspace_membership(db, UUID(workspace_id), user_id)

        # Get all members of the workspace with user details
        members_query = (
            select(WorkspaceMembers, Users)
            .join(Users, Users.id == WorkspaceMembers.user_id)
            .where(WorkspaceMembers.workspace_id == workspace_id)
        )
        result = await db.execute(members_query)
        members = result.all()

        members_data = []
        for member, user_info in members:
            members_data.append({
                "id": str(member.id),
                "user_id": str(member.user_id),
                "workspace_id": str(member.workspace_id),
                "status": member.status,
                "is_default": member.is_default,
                "joined_at": member.joined_at.isoformat() if member.joined_at else None,
                "last_activity_at": member.last_activity_at.isoformat() if member.last_activity_at else None,
                "user": {
                    "id": str(user_info.id),
                    "email": user_info.email,
                    "display_name": user_info.display_name,
                    "is_verified": user_info.email_verified,
                }
            })

        return success(
            data={"members": members_data, "total_count": len(members_data)},
            request=request,
            message=f"Retrieved {len(members_data)} members successfully"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching workspace members {workspace_id}")
        return error(
            message="Failed to retrieve workspace members",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


# -------------------------
# Add workspace member
# -------------------------
@router.post("/{workspace_id}/members")
async def add_workspace_member(
    workspace_id: str,
    email: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    try:
        workspace, membership = await verify_workspace_membership(db, UUID(workspace_id), user_id)

        # Find user by email
        result = await db.execute(select(Users).where(Users.email == email, Users.deleted_at == None))
        new_user = result.scalar_one_or_none()
        if not new_user:
            raise ResourceNotFoundException(resource_type="user", resource_id=email)

        # Check if already a member
        result = await db.execute(select(WorkspaceMembers).where(
            WorkspaceMembers.workspace_id == workspace_id,
            WorkspaceMembers.user_id == new_user.id
        ))
        existing_member = result.scalar_one_or_none()
        if existing_member:
            raise DuplicateResourceException(
                message=f"User {email} is already a member of this workspace",
                resource_type="workspace_member",
                conflicting_field="user_id",
                conflicting_value=str(new_user.id)
            )

        # Add as member
        new_member = WorkspaceMembers(
            user_id=new_user.id,
            workspace_id=workspace_id,
            status="active",
            is_default=False,
            joined_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc)
        )
        db.add(new_member)
        await db.commit()
        await db.refresh(new_member)

        return success(
            data={
                "member": {
                    "id": str(new_member.id),
                    "user_id": str(new_user.id),
                    "email": new_user.email,
                    "display_name": new_user.display_name,
                    "status": new_member.status,
                }
            },
            request=request,
            message=f"User {email} added to workspace successfully"
        )

    except (ResourceNotFoundException, DuplicateResourceException):
        raise
    except Exception as e:
        logger.exception(f"Error adding member to workspace {workspace_id}")
        await db.rollback()
        return error(
            message="Failed to add member to workspace",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


# -------------------------
# Remove workspace member
# -------------------------
@router.delete("/{workspace_id}/members/{member_id}")
async def remove_workspace_member(
    workspace_id: str,
    member_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    try:
        workspace, membership = await verify_workspace_membership(db, UUID(workspace_id), user_id)

        # Get member to remove
        result = await db.execute(select(WorkspaceMembers).where(
            WorkspaceMembers.id == member_id,
            WorkspaceMembers.workspace_id == workspace_id
        ))
        member = result.scalar_one_or_none()

        if not member:
            raise ResourceNotFoundException(resource_type="member", resource_id=member_id)

        # Cannot remove workspace owner (is_default=True)
        if member.is_default:
            raise WrextValidationException(
                message="Cannot remove workspace owner",
                validation_errors={"member_id": "This member is the workspace owner"}
            )

        # Delete member
        await db.delete(member)
        await db.commit()

        return success(
            data={"member_id": member_id},
            request=request,
            message="Member removed from workspace successfully"
        )

    except (ResourceNotFoundException, WrextValidationException):
        raise
    except Exception as e:
        logger.exception(f"Error removing member from workspace {workspace_id}")
        await db.rollback()
        return error(
            message="Failed to remove member from workspace",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


# -------------------------
# Change workspace member role
# -------------------------
@router.put("/{workspace_id}/members/{member_id}/role")
async def change_member_role(
    workspace_id: str,
    member_id: str,
    role_request: ChangeMemberRoleRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Change the role of a workspace member.

    - Updates the user_roles table for workspace-specific role assignment
    - Cannot change role of workspace owner
    - Validates that the new role exists
    - Logs the role change in audit trail
    """
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    try:
        workspace, membership = await verify_workspace_membership(db, UUID(workspace_id), user_id)

        # Get member whose role will be changed
        result = await db.execute(select(WorkspaceMembers).where(
            WorkspaceMembers.id == member_id,
            WorkspaceMembers.workspace_id == workspace_id
        ))
        member = result.scalar_one_or_none()

        if not member:
            raise ResourceNotFoundException(resource_type="member", resource_id=member_id)

        # Cannot change role of workspace owner
        if member.is_default:
            raise WrextValidationException(
                message="Cannot change role of workspace owner",
                validation_errors={"member_id": "This member is the workspace owner"}
            )

        # Verify new role exists
        result = await db.execute(select(Role).where(Role.id == role_request.role_id))
        new_role = result.scalar_one_or_none()
        if not new_role:
            raise ResourceNotFoundException(resource_type="role", resource_id=role_request.role_id)

        # Cannot assign system roles
        if new_role.is_system_role:
            raise WrextValidationException(
                message="Cannot assign system roles to workspace members",
                validation_errors={"role_id": "This is a system role"}
            )

        # Get or create user_role entry for this workspace
        result = await db.execute(select(UserRole).where(
            UserRole.user_id == member.user_id,
            UserRole.workspace_id == workspace_id
        ))
        existing_role = result.scalar_one_or_none()

        if existing_role:
            # Update existing role
            old_role_id = existing_role.role_id
            existing_role.role_id = role_request.role_id
            existing_role.assigned_by_user_id = user_id
            existing_role.assigned_at = datetime.now(timezone.utc)
        else:
            # Create new role assignment
            old_role_id = None
            new_user_role = UserRole(
                user_id=member.user_id,
                role_id=role_request.role_id,
                workspace_id=workspace_id,
                assigned_by_user_id=user_id,
                is_primary=False
            )
            db.add(new_user_role)

        await db.commit()

        # Get member user details for response
        result = await db.execute(select(Users).where(Users.id == member.user_id))
        member_user = result.scalar_one_or_none()

        logger.info(
            f"User {user_id} changed role for member {member.user_id} in workspace {workspace_id} "
            f"from {old_role_id} to {role_request.role_id}"
        )

        return success(
            data={
                "member_id": str(member.id),
                "user_id": str(member.user_id),
                "workspace_id": str(workspace_id),
                "role_id": str(role_request.role_id),
                "role_name": new_role.display_name,
                "updated_by": str(user_id),
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            request=request,
            message=f"Role updated to {new_role.display_name} successfully"
        )

    except (ResourceNotFoundException, WrextValidationException):
        raise
    except Exception as e:
        logger.exception(f"Error changing member role in workspace {workspace_id}")
        await db.rollback()
        return error(
            message="Failed to change member role",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )
