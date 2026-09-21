"""Seed RBAC roles and permissions. Consolidates all seed migrations into a single idempotent script."""

import asyncio
from sqlalchemy import text
from uuid import uuid4

from scripts.seeds.base import get_seed_session, utc_now

# ============================================================================
# ROLE DEFINITIONS
# ============================================================================
ROLES = [
    {
        "name": "super_admin",
        "display_name": "Super Administrator",
        "description": "Full system access with all permissions",
        "hierarchy_level": 100,
        "is_system_role": True,
        "is_workspace_role": False,
    },
    {
        "name": "admin",
        "display_name": "Administrator",
        "description": "Administrative access with most permissions",
        "hierarchy_level": 80,
        "is_system_role": True,
        "is_workspace_role": False,
    },
    {
        "name": "workspace_owner",
        "display_name": "Workspace Owner",
        "description": "Full control over owned workspaces",
        "hierarchy_level": 60,
        "is_system_role": False,
        "is_workspace_role": True,
    },
    {
        "name": "workspace_admin",
        "display_name": "Workspace Administrator",
        "description": "Manage workspace members and content",
        "hierarchy_level": 50,
        "is_system_role": False,
        "is_workspace_role": True,
    },
    {
        "name": "editor",
        "display_name": "Editor",
        "description": "Create and edit content",
        "hierarchy_level": 30,
        "is_system_role": False,
        "is_workspace_role": True,
    },
    {
        "name": "viewer",
        "display_name": "Viewer",
        "description": "Read-only access to content",
        "hierarchy_level": 10,
        "is_system_role": False,
        "is_workspace_role": True,
    },
    {
        "name": "support",
        "display_name": "Support",
        "description": "Customer support role with read-only access",
        "hierarchy_level": 3,
        "is_system_role": True,
        "is_workspace_role": False,
    },
]

# ============================================================================
# PERMISSION DEFINITIONS
# ============================================================================
PERMISSIONS = [
    # Workspace Management
    (
        "workspace.read",
        "View Workspace",
        "View workspace details and settings",
        "workspace",
        "read",
    ),
    ("workspace.update", "Update Workspace", "Edit workspace settings", "workspace", "update"),
    ("workspace.delete", "Delete Workspace", "Delete workspace permanently", "workspace", "delete"),
    # Content Management
    ("content.create", "Create Content", "Create new content", "content", "create"),
    ("content.read", "Read Content", "View content", "content", "read"),
    ("content.update", "Update Content", "Edit existing content", "content", "update"),
    ("content.delete", "Delete Content", "Delete content", "content", "delete"),
    ("content.publish", "Publish Content", "Publish content to production", "content", "publish"),
    # Member Management
    ("member.read", "View Members", "View workspace members", "member", "read"),
    ("member.update_role", "Update Member Roles", "Change member roles", "member", "update_role"),
    ("member.invite", "Invite Members", "Invite members to workspace", "member", "invite"),
    ("member.remove", "Remove Members", "Remove members from workspace", "member", "remove"),
    # User Management
    # NOTE: user.read / user.update are the SELF-SERVICE permissions every
    # account needs (profile, sessions, preferences), so they stay on the
    # default `user` role. Cross-user admin actions (list all users, edit/
    # suspend/ban ANY account) require user.manage, which the default role
    # must never hold.
    ("user.read", "View Own Account", "View own profile and session data", "user", "read"),
    ("user.update", "Update Own Account", "Edit own profile and settings", "user", "update"),
    (
        "user.manage",
        "Manage Users",
        "List, edit, suspend, ban and manage other users' accounts",
        "user",
        "manage",
    ),
    ("user.delete", "Delete Users", "Delete users", "user", "delete"),
    (
        "user.manage_roles",
        "Manage User Roles",
        "Assign global roles to users",
        "user",
        "manage_roles",
    ),
    # Role Management
    ("role.create", "Create Roles", "Create custom roles", "role", "create"),
    ("role.read", "View Roles", "View all roles", "role", "read"),
    ("role.update", "Update Roles", "Update role definitions", "role", "update"),
    ("role.delete", "Delete Roles", "Delete custom roles", "role", "delete"),
    (
        "role.manage_permissions",
        "Manage Permissions",
        "Assign permissions to roles",
        "role",
        "manage_permissions",
    ),
    # Billing Management
    (
        "billing.read",
        "View Billing",
        "View billing history, invoices, and subscription information",
        "billing",
        "read",
    ),
    (
        "billing.manage",
        "Manage Billing",
        "Update payment methods, manage subscription plans and refunds",
        "billing",
        "manage",
    ),
    # Security
    (
        "security.read",
        "View Security & Monitoring",
        "Access System Monitoring, Email Analytics, and Security settings",
        "security",
        "read",
    ),
    (
        "security.manage",
        "Manage Security & Monitoring",
        "Manage System Monitoring and Security settings",
        "security",
        "manage",
    ),
    ("audit.read", "View Audit Logs", "View audit logs and analytics", "audit", "read"),
    ("audit.export", "Export Audit Logs", "Export audit logs", "audit", "export"),
    ("user.invite", "Invite Users", "Send user or administrator invitations", "user", "invite"),
    ("permission.read", "View Permissions", "View permissions", "permission", "read"),
    ("permission.update", "Update Permissions", "Update permissions", "permission", "update"),
    (
        "user.impersonate",
        "Impersonate Users",
        "Impersonate users for support",
        "user",
        "impersonate",
    ),
    ("integration.read", "View Integrations", "View integrations", "integration", "read"),
    ("integration.create", "Connect Integrations", "Connect integrations", "integration", "create"),
    ("integration.update", "Update Integrations", "Update integrations", "integration", "update"),
    ("integration.delete", "Delete Integrations", "Delete integrations", "integration", "delete"),
    ("brand_voice.read", "View Brand Voice", "View brand voice", "brand_voice", "read"),
    ("brand_voice.update", "Update Brand Voice", "Update brand voice", "brand_voice", "update"),
    ("persona.read", "View Personas", "View personas", "persona", "read"),
    ("persona.create", "Create Personas", "Create personas", "persona", "create"),
    ("persona.update", "Update Personas", "Update personas", "persona", "update"),
    ("persona.delete", "Delete Personas", "Delete personas", "persona", "delete"),
]

