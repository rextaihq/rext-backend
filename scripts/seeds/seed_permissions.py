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
        "is_workspace_role": False
    },
    {
        "name": "admin",
        "display_name": "Administrator",
        "description": "Administrative access with most permissions",
        "hierarchy_level": 80,
        "is_system_role": True,
        "is_workspace_role": False
    },
    {
        "name": "workspace_owner",
        "display_name": "Workspace Owner",
        "description": "Full control over owned workspaces",
        "hierarchy_level": 60,
        "is_system_role": False,
        "is_workspace_role": True
    },
    {
        "name": "workspace_admin",
        "display_name": "Workspace Administrator",
        "description": "Manage workspace members and content",
        "hierarchy_level": 50,
        "is_system_role": False,
        "is_workspace_role": True
    },
    {
        "name": "editor",
        "display_name": "Editor",
        "description": "Create and edit content",
        "hierarchy_level": 30,
        "is_system_role": False,
        "is_workspace_role": True
    },
    {
        "name": "viewer",
        "display_name": "Viewer",
        "description": "Read-only access to content",
        "hierarchy_level": 10,
        "is_system_role": False,
        "is_workspace_role": True
    },
    {
        "name": "user",
        "display_name": "User",
        "description": "Default role for regular users",
        "hierarchy_level": 1,
        "is_system_role": True,
        "is_workspace_role": False
    },
    {
        "name": "support",
        "display_name": "Support",
        "description": "Customer support role with read-only access",
        "hierarchy_level": 3,
        "is_system_role": True,
        "is_workspace_role": False
    },
]

