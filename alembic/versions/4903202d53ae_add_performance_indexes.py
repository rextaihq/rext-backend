"""add_performance_indexes

Revision ID: 4903202d53ae
Revises: 2ee3c8122fed
Create Date: 2025-10-16 07:03:21.359697

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4903202d53ae'
down_revision: Union[str, Sequence[str], None] = '2ee3c8122fed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add performance indexes for frequently queried columns."""

    # Single column indexes
    # =====================

    # users.status - For filtering active/inactive users
    op.create_index(
        'ix_users_status',
        'users',
        ['status'],
        unique=False
    )

    # content.created_at - For date range queries and sorting
    op.create_index(
        'ix_content_created_at',
        'content',
        ['created_at'],
        unique=False
    )

    # NOTE: ix_audit_logs_created_at already exists from migration 2cc855f144c1
    # Removed to avoid duplicate index error

    # Composite indexes for common query patterns
    # ===========================================

    # content (workspace_id, status) - Most common content query pattern
    # Used in: "SELECT * FROM content WHERE workspace_id = X AND status = 'published'"
    op.create_index(
        'ix_content_workspace_status',
        'content',
        ['workspace_id', 'status'],
        unique=False
    )

    # content (workspace_id, created_at) - Dashboard and analytics queries
    # Used in: "SELECT * FROM content WHERE workspace_id = X ORDER BY created_at DESC"
    op.create_index(
        'ix_content_workspace_created_at',
        'content',
        ['workspace_id', 'created_at'],
        unique=False
    )

    # user_roles (user_id, workspace_id) - RBAC permission checks
    # Used in: "SELECT * FROM user_roles WHERE user_id = X AND workspace_id = Y"
    op.create_index(
        'ix_user_roles_user_workspace',
        'user_roles',
        ['user_id', 'workspace_id'],
        unique=False
    )

    # user_roles (workspace_id, role_id) - Workspace member queries
    # Used in: "SELECT * FROM user_roles WHERE workspace_id = X AND role_id = Y"
    op.create_index(
        'ix_user_roles_workspace_role',
        'user_roles',
        ['workspace_id', 'role_id'],
        unique=False
    )


def downgrade() -> None:
    """Remove performance indexes."""

    # Drop composite indexes
    op.drop_index('ix_user_roles_workspace_role', table_name='user_roles')
    op.drop_index('ix_user_roles_user_workspace', table_name='user_roles')
    op.drop_index('ix_content_workspace_created_at', table_name='content')
    op.drop_index('ix_content_workspace_status', table_name='content')

    # Drop single column indexes
    # NOTE: ix_audit_logs_created_at not dropped here as it's managed by migration 2cc855f144c1
    op.drop_index('ix_content_created_at', table_name='content')
    op.drop_index('ix_users_status', table_name='users')