# ============================================================================
# ROLE PERMISSION ASSIGNMENTS
# ============================================================================
ROLE_PERMISSION_ASSIGNMENTS = {
    "workspace_owner": [
        "workspace.read",
        "workspace.update",
        "workspace.delete",
        "member.read",
        "member.update_role",
        "member.invite",
        "member.remove",
        "content.create",
        "content.read",
        "content.update",
        "content.delete",
        "content.publish",
        "integration.read",
        "integration.create",
        "integration.update",
        "integration.delete",
        "brand_voice.read",
        "brand_voice.update",
        "persona.read",
        "persona.create",
        "persona.update",
        "persona.delete",
    ],
    "workspace_admin": [
        "workspace.read",
        "workspace.update",
        "member.read",
        "member.update_role",
        "member.invite",
        "member.remove",
        "content.create",
        "content.read",
        "content.update",
        "content.delete",
        "content.publish",
        # role.read intentionally removed: every role.* route is global-scoped,
        # so a workspace role can never use it (SEC-RBAC-15).
        "integration.read",
        "integration.create",
        "integration.update",
        "integration.delete",
        "brand_voice.read",
        "brand_voice.update",
        "persona.read",
        "persona.create",
        "persona.update",
        "persona.delete",
    ],
    "editor": [
        "workspace.read",
        "member.read",
        "content.create",
        "content.read",
        "content.update",
        "integration.read",
        "integration.update",
        "brand_voice.read",
        "brand_voice.update",
        "persona.read",
        "persona.create",
        "persona.update",
    ],
    "viewer": [
        "workspace.read",
        "member.read",
        "content.read",
        "integration.read",
        "brand_voice.read",
        "persona.read",
    ],
    "super_admin": [name for name, *_ in PERMISSIONS],
    # Platform admin: everything except managing billing.
    "admin": [name for name, *_ in PERMISSIONS if name != "billing.manage"],
    "support": [
        "workspace.read",
        "member.read",
        "content.read",
        "user.read",
        # Support views the audit-log page. Safe since SEC-RBAC-09 moved revenue
        # reports (billing.read), webhook replay (billing.manage) and email
        # resend (security.manage) off audit.read; it now gates reads only.
        "audit.read",
        # Read-only view of the admin Subscriptions and Refund Management pages.
        # Writes (refund, cancel, extend trial, plans) stay on billing.manage.
        "billing.read",
    ],
}


