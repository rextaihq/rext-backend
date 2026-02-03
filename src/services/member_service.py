"""
Member Service - Business Logic for Workspace Member Operations

This service encapsulates all business logic related to workspace membership,
including adding/removing members, updating member status, and member queries.

Responsibilities:
- Member CRUD operations
- Member status management (active/inactive/pending)
- Member validation and duplicate checking
- Default workspace management

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Authentication/authorization (that's decorators)
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.user_models.users import Users
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    DuplicateResourceException,
    RextValidationException
)
from src.services.invitation_service import InvitationService

class MemberService(InvitationService):
    """Service for workspace member business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize MemberService.

        Args:
            db: Async database session
        """
        self.db = db

    async def add_member(
        self,
        workspace_id: UUID,
        user_id: UUID,
        invitation_id: Optional[UUID] = None,
        status: str = "active"
    ) -> WorkspaceMembers:
        """
        Add a member to a workspace.

        Business Rules:
        - Workspace must exist
        - User must not already be a member
        - Status defaults to 'active' unless specified

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID to add
            invitation_id: Optional invitation UUID
            status: Member status (active/pending/inactive)

        Returns:
            Created WorkspaceMembers object

        Raises:
            ResourceNotFoundException: If workspace doesn't exist
            DuplicateResourceException: If user is already a member
        """
        # Verify workspace exists
        result = await self.db.execute(
            select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
        )
        workspace = result.scalar_one_or_none()
        if not workspace:
            raise ResourceNotFoundException(
                resource_type="Workspace",
                resource_id=str(workspace_id)
            )

        # Check for existing membership
        result = await self.db.execute(
            select(WorkspaceMembers).where(
                and_(
                    WorkspaceMembers.workspace_id == workspace_id,
                    WorkspaceMembers.user_id == user_id
                )
            )
        )
        existing_member = result.scalar_one_or_none()
        if existing_member:
            raise DuplicateResourceException(
                resource_type="WorkspaceMember",
                conflicting_field="user_id",
                conflicting_value=str(user_id),
                context={"workspace_id": str(workspace_id)}
            )

        # Create new member
        new_member = WorkspaceMembers(
            workspace_id=workspace_id,
            user_id=user_id,
            invitation_id=invitation_id,
            status=status,
            joined_at=datetime.utcnow(),
            last_activity_at=datetime.utcnow()
        )
        self.db.add(new_member)
        await self.db.flush()
        await self.db.refresh(new_member)

        logger.info(
            f"Member added to workspace: user={user_id}, workspace={workspace_id}",
            extra={
                "user_id": str(user_id),
                "workspace_id": str(workspace_id),
                "status": status
            }
        )

        return new_member

    async def remove_member(
        self,
        workspace_id: UUID,
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Remove a member from a workspace.

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID to remove

        Returns:
            Dict with deletion details

        Raises:
            ResourceNotFoundException: If member not found
        """
        result = await self.db.execute(
            select(WorkspaceMembers).where(
                and_(
                    WorkspaceMembers.workspace_id == workspace_id,
                    WorkspaceMembers.user_id == user_id
                )
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            raise ResourceNotFoundException(
                resource_type="WorkspaceMember",
                resource_id=str(user_id),
                context={"workspace_id": str(workspace_id)}
            )

        await self.db.delete(member)

        logger.info(
            f"Member removed from workspace: user={user_id}, workspace={workspace_id}",
            extra={
                "user_id": str(user_id),
                "workspace_id": str(workspace_id)
            }
        )

        return {
            "user_id": str(user_id),
            "workspace_id": str(workspace_id),
            "removed_at": datetime.utcnow()
        }

    async def get_workspace_members(
        self,
        workspace_id: UUID,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[WorkspaceMembers]:
        """
        Get members of a workspace with optional filtering.

        Args:
            workspace_id: Workspace UUID
            status: Optional status filter (active/inactive/pending)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of WorkspaceMembers
        """
        query = select(WorkspaceMembers).where(
            WorkspaceMembers.workspace_id == workspace_id
        )

        if status:
            query = query.where(WorkspaceMembers.status == status)

        query = query.limit(limit).offset(offset).order_by(
            WorkspaceMembers.joined_at.desc()
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_user_workspaces(
        self,
        user_id: UUID,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[WorkspaceMembers]:
        """
        Get all workspaces a user is a member of.

        Args:
            user_id: User UUID
            status: Optional status filter
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of WorkspaceMembers
        """
        query = select(WorkspaceMembers).where(
            WorkspaceMembers.user_id == user_id
        )

        if status:
            query = query.where(WorkspaceMembers.status == status)

        query = query.limit(limit).offset(offset).order_by(
            WorkspaceMembers.joined_at.desc()
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_member_status(
        self,
        workspace_id: UUID,
        user_id: UUID,
        status: str
    ) -> WorkspaceMembers:
        """
        Update member status.

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID
            status: New status (active/inactive/pending)

        Returns:
            Updated WorkspaceMembers object

        Raises:
            ResourceNotFoundException: If member not found
            RextValidationException: If status invalid
        """
        valid_statuses = ["active", "inactive", "pending"]
        if status not in valid_statuses:
            raise RextValidationException(
                message=f"Invalid status: {status}",
                field_errors={
                    "status": [f"Status must be one of: {', '.join(valid_statuses)}"]
                }
            )

        result = await self.db.execute(
            select(WorkspaceMembers).where(
                and_(
                    WorkspaceMembers.workspace_id == workspace_id,
                    WorkspaceMembers.user_id == user_id
                )
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            raise ResourceNotFoundException(
                resource_type="WorkspaceMember",
                resource_id=str(user_id),
                context={"workspace_id": str(workspace_id)}
            )

        member.status = status
        member.last_activity_at = datetime.utcnow()

        logger.info(
            f"Member status updated: user={user_id}, workspace={workspace_id}, status={status}",
            extra={
                "user_id": str(user_id),
                "workspace_id": str(workspace_id),
                "status": status
            }
        )

        return member

    async def set_default_workspace(
        self,
        user_id: UUID,
        workspace_id: UUID
    ) -> WorkspaceMembers:
        """
        Set a workspace as the default for a user.
        Clears any previous default workspace.

        Args:
            user_id: User UUID
            workspace_id: Workspace UUID to set as default

        Returns:
            Updated WorkspaceMembers object

        Raises:
            ResourceNotFoundException: If member not found
        """
        # Bulk-clear any existing default
        from sqlalchemy import update
        await self.db.execute(
            update(WorkspaceMembers)
            .where(
                and_(
                    WorkspaceMembers.user_id == user_id,
                    WorkspaceMembers.is_default == True
                )
            )
            .values(is_default=False)
        )

        # Set new default
        result = await self.db.execute(
            select(WorkspaceMembers).where(
                and_(
                    WorkspaceMembers.workspace_id == workspace_id,
                    WorkspaceMembers.user_id == user_id
                )
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            raise ResourceNotFoundException(
                resource_type="WorkspaceMember",
                resource_id=str(user_id),
                context={"workspace_id": str(workspace_id)}
            )

        member.is_default = True

        logger.info(
            f"Default workspace set: user={user_id}, workspace={workspace_id}",
            extra={
                "user_id": str(user_id),
                "workspace_id": str(workspace_id)
            }
        )

        return member

    async def get_member_count(
        self,
        workspace_id: UUID,
        status: Optional[str] = None
    ) -> int:
        """
        Get count of workspace members.

        Args:
            workspace_id: Workspace UUID
            status: Optional status filter

        Returns:
            Count of members
        """
        query = select(func.count(WorkspaceMembers.id)).where(
            WorkspaceMembers.workspace_id == workspace_id
        )

        if status:
            query = query.where(WorkspaceMembers.status == status)

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def update_last_activity(
        self,
        workspace_id: UUID,
        user_id: UUID
    ) -> None:
        """
        Update member's last activity timestamp.

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID

        Raises:
            ResourceNotFoundException: If member not found
        """
        result = await self.db.execute(
            select(WorkspaceMembers).where(
                and_(
                    WorkspaceMembers.workspace_id == workspace_id,
                    WorkspaceMembers.user_id == user_id
                )
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            raise ResourceNotFoundException(
                resource_type="WorkspaceMember",
                resource_id=str(user_id),
                context={"workspace_id": str(workspace_id)}
            )

        member.last_activity_at = datetime.utcnow()

        logger.debug(
            f"Member activity updated: user={user_id}, workspace={workspace_id}",
            extra={
                "user_id": str(user_id),
                "workspace_id": str(workspace_id)
            }
        )

    async def get_member_by_id(
        self,
        member_id: UUID,
        workspace_id: UUID
    ) -> WorkspaceMembers:
        """
        Get workspace member by member ID.

        Args:
            member_id: Member UUID
            workspace_id: Workspace UUID for validation

        Returns:
            WorkspaceMembers object

        Raises:
            ResourceNotFoundException: If member not found
        """
        result = await self.db.execute(
            select(WorkspaceMembers).where(
                WorkspaceMembers.id == member_id,
                WorkspaceMembers.workspace_id == workspace_id
            )
        )
        member = result.scalar_one_or_none()

        if not member:
            raise ResourceNotFoundException(
                resource_type="member",
                resource_id=str(member_id)
            )

        logger.debug(f"Retrieved member {member_id} from workspace {workspace_id}")
        return member

    async def get_member_with_user(
        self,
        member_id: UUID,
        workspace_id: UUID
    ) -> tuple[WorkspaceMembers, "Users"]:
        """
        Get workspace member with associated user details.

        Args:
            member_id: Member UUID
            workspace_id: Workspace UUID

        Returns:
            Tuple of (WorkspaceMembers, Users)

        Raises:
            ResourceNotFoundException: If member not found
        """
        from src.api.models.user_models.users import Users

        # Get member first
        member = await self.get_member_by_id(member_id, workspace_id)

        # Get associated user
        result = await self.db.execute(
            select(Users).where(Users.id == member.user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(
                resource_type="user",
                resource_id=str(member.user_id)
            )

        logger.debug(f"Retrieved member {member_id} with user details")
        return member, user

    async def update_member_role(
        self,
        workspace_id: UUID,
        member_id: UUID,
        new_role_id: UUID,
        assigned_by_user_id: UUID
    ) -> tuple[WorkspaceMembers, "Users", "Role", "Role | None"]:
        """
        Update workspace member's role.

        Args:
            workspace_id: Workspace UUID
            member_id: Member UUID
            new_role_id: New role UUID to assign
            assigned_by_user_id: User performing the role change

        Returns:
            Tuple of (member, member_user, new_role, old_role)

        Raises:
            ResourceNotFoundException: If member or role not found
            RextValidationException: If member is workspace owner
        """
        from src.api.models.user_models.users import Users
        from src.api.models.user_models.roles import Role
        from src.api.models.user_models.user_roles import UserRole

        # Get member with validation
        member, member_user = await self.get_member_with_user(member_id, workspace_id)

        # Validate member can be updated
        if member.is_default:
            raise RextValidationException(
                message="Cannot change role of workspace owner",
                field_errors={"member_id": ["Workspace owner role is immutable"]},
                error_code="VALIDATION_ERROR",
                error_severity="ERROR"
            )

        # Get new role
        result = await self.db.execute(
            select(Role).where(Role.id == new_role_id)
        )
        new_role = result.scalar_one_or_none()
        if not new_role:
            raise ResourceNotFoundException(
                resource_type="role",
                resource_id=str(new_role_id)
            )

        # Get current user role
        result = await self.db.execute(
            select(UserRole).where(
                UserRole.user_id == member.user_id,
                UserRole.workspace_id == workspace_id
            )
        )
        user_role = result.scalar_one_or_none()

        # Track old role for response
        old_role = None
        if user_role and user_role.role_id:
            old_role_result = await self.db.execute(
                select(Role).where(Role.id == user_role.role_id)
            )
            old_role = old_role_result.scalar_one_or_none()

        # Update or create user role
        # Use utcnow() for timezone-naive datetime to match TIMESTAMP WITHOUT TIME ZONE column
        timestamp = datetime.utcnow()
        if user_role:
            user_role.role_id = new_role_id
            user_role.assigned_by_user_id = assigned_by_user_id
            user_role.assigned_at = timestamp
        else:
            self.db.add(
                UserRole(
                    user_id=member.user_id,
                    workspace_id=workspace_id,
                    role_id=new_role_id,
                    assigned_by_user_id=assigned_by_user_id,
                    assigned_at=timestamp,
                    is_primary=False
                )
            )

        logger.info(f"Updated role for member {member_id} in workspace {workspace_id}")
        return member, member_user, new_role, old_role


    async def remove_user_roles_in_workspace(
        self,
        workspace_id: UUID,
        user_id: UUID
    ) -> None:
        """
        Remove all roles assigned to a user in a specific workspace.
        Args:
            workspace_id: Workspace UUID
            user_id: User UUID
        """
        from src.api.models.user_models.user_roles import UserRole

        # Fetch all roles for the user in the given workspace
        result = await self.db.execute(
            select(UserRole).where(
                and_(
                    UserRole.workspace_id == workspace_id,
                    UserRole.user_id == user_id
                )
            )
        )

        user_roles = result.scalars().all()

        # Delete each user role
        for user_role in user_roles:
            await self.db.delete(user_role)

        # ✅ Commit the changes
        await self.db.commit()

    async def get_workspace_members_with_users(
        self,
        workspace_id: UUID,
        status: Optional[str] = None
    ) -> List[tuple[WorkspaceMembers, "Users", Optional["Role"]]]:
        """
        Get workspace members with their user details and roles.

        Args:
            workspace_id: Workspace UUID
            status: Optional status filter

        Returns:
            List of (WorkspaceMembers, Users, Role) tuples
        """
        from src.api.models.user_models.users import Users
        from src.api.models.user_models.user_roles import UserRole
        from src.api.models.user_models.roles import Role

        query = (
            select(WorkspaceMembers, Users, Role)
            .join(Users, Users.id == WorkspaceMembers.user_id)
            .outerjoin(
                UserRole,
                and_(
                    UserRole.user_id == WorkspaceMembers.user_id,
                    UserRole.workspace_id == workspace_id
                )
            )
            .outerjoin(Role, Role.id == UserRole.role_id)
            .where(WorkspaceMembers.workspace_id == workspace_id)
            .order_by(WorkspaceMembers.joined_at.asc())
        )

        if status:
            query = query.where(WorkspaceMembers.status == status)

        result = await self.db.execute(query)
        rows = result.all()

        logger.debug(f"Retrieved {len(rows)} members with user details for workspace {workspace_id}")
        return rows

    async def get_admin_members_with_users(
        self,
        workspace_id: UUID
    ) -> List[tuple[WorkspaceMembers, "Users"]]:
        """
        Get workspace admin/owner members with their user details.

        Args:
            workspace_id: Workspace UUID

        Returns:
            List of (WorkspaceMembers, Users) tuples for admins and owners
        """
        from src.api.models.user_models.users import Users
        from src.api.models.user_models.roles import Role

        query = (
            select(WorkspaceMembers, Users)
            .join(Users, Users.id == WorkspaceMembers.user_id)
            .join(Role, WorkspaceMembers.role_id == Role.id)
            .where(WorkspaceMembers.workspace_id == workspace_id)
            .where(Role.name.in_(["owner", "admin"]))
            .order_by(WorkspaceMembers.joined_at.asc())
        )

        result = await self.db.execute(query)
        rows = result.all()

        logger.debug(f"Retrieved {len(rows)} admin members for workspace {workspace_id}")
        return rows
    