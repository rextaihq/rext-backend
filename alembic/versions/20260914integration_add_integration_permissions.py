"""Add granular integration, brand voice, persona and security permissions.

Revision ID: 20260914integration
Revises: 20260909recovery, 20260910mrgowner
"""

from alembic import op


revision = "20260914integration"
down_revision = ("20260909recovery", "20260910mrgowner")
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("integration.read", "View Integrations", "View connected CMS and store integrations", "integration", "read"),
    ("integration.create", "Connect Integrations", "Connect CMS and store integrations", "integration", "create"),
    ("integration.update", "Update Integrations", "Update or activate integrations", "integration", "update"),
    ("integration.delete", "Delete Integrations", "Remove integrations", "integration", "delete"),
    ("brand_voice.read", "View Brand Voice", "View workspace brand voice", "brand_voice", "read"),
    ("brand_voice.create", "Create Brand Voice", "Create workspace brand voice", "brand_voice", "create"),
    ("brand_voice.update", "Update Brand Voice", "Update workspace brand voice", "brand_voice", "update"),
    ("brand_voice.delete", "Delete Brand Voice", "Delete workspace brand voice", "brand_voice", "delete"),
    ("persona.read", "View Personas", "View workspace personas", "persona", "read"),
    ("persona.create", "Create Personas", "Create workspace personas", "persona", "create"),
    ("persona.update", "Update Personas", "Update workspace personas", "persona", "update"),
    ("persona.delete", "Delete Personas", "Delete workspace personas", "persona", "delete"),
    ("security.read", "View Security & Monitoring", "View security administration pages", "security", "read"),
    ("security.manage", "Manage Security & Monitoring", "Manage security administration pages", "security", "manage"),
]

ROLE_ASSIGNMENTS = {
    "integration.read": ["super_admin", "workspace_owner", "workspace_admin", "editor", "viewer"],
    "integration.create": ["super_admin", "workspace_owner", "workspace_admin"],
    "integration.update": ["super_admin", "workspace_owner", "workspace_admin", "editor"],
    "integration.delete": ["super_admin", "workspace_owner", "workspace_admin"],
    "brand_voice.read": ["super_admin", "workspace_owner", "workspace_admin", "editor", "viewer"],
    "brand_voice.create": ["super_admin", "workspace_owner", "workspace_admin"],
    "brand_voice.update": ["super_admin", "workspace_owner", "workspace_admin", "editor"],
    "brand_voice.delete": ["super_admin", "workspace_owner", "workspace_admin"],
    "persona.read": ["super_admin", "workspace_owner", "workspace_admin", "editor", "viewer"],
    "persona.create": ["super_admin", "workspace_owner", "workspace_admin", "editor"],
    "persona.update": ["super_admin", "workspace_owner", "workspace_admin", "editor"],
    "persona.delete": ["super_admin", "workspace_owner", "workspace_admin"],
    "security.read": ["super_admin"], "security.manage": ["super_admin"],
}


def _grant(permission: str, roles: list[str]) -> None:
    role_list = ", ".join(f"'{role}'" for role in roles)
    op.execute(f"""INSERT INTO role_permissions (id, role_id, permission_id, created_at)
        SELECT gen_random_uuid(), r.id, p.id, NOW() FROM roles r CROSS JOIN permissions p
        WHERE r.name IN ({role_list}) AND p.name = '{permission}'
          AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id)""")


def upgrade() -> None:
    for name, display_name, description, resource, action in PERMISSIONS:
        op.execute(f"""INSERT INTO permissions (id, name, display_name, description, resource, action, is_system, created_at)
            SELECT gen_random_uuid(), '{name}', '{display_name}', '{description}', '{resource}', '{action}', true, NOW()
            WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = '{name}')""")
    op.execute("UPDATE permissions SET name = 'user.invite', display_name = 'Invite Users', description = 'Send user or administrator invitations', resource = 'user' WHERE name = 'admin.invite'")
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE name IN ('integration.manage', 'workspace.manage_members', 'member.update', 'user.create', 'permission.create', 'audit.write', 'license.read', 'license.view', 'license.activate', 'license.deactivate', 'license.revoke'))")
    op.execute("DELETE FROM permissions WHERE name IN ('integration.manage', 'workspace.manage_members', 'member.update', 'user.create', 'permission.create', 'audit.write', 'license.read', 'license.view', 'license.activate', 'license.deactivate', 'license.revoke')")
    for permission, roles in ROLE_ASSIGNMENTS.items():
        _grant(permission, roles)
    op.execute("""INSERT INTO role_permissions (id, role_id, permission_id, created_at)
        SELECT gen_random_uuid(), rp.role_id, billing.id, NOW() FROM role_permissions rp
        JOIN permissions old ON old.id = rp.permission_id
        JOIN permissions billing ON billing.name = CASE old.name WHEN 'subscription.read' THEN 'billing.read' ELSE 'billing.manage' END
        JOIN roles r ON r.id = rp.role_id WHERE old.name IN ('subscription.read', 'subscription.manage') AND r.name <> 'user'
        AND NOT EXISTS (SELECT 1 FROM role_permissions x WHERE x.role_id = rp.role_id AND x.permission_id = billing.id)""")
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE name LIKE 'subscription.%')")
    op.execute("DELETE FROM permissions WHERE name LIKE 'subscription.%'")
    op.execute("DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE name = 'user') AND permission_id IN (SELECT id FROM permissions WHERE name IN ('billing.read', 'billing.manage'))")
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE name LIKE 'knowledge.%' OR name LIKE 'topic.%')")
    op.execute("DELETE FROM permissions WHERE name LIKE 'knowledge.%' OR name LIKE 'topic.%'")


def downgrade() -> None:
    names = ", ".join(f"'{name}'" for name, *_ in PERMISSIONS)
    op.execute(f"DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE name IN ({names}))")
    op.execute(f"DELETE FROM permissions WHERE name IN ({names})")
    # Deleted subscription.*, knowledge.* and topic.* data is intentionally not restored.