# ============================================================================
# PERMISSION DEFINITIONS
# ============================================================================
PERMISSIONS = [
    # --- From seed009 ---
    # Workspace Management
    ("workspace.read", "View Workspace", "View workspace details and settings", "workspace", "read"),
    ("workspace.create", "Create Workspace", "Create new workspaces", "workspace", "create"),
    ("workspace.write", "Write Workspace", "Write workspace details and settings", "workspace", "write"),
    ("workspace.update", "Update Workspace", "Edit workspace settings", "workspace", "update"),
    ("workspace.delete", "Delete Workspace", "Delete workspace permanently", "workspace", "delete"),
    ("workspace.transfer", "Transfer Ownership", "Transfer workspace ownership to another user", "workspace", "transfer"),
    ("workspace.manage_members", "Manage Members", "Add/remove workspace members", "workspace", "manage_members"),
    ("workspace.manage_roles", "Manage Roles", "Assign/change member roles", "workspace", "manage_roles"),
    ("workspace.invite", "Send Invitations", "Send workspace invitations", "workspace", "invite"),

    # Billing & Subscription
    ("subscription.read", "View Subscription", "View subscription details and status", "subscription", "read"),
    ("subscription.manage", "Manage Subscription", "Change plans, update billing, cancel subscription", "subscription", "manage"),
    ("billing.read", "View Billing", "View billing history and invoices", "billing", "read"),
    ("billing.manage", "Manage Billing", "Update payment methods and billing information", "billing", "manage"),
    ("usage.read", "View Usage", "View usage statistics and limits", "usage", "read"),

    # Content Management
    ("content.create", "Create Content", "Create new content", "content", "create"),
    ("content.read", "Read Content", "View content", "content", "read"),
    ("content.update", "Update Content", "Edit existing content", "content", "update"),
    ("content.delete", "Delete Content", "Delete content", "content", "delete"),
    ("content.publish", "Publish Content", "Publish content to production", "content", "publish"),
    ("content.submit_review", "Submit for Review", "Submit content for approval", "content", "submit_review"),
    ("content.approve", "Approve Content", "Approve content for publishing", "content", "approve"),
    ("content.reject", "Reject Content", "Reject submitted content", "content", "reject"),
    ("content.export", "Export Content", "Export content data", "content", "export"),

    # Topic Management
    ("topic.create", "Create Topics", "Create new topics", "topic", "create"),
    ("topic.read", "Read Topics", "View topics", "topic", "read"),
    ("topic.update", "Update Topics", "Edit topics", "topic", "update"),
    ("topic.delete", "Delete Topics", "Delete topics", "topic", "delete"),
    ("topic.approve", "Approve Topics", "Approve topics for content generation", "topic", "approve"),

    # Knowledge Base
    ("knowledge.create", "Create Knowledge", "Create knowledge bases", "knowledge", "create"),
    ("knowledge.read", "Read Knowledge", "View knowledge bases", "knowledge", "read"),
    ("knowledge.update", "Update Knowledge", "Update knowledge bases", "knowledge", "update"),
    ("knowledge.delete", "Delete Knowledge", "Delete knowledge bases", "knowledge", "delete"),

    # Media Management
    ("media.upload", "Upload Media", "Upload media files", "media", "upload"),
    ("media.read", "View Media", "View media library", "media", "read"),
    ("media.organize", "Organize Media", "Organize media into folders", "media", "organize"),
    ("media.view", "View Media (Legacy)", "View media files in workspace", "media", "view"),
    ("media.create", "Upload Media (Legacy)", "Upload new media files to workspace", "media", "create"),
    ("media.update", "Update Media (Legacy)", "Update media file metadata", "media", "update"),
    ("media.delete", "Delete Media", "Delete media files from workspace", "media", "delete"),

    # Member Management
    ("member.read", "View Members", "View workspace members", "member", "read"),
    ("member.update", "Update Members", "Update member roles and permissions", "member", "update"),
    ("member.invite", "Invite Members", "Invite members to workspace", "member", "invite"),
    ("member.remove", "Remove Members", "Remove members from workspace", "member", "remove"),
    ("member.update_role", "Update Member Roles", "Change member roles", "member", "update_role"),
    ("member.resend_invitation", "Resend Invitations", "Resend invitation emails", "member", "resend_invitation"),
    ("member.revoke_invitation", "Revoke Invitations", "Cancel pending invitations", "member", "revoke_invitation"),

    # User Management (Platform Level)
    ("user.create", "Create Users", "Create new users", "user", "create"),
    ("user.read", "View Users", "View all users", "user", "read"),
    ("user.update", "Update Users", "Edit user profiles", "user", "update"),
    ("user.impersonate", "Impersonate Users", "Impersonate other users for support", "user", "impersonate"),
    ("user.delete", "Delete Users", "Delete users", "user", "delete"),
    ("user.manage_roles", "Manage User Roles", "Assign global roles to users", "user", "manage_roles"),

    # Role & Permission Management
    ("role.create", "Create Roles", "Create custom roles", "role", "create"),
    ("role.read", "View Roles", "View all roles", "role", "read"),
    ("role.update", "Update Roles", "Update role definitions", "role", "update"),
    ("role.delete", "Delete Roles", "Delete custom roles", "role", "delete"),
    ("role.manage_permissions", "Manage Permissions", "Assign permissions to roles", "role", "manage_permissions"),

    ("permission.create", "Create Permissions", "Create new permissions", "permission", "create"),
    ("permission.read", "View Permissions", "View all permissions", "permission", "read"),
    ("permission.update", "Update Permissions", "Update permission definitions", "permission", "update"),
    ("permission.delete", "Delete Permissions", "Delete permissions", "permission", "delete"),

    # Platform Management
    ("audit.read", "View Audit Logs", "View audit logs", "audit", "read"),
    ("audit.write", "Write Audit Logs", "Allows modifying audit/monitoring records (resolve errors, etc.)", "audit", "write"),
    ("audit.export", "Export Audit Logs", "Export audit logs", "audit", "export"),
    ("audit.admin", "Admin Audit Access", "Admin access to all audit logs and monitoring", "audit", "admin"),
    ("audit.webhooks", "Webhook Monitoring", "Monitor and retry webhook events", "audit", "webhooks"),

    # Email Management (Admin)
    ("email.resend", "Resend Emails", "Allows resending failed emails via admin panel", "email", "resend"),

    # Support Staff Permissions
    ("support.view_workspace", "View Any Workspace", "View any workspace (read-only)", "support", "view_workspace"),
    ("support.view_billing", "View Billing Info", "View billing information for support", "support", "view_billing"),

    # License Management
    ("license.view", "View Licenses", "View own license keys and activations", "license", "view"),
    ("license.read", "View Licenses (Canonical)", "View own license keys and activations (canonical)", "license", "read"),
    ("license.activate", "Activate License", "Activate license on a device or instance", "license", "activate"),
    ("license.deactivate", "Deactivate License", "Deactivate license from a device or instance", "license", "deactivate"),
    ("license.revoke", "Revoke License", "Revoke a license (admin only)", "license", "revoke"),
]

