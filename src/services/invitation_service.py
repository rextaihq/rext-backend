"""
Invitation Service - Business Logic for User Invitations

This service encapsulates all business logic related to workspace invitations,
including creating, accepting, revoking, and managing invitation lifecycle.

Responsibilities:
- Invitation CRUD operations
- Token generation and validation
- Expiry management
- Duplicate checking
- Status transitions (pending -> accepted/revoked/expired)

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Send emails (that's background tasks)
- Commit transactions (that's decorators/routes)
- Authentication/authorization (that's decorators)
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone, timedelta,timezone
import secrets

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.utils.invitation_utils import validate_expiry_days
from src.utils.invitation_utils import normalize_email
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.user_models.roles import Role
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    DuplicateResourceException,
    RextValidationException,
    BusinessRuleViolationException
)


class InvitationService:
    """Service for invitation business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize InvitationService.

        Args:
            db: Async database session
        """
        self.db = db

    def _generate_invitation_token(self, email: str, workspace_id: UUID) -> str:
        """
        Generate a secure invitation token.

        Args:
            email: Invitee email (unused — kept for API compatibility)
            workspace_id: Workspace UUID (unused — kept for API compatibility)

        Returns:
            Secure token string
        """
        from src.utils.invitation_utils import generate_invitation_token
        return generate_invitation_token(nbytes=32)

    async def create_invitation(
        self,
        email: str,
        workspace_id: UUID,
        role_id: UUID,
        invited_by_user_id: UUID,
        expiry_days: int = 7
    ) -> UserInvitations:
        """
        Create a new invitation.

        Business Rules:
        - Workspace must exist
        - Role must exist
        - Inviter must exist
        - No duplicate active invitations (email + workspace)
        - User must not already be a member
        - Expiry days must be between 1-30

        Args:
            email: Email to invite
            workspace_id: Workspace UUID
            role_id: Role UUID to assign
            invited_by_user_id: User UUID who is inviting
            expiry_days: Days until expiration (1-30)

        Returns:
            Created UserInvitations object

        Raises:
            ResourceNotFoundException: If workspace/role/inviter not found
            DuplicateResourceException: If active invitation exists
            BusinessRuleViolationException: If user already a member
            RextValidationException: If expiry_days invalid
        """
        # Validate expiry_days
        validate_expiry_days(expiry_days)

        # Normalize email
        email = normalize_email(email)

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

        # Verify role exists
        result = await self.db.execute(
            select(Role).where(Role.id == role_id)
        )
        role = result.scalar_one_or_none()
        if not role:
            raise ResourceNotFoundException(
                resource_type="Role",
                resource_id=str(role_id)
            )

        # Verify inviter exists
        result = await self.db.execute(
            select(Users).where(Users.id == invited_by_user_id)
        )
        inviter = result.scalar_one_or_none()
        if not inviter:
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=str(invited_by_user_id)
            )

        # Check for existing active invitation
        result = await self.db.execute(
            select(UserInvitations).where(
                and_(
                    UserInvitations.email == email,
                    UserInvitations.workspace_id == workspace_id
                )
            )
        )
        existing_invitation = result.scalar_one_or_none()
        if existing_invitation:
            # check the invitation status if status is revoked or expired, allow new invitation creation
            if existing_invitation.status in ("revoked", "expired"):
                # Generate token and create invitation
                token = self._generate_invitation_token(email, workspace_id)
                expires_at = datetime.now(timezone.utc) + timedelta(days=expiry_days)
                
                # update the existing invitation
                existing_invitation.invitation_token = token
                existing_invitation.role_id = role_id
                existing_invitation.invited_by_user_id = invited_by_user_id
                existing_invitation.status = "pending"
                existing_invitation.expires_at = expires_at
                await self.db.flush()
                return existing_invitation
            elif existing_invitation.status == "pending":
                raise DuplicateResourceException(
                    resource_type="Invitation",
                    conflicting_field="email",
                    conflicting_value=email,
                    context={"workspace_id": str(workspace_id)}
                )

        # Check if user already a member
        result = await self.db.execute(
            select(Users).where(Users.email == email)
        )
        existing_user = result.scalar_one_or_none()
        if existing_user:
            result = await self.db.execute(
                select(WorkspaceMembers).where(
                    and_(
                        WorkspaceMembers.user_id == existing_user.id,
                        WorkspaceMembers.workspace_id == workspace_id
                    )
                )
            )
            existing_membership = result.scalar_one_or_none()
            if existing_membership:
                raise BusinessRuleViolationException(
                    message=f"User with email {email} is already a member of this workspace",
                    rule_name="no_duplicate_members"
                )

        # Generate token and create invitation
        token = self._generate_invitation_token(email, workspace_id)
        expires_at = datetime.now(timezone.utc) + timedelta(days=expiry_days)

        invitation = UserInvitations(
            email=email,
            workspace_id=workspace_id,
            role_id=role_id,
            invited_by_user_id=invited_by_user_id,
            invitation_token=token,
            status="pending",
            expires_at=expires_at
        )

        self.db.add(invitation)
        return invitation

    async def get_invitation_by_id(
        self,
        invitation_id: UUID
    ) -> UserInvitations:
        """
        Get invitation by ID.

        Args:
            invitation_id: Invitation UUID

        Returns:
            UserInvitations object

        Raises:
            ResourceNotFoundException: If invitation not found
        """
        result = await self.db.execute(
            select(UserInvitations).where(UserInvitations.id == invitation_id)
        )
        invitation = result.scalar_one_or_none()
        if not invitation:
            raise ResourceNotFoundException(
                resource_type="Invitation",
                resource_id=str(invitation_id)
            )
        return invitation

    async def get_invitation_by_token(
        self,
        token: str
    ) -> UserInvitations:
        """
        Get invitation by token.

        Args:
            token: Invitation token

        Returns:
            UserInvitations object

        Raises:
            ResourceNotFoundException: If invitation not found
        """
        result = await self.db.execute(
            select(UserInvitations).where(
                UserInvitations.invitation_token == token
            )
        )
        invitation = result.scalar_one_or_none()
        if not invitation:
            raise ResourceNotFoundException(
                resource_type="Invitation",
                resource_id=token
            )
        return invitation

    async def get_invitations_by_email(
        self,
        email: str,
        status: Optional[str] = None
    ) -> List[UserInvitations]:
        """
        Get all invitations for a specific email address.

        This is used during login to auto-accept pending invitations
        for existing users.

        Args:
            email: Email address to search for
            status: Optional status filter (pending/accepted/revoked/expired)

        Returns:
            List of UserInvitations objects
        """
        # Normalize email for case-insensitive comparison
        email = normalize_email(email)

        query = select(UserInvitations).where(
            UserInvitations.email == email
        )

        if status:
            query = query.where(UserInvitations.status == status)

        query = query.order_by(UserInvitations.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_workspace_invitations(
        self,
        workspace_id: UUID,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[UserInvitations]:
        """
        Get invitations for a workspace.

        Args:
            workspace_id: Workspace UUID
            status: Optional status filter (pending/accepted/revoked/expired)
            limit: Maximum results
            offset: Results to skip

        Returns:
            List of UserInvitations
        """
        query = select(UserInvitations).where(
            UserInvitations.workspace_id == workspace_id
        )

        if status:
            query = query.where(UserInvitations.status == status)

        query = query.order_by(
            UserInvitations.created_at.desc()
        ).limit(limit).offset(offset)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def accept_invitation(
        self,
        invitation_id: UUID,
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Accept an invitation and create workspace membership.

        Business Rules:
        - Invitation must be pending
        - Invitation must not be expired
        - User accepting must match invitation email
        - Creates WorkspaceMember record

        Args:
            invitation_id: Invitation UUID
            user_id: User UUID accepting

        Returns:
            Dict with invitation and membership details

        Raises:
            ResourceNotFoundException: If invitation not found
            BusinessRuleViolationException: If invitation expired/not pending
        """
        invitation = await self.get_invitation_by_id(invitation_id)

        # Check status
        if invitation.status != "pending":
            raise BusinessRuleViolationException(
                message=f"Invitation is {invitation.status}, cannot accept",
                rule_name="invitation_must_be_pending"
            )

        # Check expiry
        if invitation.expires_at < datetime.now(timezone.utc):
            invitation.status = "expired"
            await self.db.flush()
            raise BusinessRuleViolationException(
                message="Invitation has expired",
                rule_name="invitation_not_expired"
            )

        # Verify user email matches invitation
        result = await self.db.execute(
            select(Users).where(Users.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=str(user_id)
            )

        if normalize_email(user.email) != normalize_email(invitation.email):
            raise BusinessRuleViolationException(
                message="User email does not match invitation email",
                rule_name="email_must_match"
            )

        # Check if already a member
        result = await self.db.execute(
            select(WorkspaceMembers).where(
                and_(
                    WorkspaceMembers.user_id == user_id,
                    WorkspaceMembers.workspace_id == invitation.workspace_id
                )
            )
        )
        existing_member = result.scalar_one_or_none()
        if existing_member:
            # Update invitation status even if already member
            invitation.status = "accepted"
            await self.db.flush()
            raise BusinessRuleViolationException(
                message="User is already a member of this workspace",
                rule_name="no_duplicate_members"
            )

        # Create workspace member
        member = WorkspaceMembers(
            workspace_id=invitation.workspace_id,
            user_id=user_id,
            invitation_id=invitation.id,
            status="active",
            joined_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc)
        )
        self.db.add(member)

        # Create user role assignment from invitation
        from src.api.models.user_models.user_roles import UserRole
        user_role = UserRole(
            user_id=user_id,
            role_id=invitation.role_id,
            workspace_id=invitation.workspace_id,
            assigned_by_user_id=invitation.invited_by_user_id,
            is_primary=True
        )
        self.db.add(user_role)

        # Update invitation status
        invitation.status = "accepted"
        await self.db.flush()
        await self.db.refresh(member)

        logger.info(
            f"Invitation accepted: {invitation.email}",
            extra={
                "invitation_id": str(invitation.id),
                "user_id": str(user_id),
                "workspace_id": str(invitation.workspace_id)
            }
        )

        return {
            "invitation_id": str(invitation.id),
            "membership_id": str(member.id),
            "workspace_id": str(invitation.workspace_id),
            "user_id": str(user_id)
        }

    async def revoke_invitation(
        self,
        invitation_id: UUID,
        revoked_by_user_id: UUID
    ) -> UserInvitations:
        """
        Revoke an invitation.

        Args:
            invitation_id: Invitation UUID
            revoked_by_user_id: User UUID revoking (for audit)

        Returns:
            Updated UserInvitations object

        Raises:
            ResourceNotFoundException: If invitation not found
            BusinessRuleViolationException: If already accepted/revoked
        """
        invitation = await self.get_invitation_by_id(invitation_id)

        if invitation.status != "pending":
            raise BusinessRuleViolationException(
                message=f"Cannot revoke invitation with status: {invitation.status}",
                rule_name="can_only_revoke_pending"
            )

        invitation.status = "revoked"

        logger.info(
            f"Invitation revoked: {invitation.email}",
            extra={
                "invitation_id": str(invitation.id),
                "revoked_by": str(revoked_by_user_id)
            }
        )

        return invitation

    async def expire_old_invitations(
        self,
        batch_size: int = 100
    ) -> int:
        """
        Expire invitations past their expiry date.
        Utility method for batch processing.

        Args:
            batch_size: Maximum invitations to expire in one call

        Returns:
            Count of expired invitations
        """
        result = await self.db.execute(
            select(UserInvitations).where(
                and_(
                    UserInvitations.status == "pending",
                    UserInvitations.expires_at < datetime.now(timezone.utc)
                )
            ).limit(batch_size)
        )
        expired_invitations = result.scalars().all()

        count = 0
        for invitation in expired_invitations:
            invitation.status = "expired"
            count += 1

        if count > 0:
            await self.db.flush()
            logger.info(f"Expired {count} old invitations")

        return count

    async def resend_invitation(
        self,
        invitation_id: UUID,
        extend_days: int = 7
    ) -> UserInvitations:
        """
        Resend a workspace invitation by generating a new token.

        The old token is overwritten in the database, which means any
        previously sent email links will no longer work. This is by design —
        only the most recent token is valid at any time.

        Args:
            invitation_id: UUID of the invitation to resend
            extend_days: Days to extend expiry

        Returns:
            Updated UserInvitations object

        Raises:
            ResourceNotFoundException: If invitation not found
            BusinessRuleViolationException: If invitation not pending
        """
        invitation = await self.get_invitation_by_id(invitation_id)

        if invitation.status != "pending":
            raise BusinessRuleViolationException(
                message=f"Cannot resend invitation with status: {invitation.status}",
                rule_name="can_only_resend_pending"
            )

        # Store old token hash for audit trail (do not log the full token)
        old_token_prefix = invitation.invitation_token[:8] if invitation.invitation_token else "none"
        old_expires_at = invitation.expires_at

        # Generate new token — this overwrites the old token in the database,
        # effectively invalidating any previously sent email links
        invitation.invitation_token = self._generate_invitation_token(
            invitation.email,
            invitation.workspace_id
        )
        invitation.expires_at = datetime.now(timezone.utc) + timedelta(days=extend_days)

        logger.info(
            "Invitation token rotated on resend",
            extra={
                "invitation_id": str(invitation.id),
                "email": invitation.email,
                "old_token_prefix": old_token_prefix,
                "new_token_prefix": invitation.invitation_token[:8],
                "old_expires_at": old_expires_at.isoformat() if old_expires_at else None,
                "new_expires_at": invitation.expires_at.isoformat(),
                "event_type": "token_rotation",
            }
        )

        return invitation

    # Remove invitation if it exists
    async def remove_invitation_if_exists(
        self,
        workspace_id: UUID,
        email: str
    ) -> None:
        """
        Remove an invitation if it exists for the given email and workspace.

        Args:
            workspace_id: Workspace UUID
            email: Invitee email
        Returns:
            None
        """
        email = normalize_email(email)
        result = await self.db.execute(
            select(UserInvitations).where(
                and_(
                    UserInvitations.email == email,
                    UserInvitations.workspace_id == workspace_id
                )
            )
        )
        invitation = result.scalar_one_or_none()
        if invitation:
            await self.db.delete(invitation)
            logger.info(
                f"Invitation removed: {email}",
                extra={
                    "workspace_id": str(workspace_id),
                    "invitation_id": str(invitation.id)
                }
            )