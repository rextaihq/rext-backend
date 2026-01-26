"""
Admin Invitation Service - Business Logic for Platform Admin Invitations

This service manages invitations for platform-level administrators.
Unlike InvitationService (workspace invitations), this handles super_admin invitations.

Key Differences:
- Platform-level access (not workspace-scoped)
- Only super_admin can create invitations
- Grants admin role upon acceptance
- More restrictive security checks

Responsibilities:
- Create admin invitations (super_admin only)
- Accept admin invitations (existing users)
- Revoke admin invitations
- Validate admin invitation tokens
- Assign admin roles upon acceptance

Security:
- Only super_admin can create admin invitations
- Audit all admin invitation actions
- Rate limit invitation creation
- Require email verification for admin access
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime, timedelta
import secrets
import hashlib

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.models.admin_models.admin_invitations import PlatformAdminInvitations
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    DuplicateResourceException,
    RextValidationException,
    BusinessRuleViolationException,
    RextAuthorizationException
)


class AdminInvitationService:
    """Service for platform admin invitation business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize AdminInvitationService.

        Args:
            db: Async database session
        """
        self.db = db

    def _generate_invitation_token(self, email: str) -> str:
        """
        Generate a secure admin invitation token.

        Args:
            email: Invitee email

        Returns:
            Secure token string
        """
        random_part = secrets.token_urlsafe(48)  # Longer for admin invitations
        combined = f"{email}:{random_part}:{datetime.utcnow().timestamp()}"
        token_hash = hashlib.sha256(combined.encode()).hexdigest()
        return token_hash

    async def _verify_super_admin(self, user_id: UUID) -> None:
        """
        Verify that user is a super_admin.

        Args:
            user_id: User UUID to check

        Raises:
            RextAuthorizationException: If user is not super_admin
        """
        # Check if user has super_admin role
        result = await self.db.execute(
            select(UserRole)
            .join(Role)
            .where(
                and_(
                    UserRole.user_id == user_id,
                    Role.name == 'super_admin',
                    UserRole.workspace_id.is_(None)  # Platform-level role
                )
            )
        )
        super_admin_role = result.scalar_one_or_none()

        if not super_admin_role:
            raise RextAuthorizationException(
                message="Only super admins can create admin invitations",
                required_permission="admin.invite"
            )

    async def _validate_admin_role(self, admin_role: str) -> Role:
        """
        Validate that admin role exists and is an admin role.

        Args:
            admin_role: Role name (e.g., 'super_admin', 'support_admin')

        Returns:
            Role object

        Raises:
            RextValidationException: If role invalid
        """
        # Query role
        result = await self.db.execute(
            select(Role).where(Role.name == admin_role)
        )
        role = result.scalar_one_or_none()

        if not role:
            raise RextValidationException(
                message=f"Admin role '{admin_role}' does not exist",
                field_errors={"admin_role": [f"Role '{admin_role}' not found"]}
            )

        # Verify it's an admin role (you may want to add a flag to Role model)
        valid_admin_roles = ['super_admin', 'support_admin', 'platform_admin']
        if admin_role not in valid_admin_roles:
            raise RextValidationException(
                message=f"'{admin_role}' is not a valid admin role",
                field_errors={"admin_role": [
                    f"Must be one of: {', '.join(valid_admin_roles)}"
                ]}
            )

        return role

    async def create_admin_invitation(
        self,
        email: str,
        admin_role: str,
        invited_by_admin_id: UUID,
        message: Optional[str] = None,
        permissions: Optional[dict] = None,
        expiry_days: int = 7
    ) -> PlatformAdminInvitations:
        """
        Create a new admin invitation.

        Business Rules:
        - Only super_admin can create admin invitations
        - Admin role must exist and be valid
        - Email must not have existing pending invitation
        - User with email must not already be an admin
        - Expiry days must be between 1-30

        Args:
            email: Email to invite
            admin_role: Admin role name (e.g., 'super_admin')
            invited_by_admin_id: Super admin creating invitation
            message: Optional personalized message
            permissions: Optional additional permissions (JSONB)
            expiry_days: Days until expiration (1-30)

        Returns:
            Created PlatformAdminInvitations object

        Raises:
            RextAuthorizationException: If inviter is not super_admin
            RextValidationException: If role invalid or expiry invalid
            DuplicateResourceException: If pending invitation exists
            BusinessRuleViolationException: If user already admin
        """
        # Verify inviter is super_admin
        await self._verify_super_admin(invited_by_admin_id)

        # Validate expiry_days
        if not 1 <= expiry_days <= 30:
            raise RextValidationException(
                message="Expiry days must be between 1 and 30",
                field_errors={"expiry_days": ["Must be between 1 and 30 days"]}
            )

        # Normalize email
        email = email.lower().strip()

        # Validate admin role
        await self._validate_admin_role(admin_role)

        # Check for existing pending invitation
        result = await self.db.execute(
            select(PlatformAdminInvitations).where(
                and_(
                    PlatformAdminInvitations.email == email,
                    PlatformAdminInvitations.status == 'pending'
                )
            )
        )
        existing_invitation = result.scalar_one_or_none()

        if existing_invitation:
            raise DuplicateResourceException(
                resource_type="AdminInvitation",
                identifier=f"email={email}",
                message=f"Pending admin invitation already exists for {email}"
            )

        # Check if user with email already has admin role
        result = await self.db.execute(
            select(Users)
            .join(UserRole)
            .join(Role)
            .where(
                and_(
                    Users.email == email,
                    Role.name.in_(['super_admin', 'support_admin', 'platform_admin']),
                    UserRole.workspace_id.is_(None)  # Platform-level
                )
            )
        )
        existing_admin = result.scalar_one_or_none()

        if existing_admin:
            raise BusinessRuleViolationException(
                message=f"User {email} is already a platform admin",
                rule_name="user_already_admin"
            )

        # Generate token and expiry
        token = self._generate_invitation_token(email)
        expires_at = datetime.utcnow() + timedelta(days=expiry_days)

        # Create invitation
        invitation = PlatformAdminInvitations(
            email=email,
            admin_role=admin_role,
            invited_by_admin_id=invited_by_admin_id,
            invitation_token=token,
            status="pending",
            message=message,
            permissions=permissions,
            expires_at=expires_at
        )

        self.db.add(invitation)
        logger.info(
            f"Admin invitation created: {email} for role {admin_role} "
            f"by admin {invited_by_admin_id}"
        )

        return invitation

    async def get_invitation_by_token(
        self,
        token: str
    ) -> PlatformAdminInvitations:
        """
        Get admin invitation by token.

        Args:
            token: Invitation token

        Returns:
            PlatformAdminInvitations object

        Raises:
            ResourceNotFoundException: If invitation not found
        """
        result = await self.db.execute(
            select(PlatformAdminInvitations)
            .options(selectinload(PlatformAdminInvitations.invited_by))
            .where(PlatformAdminInvitations.invitation_token == token)
        )
        invitation = result.scalar_one_or_none()

        if not invitation:
            raise ResourceNotFoundException(
                resource_type="AdminInvitation",
                resource_id=token
            )

        return invitation

    async def get_invitation_by_id(
        self,
        invitation_id: UUID
    ) -> PlatformAdminInvitations:
        """
        Get admin invitation by ID.

        Args:
            invitation_id: Invitation UUID

        Returns:
            PlatformAdminInvitations object

        Raises:
            ResourceNotFoundException: If invitation not found
        """
        result = await self.db.execute(
            select(PlatformAdminInvitations)
            .options(selectinload(PlatformAdminInvitations.invited_by))
            .where(PlatformAdminInvitations.id == invitation_id)
        )
        invitation = result.scalar_one_or_none()

        if not invitation:
            raise ResourceNotFoundException(
                resource_type="AdminInvitation",
                resource_id=str(invitation_id)
            )

        return invitation

    async def get_all_invitations(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[PlatformAdminInvitations]:
        """
        Get all admin invitations (super_admin only).

        Args:
            status: Optional status filter (pending/accepted/revoked/expired)
            limit: Maximum results
            offset: Results to skip

        Returns:
            List of PlatformAdminInvitations
        """
        query = select(PlatformAdminInvitations).options(
            selectinload(PlatformAdminInvitations.invited_by),
            selectinload(PlatformAdminInvitations.accepted_by)
        )

        if status:
            query = query.where(PlatformAdminInvitations.status == status)

        query = query.order_by(
            PlatformAdminInvitations.created_at.desc()
        ).limit(limit).offset(offset)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def accept_admin_invitation(
        self,
        token: str,
        user_id: UUID
    ) -> PlatformAdminInvitations:
        """
        Accept admin invitation and assign admin role.

        Business Rules:
        - User must exist
        - Invitation must be pending and not expired
        - Email must match user's email
        - User must not already have admin role

        Args:
            token: Invitation token
            user_id: User UUID accepting invitation

        Returns:
            Updated PlatformAdminInvitations object

        Raises:
            ResourceNotFoundException: If invitation or user not found
            BusinessRuleViolationException: If invitation invalid or expired
        """
        # Get invitation
        invitation = await self.get_invitation_by_token(token)

        # Check status
        if invitation.status != 'pending':
            raise BusinessRuleViolationException(
                message=f"Invitation has already been {invitation.status}",
                rule_name="invitation_already_processed"
            )

        # Check expiry
        if invitation.is_expired():
            invitation.status = 'expired'
            raise BusinessRuleViolationException(
                message="Invitation has expired",
                rule_name="invitation_expired"
            )

        # Get user
        result = await self.db.execute(
            select(Users).where(Users.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=str(user_id)
            )

        # Verify email match (security)
        if user.email.lower() != invitation.email.lower():
            raise BusinessRuleViolationException(
                message=f"This invitation is for {invitation.email}",
                rule_name="email_mismatch"
            )

        # Get admin role
        result = await self.db.execute(
            select(Role).where(Role.name == invitation.admin_role)
        )
        admin_role = result.scalar_one_or_none()

        if not admin_role:
            raise ResourceNotFoundException(
                resource_type="Role",
                resource_id=invitation.admin_role
            )

        # Check if user already has this admin role
        result = await self.db.execute(
            select(UserRole).where(
                and_(
                    UserRole.user_id == user_id,
                    UserRole.role_id == admin_role.id,
                    UserRole.workspace_id.is_(None)  # Platform-level
                )
            )
        )
        existing_role = result.scalar_one_or_none()

        if existing_role:
            raise BusinessRuleViolationException(
                message=f"User already has {invitation.admin_role} role",
                rule_name="user_already_has_admin_role"
            )

        # Assign admin role
        user_role = UserRole(
            user_id=user_id,
            role_id=admin_role.id,
            workspace_id=None,  # Platform-level
            assigned_by_user_id=invitation.invited_by_admin_id,
            is_primary=True,
            assigned_at=datetime.utcnow()
        )
        self.db.add(user_role)

        # Update invitation
        invitation.status = 'accepted'
        invitation.accepted_at = datetime.utcnow()
        invitation.accepted_by_user_id = user_id

        logger.info(
            f"Admin invitation accepted: {user.email} now has {invitation.admin_role} role"
        )

        return invitation

    async def revoke_admin_invitation(
        self,
        invitation_id: UUID,
        revoked_by_admin_id: UUID,
        reason: Optional[str] = None
    ) -> PlatformAdminInvitations:
        """
        Revoke an admin invitation.

        Args:
            invitation_id: Invitation UUID
            revoked_by_admin_id: Admin revoking the invitation
            reason: Optional reason for revoking

        Returns:
            Updated PlatformAdminInvitations object

        Raises:
            RextAuthorizationException: If revoker not super_admin
            ResourceNotFoundException: If invitation not found
            BusinessRuleViolationException: If invitation already processed
        """
        # Verify revoker is super_admin
        await self._verify_super_admin(revoked_by_admin_id)

        # Get invitation
        invitation = await self.get_invitation_by_id(invitation_id)

        # Check if already processed
        if invitation.status != 'pending':
            raise BusinessRuleViolationException(
                message=f"Cannot revoke: invitation is {invitation.status}",
                rule_name="invitation_already_processed"
            )

        # Revoke invitation
        invitation.status = 'revoked'
        invitation.revoked_at = datetime.utcnow()
        invitation.revoked_by_admin_id = revoked_by_admin_id
        invitation.revoked_reason = reason

        logger.info(
            f"Admin invitation revoked: {invitation.email} by admin {revoked_by_admin_id}"
        )

        return invitation

    async def decline_admin_invitation(
        self,
        token: str,
        reason: Optional[str] = None
    ) -> PlatformAdminInvitations:
        """
        Decline an admin invitation.

        Args:
            token: Invitation token
            reason: Optional reason for declining

        Returns:
            Updated PlatformAdminInvitations object

        Raises:
            ResourceNotFoundException: If invitation not found
            BusinessRuleViolationException: If invitation already processed
        """
        # Get invitation
        invitation = await self.get_invitation_by_token(token)

        # Check if already processed
        if invitation.status != 'pending':
            raise BusinessRuleViolationException(
                message=f"Cannot decline: invitation is {invitation.status}",
                rule_name="invitation_already_processed"
            )

        # Decline invitation
        invitation.status = 'declined'
        invitation.declined_at = datetime.utcnow()
        invitation.declined_reason = reason

        logger.info(
            f"Admin invitation declined: {invitation.email}"
        )

        return invitation

    async def resend_admin_invitation(
        self,
        invitation_id: UUID,
        resent_by_admin_id: UUID,
        expiry_days: int = 7
    ) -> PlatformAdminInvitations:
        """
        Resend (refresh) an admin invitation with new token and expiry.

        Args:
            invitation_id: Invitation UUID
            resent_by_admin_id: Admin resending the invitation
            expiry_days: New expiry days (1-30)

        Returns:
            Updated PlatformAdminInvitations object

        Raises:
            RextAuthorizationException: If resender not super_admin
            ResourceNotFoundException: If invitation not found
            RextValidationException: If expiry invalid
        """
        # Verify resender is super_admin
        await self._verify_super_admin(resent_by_admin_id)

        # Validate expiry
        if not 1 <= expiry_days <= 30:
            raise RextValidationException(
                message="Expiry days must be between 1 and 30",
                field_errors={"expiry_days": ["Must be between 1 and 30 days"]}
            )

        # Get invitation
        invitation = await self.get_invitation_by_id(invitation_id)

        # Can only resend pending or expired invitations
        if invitation.status not in ['pending', 'expired']:
            raise BusinessRuleViolationException(
                message=f"Cannot resend: invitation is {invitation.status}",
                rule_name="invitation_cannot_be_resent"
            )

        # Generate new token and expiry
        invitation.invitation_token = self._generate_invitation_token(invitation.email)
        invitation.expires_at = datetime.utcnow() + timedelta(days=expiry_days)
        invitation.status = 'pending'

        logger.info(
            f"Admin invitation resent: {invitation.email} by admin {resent_by_admin_id}"
        )

        return invitation
