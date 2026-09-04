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
from datetime import datetime,timezone

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
        super().__init__(db)

    async def add_member(
        self,
        workspace_id: UUID,
        user_id: UUID,
        role_id: Optional[UUID] = None,
        invitation_id: Optional[UUID] = None,
        status: str = "active"
    ) -> WorkspaceMembers:
        """
        Add a member to a workspace and assign a role.

        Business Rules:
        - Workspace must exist
        - User must not already be a member
        - Every member MUST have a role in the workspace
        - Defaults to 'viewer' role if no role_id provided

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID to add
            role_id: Optional Role UUID to assign
            invitation_id: Optional invitation UUID
            status: Member status (active/pending/inactive)

        Returns:
            Created WorkspaceMembers object

        Raises:
            ResourceNotFoundException: If workspace or role doesn't exist
            DuplicateResourceException: If user is already a member
        """
        from src.api.models.user_models.roles import Role
        from src.api.models.user_models.user_roles import UserRole

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

        # Handle role assignment
        if not role_id:
            # Default to viewer role
            result = await self.db.execute(
                select(Role).where(Role.name == "viewer", Role.is_workspace_role == True)
            )
            role = result.scalar_one_or_none()
            if not role:
                # Fallback to any role named viewer if is_workspace_role flag is inconsistent
                result = await self.db.execute(
                    select(Role).where(func.lower(Role.name) == "viewer")
                )
                role = result.scalar_one_or_none()
            
            if not role:
                logger.error("Default 'viewer' role not found in database")
                raise ResourceNotFoundException(
                    message="Default role 'viewer' not found. Roles must be seeded.",
                    resource_type="role"
                )
            role_id = role.id

        # Create new member record
        new_member = WorkspaceMembers(
            workspace_id=workspace_id,
            user_id=user_id,
            invitation_id=invitation_id,
            status=status,
            joined_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc)
        )
        self.db.add(new_member)

        # Create role assignment
        # Check if they already have *any* role in this workspace to avoid duplicates
        role_result = await self.db.execute(
            select(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.workspace_id == workspace_id
            )
        )
        if not role_result.first():
            user_role = UserRole(
                user_id=user_id,
                role_id=role_id,
                workspace_id=workspace_id,
                is_primary=True
            )
            self.db.add(user_role)

        await self.db.flush()
        await self.db.refresh(new_member)

        logger.info(
            f"Member added to workspace with role: user={user_id}, workspace={workspace_id}, role={role_id}",
            extra={
                "user_id": str(user_id),
                "workspace_id": str(workspace_id),
                "role_id": str(role_id),
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
            "removed_at": datetime.now(timezone.utc)
        }

    async def get_workspace_member(
        self,
        workspace_id: UUID,
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Get a single workspace member with their role information.

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID

        Returns:
            Dict containing member data and workspace_role

        Raises:
            ResourceNotFoundException: If member not found in workspace
        """
        from src.api.models.user_models.user_roles import UserRole
        from src.api.models.user_models.roles import Role

        # Query the membership
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

        # Get the user's role in this workspace via UserRole join table
        role_result = await self.db.execute(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                and_(
                    UserRole.user_id == user_id,
                    UserRole.workspace_id == workspace_id
                )
            )
        )
        role = role_result.scalar_one_or_none()

        # Build the response dict matching the expected format
        member_dict = member.to_dict()
        
        # Ensure role data is consistently structured
        if role:
            member_dict["workspace_role"] = {
                "id": str(role.id),
                "name": role.name,
                "display_name": role.display_name
            }
        else:
            member_dict["workspace_role"] = None

        logger.debug(
            f"Retrieved workspace member: user={user_id}, workspace={workspace_id}, role={role.name if role else 'none'}",
            extra={
                "user_id": str(user_id),
                "workspace_id": str(workspace_id),
                "has_role": role is not None
            }
        )

        return member_dict

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
        member.last_activity_at = datetime.now(timezone.utc)

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

        member.last_activity_at = datetime.now(timezone.utc)

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

        # Get all current workspace-scoped roles for this user
        existing_result = await self.db.execute(
            select(UserRole).where(
                UserRole.user_id == member.user_id,
                UserRole.workspace_id == workspace_id
            )
        )
        existing_user_roles = existing_result.scalars().all()

        # Track old role for response/audit logging
        old_role = None
        if existing_user_roles and existing_user_roles[0].role_id:
            old_role_result = await self.db.execute(
                select(Role).where(Role.id == existing_user_roles[0].role_id)
            )
            old_role = old_role_result.scalar_one_or_none()

        # Delete any existing workspace-scoped roles for this member to prevent duplicate entries
        for eur in existing_user_roles:
            await self.db.delete(eur)
        if existing_user_roles:
            await self.db.flush()

        # Add the new workspace role
        timestamp = datetime.now(timezone.utc)
        new_user_role = UserRole(
            user_id=member.user_id,
            workspace_id=workspace_id,
            role_id=new_role_id,
            assigned_by_user_id=assigned_by_user_id,
            assigned_at=timestamp,
            is_primary=True
        )
        self.db.add(new_user_role)
        await self.db.flush()

        # get_user_permissions caches for 5 minutes, so without this a demoted
        # member keeps their old access (and a promoted one waits) until the
        # TTL lapses. RoleService.assign_role/revoke_role already do this.
        from src.api.cache.decorators import invalidate_cache
        await invalidate_cache(f"user:permissions:{member.user_id}:*")
        await invalidate_cache(f"user:roles:{member.user_id}:*")

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

        # Flush to execute deletes within current transaction
        await self.db.flush()

    async def get_workspace_members_with_users(
        self,
        workspace_id: UUID,
        status: Optional[str] = None
    ) -> List[tuple[WorkspaceMembers, "Users", List["Role"]]]:
        """
        Get workspace members with their user details and all workspace-scoped roles.

        Aggregates multiple roles for a single member so that each member
        appears exactly once in the returned list. If a member has no
        workspace-scoped role, this method self-heals by looking up the role
        from the member's accepted invitation (or owner role) and re-creating
        the user_roles row so subsequent calls return correctly.

        Args:
            workspace_id: Workspace UUID
            status: Optional status filter

        Returns:
            List of (WorkspaceMembers, Users, List[Role]) tuples
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

        # Group roles by member ID while maintaining order
        member_map: Dict[UUID, tuple[WorkspaceMembers, Users, List[Role]]] = {}
        for row in rows:
            member = row[0]
            user = row[1]
            role = row[2] if len(row) > 2 else None

            if member.id not in member_map:
                member_map[member.id] = (member, user, [])
            if role is not None:
                # Add role if not already in list
                existing_role_ids = {r.id for r in member_map[member.id][2]}
                if role.id not in existing_role_ids:
                    member_map[member.id][2].append(role)

        # Get workspace record to check owner
        from src.api.models.workspace_models.workspace_model import WorkspaceModel
        ws_res = await self.db.execute(
            select(WorkspaceModel.user_id).where(WorkspaceModel.id == workspace_id)
        )
        workspace_owner_id = ws_res.scalar_one_or_none()

        workspace_owner_role = None

        # Self-heal: for any member missing a workspace-scoped role, recover it:
        # 1. If member is workspace owner -> ensure workspace_owner role
        # 2. If member has an accepted invitation -> recover invitation role
        # 3. Otherwise -> auto-assign default viewer role
        healed_rows = []
        should_flush = False

        for member_id, (member, user, roles_list) in member_map.items():
            # Case 1: Member is the workspace owner
            if workspace_owner_id and user.id == workspace_owner_id:
                has_owner_role = any(r.name == "workspace_owner" for r in roles_list)
                if not has_owner_role:
                    if not workspace_owner_role:
                        wo_result = await self.db.execute(
                            select(Role).where(
                                Role.name == "workspace_owner",
                                Role.is_workspace_role == True
                            )
                        )
                        workspace_owner_role = wo_result.scalar_one_or_none()

                    if workspace_owner_role:
                        from datetime import datetime, timezone
                        healed_user_role = UserRole(
                            user_id=user.id,
                            role_id=workspace_owner_role.id,
                            workspace_id=workspace_id,
                            assigned_by_user_id=user.id,
                            is_primary=True,
                            assigned_at=datetime.now(timezone.utc)
                        )
                        self.db.add(healed_user_role)
                        roles_list.append(workspace_owner_role)
                        should_flush = True

                        logger.info(
                            "Self-healed missing workspace_owner role for workspace creator",
                            extra={
                                "user_id": str(user.id),
                                "workspace_id": str(workspace_id),
                                "role_name": workspace_owner_role.name,
                            }
                        )

            # Case 2: Member is not workspace owner, but has no role assigned
            elif not roles_list:
                try:
                    # Look up the accepted invitation for this user+workspace
                    from src.api.models.user_models.invitations import UserInvitations
                    inv_result = await self.db.execute(
                        select(UserInvitations)
                        .where(
                            UserInvitations.email == user.email,
                            UserInvitations.workspace_id == workspace_id,
                            UserInvitations.status == "accepted"
                        )
                        .order_by(UserInvitations.created_at.desc())
                        .limit(1)
                    )
                    invitation = inv_result.scalar_one_or_none()

                    inv_role = None
                    if invitation and getattr(invitation, "role_id", None):
                        role_result = await self.db.execute(
                            select(Role).where(Role.id == invitation.role_id)
                        )
                        inv_role = role_result.scalar_one_or_none()

                    if not inv_role:
                        # Fallback to viewer role if no invitation role found
                        v_res = await self.db.execute(
                            select(Role).where(
                                Role.name == "viewer",
                                Role.is_workspace_role == True
                            )
                        )
                        inv_role = v_res.scalar_one_or_none()

                    if inv_role:
                        from datetime import datetime, timezone
                        healed_user_role = UserRole(
                            user_id=user.id,
                            role_id=inv_role.id,
                            workspace_id=workspace_id,
                            assigned_by_user_id=user.id,
                            is_primary=True,
                            assigned_at=datetime.now(timezone.utc)
                        )
                        self.db.add(healed_user_role)
                        roles_list.append(inv_role)
                        should_flush = True

                        logger.info(
                            "Self-healed missing workspace role",
                            extra={
                                "user_id": str(user.id),
                                "workspace_id": str(workspace_id),
                                "role_name": inv_role.name,
                            }
                        )
                except Exception as e:
                    logger.warning(
                        f"Could not self-heal role for member {user.email}: {e}",
                        extra={"workspace_id": str(workspace_id)}
                    )

            healed_rows.append((member, user, roles_list))

        # Flush any healed rows
        if should_flush:
            try:
                await self.db.flush()
            except Exception as e:
                logger.warning(
                    f"Could not flush self-healed role rows: {e}",
                    extra={"workspace_id": str(workspace_id)}
                )

        logger.debug(f"Retrieved {len(healed_rows)} unique members with user details for workspace {workspace_id}")
        return healed_rows


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
        from src.api.models.user_models.user_roles import UserRole
        from src.utils.rbac_utils import ADMIN_HIERARCHY_THRESHOLD

        query = (
            select(WorkspaceMembers, Users)
            .join(Users, Users.id == WorkspaceMembers.user_id)
            .join(UserRole, and_(
                UserRole.user_id == WorkspaceMembers.user_id,
                UserRole.workspace_id == workspace_id
            ))
            .join(Role, Role.id == UserRole.role_id)
            .where(WorkspaceMembers.workspace_id == workspace_id)
            .where(Role.hierarchy_level >= 60) # 60 is workspace_owner
            .order_by(WorkspaceMembers.joined_at.asc())
        )

        result = await self.db.execute(query)
        rows = result.all()

        logger.debug(f"Retrieved {len(rows)} admin members for workspace {workspace_id}")
        return rows
    
