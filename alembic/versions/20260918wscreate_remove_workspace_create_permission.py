"""Remove the workspace.create permission from RBAC.

Revision ID: 20260918wscreate
Revises: 20260919wsobilling

workspace.create was granted to every account through the irrevocable
platform-floor 'user' role (AuthService.DEFAULT_PERMISSIONS), so the
@require_permissions("workspace.create") gate on POST /workspaces/ was
equivalent to "is authenticated" and provided no authorization value.
Workspace creation stays gated by authentication, RequireFeature("workspaces")
and the plan-based check_workspace_limit() quota.

The seed is additive-only, so existing databases keep the grants and the
permission row until this migration removes them. After deploying, flush the
Redis permission cache (user:permissions:*).

Permission removal is not restored on downgrade.
"""

from alembic import op

revision = "20260918wscreate"
down_revision = "20260919wsobilling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions rp
        USING permissions p
        WHERE rp.permission_id = p.id
          AND p.name = 'workspace.create'
        """
    )
    op.execute("DELETE FROM permissions WHERE name = 'workspace.create'")


def downgrade() -> None:
    pass
