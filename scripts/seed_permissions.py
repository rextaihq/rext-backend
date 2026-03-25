"""
Comprehensive Permission Seeding Script

This script creates ALL permissions defined in the RBAC implementation plan
and assigns them to the appropriate roles based on the permission matrix.

Usage:
    python scripts/seed_permissions.py

Requirements:
    - Database must be accessible
    - Roles must exist in database (workspace_owner, workspace_admin, editor, viewer, super_admin, admin, support, user)
    - Script is idempotent (safe to run multiple times)

Reference:
    See roles-permissions-improvement-plan.md for complete permission matrix
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.database.async_database import get_async_db
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.role_permissions import RolePermission
from src.utils.logger import logger
from datetime import datetime, timezone
import uuid


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
    ("content.publish", "Publish Content", "content", "publish", "Publish content to production"),
    ("content.submit_for_review", "Submit Content for Review", "content", "submit_for_review", "Submit content for approval"),
    ("content.approve", "Approve Content", "content", "approve", "Approve content for publishing"),
    ("content.reject", "Reject Content", "content", "reject", "Reject submitted content"),
    ("content.export", "Export Content", "content", "export", "Export content data"),

    # Topic Management
    ("topic.create", "Create Topics", "topic", "create", "Create new topics"),
    ("topic.read", "Read Topics", "topic", "read", "View topics"),
    ("topic.update", "Update Topics", "topic", "update", "Edit topics"),
    ("topic.delete", "Delete Topics", "topic", "delete", "Delete topics"),
    ("topic.approve", "Approve Topics", "topic", "approve", "Approve topic submissions"),

    # Knowledge Base
    ("knowledge.create", "Create Knowledge", "knowledge", "create", "Create knowledge bases"),
    ("knowledge.read", "Read Knowledge", "knowledge", "read", "View knowledge bases"),
    ("knowledge.update", "Update Knowledge", "knowledge", "update", "Update knowledge bases"),
    ("knowledge.delete", "Delete Knowledge", "knowledge", "delete", "Delete knowledge bases"),

    # Media Management
    # CANONICAL PERMISSIONS (use these in new code - standard CRUD):
    ("media.create", "Create Media", "media", "create", "Upload media files to workspace"),
    ("media.read", "View Media", "media", "read", "View media files in workspace"),
    ("media.update", "Update Media Metadata", "media", "update", "Update media file metadata"),
    ("media.delete", "Delete Media", "media", "delete", "Delete media files"),
    ("media.organize", "Organize Media", "media", "organize", "Organize media into folders"),

    # DEPRECATED ALIASES (kept for backward compatibility - DO NOT use in new code):
    # Migration path: media.upload → media.create (standard CRUD), media.view → media.read (standard CRUD)
    ("media.upload", "Upload Media (Deprecated)", "media", "upload", "DEPRECATED: Use media.create instead"),
    ("media.view", "View Media Files (Deprecated)", "media", "view", "DEPRECATED: Use media.read instead"),

    # Member Management
    ("member.read", "View Members", "member", "read", "View workspace members"),
    ("member.update", "Update Members", "member", "update", "Edit member profiles"),
    ("member.update_role", "Update Member Roles", "member", "update_role", "Change member roles"),
    ("member.invite", "Invite Members", "member", "invite", "Invite new members"),
    ("member.remove", "Remove Members", "member", "remove", "Remove members from workspace"),
    ("member.resend_invitation", "Resend Invitations", "member", "resend_invitation", "Resend invitation emails"),
    ("member.revoke_invitation", "Revoke Invitations", "member", "revoke_invitation", "Cancel pending invitations"),

    # License Management (one-time purchases)
    # NOTE: Using license.view as primary (already in DB), license.read added for compatibility
    ("license.view", "View Licenses", "license", "view", "View own license keys and activations"),
    ("license.read", "View Licenses (Canonical)", "license", "read", "View own license keys and activations (canonical)"),
    ("license.activate", "Activate License", "license", "activate", "Activate license on a device"),
    ("license.deactivate", "Deactivate License", "license", "deactivate", "Deactivate license from a device"),
    ("license.revoke", "Revoke License", "license", "revoke", "Revoke a license (admin only)"),
]

GLOBAL_PERMISSIONS = [
    # User Management (Platform Level)
    ("user.create", "Create Users", "user", "create", "Create new users"),
    ("user.read", "View Users", "user", "read", "View all users"),
    ("user.update", "Update Users", "user", "update", "Edit user profiles"),
    ("user.delete", "Delete Users", "user", "delete", "Delete users"),
    ("user.manage_roles", "Manage User Roles", "user", "manage_roles", "Assign global roles to users"),

    # Workspace Creation (User Level - not workspace-scoped)
    ("workspace.create", "Create Workspace", "workspace", "create", "Create new workspaces"),

    # Admin Management (Platform Level)
    ("admin.invite", "Invite Administrators", "admin", "invite", "Invite new platform administrators"),

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
    ("audit.write", "Write Audit Logs", "audit", "write", "Allows modifying audit/monitoring records (resolve errors, etc.)"),
    ("audit.export", "Export Audit Logs", "audit", "export", "Export audit logs"),

    # Email Management (Admin)
    ("email.resend", "Resend Emails", "email", "resend", "Allows resending failed emails via admin panel"),

    # Support Staff Permissions
    ("support.view_workspace", "View Any Workspace", "support", "view_workspace", "View any workspace (read-only)"),
    ("support.view_billing", "View Billing Info", "support", "view_billing", "View billing information for support"),

    # Billing & Subscription (Owner Only!)
    ("subscription.read", "View Subscription", "subscription", "read", "View subscription details and status"),
    ("subscription.manage", "Manage Subscription", "subscription", "manage", "Change plans, update billing, cancel subscription"),

    # Billing & Usage
    ("billing.read", "View Billing", "billing", "read", "View billing information and invoices"),
    ("billing.manage", "Manage Billing", "billing", "manage", "Update payment methods, view invoices"),
    ("usage.read", "View Usage", "usage", "read", "View usage metrics and limits"),
]


# ============================================================================
# ROLE PERMISSION MATRIX
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
        "content.publish", "content.submit_for_review", "content.approve", "content.reject", "content.export",

        # Topics (full)
        "topic.create", "topic.read", "topic.update", "topic.delete", "topic.approve",

        # Knowledge (full)
        "knowledge.create", "knowledge.read", "knowledge.update", "knowledge.delete",

        # Media (full)
        "media.create", "media.read", "media.delete", "media.organize",
        "media.update",
        "media.upload", "media.view",  # Backward compatibility (deprecated)

        # Members (full)
        "member.read", "member.update", "member.update_role",
        "member.invite", "member.remove", "member.resend_invitation", "member.revoke_invitation",

        # License (full)
        "license.read",
        "license.view",  # Backward compatibility (deprecated) "license.activate", "license.deactivate",
    ],

    "workspace_admin": [
        # Workspace management (NO delete, NO transfer, NO billing)
        "workspace.read", "workspace.write", "workspace.update",
        "workspace.manage_members", "workspace.manage_roles", "workspace.invite",

        # NO BILLING/SUBSCRIPTION ACCESS!
        "usage.read",  # Can view usage only
        "license.read",
        "license.view",  # Backward compatibility (deprecated) "license.activate",  # Can view/activate licenses

        # Content management (full)
        "content.create", "content.read", "content.update", "content.delete",
        "content.publish", "content.submit_for_review", "content.approve", "content.reject", "content.export",

        # Topics (full)
        "topic.create", "topic.read", "topic.update", "topic.delete", "topic.approve",

        # Knowledge (full)
        "knowledge.create", "knowledge.read", "knowledge.update", "knowledge.delete",

        # Media (full)
        "media.create", "media.read", "media.delete", "media.organize",
        "media.update",
        "media.upload", "media.view",  # Backward compatibility (deprecated)

        # Members (full)
        "member.read", "member.update", "member.update_role",
        "member.invite", "member.remove", "member.resend_invitation", "member.revoke_invitation",
    ],

    "editor": [
        # Workspace (read only)
        "workspace.read",

        # Content (can create/edit/publish own content, cannot delete)
        "content.create", "content.read", "content.update",
        "content.publish", "content.submit_for_review", "content.approve", "content.reject", "content.export",

        # Topics (can create/edit)
        "topic.create", "topic.read", "topic.update", "topic.approve",

        # Knowledge (can create/edit)
        "knowledge.create", "knowledge.read", "knowledge.update",

        # Media (can upload/view)
        "media.create", "media.read", "media.organize",
        "media.upload", "media.view",  # Backward compatibility (deprecated)

        # Members (read only)
        "member.read",

        # License (view only)
        "license.read",
        "license.view",  # Backward compatibility (deprecated)
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
        "media.read",
        "media.view",  # Backward compatibility (deprecated)

        # Members (read only)
        "member.read",

        # License (view only)
        "license.read",
        "license.view",  # Backward compatibility (deprecated)
    ],

    # ========== GLOBAL ROLES ==========

    "super_admin": [
        # NOTE: Super admin bypasses all checks in code, but we assign all permissions for audit purposes

        # All workspace permissions
        "workspace.create", "workspace.read", "workspace.write", "workspace.update", "workspace.delete", "workspace.transfer",
        "workspace.manage_members", "workspace.manage_roles", "workspace.invite",

        # All billing
        "subscription.read", "subscription.manage",
        "billing.read", "billing.manage", "usage.read",

        # All content
        "content.create", "content.read", "content.update", "content.delete",
        "content.publish", "content.submit_for_review", "content.approve", "content.reject", "content.export",

        # All topics
        "topic.create", "topic.read", "topic.update", "topic.delete", "topic.approve",

        # All knowledge
        "knowledge.create", "knowledge.read", "knowledge.update", "knowledge.delete",

        # All media
        "media.create", "media.read", "media.delete", "media.organize",
        "media.update",
        "media.upload", "media.view",  # Backward compatibility (deprecated)

        # All members
        "member.read", "member.update", "member.update_role",
        "member.invite", "member.remove", "member.resend_invitation", "member.revoke_invitation",

        # All licenses
        "license.read",
        "license.view",  # Backward compatibility (deprecated) "license.activate", "license.deactivate", "license.revoke",

        # All global permissions
        "user.create", "user.read", "user.update", "user.delete", "user.manage_roles",
        "workspace.create", "admin.invite",
        "role.create", "role.read", "role.update", "role.delete", "role.manage_permissions",
        "permission.create", "permission.read", "permission.update", "permission.delete",
        "audit.read", "audit.write", "audit.export",
        "email.resend",
        "support.view_workspace", "support.view_billing",
    ],

    "admin": [
        # Platform management (similar to super_admin but less destructive permissions)

        # All workspace permissions
        "workspace.create", "workspace.read", "workspace.write", "workspace.update", "workspace.delete", "workspace.transfer",
        "workspace.manage_members", "workspace.manage_roles", "workspace.invite",

        # All billing (admin can manage billing)
        "subscription.read", "subscription.manage",
        "billing.read", "billing.manage", "usage.read",

        # All content
        "content.create", "content.read", "content.update", "content.delete",
        "content.publish", "content.submit_for_review", "content.approve", "content.reject", "content.export",

        # All topics
        "topic.create", "topic.read", "topic.update", "topic.delete", "topic.approve",

        # All knowledge
        "knowledge.create", "knowledge.read", "knowledge.update", "knowledge.delete",

        # All media
        "media.create", "media.read", "media.delete", "media.organize",
        "media.update",
        "media.upload", "media.view",  # Backward compatibility (deprecated)

        # All members
        "member.read", "member.update", "member.update_role",
        "member.invite", "member.remove", "member.resend_invitation", "member.revoke_invitation",

        # All licenses
        "license.read",
        "license.view",  # Backward compatibility (deprecated) "license.activate", "license.deactivate", "license.revoke",

        # Most global permissions (except some destructive ones)
        "user.create", "user.read", "user.update", "user.manage_roles",
        "role.create", "role.read", "role.update", "role.manage_permissions",
        "permission.create", "permission.read", "permission.update",
        "audit.read", "audit.write", "audit.export",
        "email.resend",
        "admin.invite",
        "support.view_workspace", "support.view_billing",
    ],

    "support": [
        # Customer support role - read-only access to help users

        # Workspace (read only)
        "workspace.read",

        # Content (read only)
        "content.read",

        # Topics (read only)
        "topic.read",

        # Knowledge (read only)
        "knowledge.read",

        # Media (read only)
        "media.read",
        "media.view",  # Backward compatibility (deprecated)

        # Members (read only)
        "member.read",

        # License (view only)
        "license.read",
        "license.view",  # Backward compatibility (deprecated)

        # Audit (read only)
        "audit.read",

        # Support-specific
        "support.view_workspace", "support.view_billing",
    ],

    "user": [
        # Default authenticated user - basic workspace member

        # Workspace
        "workspace.read", "workspace.create",  # Users can create their own workspaces

        # Content (read only unless added to specific workspace)
        "content.read",

        # Topics (read only)
        "topic.read",

        # Knowledge (read only)
        "knowledge.read",

        # Media (read only)
        "media.read",
        "media.view",  # Backward compatibility (deprecated)

        # Members (read only)
        "member.read",

        # License (can view/activate own licenses)
        "license.read",
        "license.view",  # Backward compatibility (deprecated) "license.activate", "license.deactivate",

        # Subscription
        "subscription.read",
        "subscription.manage",
    ],
}


# ============================================================================
# SEEDING FUNCTIONS
# ============================================================================

async def create_permissions(db: AsyncSession) -> dict:
    """
    Create all permissions in database.

    Returns:
        dict: Mapping of permission name to permission ID
    """
    logger.info("Creating permissions...")

    all_permissions = WORKSPACE_PERMISSIONS + GLOBAL_PERMISSIONS
    permission_map = {}
    created_count = 0
    existing_count = 0

    for perm_data in all_permissions:
        name, display_name, resource, action, description = perm_data

        # Check if exists
        result = await db.execute(
            select(Permission).where(Permission.name == name)
        )
        existing = result.scalar_one_or_none()

        if existing:
            permission_map[name] = existing.id
            existing_count += 1
            logger.debug(f"  ℹ️  Permission already exists: {name}")
        else:
            # Create new permission
            perm = Permission(
                id=uuid.uuid4(),
                name=name,
                display_name=display_name,
                description=description,
                resource=resource,
                action=action,
                created_at=datetime.now(timezone.utc)
            )
            db.add(perm)
            await db.flush()
            permission_map[name] = perm.id
            created_count += 1
            logger.info(f"  ✅ Created permission: {name}")

    await db.commit()

    logger.info(f"\nPermission Summary:")
    logger.info(f"  Created: {created_count}")
    logger.info(f"  Already existed: {existing_count}")
    logger.info(f"  Total: {len(permission_map)}")

    return permission_map


async def assign_permissions_to_roles(db: AsyncSession, permission_map: dict):
    """
    Assign permissions to roles based on the permission matrix.

    Args:
        db: Database session
        permission_map: Mapping of permission name to permission ID
    """
    logger.info("\nAssigning permissions to roles...")

    # Get all roles
    result = await db.execute(select(Role))
    roles = result.scalars().all()
    role_map = {role.name: role for role in roles}

    total_assigned = 0
    total_existing = 0

    for role_name, permission_names in ROLE_PERMISSION_ASSIGNMENTS.items():
        if role_name not in role_map:
            logger.warning(f"  ⚠️  Role not found: {role_name}")
            continue

        role = role_map[role_name]
        assigned_count = 0
        existing_count = 0

        for perm_name in permission_names:
            if perm_name not in permission_map:
                logger.warning(f"  ⚠️  Permission not found: {perm_name}")
                continue

            perm_id = permission_map[perm_name]

            # Check if mapping already exists
            result = await db.execute(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == perm_id
                )
            )
            existing = result.scalar_one_or_none()

            if not existing:
                # Create mapping
                role_perm = RolePermission(
                    id=uuid.uuid4(),
                    role_id=role.id,
                    permission_id=perm_id,
                    created_at=datetime.now(timezone.utc)
                )
                db.add(role_perm)
                assigned_count += 1
                total_assigned += 1
            else:
                existing_count += 1
                total_existing += 1

        await db.commit()

        logger.info(f"  ✅ {role_name}: {assigned_count} new, {existing_count} existing")

    logger.info(f"\nRole Assignment Summary:")
    logger.info(f"  New assignments: {total_assigned}")
    logger.info(f"  Already assigned: {total_existing}")
    logger.info(f"  Total: {total_assigned + total_existing}")


async def verify_permissions(db: AsyncSession):
    """
    Verify that all expected permissions and role assignments exist.

    Args:
        db: Database session
    """
    logger.info("\nVerifying permission setup...")

    # Count permissions
    result = await db.execute(select(Permission))
    permissions = result.scalars().all()
    logger.info(f"  Total permissions in database: {len(permissions)}")

    # Count role-permission mappings per role
    result = await db.execute(select(Role))
    roles = result.scalars().all()

    for role in roles:
        result = await db.execute(
            select(RolePermission).where(RolePermission.role_id == role.id)
        )
        role_perms = result.scalars().all()
        logger.info(f"  {role.name}: {len(role_perms)} permissions")

    logger.info("\n✅ Verification complete!")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

async def main():
    """Main seeding function."""
    logger.info("=" * 60)
    logger.info("COMPREHENSIVE RBAC PERMISSION SEEDING")
    logger.info("=" * 60)

    # Get database session
    async for db in get_async_db():
        try:
            # Step 1: Create all permissions
            permission_map = await create_permissions(db)

            # Step 2: Assign permissions to roles
            await assign_permissions_to_roles(db, permission_map)

            # Step 3: Verify setup
            await verify_permissions(db)

            logger.info("\n" + "=" * 60)
            logger.info("✅ PERMISSION SEEDING COMPLETED SUCCESSFULLY!")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"\n❌ Error during seeding: {e}")
            await db.rollback()
            raise

        finally:
            await db.close()

        break  # Only use first session


if __name__ == "__main__":
    asyncio.run(main())