# ============================================================================
# ROLE PERMISSION ASSIGNMENTS
# ============================================================================
ROLE_PERMISSION_ASSIGNMENTS = {
    "workspace_owner": [
        "workspace.read", "workspace.write", "workspace.update", "workspace.delete", "workspace.transfer",
        "workspace.manage_members", "workspace.manage_roles", "workspace.invite",
        "subscription.read", "subscription.manage",
        "billing.read", "billing.manage",
        "usage.read",
        "content.create", "content.read", "content.update", "content.delete",
        "content.publish", "content.submit_review", "content.approve", "content.reject", "content.export",
        "topic.create", "topic.read", "topic.update", "topic.delete", "topic.approve",
        "knowledge.create", "knowledge.read", "knowledge.update", "knowledge.delete",
        "media.upload", "media.read", "media.delete", "media.organize",
        "media.view", "media.create", "media.update",
        "member.read", "member.update", "member.update_role",
        "member.invite", "member.remove", "member.resend_invitation", "member.revoke_invitation",
        "license.view", "license.read", "license.activate", "license.deactivate",
    ],
    "workspace_admin": [
        "workspace.read", "workspace.write", "workspace.update",
        "workspace.manage_members", "workspace.manage_roles", "workspace.invite",
        "usage.read",
        "license.view", "license.read", "license.activate",
        "content.create", "content.read", "content.update", "content.delete",
        "content.publish", "content.submit_review", "content.approve", "content.reject", "content.export",
        "topic.create", "topic.read", "topic.update", "topic.delete", "topic.approve",
        "knowledge.create", "knowledge.read", "knowledge.update", "knowledge.delete",
        "media.upload", "media.read", "media.delete", "media.organize",
        "media.view", "media.create", "media.update",
        "member.read", "member.update", "member.update_role",
        "member.invite", "member.remove", "member.resend_invitation", "member.revoke_invitation",
    ],
    "editor": [
        "workspace.read",
        "content.create", "content.read", "content.update",
        "content.publish", "content.submit_review", "content.approve", "content.reject", "content.export",
        "topic.create", "topic.read", "topic.update", "topic.approve",
        "knowledge.create", "knowledge.read", "knowledge.update",
        "media.upload", "media.read", "media.organize",
        "media.view", "media.create",
        "member.read",
        "license.view", "license.read",
    ],
    "viewer": [
        "workspace.read",
        "content.read",
        "topic.read",
        "knowledge.read",
        "media.read", "media.view",
        "member.read",
        "license.view", "license.read",
    ],
    "super_admin": ["*"],
    "admin": [
        "workspace.read", "workspace.write", "workspace.update", "workspace.delete",
        "workspace.manage_members", "workspace.manage_roles", "workspace.invite",
        "subscription.read", "subscription.manage",
        "billing.read", "billing.manage", "usage.read",
        "content.create", "content.read", "content.update", "content.delete",
        "content.publish", "content.submit_review", "content.approve", "content.reject", "content.export",
        "topic.create", "topic.read", "topic.update", "topic.delete", "topic.approve",
        "knowledge.create", "knowledge.read", "knowledge.update", "knowledge.delete",
        "media.upload", "media.read", "media.delete", "media.organize",
        "media.view", "media.create", "media.update",
        "member.read", "member.update", "member.update_role",
        "member.invite", "member.remove", "member.resend_invitation", "member.revoke_invitation",
        "license.view", "license.read", "license.activate", "license.deactivate", "license.revoke",
        "user.create", "user.read", "user.update", "user.manage_roles",
        "role.read", "role.update", "role.manage_permissions",
        "permission.read", "permission.create", "permission.update",
        "role.create", "workspace.transfer",
        "audit.read", "audit.write", "audit.export", "audit.admin",
        "email.resend",
        "support.view_workspace", "support.view_billing",
    ],
    "support": [
        "workspace.read",
        "subscription.read", "billing.read", "usage.read",
        "content.read",
        "topic.read",
        "knowledge.read",
        "media.read", "media.view",
        "member.read",
        "license.view", "license.read",
        "user.read",
        "audit.read", "audit.admin", "audit.webhooks",
        "support.view_workspace", "support.view_billing",
    ],
    "user": [
        "workspace.read", "workspace.create",
        "content.read",
        "topic.read",
        "knowledge.read",
        "media.view",
        "member.read",
        "license.view", "license.read",
        "subscription.read", "subscription.manage",
        "usage.read",
        "billing.read",
        "audit.read",
    ],
}

async def seed_permissions():
    """Seed RBAC roles and permissions (idempotent)."""
    async with get_seed_session() as session:
        # 1. Seed Roles
        print("\nSeeding roles...")
        role_map = {}
        for role_data in ROLES:
            result = await session.execute(
                text("SELECT id FROM roles WHERE name = :name"),
                {"name": role_data["name"]}
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
                }
            )
            role_map[role_data["name"]] = role_id
            print(f"  ✅ Created role: {role_data['name']}")

        # 2. Seed Permissions
        print("\nSeeding permissions...")
        permission_map = {}
        for perm in PERMISSIONS:
            name, display_name, description, resource, action = perm
            result = await session.execute(
                text("SELECT id FROM permissions WHERE name = :name"),
                {"name": name}
            )
            existing = result.fetchone()
            if existing:
                permission_map[name] = existing[0]
                print(f"  ℹ️  Permission already exists: {name}")
                continue
            
            perm_id = uuid4()
            await session.execute(
                text("""
                    INSERT INTO permissions (id, name, display_name, description, resource, action, created_at)
                    VALUES (:id, :name, :display_name, :description, :resource, :action, :created_at)
                """),
                {
                    "id": perm_id,
                    "name": name,
                    "display_name": display_name,
                    "description": description,
                    "resource": resource,
                    "action": action,
                    "created_at": utc_now(),
                }
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
            
            # Special case for super_admin
            if perm_names == ["*"]:
                actual_perm_names = list(permission_map.keys())
            else:
                actual_perm_names = perm_names

            for perm_name in actual_perm_names:
                if perm_name not in permission_map:
                    print(f"  ⚠️  Permission not found: {perm_name}")
                    continue
                
                perm_id = permission_map[perm_name]
                
                # Check if mapping exists
                result = await session.execute(
                    text("SELECT id FROM role_permissions WHERE role_id = :role_id AND permission_id = :perm_id"),
                    {"role_id": role_id, "perm_id": perm_id}
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
                    }
                )
                print(f"  ✅ Assigned {perm_name} to {role_name}")

if __name__ == "__main__":
    asyncio.run(seed_permissions())
