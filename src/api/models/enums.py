import enum


class InvitationStatus(str, enum.Enum):
    """Status values for workspace and admin invitations.

    Follows the same (str, enum.Enum) pattern used by LicenseStatus,
    RefundStatus, and SubscriptionStatus in the subscription models.
    """
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"
    DECLINED = "declined"

class RecoveryRequestStatus(str, enum.Enum):
    """Status values for admin-reviewed account recovery requests."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# Convenience frozenset for .in_() queries and membership checks
VALID_RECOVERY_REQUEST_STATUSES: frozenset[str] = frozenset(
    s.value for s in RecoveryRequestStatus
)


class AdminRole(str, enum.Enum):
    """Valid platform-level admin roles.

    Used by AdminInvitationService for role validation and
    admin duplicate detection queries.
    """
    SUPER_ADMIN = "super_admin"
    SUPPORT_ADMIN = "support_admin"
    PLATFORM_ADMIN = "platform_admin"


# Convenience frozenset for .in_() queries and membership checks
VALID_ADMIN_ROLES: frozenset[str] = frozenset(role.value for role in AdminRole)
