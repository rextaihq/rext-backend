"""Create platform admin invitations table

Revision ID: admin001
Revises: seed008
Create Date: 2025-10-23

This migration creates the platform_admin_invitations table for managing
invitations to platform-level administrators (super_admin, support_admin, etc.).

Key Features:
- Separate from workspace invitations for security
- Tracks invitation lifecycle (pending → accepted/declined/revoked/expired)
- Unique email constraint (one admin invitation per email)
- Comprehensive audit trail (who invited, who accepted, when, etc.)
- Optional permissions beyond role
- Decline and revoke tracking with reasons

Security:
- Only super_admin can create these invitations
- Tokens must be secure and single-use
- Audit all actions in audit_logs table
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = 'admin001'
down_revision = 'seed008'
branch_labels = None
depends_on = None


def upgrade():
    """Create platform_admin_invitations table."""
    op.create_table(
        'platform_admin_invitations',
        # Primary Key
        sa.Column(
            'id',
            UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            comment='Unique identifier for the admin invitation'
        ),

        # Invitation Details
        sa.Column(
            'email',
            sa.String(255),
            nullable=False,
            comment='Email address of the invited admin'
        ),
        sa.Column(
            'invitation_token',
            sa.String(255),
            unique=True,
            nullable=False,
            comment='Secure token for invitation acceptance'
        ),

        # Status & Role
        sa.Column(
            'status',
            sa.String(50),
            nullable=False,
            server_default='pending',
            comment='Invitation status: pending, accepted, revoked, expired, declined'
        ),
        sa.Column(
            'admin_role',
            sa.String(50),
            nullable=False,
            comment='Admin role to assign: super_admin, support_admin, etc.'
        ),

        # Optional: Additional permissions beyond role
        sa.Column(
            'permissions',
            JSONB,
            nullable=True,
            comment='Optional: Additional permissions beyond standard role (JSONB)'
        ),

        # Invitation Message (optional)
        sa.Column(
            'message',
            sa.Text,
            nullable=True,
            comment='Optional personalized message from inviter'
        ),

        # Relationships - Inviter
        sa.Column(
            'invited_by_admin_id',
            UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
            comment='Admin who sent the invitation'
        ),

        # Timestamps
        sa.Column(
            'created_at',
            sa.TIMESTAMP,
            nullable=False,
            server_default=sa.text('NOW()'),
            comment='When invitation was created'
        ),
        sa.Column(
            'expires_at',
            sa.TIMESTAMP,
            nullable=False,
            comment='When invitation expires'
        ),
        sa.Column(
            'accepted_at',
            sa.TIMESTAMP,
            nullable=True,
            comment='When invitation was accepted'
        ),

        # Relationships - Accepter
        sa.Column(
            'accepted_by_user_id',
            UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
            comment='User who accepted the invitation'
        ),

        # Declined tracking
        sa.Column(
            'declined_at',
            sa.TIMESTAMP,
            nullable=True,
            comment='When invitation was declined (if declined)'
        ),
        sa.Column(
            'declined_reason',
            sa.Text,
            nullable=True,
            comment='Reason for declining (optional)'
        ),

        # Revoked tracking
        sa.Column(
            'revoked_at',
            sa.TIMESTAMP,
            nullable=True,
            comment='When invitation was revoked'
        ),
        sa.Column(
            'revoked_by_admin_id',
            UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
            comment='Admin who revoked the invitation'
        ),
        sa.Column(
            'revoked_reason',
            sa.Text,
            nullable=True,
            comment='Reason for revoking (optional)'
        ),

        # Table-level comment
        comment='Platform admin invitations - For inviting platform-level administrators'
    )

    # Indexes for performance
    op.create_index(
        'ix_platform_admin_invitations_email',
        'platform_admin_invitations',
        ['email']
    )
    op.create_index(
        'ix_platform_admin_invitations_token',
        'platform_admin_invitations',
        ['invitation_token'],
        unique=True
    )
    op.create_index(
        'ix_platform_admin_invitations_status',
        'platform_admin_invitations',
        ['status']
    )
    op.create_index(
        'ix_platform_admin_invitations_expires_at',
        'platform_admin_invitations',
        ['expires_at']
    )

    # Unique constraint: one admin invitation per email
    op.create_unique_constraint(
        'uq_admin_invitation_email',
        'platform_admin_invitations',
        ['email']
    )

    print("\n" + "="*80)
    print("✅ CREATED: platform_admin_invitations table")
    print("="*80)
    print("\nTable Features:")
    print("  - Tracks admin-level invitations")
    print("  - Unique email constraint")
    print("  - Comprehensive audit trail")
    print("  - Decline and revoke tracking")
    print("  - Indexed for fast lookups")
    print("\nNext Steps:")
    print("  1. Create AdminInvitationService")
    print("  2. Add admin invitation API endpoints")
    print("  3. Add frontend UI for admin management")
    print("="*80 + "\n")


def downgrade():
    """Drop platform_admin_invitations table."""
    # Drop indexes first
    op.drop_index('ix_platform_admin_invitations_expires_at', 'platform_admin_invitations')
    op.drop_index('ix_platform_admin_invitations_status', 'platform_admin_invitations')
    op.drop_index('ix_platform_admin_invitations_token', 'platform_admin_invitations')
    op.drop_index('ix_platform_admin_invitations_email', 'platform_admin_invitations')

    # Drop table
    op.drop_table('platform_admin_invitations')

    print("\n✅ DROPPED: platform_admin_invitations table\n")
