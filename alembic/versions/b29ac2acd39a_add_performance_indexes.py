"""add_performance_indexes

Revision ID: b29ac2acd39a
Revises: e1b98c2a4c0f
Create Date: 2025-10-02 11:37:10.868232

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b29ac2acd39a'
down_revision: Union[str, Sequence[str], None] = 'e1b98c2a4c0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add indexes for performance optimization."""
    # Users table indexes
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_status', 'users', ['status'])
    op.create_index('idx_users_email_verified', 'users', ['email_verified'])
    op.create_index('idx_users_deleted_at', 'users', ['deleted_at'])

    # Roles table indexes
    op.create_index('idx_roles_name', 'roles', ['name'])
    op.create_index('idx_roles_is_system_role', 'roles', ['is_system_role'])

    # Permissions table indexes
    op.create_index('idx_permissions_name', 'permissions', ['name'])
    op.create_index('idx_permissions_resource_action', 'permissions', ['resource', 'action'])

    # UserRole table indexes
    op.create_index('idx_user_roles_user_id', 'user_roles', ['user_id'])
    op.create_index('idx_user_roles_role_id', 'user_roles', ['role_id'])
    op.create_index('idx_user_roles_workspace_id', 'user_roles', ['workspace_id'])
    op.create_index('idx_user_roles_is_primary', 'user_roles', ['is_primary'])

    # RolePermission table indexes
    op.create_index('idx_role_permissions_role_id', 'role_permissions', ['role_id'])
    op.create_index('idx_role_permissions_permission_id', 'role_permissions', ['permission_id'])

    # Workspace table indexes
    op.create_index('idx_workspace_user_id', 'workspace', ['user_id'])
    op.create_index('idx_workspace_name', 'workspace', ['name'])

    # WorkspaceMembers table indexes
    op.create_index('idx_workspace_members_workspace_id', 'workspace_members', ['workspace_id'])
    op.create_index('idx_workspace_members_user_id', 'workspace_members', ['user_id'])

    # UserInvitations table indexes
    op.create_index('idx_user_invitations_email', 'user_invitations', ['email'])
    op.create_index('idx_user_invitations_workspace_id', 'user_invitations', ['workspace_id'])
    op.create_index('idx_user_invitations_status', 'user_invitations', ['status'])
    op.create_index('idx_user_invitations_token', 'user_invitations', ['invitation_token'])
    op.create_index('idx_user_invitations_expires_at', 'user_invitations', ['expires_at'])


def downgrade() -> None:
    """Remove indexes."""
    # Drop in reverse order
    op.drop_index('idx_user_invitations_expires_at', 'user_invitations')
    op.drop_index('idx_user_invitations_token', 'user_invitations')
    op.drop_index('idx_user_invitations_status', 'user_invitations')
    op.drop_index('idx_user_invitations_workspace_id', 'user_invitations')
    op.drop_index('idx_user_invitations_email', 'user_invitations')
    op.drop_index('idx_workspace_members_user_id', 'workspace_members')
    op.drop_index('idx_workspace_members_workspace_id', 'workspace_members')
    op.drop_index('idx_workspace_name', 'workspace')
    op.drop_index('idx_workspace_user_id', 'workspace')
    op.drop_index('idx_role_permissions_permission_id', 'role_permissions')
    op.drop_index('idx_role_permissions_role_id', 'role_permissions')
    op.drop_index('idx_user_roles_is_primary', 'user_roles')
    op.drop_index('idx_user_roles_workspace_id', 'user_roles')
    op.drop_index('idx_user_roles_role_id', 'user_roles')
    op.drop_index('idx_user_roles_user_id', 'user_roles')
    op.drop_index('idx_permissions_resource_action', 'permissions')
    op.drop_index('idx_permissions_name', 'permissions')
    op.drop_index('idx_roles_is_system_role', 'roles')
    op.drop_index('idx_roles_name', 'roles')
    op.drop_index('idx_users_deleted_at', 'users')
    op.drop_index('idx_users_email_verified', 'users')
    op.drop_index('idx_users_status', 'users')
    op.drop_index('idx_users_email', 'users')
