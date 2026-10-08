import enum


class InvitationStatus(str, enum.Enum):
    """Status values for workspace and admin invitations.

    Follows the same (str, enum.Enum) pattern used by RefundStatus and
    SubscriptionStatus in the subscription models.
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
VALID_RECOVERY_REQUEST_STATUSES: frozenset[str] = frozenset(s.value for s in RecoveryRequestStatus)


class AdminRole(str, enum.Enum):
    """The platform roles an admin invitation can give, by the names the roles table
    holds (scripts/seeds/seed_permissions.py): each is held outside any workspace.

    Used by AdminInvitationService for role validation and
    admin duplicate detection queries.
    """

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    SUPPORT = "support"


# Convenience frozenset for .in_() queries and membership checks
VALID_ADMIN_ROLES: frozenset[str] = frozenset(role.value for role in AdminRole)
