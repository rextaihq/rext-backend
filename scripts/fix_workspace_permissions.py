"""
Fix workspace permissions for existing workspaces.

This script grants workspace admin role all necessary permissions for existing workspaces.
Run this after the workspace service was updated to include workspace permissions.

Usage:
    python scripts/fix_workspace_permissions.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.api.database.async_database import get_async_db
from src.api.models.user_models.roles import Role
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.utils.logger import logger


async def fix_workspace_permissions():
    """Add missing permissions to all workspace admin roles."""

    # Resources that workspace admins should have access to
    required_resources = ["workspace", "topic", "content", "member", "knowledge"]

    async for db in get_async_db():
        try:
            # Get all workspace admin roles (name contains 'workspace_admin')
            result = await db.execute(
                select(Role).where(
                    Role.name.like("%workspace_admin%") | Role.name.like("%workspace_owner%")
                )
            )
            workspace_admin_roles = result.scalars().all()

            logger.info(f"Found {len(workspace_admin_roles)} workspace admin roles")

            # Get all permissions for required resources
            result = await db.execute(
                select(Permission).where(
                    Permission.resource.in_(required_resources)
                )
            )
            permissions = result.scalars().all()

            logger.info(f"Found {len(permissions)} permissions for resources: {required_resources}")

            # For each workspace admin role, ensure all permissions are assigned
            permissions_added = 0
            for role in workspace_admin_roles:
                for permission in permissions:
                    # Check if permission already assigned
                    result = await db.execute(
                        select(RolePermission).where(
                            RolePermission.role_id == role.id,
                            RolePermission.permission_id == permission.id
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if not existing:
                        # Add permission
                        db.add(RolePermission(
                            role_id=role.id,
                            permission_id=permission.id
                        ))
                        permissions_added += 1
                        logger.info(
                            f"Added permission '{permission.name}' to role '{role.name}' "
                            f"(workspace_id: {role.workspace_id})"
                        )

            # Commit all changes
            await db.commit()

            logger.info(f"✅ Successfully added {permissions_added} permissions")

        except Exception as e:
            logger.error(f"Error fixing workspace permissions: {e}", exc_info=True)
            await db.rollback()
            raise

        break  # Only use first DB session


if __name__ == "__main__":
    print("🔧 Fixing workspace permissions...")
    asyncio.run(fix_workspace_permissions())
    print("✅ Done!")
