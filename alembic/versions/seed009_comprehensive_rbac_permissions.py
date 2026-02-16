# NOTE: This seed migration is superseded by scripts/seeds/.
# It remains in the migration chain for backward compatibility with existing databases.
# For new environments, use: python -m scripts.seeds.run_all

"""Seed comprehensive RBAC permissions

Revision ID: seed009
Revises: seed008
Create Date: 2025-10-23

This migration adds ALL permissions defined in the RBAC implementation plan (Phase 1):
- Complete workspace management permissions
- Billing & subscription permissions (owner-only)
- Content management permissions (create, read, update, delete, publish, review, approve, reject, export)
- Topic management permissions
- Knowledge base permissions
- Member management permissions (full suite)
- Global platform permissions (user, role, permission management)
- Audit permissions
- Support role permissions

This establishes the complete permission inventory for 100% RBAC coverage.

Reference: roles-permissions-improvement-plan.md
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone
from uuid import uuid4


# revision identifiers, used by Alembic.
revision = 'seed009'
down_revision = 'seed008'
branch_labels = None
depends_on = None


# ============================================================================
# PERMISSION DEFINITIONS
# ============================================================================

WORKSPACE_PERMISSIONS = [
    # Workspace Management
    ("workspace.read", "View Workspace", "workspace", "read", "View workspace details and settings"),
    ("workspace.write", "Write Workspace", "workspace", "write", "Write workspace details and settings"),
    ("workspace.update", "Update Workspace", "workspace", "update", "Edit workspace settings"),
    ("workspace.delete", "Delete Workspace", "workspace", "delete", "Delete workspace permanently"),
    ("workspace.transfer", "Transfer Ownership", "workspace", "transfer", "Transfer workspace ownership to another user"),
    ("workspace.manage_members", "Manage Members", "workspace", "manage_members", "Add/remove workspace members"),
    ("workspace.manage_roles", "Manage Roles", "workspace", "manage_roles", "Assign/change member roles"),
    ("workspace.invite", "Send Invitations", "workspace", "invite", "Send workspace invitations"),

    # Billing & Subscription (Owner Only!)
    ("subscription.read", "View Subscription", "subscription", "read", "View subscription details and status"),
    ("subscription.manage", "Manage Subscription", "subscription", "manage", "Change plans, update billing, cancel subscription"),
    ("billing.read", "View Billing", "billing", "read", "View billing history and invoices"),
    ("billing.manage", "Manage Billing", "billing", "manage", "Update payment methods and billing information"),
    ("usage.read", "View Usage", "usage", "read", "View usage statistics and limits"),

    # Content Management
    ("content.create", "Create Content", "content", "create", "Create new content"),
    ("content.read", "Read Content", "content", "read", "View content"),
    ("content.update", "Update Content", "content", "update", "Edit existing content"),
    ("content.delete", "Delete Content", "content", "delete", "Delete content"),
    # content.publish already exists from seed006
    ("content.submit_review", "Submit for Review", "content", "submit_review", "Submit content for approval"),
    ("content.approve", "Approve Content", "content", "approve", "Approve content for publishing"),
    ("content.reject", "Reject Content", "content", "reject", "Reject submitted content"),
    ("content.export", "Export Content", "content", "export", "Export content data"),

    # Topic Management
    ("topic.create", "Create Topics", "topic", "create", "Create new topics"),
    ("topic.read", "Read Topics", "topic", "read", "View topics"),
    ("topic.update", "Update Topics", "topic", "update", "Edit topics"),
    ("topic.delete", "Delete Topics", "topic", "delete", "Delete topics"),
    # topic.approve already exists from seed006

    # Knowledge Base
    ("knowledge.create", "Create Knowledge", "knowledge", "create", "Create knowledge bases"),
    ("knowledge.read", "Read Knowledge", "knowledge", "read", "View knowledge bases"),
    ("knowledge.update", "Update Knowledge", "knowledge", "update", "Update knowledge bases"),
    ("knowledge.delete", "Delete Knowledge", "knowledge", "delete", "Delete knowledge bases"),

    # Media Management (some already exist, adding missing ones)
    ("media.upload", "Upload Media", "media", "upload", "Upload media files"),
    ("media.read", "View Media", "media", "read", "View media library"),
    # media.delete already exists from seed008
    ("media.organize", "Organize Media", "media", "organize", "Organize media into folders"),

    # Member Management (some already exist, adding missing ones)
    # member.read, member.update, member.invite, member.remove already exist
    ("member.update_role", "Update Member Roles", "member", "update_role", "Change member roles"),
    ("member.resend_invitation", "Resend Invitations", "member", "resend_invitation", "Resend invitation emails"),
    ("member.revoke_invitation", "Revoke Invitations", "member", "revoke_invitation", "Cancel pending invitations"),
]

GLOBAL_PERMISSIONS = [
    # User Management (Platform Level)
    ("user.create", "Create Users", "user", "create", "Create new users"),
    ("user.read", "View Users", "user", "read", "View all users"),
    ("user.update", "Update Users", "user", "update", "Edit user profiles"),
    ("user.delete", "Delete Users", "user", "delete", "Delete users"),
    ("user.manage_roles", "Manage User Roles", "user", "manage_roles", "Assign global roles to users"),

    # Role & Permission Management
    ("role.create", "Create Roles", "role", "create", "Create custom roles"),
    ("role.read", "View Roles", "role", "read", "View all roles"),
    ("role.update", "Update Roles", "role", "update", "Update role definitions"),
    ("role.delete", "Delete Roles", "role", "delete", "Delete custom roles"),
    ("role.manage_permissions", "Manage Permissions", "role", "manage_permissions", "Assign permissions to roles"),

    ("permission.create", "Create Permissions", "permission", "create", "Create new permissions"),
    ("permission.read", "View Permissions", "permission", "read", "View all permissions"),
    ("permission.update", "Update Permissions", "permission", "update", "Update permission definitions"),
    ("permission.delete", "Delete Permissions", "permission", "delete", "Delete permissions"),

    # Platform Management
    ("audit.read", "View Audit Logs", "audit", "read", "View audit logs"),
    ("audit.export", "Export Audit Logs", "audit", "export", "Export audit logs"),

    # Support Staff Permissions
    ("support.view_workspace", "View Any Workspace", "support", "view_workspace", "View any workspace (read-only)"),
    ("support.view_billing", "View Billing Info", "support", "view_billing", "View billing information for support"),
]


# ============================================================================
# ROLE PERMISSION ASSIGNMENTS
# ============================================================================

ROLE_PERMISSION_ASSIGNMENTS = {
    # ========== WORKSPACE ROLES ==========

    "workspace_owner": [
        # Full workspace control including billing
        "workspace.read", "workspace.write", "workspace.update", "workspace.delete", "workspace.transfer",
        "workspace.manage_members", "workspace.manage_roles", "workspace.invite",

        # BILLING & SUBSCRIPTION (OWNER ONLY!)
        "subscription.read", "subscription.manage",
        "billing.read", "billing.manage",
        "usage.read",

        # Content management (full)
        "content.create", "content.read", "content.update", "content.delete",
        "content.publish", "content.submit_review", "content.approve", "content.reject", "content.export",

        # Topics (full)
        "topic.create", "topic.read", "topic.update", "topic.delete", "topic.approve",

        # Knowledge (full)
        "knowledge.create", "knowledge.read", "knowledge.update", "knowledge.delete",

        # Media (full)
        "media.upload", "media.read", "media.delete", "media.organize",
        "media.view", "media.create", "media.update",  # Backward compatibility

        # Members (full)
        "member.read", "member.update", "member.update_role",
        "member.invite", "member.remove", "member.resend_invitation", "member.revoke_invitation",

        # License (full)
        "license.view", "license.activate", "license.deactivate",
    ],

    "workspace_admin": [
        # Workspace management (NO delete, NO transfer, NO billing)
        "workspace.read", "workspace.write", "workspace.update",
        "workspace.manage_members", "workspace.manage_roles", "workspace.invite",

        # NO BILLING/SUBSCRIPTION ACCESS!
        "usage.read",  # Can view usage only
        "license.view", "license.activate",  # Can view/activate licenses

        # Content management (full)
        "content.create", "content.read", "content.update", "content.delete",
        "content.publish", "content.submit_review", "content.approve", "content.reject", "content.export",

        # Topics (full)
        "topic.create", "topic.read", "topic.update", "topic.delete", "topic.approve",

        # Knowledge (full)
        "knowledge.create", "knowledge.read", "knowledge.update", "knowledge.delete",

        # Media (full)
        "media.upload", "media.read", "media.delete", "media.organize",
        "media.view", "media.create", "media.update",

        # Members (full)
        "member.read", "member.update", "member.update_role",
        "member.invite", "member.remove", "member.resend_invitation", "member.revoke_invitation",
    ],

    "editor": [
        # Workspace (read only)
        "workspace.read",

        # Content (can create/edit/publish own content, cannot delete)
        "content.create", "content.read", "content.update",
        "content.publish", "content.submit_review", "content.approve", "content.reject", "content.export",

        # Topics (can create/edit)
        "topic.create", "topic.read", "topic.update", "topic.approve",

        # Knowledge (can create/edit)
        "knowledge.create", "knowledge.read", "knowledge.update",

        # Media (can upload/view)
        "media.upload", "media.read", "media.organize",
        "media.view", "media.create",  # Backward compatibility

        # Members (read only)
        "member.read",

        # License (view only)
        "license.view",
    ],

    "viewer": [
        # Workspace (read only)
        "workspace.read",

        # Content (read only)
        "content.read",

        # Topics (read only)
        "topic.read",

        # Knowledge (read only)
        "knowledge.read",

        # Media (read only)
        "media.read", "media.view",

        # Members (read only)
        "member.read",

        # License (view only)
        "license.view",
    ],

    # ========== GLOBAL ROLES ==========

    "super_admin": [
        # All permissions (super admin bypasses checks but we assign for audit purposes)
        "*"  # Special marker meaning "all permissions"
    ],

    "admin": [
        # Platform management (similar to super_admin but less destructive permissions)
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

        "license.view", "license.activate", "license.deactivate", "license.revoke",

        "user.create", "user.read", "user.update", "user.manage_roles",
        "role.read", "role.update", "role.manage_permissions",
        "permission.read",
        "audit.read", "audit.export",
        "support.view_workspace", "support.view_billing",
    ],

    "support": [
        # Customer support role - read-only access
        "workspace.read",
        "subscription.read", "billing.read", "usage.read",
        "content.read",
        "topic.read",
        "knowledge.read",
        "media.read", "media.view",
        "member.read",
        "license.view", "license.activate", "license.deactivate",
        "user.read",
        "audit.read",
        "support.view_workspace", "support.view_billing",
    ],

    "user": [
        # Default authenticated user
        "workspace.read",
        "content.read",
        "topic.read",
        "knowledge.read",
        "media.read", "media.view",
        "member.read",
        "license.view", "license.activate", "license.deactivate",
    ],
}


def upgrade():
    """Add comprehensive RBAC permissions."""
    conn = op.get_bind()

    all_permissions = WORKSPACE_PERMISSIONS + GLOBAL_PERMISSIONS
    permission_map = {}

    print("\n" + "=" * 60)
    print("SEEDING COMPREHENSIVE RBAC PERMISSIONS")
    print("=" * 60)

    # Step 1: Create all permissions
    print("\n1. Creating permissions...")
    created_count = 0
    existing_count = 0

    for perm_data in all_permissions:
        name, display_name, resource, action, description = perm_data

        # Check if exists
        result = conn.execute(
            sa.text("SELECT id FROM permissions WHERE name = :name"),
            {'name': name}
        ).fetchone()

        if result:
            permission_map[name] = result[0]
            existing_count += 1
            print(f"  ℹ️  {name}")
        else:
            perm_id = str(uuid4())
            conn.execute(
                sa.text("""
                    INSERT INTO permissions (id, name, display_name, description, resource, action, created_at)
                    VALUES (:id, :name, :display_name, :description, :resource, :action, :created_at)
                """),
                {
                    'id': perm_id,
                    'name': name,
                    'display_name': display_name,
                    'description': description,
                    'resource': resource,
                    'action': action,
                    'created_at': datetime.now(timezone.utc)
                }
            )
            permission_map[name] = perm_id
            created_count += 1
            print(f"  ✅ {name}")

    print(f"\n  Created: {created_count}, Existed: {existing_count}")

    # Step 2: Get all roles
    print("\n2. Loading roles...")
    roles = conn.execute(sa.text("SELECT id, name FROM roles")).fetchall()
    role_map = {row[1]: row[0] for row in roles}
    print(f"  Found {len(role_map)} roles: {', '.join(role_map.keys())}")

    # Step 3: Assign permissions to roles
    print("\n3. Assigning permissions to roles...")
    total_assigned = 0
    total_existing = 0

    for role_name, permission_names in ROLE_PERMISSION_ASSIGNMENTS.items():
        if role_name not in role_map:
            print(f"  ⚠️  Role not found: {role_name}")
            continue

        role_id = role_map[role_name]
        assigned_count = 0
        existing_count = 0

        # Handle super_admin special case (all permissions)
        if permission_names == ["*"]:
            permission_names = list(permission_map.keys())

        for perm_name in permission_names:
            if perm_name not in permission_map:
                print(f"  ⚠️  Permission not found: {perm_name}")
                continue

            perm_id = permission_map[perm_name]

            # Check if mapping exists
            result = conn.execute(
                sa.text("""
                    SELECT id FROM role_permissions
                    WHERE role_id = :role_id AND permission_id = :permission_id
                """),
                {'role_id': role_id, 'permission_id': perm_id}
            ).fetchone()

            if not result:
                conn.execute(
                    sa.text("""
                        INSERT INTO role_permissions (id, role_id, permission_id, created_at)
                        VALUES (:id, :role_id, :permission_id, :created_at)
                    """),
                    {
                        'id': str(uuid4()),
                        'role_id': role_id,
                        'permission_id': perm_id,
                        'created_at': datetime.now(timezone.utc)
                    }
                )
                assigned_count += 1
                total_assigned += 1
            else:
                existing_count += 1
                total_existing += 1

        print(f"  ✅ {role_name}: {assigned_count} new, {existing_count} existing")

    print(f"\n  Total new assignments: {total_assigned}")
    print(f"  Total existing: {total_existing}")

    print("\n" + "=" * 60)
    print("✅ COMPREHENSIVE RBAC PERMISSIONS SEEDED SUCCESSFULLY!")
    print("=" * 60 + "\n")


def downgrade():
    """Remove comprehensive RBAC permissions."""
    conn = op.get_bind()

    print("\nRemoving comprehensive RBAC permissions...")

    all_permissions = WORKSPACE_PERMISSIONS + GLOBAL_PERMISSIONS
    permission_names = [perm[0] for perm in all_permissions]

    # Delete role-permission mappings
    for perm_name in permission_names:
        result = conn.execute(
            sa.text("SELECT id FROM permissions WHERE name = :name"),
            {'name': perm_name}
        ).fetchone()

        if result:
            perm_id = result[0]
            conn.execute(
                sa.text("DELETE FROM role_permissions WHERE permission_id = :perm_id"),
                {'perm_id': perm_id}
            )

    # Delete permissions
    for perm_name in permission_names:
        conn.execute(
            sa.text("DELETE FROM permissions WHERE name = :name"),
            {'name': perm_name}
        )

    print("✅ Comprehensive RBAC permissions removed")
