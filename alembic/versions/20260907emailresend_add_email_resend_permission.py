"""add email.resend permission for admin email resend operations

Revision ID: 20260907emailresend
Revises: 20260904mrgheads
Create Date: 2026-09-07

Seeds the ``email.resend`` permission and assigns it to super_admin and admin.

NOTE: The resend routes (/{id}/resend and /resend-batch) currently guard with
``audit.write`` (already seeded) so they work without this migration. This
migration seeds ``email.resend`` for future fine-grained permission control —
when the route guards are switched back to ``email.resend``, this permission
must exist in the DB.

``content.submit_review`` and ``audit.webhooks`` were investigated but are NOT
referenced by any route ``require_permissions`` guard in the codebase, so they
are intentionally NOT added here.
"""
from alembic import op


revision = "20260907emailresend"
down_revision = "20260904rbacfloor"
branch_labels = None
depends_on = None


PERMISSIONS = [
    # (name, display_name, description, resource, action)
    (
        "email.resend",
        "Resend Failed Emails",
        "Resend individual or batch failed/bounced email messages from the admin panel",
        "email",
        "resend",
    ),
]

ROLE_ASSIGNMENTS = {
    "email.resend": ["super_admin", "admin"],
}


def upgrade() -> None:
    for name, display_name, description, resource, action in PERMISSIONS:
        op.execute(
            f"""
            INSERT INTO permissions (id, name, display_name, description, resource, action, created_at)
            SELECT gen_random_uuid(), '{name}', '{display_name}', '{description}', '{resource}', '{action}', NOW()
            WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = '{name}')
            """
        )

    for perm_name, role_names in ROLE_ASSIGNMENTS.items():
        role_list = ", ".join(f"'{r}'" for r in role_names)
        op.execute(
            f"""
            INSERT INTO role_permissions (id, role_id, permission_id, created_at)
            SELECT gen_random_uuid(), r.id, p.id, NOW()
            FROM roles r
            CROSS JOIN permissions p
            WHERE r.name IN ({role_list})
              AND p.name = '{perm_name}'
              AND NOT EXISTS (
                  SELECT 1 FROM role_permissions rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
            """
        )


def downgrade() -> None:
    for name, *_ in PERMISSIONS:
        op.execute(
            f"DELETE FROM role_permissions WHERE permission_id = "
            f"(SELECT id FROM permissions WHERE name = '{name}')"
        )
        op.execute(f"DELETE FROM permissions WHERE name = '{name}'")
