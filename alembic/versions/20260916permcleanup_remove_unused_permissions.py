"""Remove permissions that have no product feature behind them.

Revision ID: 20260916permcleanup
Revises: 20260915media

- content.approve / reject / submit_for_review / export: there is no review or
  export workflow.
- member.resend_invitation / revoke_invitation: resend and revoke are authorized
  by member.invite. Grants are dropped, not mapped: the dependency map already
  required member.invite for both, so every holder keeps the action through it.
- workspace.manage_roles: member role changes use member.update_role.
- workspace.manage_billing: billing is billing.*, never a workspace permission.
- workspace.transfer / transfer_ownership: there is no transfer feature.
- workspace.write / workspace.invite: unused aliases.
- usage.read: usage statistics are gated by security.read.

Deleted permissions and grants are not restored on downgrade.
"""

from alembic import op


revision = "20260916permcleanup"
down_revision = "20260915media"
branch_labels = None
depends_on = None

REMOVED_PERMISSIONS = [
    "content.approve",
    "content.reject",
    "content.submit_for_review",
    "content.export",
    "member.resend_invitation",
    "member.revoke_invitation",
    "workspace.manage_roles",
    "workspace.manage_billing",
    "workspace.transfer",
    "workspace.transfer_ownership",
    "workspace.write",
    "workspace.invite",
    "usage.read",
]


def upgrade() -> None:
    names = ", ".join(f"'{name}'" for name in REMOVED_PERMISSIONS)
    op.execute(f"DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE name IN ({names}))")
    op.execute(f"DELETE FROM permissions WHERE name IN ({names})")


def downgrade() -> None:
    # Removed permissions and their grants are intentionally not restored.
    pass
