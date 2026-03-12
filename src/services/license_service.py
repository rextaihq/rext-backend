"""
License Management Service

Handles license key validation, activation, deactivation, and management
for one-time purchase products.

Business Rules:
- License keys can have activation limits (or unlimited)
- Each activation is tied to a unique instance_id (device, domain, etc.)
- Users can deactivate instances to free up activation slots
- Admins can revoke licenses
- Expired licenses cannot be activated
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.exc import IntegrityError

from src.api.models.subscription_models.licenses import License, LicenseStatus
from src.api.models.subscription_models.license_activations import LicenseActivation
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
    DuplicateResourceException,
    RextAuthorizationException as UnauthorizedException
)


class LicenseService:
    """Service for managing software licenses and activations."""

    def __init__(self, db: AsyncSession):
        """
        Initialize license service.

        Args:
            db: SQLAlchemy async session
        """
        self.db = db

    async def validate_license_key(self, license_key: str) -> License:
        """
        Validate a license key and return the license if valid.

        Args:
            license_key: The license key to validate

        Returns:
            License object if valid

        Raises:
            ResourceNotFoundException: If license not found
            RextValidationException: If license is invalid/expired/disabled
        """
        # Find license by key
        stmt = select(License).where(License.license_key == license_key)
        result = await self.db.execute(stmt)
        license_obj = result.scalar_one_or_none()

        if not license_obj:
            raise ResourceNotFoundException(
                resource_type="License",
                resource_id=license_key,
                message="License key not found"
            )

        # Check if license is disabled
        if license_obj.status == LicenseStatus.DISABLED:
            raise RextValidationException(
                message="This license has been disabled",
                field_errors={"license_key": ["License is disabled"]}
            )

        if license_obj.status == LicenseStatus.REVOKED:
            raise RextValidationException(
                message="This license has been revoked",
                field_errors={"license_key": ["License has been revoked by an administrator"]}
            )

        # Check if license is expired
        if license_obj.is_expired:
            raise RextValidationException(
                message="This license has expired",
                field_errors={"license_key": ["License expired"]}
            )

        logger.info(f"Validated license {license_key[:12]}...")
        return license_obj

    async def activate_license(
        self,
        user_id: UUID,
        license_key: str,
        instance_id: str,
        instance_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> LicenseActivation:
        """
        Activate a license for a specific device/instance.

        Args:
            user_id: User UUID
            license_key: License key to activate
            instance_id: Unique identifier for the instance (device ID, domain, etc.)
            instance_name: Human-readable name for the instance
            metadata: Additional metadata (IP, user agent, OS, etc.)

        Returns:
            LicenseActivation object

        Raises:
            ResourceNotFoundException: If license not found
            RextValidationException: If license invalid or activation limit exceeded
            DuplicateResourceException: If instance already activated
        """
        # Validate license
        license_obj = await self.validate_license_key(license_key)

        # Check if user owns this license (or if license is not yet claimed)
        # Note: license.user_id might be a UUID object, user_id is a string, so compare as strings
        if license_obj.user_id and str(license_obj.user_id) != str(user_id):
            raise UnauthorizedException(
                message="You do not own this license",
                required_permission="license.activate"
            )

        # If license isn't claimed yet, claim it
        if not license_obj.user_id:
            license_obj.user_id = user_id
            license_obj.activated_at = datetime.now(timezone.utc)
            await self.db.flush()

        # Check if this instance is already activated
        existing_activation = await self._get_activation_by_instance(
            license_obj.id,
            instance_id
        )

        if existing_activation and existing_activation.is_active:
            raise DuplicateResourceException(
                message="This instance is already activated",
                resource_type="LicenseActivation",
                conflicting_field="instance_id",
                conflicting_value=instance_id
            )

        # Check activation limits
        if not license_obj.can_activate:
            active_count = await self._count_active_activations(license_obj.id)
            raise RextValidationException(
                message=f"Activation limit reached ({license_obj.activation_limit} max)",
                field_errors={
                    "license_key": [
                        f"Maximum activations ({license_obj.activation_limit}) reached. "
                        f"Currently {active_count} active. Deactivate an instance first."
                    ]
                }
            )

        # Create or reactivate activation
        if existing_activation:
            # Reactivate previously deactivated instance
            existing_activation.is_active = True
            existing_activation.activated_at = datetime.now(timezone.utc)
            existing_activation.deactivated_at = None
            if instance_name:
                existing_activation.instance_name = instance_name
            if metadata:
                existing_activation.activation_metadata = metadata
            activation = existing_activation
        else:
            # Create new activation
            activation = LicenseActivation(
                license_id=license_obj.id,
                instance_id=instance_id,
                instance_name=instance_name,
                is_active=True,
                activated_at=datetime.now(timezone.utc),
                activation_metadata=metadata or {}
            )
            self.db.add(activation)

        # Increment activation count
        license_obj.activation_count = await self._count_active_activations(license_obj.id) + 1

        # Update license status if this is first activation
        if license_obj.status == LicenseStatus.INACTIVE:
            license_obj.status = LicenseStatus.ACTIVE

        await self.db.flush()

        logger.info(
            f"Activated license {license_key[:12]}... for instance {instance_id}",
            extra={
                "license_id": str(license_obj.id),
                "user_id": str(user_id),
                "instance_id": instance_id
            }
        )

        return activation

    async def deactivate_license(
        self,
        user_id: UUID,
        license_id: UUID,
        instance_id: str
    ) -> LicenseActivation:
        """
        Deactivate a license activation for a specific instance.

        Args:
            user_id: User UUID
            license_id: License UUID
            instance_id: Instance identifier to deactivate

        Returns:
            Deactivated LicenseActivation object

        Raises:
            ResourceNotFoundException: If license or activation not found
            UnauthorizedException: If user doesn't own the license
        """
        # Get license
        license_obj = await self._get_license_or_404(license_id)

        # Check ownership
        # Note: license.user_id might be a UUID object, user_id is a string, so compare as strings
        if str(license_obj.user_id) != str(user_id):
            raise UnauthorizedException(
                message="You do not own this license",
                required_permission="license.deactivate"
            )

        # Get activation
        activation = await self._get_activation_by_instance(license_id, instance_id)

        if not activation:
            raise ResourceNotFoundException(
                resource_type="LicenseActivation",
                resource_id=instance_id,
                message=f"Activation not found for instance {instance_id}"
            )

        if not activation.is_active:
            raise RextValidationException(
                message="This activation is already inactive",
                field_errors={"instance_id": ["Activation already deactivated"]}
            )

        # Deactivate
        activation.deactivate()

        # Update license activation count
        license_obj.activation_count = await self._count_active_activations(license_id)

        await self.db.flush()

        logger.info(
            f"Deactivated license {license_obj.license_key[:12]}... for instance {instance_id}",
            extra={
                "license_id": str(license_id),
                "user_id": str(user_id),
                "instance_id": instance_id
            }
        )

        return activation

    async def get_user_licenses(self, user_id: UUID) -> List[License]:
        """
        Get all licenses owned by a user.

        Args:
            user_id: User UUID

        Returns:
            List of License objects
        """
        stmt = select(License).where(License.user_id == user_id)
        result = await self.db.execute(stmt)
        licenses = result.scalars().all()

        return list(licenses)

    async def get_license_by_id(self, license_id: UUID) -> Optional[License]:
        """
        Get a license by ID.

        Args:
            license_id: License UUID

        Returns:
            License object or None
        """
        stmt = select(License).where(License.id == license_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_license_activations(
        self,
        user_id: UUID,
        license_id: UUID
    ) -> List[LicenseActivation]:
        """
        Get all activations for a license.

        Args:
            user_id: User UUID (for ownership check)
            license_id: License UUID

        Returns:
            List of LicenseActivation objects

        Raises:
            UnauthorizedException: If user doesn't own the license
        """
        # Get license and check ownership
        license_obj = await self._get_license_or_404(license_id)

        # Note: license.user_id might be a UUID object, user_id is a string, so compare as strings
        if str(license_obj.user_id) != str(user_id):
            raise UnauthorizedException(
                message="You do not own this license",
                required_permission="license.view"
            )

        # Get activations
        stmt = select(LicenseActivation).where(
            LicenseActivation.license_id == license_id
        ).order_by(LicenseActivation.activated_at.desc())

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def revoke_license(
        self,
        license_id: UUID,
        revoked_by_user_id: UUID
    ) -> License:
        """
        Revoke a license (admin only).

        This disables the license and deactivates all active instances.

        Args:
            license_id: License UUID to revoke
            revoked_by_user_id: UUID of admin user performing revocation

        Returns:
            Revoked License object

        Raises:
            ResourceNotFoundException: If license not found
        """
        # Get license
        license_obj = await self._get_license_or_404(license_id)

        # Deactivate all active instances
        stmt = select(LicenseActivation).where(
            and_(
                LicenseActivation.license_id == license_id,
                LicenseActivation.is_active.is_(True)
            )
        )
        result = await self.db.execute(stmt)
        active_activations = result.scalars().all()

        for activation in active_activations:
            activation.deactivate()

        # Update license status
        license_obj.status = LicenseStatus.REVOKED
        license_obj.activation_count = 0

        await self.db.flush()

        logger.warning(
            f"License {license_obj.license_key[:12]}... revoked by user {revoked_by_user_id}",
            extra={
                "license_id": str(license_id),
                "revoked_by": str(revoked_by_user_id),
                "deactivated_count": len(active_activations)
            }
        )

        return license_obj

    # Helper methods

    async def _get_license_or_404(self, license_id: UUID) -> License:
        """Get license by ID or raise 404."""
        stmt = select(License).where(License.id == license_id)
        result = await self.db.execute(stmt)
        license_obj = result.scalar_one_or_none()

        if not license_obj:
            raise ResourceNotFoundException(
                resource_type="License",
                resource_id=str(license_id),
                message="License not found"
            )

        return license_obj

    async def _get_activation_by_instance(
        self,
        license_id: UUID,
        instance_id: str
    ) -> Optional[LicenseActivation]:
        """Get activation by license and instance ID."""
        stmt = select(LicenseActivation).where(
            and_(
                LicenseActivation.license_id == license_id,
                LicenseActivation.instance_id == instance_id
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _count_active_activations(self, license_id: UUID) -> int:
        """Count active activations for a license."""
        stmt = select(func.count(LicenseActivation.id)).where(
            and_(
                LicenseActivation.license_id == license_id,
                LicenseActivation.is_active.is_(True)
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0