async def seed_permissions():
    """Seed RBAC roles and permissions (idempotent, additive-only)."""
    async with get_seed_session() as session:
        # Update renamed permissions if present
        await session.execute(
            text(
                "UPDATE permissions SET name = 'user.invite', display_name = 'Invite Users', description = 'Send user or administrator invitations', resource = 'user' WHERE name = 'admin.invite'"
            )
        )

        # 1. Seed Roles
        print("\nSeeding roles...")
        role_map = {}
        for role_data in ROLES:
            result = await session.execute(
                text("SELECT id FROM roles WHERE name = :name"), {"name": role_data["name"]}
            )
            existing = result.fetchone()
            if existing:
                role_map[role_data["name"]] = existing[0]
                print(f"  ℹ️  Role already exists: {role_data['name']}")
                continue

            role_id = uuid4()
            await session.execute(
                text("""
                    INSERT INTO roles (id, name, display_name, description, hierarchy_level, is_system_role, is_workspace_role, created_at, updated_at)
                    VALUES (:id, :name, :display_name, :description, :hierarchy_level, :is_system_role, :is_workspace_role, :created_at, :updated_at)
                """),
                {
                    "id": role_id,
                    "name": role_data["name"],
                    "display_name": role_data["display_name"],
                    "description": role_data["description"],
                    "hierarchy_level": role_data["hierarchy_level"],
                    "is_system_role": role_data["is_system_role"],
                    "is_workspace_role": role_data["is_workspace_role"],
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                },
            )
            role_map[role_data["name"]] = role_id
            print(f"  ✅ Created role: {role_data['name']}")

        # 2. Seed Permissions
        print("\nSeeding permissions...")
        permission_map = {}
        for perm in PERMISSIONS:
            name, display_name, description, resource, action = perm
            result = await session.execute(
                text("SELECT id FROM permissions WHERE name = :name"), {"name": name}
            )
            existing = result.fetchone()
            if existing:
                permission_map[name] = existing[0]
                print(f"  ℹ️  Permission already exists: {name}")
                continue

            perm_id = uuid4()
            await session.execute(
                text("""
                    INSERT INTO permissions (id, name, display_name, description, resource, action, is_system, created_at)
                    VALUES (:id, :name, :display_name, :description, :resource, :action, true, :created_at)
                """),
                {
                    "id": perm_id,
                    "name": name,
                    "display_name": display_name,
                    "description": description,
                    "resource": resource,
                    "action": action,
                    "created_at": utc_now(),
                },
            )
            permission_map[name] = perm_id
            print(f"  ✅ Created permission: {name}")

        # 3. Assign Permissions to Roles
        print("\nAssigning permissions to roles...")
        for role_name, perm_names in ROLE_PERMISSION_ASSIGNMENTS.items():
            if role_name not in role_map:
                print(f"  ⚠️  Role not found: {role_name}")
                continue

            role_id = role_map[role_name]

            for perm_name in perm_names:
                if perm_name not in permission_map:
                    print(f"  ⚠️  Permission not found: {perm_name}")
                    continue

                perm_id = permission_map[perm_name]

                # Check if mapping exists
                result = await session.execute(
                    text(
                        "SELECT id FROM role_permissions WHERE role_id = :role_id AND permission_id = :perm_id"
                    ),
                    {"role_id": role_id, "perm_id": perm_id},
                )
                if result.fetchone():
                    continue

                await session.execute(
                    text("""
                        INSERT INTO role_permissions (id, role_id, permission_id, created_at)
                        VALUES (:id, :role_id, :permission_id, :created_at)
                    """),
                    {
                        "id": uuid4(),
                        "role_id": role_id,
                        "permission_id": perm_id,
                        "created_at": utc_now(),
                    },
                )
                print(f"  ✅ Assigned {perm_name} to {role_name}")


if __name__ == "__main__":
    asyncio.run(seed_permissions())
