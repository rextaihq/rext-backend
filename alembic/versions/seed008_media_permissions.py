# NOTE: This seed migration is superseded by scripts/seeds/.
# It remains in the migration chain for backward compatibility with existing databases.
# For new environments, use: python -m scripts.seeds.run_all

"""Seed media permissions

Revision ID: seed008
Revises: seed007
Create Date: 2025-10-22

This migration adds media management permissions:
- media.view: View media files in workspace
- media.create: Upload new media files
- media.update: Update media metadata
- media.delete: Delete media files

These permissions are assigned to workspace roles (owner, admin, editor).
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone
from uuid import uuid4


# revision identifiers, used by Alembic.
revision = 'seed008'
down_revision = 'seed007'
branch_labels = None
depends_on = None


def upgrade():
    """Add media permissions."""
    conn = op.get_bind()

    # Media permissions to create
    media_permissions = [
        {     
            'name': 'media.view',
            'display_name': 'View Media',
            'description': 'View media files in workspace',
            'resource': 'media',
            'action': 'view'
        },
        {
            'name': 'media.create',
            'display_name': 'Upload Media',
            'description': 'Upload new media files to workspace',
            'resource': 'media',
            'action': 'create'
        },
        {
            'name': 'media.update',
            'display_name': 'Update Media',
            'description': 'Update media file metadata',
            'resource': 'media',
            'action': 'update'
        },
        {
            'name': 'media.delete',
            'display_name': 'Delete Media',
            'description': 'Delete media files from workspace',
            'resource': 'media',
            'action': 'delete'
        },
    ]

    # Insert permissions
    permission_ids = {}
    for perm in media_permissions:
        # Check if permission already exists
        result = conn.execute(
            sa.text("SELECT id FROM permissions WHERE name = :name"),
            {'name': perm['name']}
        ).fetchone()

        if result:
            permission_ids[perm['name']] = result[0]
            print(f"Permission {perm['name']} already exists")
        else:
            perm_id = str(uuid4())
            conn.execute(
                sa.text("""
                    INSERT INTO permissions (id, name, display_name, description, resource, action, created_at)
                    VALUES (:id, :name, :display_name, :description, :resource, :action, :created_at)
                """),
                {
                    'id': perm_id,
                    'name': perm['name'],
                    'display_name': perm['display_name'],
                    'description': perm['description'],
                    'resource': perm['resource'],
                    'action': perm['action'],
                    'created_at': datetime.now(timezone.utc)
                }
            )
            permission_ids[perm['name']] = perm_id
            print(f"Created permission: {perm['name']}")

    # Assign permissions to roles
    # Get all role IDs
    roles = conn.execute(
        sa.text("SELECT id, name FROM roles")
    ).fetchall()

    role_map = {row[1]: row[0] for row in roles}

    # Define which roles get which permissions
    # super_admin, admin, workspace_owner, workspace_admin, editor get all media permissions
    full_access_roles = ['super_admin', 'admin', 'workspace_owner', 'workspace_admin', 'editor']

    # viewer gets only media.view
    view_only_roles = ['viewer']

    for role_name, role_id in role_map.items():
        permissions_to_assign = []

        if role_name in full_access_roles:
            # Full media access
            permissions_to_assign = ['media.view', 'media.create', 'media.update', 'media.delete']
        elif role_name in view_only_roles:
            # View only
            permissions_to_assign = ['media.view']

        # Assign permissions
        for perm_name in permissions_to_assign:
            if perm_name in permission_ids:
                # Check if role-permission mapping already exists
                result = conn.execute(
                    sa.text("""
                        SELECT id FROM role_permissions
                        WHERE role_id = :role_id AND permission_id = :permission_id
                    """),
                    {
                        'role_id': role_id,
                        'permission_id': permission_ids[perm_name]
                    }
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
                            'permission_id': permission_ids[perm_name],
                            'created_at': datetime.now(timezone.utc)
                        }
                    )
                    print(f"Assigned {perm_name} to {role_name}")


def downgrade():
    """Remove media permissions."""
    conn = op.get_bind()

    # Delete role-permission mappings
    conn.execute(
        sa.text("""
            DELETE FROM role_permissions
            WHERE permission_id IN (
                SELECT id FROM permissions WHERE resource = 'media'
            )
        """)
    )

    # Delete permissions
    conn.execute(
        sa.text("DELETE FROM permissions WHERE resource = 'media'")
    )

    print("Removed media permissions")
