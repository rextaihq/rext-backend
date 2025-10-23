"""add_invitation_composite_indexes

Revision ID: inv002
Revises: inv001
Create Date: 2025-10-23 18:30:00.000000

Description: Add composite and partial indexes for invitation system performance optimization.
These indexes are based on A2 recommendations to improve query performance for:
- Email + status lookups (pending invitations)
- Expiry checks (reminder jobs, cleanup jobs)
- Workspace member lookups (user switching, permission checks)
- User role lookups (permission resolution)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'inv002'
down_revision: Union[str, Sequence[str], None] = 'inv001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add composite and partial indexes for invitation system optimization."""

    # 1. COMPOSITE INDEX: user_invitations(email, status) with partial index for pending
    # Use case: Finding pending invitations for a specific email (GET /user/invitations/pending)
    # This is a partial index - only indexes pending invitations for faster lookups
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_invitations_email_status_pending
        ON user_invitations(email, status)
        WHERE status = 'pending'
    """)

    # 2. COMPOSITE INDEX: user_invitations(expires_at, status) with partial index for pending
    # Use case: Finding invitations expiring soon (reminder jobs, cleanup jobs)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_invitations_expiry_pending
        ON user_invitations(expires_at, status)
        WHERE status = 'pending'
    """)

    # 3. COMPOSITE INDEX: workspace_members(user_id, workspace_id)
    # Use case: Quick lookup of user's membership in a specific workspace
    # Already exists as idx_workspace_members_user_id and idx_workspace_members_workspace_id
    # But composite is faster for permission checks
    op.create_index(
        'idx_workspace_members_user_workspace',
        'workspace_members',
        ['user_id', 'workspace_id'],
        unique=False
    )

    # 4. COMPOSITE INDEX: workspace_members(workspace_id, status)
    # Use case: Finding all active members of a workspace
    op.create_index(
        'idx_workspace_members_workspace_status',
        'workspace_members',
        ['workspace_id', 'status'],
        unique=False
    )

    # 5. COMPOSITE INDEX: user_roles(user_id, workspace_id)
    # Use case: Finding user's role in a specific workspace (permission resolution)
    # This is critical for multi-workspace permission checks
    op.create_index(
        'idx_user_roles_user_workspace',
        'user_roles',
        ['user_id', 'workspace_id'],
        unique=False
    )

    # 6. PARTIAL INDEX: workspace_members(user_id) WHERE status = 'active'
    # Use case: GET /user/workspaces - finding all active workspaces for a user
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_workspace_members_user_active
        ON workspace_members(user_id)
        WHERE status = 'active'
    """)

    # 7. PARTIAL INDEX: user_invitations(workspace_id) WHERE status = 'pending'
    # Use case: Finding pending invitations for a workspace (workspace admin view)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_invitations_workspace_pending
        ON user_invitations(workspace_id)
        WHERE status = 'pending'
    """)

    # 8. INDEX: user_invitations(invited_by_user_id)
    # Use case: Finding all invitations sent by a user (analytics)
    op.create_index(
        'idx_invitations_invited_by',
        'user_invitations',
        ['invited_by_user_id'],
        unique=False
    )

    # 9. COMPOSITE INDEX: user_invitations(workspace_id, status, created_at)
    # Use case: Workspace invitation management - sort by date with status filter
    op.create_index(
        'idx_invitations_workspace_status_created',
        'user_invitations',
        ['workspace_id', 'status', 'created_at'],
        unique=False
    )

    # 10. INDEX: platform_admin_invitations(email, status) with partial index
    # Use case: Admin invitation lookups
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_admin_invitations_email_status_pending
        ON platform_admin_invitations(email, status)
        WHERE status = 'pending'
    """)


def downgrade() -> None:
    """Remove composite and partial indexes."""

    # Drop indexes in reverse order
    op.execute("DROP INDEX IF EXISTS idx_admin_invitations_email_status_pending")
    op.drop_index('idx_invitations_workspace_status_created', 'user_invitations')
    op.drop_index('idx_invitations_invited_by', 'user_invitations')
    op.execute("DROP INDEX IF EXISTS idx_invitations_workspace_pending")
    op.execute("DROP INDEX IF EXISTS idx_workspace_members_user_active")
    op.drop_index('idx_user_roles_user_workspace', 'user_roles')
    op.drop_index('idx_workspace_members_workspace_status', 'workspace_members')
    op.drop_index('idx_workspace_members_user_workspace', 'workspace_members')
    op.execute("DROP INDEX IF EXISTS idx_invitations_expiry_pending")
    op.execute("DROP INDEX IF EXISTS idx_invitations_email_status_pending")
