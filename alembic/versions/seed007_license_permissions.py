"""Seed license permissions

Revision ID: seed007
Revises: ls20251020
Create Date: 2025-10-21

This migration adds license management permissions for one-time purchases:
- license.view: View own licenses
- license.activate: Activate license on device
- license.deactivate: Deactivate license from device
- license.revoke: Revoke license (admin only)

These permissions are assigned to all roles by default except license.revoke
which is admin-only.
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime
from uuid import uuid4


# revision identifiers, used by Alembic.
revision = 'seed007'
down_revision = 'ls20251020'
branch_labels = None
depends_on = None


def upgrade():
    """Add license permissions."""
    conn = op.get_bind()

    # License permissions to create
    license_permissions = [
        {
            'name': 'license.view',
            'display_name': 'View Licenses',
            'description': 'View own license keys and activations',
            'resource': 'license',
            'action': 'view'
        },
        {
            'name': 'license.activate',
            'display_name': 'Activate License',
            'description': 'Activate license on a device or instance',
            'resource': 'license',
            'action': 'activate'
        },
        {
            'name': 'license.deactivate',
            'display_name': 'Deactivate License',
            'description': 'Deactivate license from a device or instance',
            'resource': 'license',
            'action': 'deactivate'
        },
        {
            'name': 'license.revoke',
            'display_name': 'Revoke License',
            'description': 'Revoke a license (admin only)',
            'resource': 'license',
            'action': 'revoke'
        },
    ]

    # Insert permissions
    permission_ids = {}
    for perm in license_permissions:
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
                    'created_at': datetime.utcnow()
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

    # Assign to all roles (except license.revoke which is admin-only)
    user_permissions = ['license.view', 'license.activate', 'license.deactivate']
    admin_only_permissions = ['license.revoke']

    for role_name, role_id in role_map.items():
        # All roles get basic license permissions
        for perm_name in user_permissions:
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
                            'created_at': datetime.utcnow()
                        }
                    )
                    print(f"Assigned {perm_name} to {role_name}")

        # Only super_admin gets revoke permission
        if role_name == 'super_admin':
            for perm_name in admin_only_permissions:
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
                                'created_at': datetime.utcnow()
                            }
                        )
                        print(f"Assigned {perm_name} to {role_name} (admin only)")


def downgrade():
    """Remove license permissions."""
    conn = op.get_bind()

    # Delete role-permission mappings
    conn.execute(
        sa.text("""
            DELETE FROM role_permissions
            WHERE permission_id IN (
                SELECT id FROM permissions WHERE resource = 'license'
            )
        """)
    )

    # Delete permissions
    conn.execute(
        sa.text("DELETE FROM permissions WHERE resource = 'license'")
    )

    print("Removed license permissions")
