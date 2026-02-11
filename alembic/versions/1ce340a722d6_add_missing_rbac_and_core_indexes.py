"""add missing rbac and core indexes

Revision ID: 1ce340a722d6
Revises: 7134b1198eef
Create Date: 2026-02-03

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1ce340a722d6"
down_revision: Union[str, Sequence[str], None] = "7134b1198eef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # RBAC tables — queried on every authenticated request
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])
    op.create_index("ix_user_roles_workspace_id", "user_roles", ["workspace_id"])
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])
    op.create_index(
        "ix_role_permissions_permission_id", "role_permissions", ["permission_id"]
    )
    op.create_index("ix_roles_name", "roles", ["name"])

    # Core tables
    op.create_index("ix_users_status", "users", ["status"])
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])
    op.create_index("ix_workspace_user_id", "workspace", ["user_id"])
    op.create_index("ix_workspace_deleted_at", "workspace", ["deleted_at"])
    op.create_index("ix_workspace_members_user_id", "workspace_members", ["user_id"])
    op.create_index(
        "ix_workspace_members_workspace_id", "workspace_members", ["workspace_id"]
    )
    op.create_index(
        "ix_user_subscriptions_user_id", "user_subscriptions", ["user_id"]
    )
    op.create_index(
        "ix_user_subscriptions_status", "user_subscriptions", ["status"]
    )
    op.create_index("ix_content_status", "content", ["status"])


def downgrade() -> None:
    op.drop_index("ix_content_status", table_name="content")
    op.drop_index("ix_user_subscriptions_status", table_name="user_subscriptions")
    op.drop_index("ix_user_subscriptions_user_id", table_name="user_subscriptions")
    op.drop_index("ix_workspace_members_workspace_id", table_name="workspace_members")
    op.drop_index("ix_workspace_members_user_id", table_name="workspace_members")
    op.drop_index("ix_workspace_deleted_at", table_name="workspace")
    op.drop_index("ix_workspace_user_id", table_name="workspace")
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_roles_name", table_name="roles")
    op.drop_index("ix_role_permissions_permission_id", table_name="role_permissions")
    op.drop_index("ix_role_permissions_role_id", table_name="role_permissions")
    op.drop_index("ix_user_roles_workspace_id", table_name="user_roles")
    op.drop_index("ix_user_roles_role_id", table_name="user_roles")
    op.drop_index("ix_user_roles_user_id", table_name="user_roles")
