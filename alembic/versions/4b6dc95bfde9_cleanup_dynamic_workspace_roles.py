"""cleanup_dynamic_workspace_roles

Migrate existing dynamic workspace admin roles ({workspace_id}_admin) to use
the standardized workspace_owner system role. This prevents role explosion
and ensures consistent permissions across all workspaces.

Revision ID: 4b6dc95bfde9
Revises: 8021696d2e4f
Create Date: 2025-10-20 11:02:31.374094

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
import uuid

# revision identifiers, used by Alembic.
revision: str = '4b6dc95bfde9'
down_revision: Union[str, Sequence[str], None] = '8021696d2e4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

Base = declarative_base()


# Lightweight models for migration
class Role(Base):
    __tablename__ = 'roles'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(100), unique=True, nullable=False)
    is_system_role = sa.Column(sa.Boolean, default=False)


class UserRole(Base):
    __tablename__ = 'user_roles'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    user_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    role_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    workspace_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))


class RolePermission(Base):
    __tablename__ = 'role_permissions'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    role_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    permission_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)


def upgrade() -> None:
    """
    Migrate dynamic workspace admin roles to workspace_owner system role.

    This migration:
    1. Finds all dynamic workspace roles (pattern: {uuid}_admin)
    2. Gets the workspace_owner system role
    3. Updates user_roles to point to workspace_owner
    4. Deletes role_permissions for dynamic roles
    5. Deletes the dynamic roles themselves
    """
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    try:
        print("\n" + "="*80)
        print("CLEANING UP DYNAMIC WORKSPACE ROLES")
        print("="*80)

        # Get workspace_owner system role
        owner_role = session.query(Role).filter_by(
            name='workspace_owner',
            is_system_role=True
        ).first()

        if not owner_role:
            print("\n⚠️  WARNING: workspace_owner system role not found")
            print("    Skipping migration. Please ensure role seeding migrations have been run.")
            session.close()
            return

        print(f"\n✓ Found workspace_owner system role: {owner_role.id}")

        # Find all dynamic workspace admin roles
        # Pattern: {workspace_id}_admin where workspace_id is a UUID
        dynamic_roles = session.query(Role).filter(
            Role.name.like('%_admin'),
            Role.is_system_role == False
        ).all()

        if not dynamic_roles:
            print("\n✓ No dynamic workspace roles found. Migration complete!")
            session.close()
            return

        print(f"\n✓ Found {len(dynamic_roles)} dynamic workspace roles to migrate:")

        migrated_count = 0
        for dynamic_role in dynamic_roles:
            print(f"\n  → Migrating role: {dynamic_role.name}")

            # Count affected user_roles
            affected_user_roles = session.query(UserRole).filter_by(
                role_id=dynamic_role.id
            ).count()

            if affected_user_roles > 0:
                print(f"    - Updating {affected_user_roles} user role assignments")

                # Update user_roles to point to workspace_owner
                session.query(UserRole).filter_by(
                    role_id=dynamic_role.id
                ).update({'role_id': owner_role.id}, synchronize_session=False)

            # Delete role_permissions for dynamic role
            deleted_perms = session.query(RolePermission).filter_by(
                role_id=dynamic_role.id
            ).delete(synchronize_session=False)

            if deleted_perms > 0:
                print(f"    - Deleted {deleted_perms} role permissions")

            # Delete the dynamic role itself
            session.delete(dynamic_role)
            migrated_count += 1
            print(f"    - ✓ Deleted dynamic role")

        session.commit()

        print("\n" + "="*80)
        print(f"✓ MIGRATION COMPLETE!")
        print(f"  Successfully migrated {migrated_count} dynamic roles to workspace_owner")
        print("="*80 + "\n")

    except Exception as e:
        session.rollback()
        print(f"\n❌ ERROR: Migration failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        session.close()


def downgrade() -> None:
    """
    Downgrade is not supported for this migration.

    Once dynamic roles are deleted and users are assigned to workspace_owner,
    we cannot recreate the original dynamic role structure as we don't have
    the original workspace_id -> dynamic_role_id mapping.

    This is acceptable because:
    1. workspace_owner provides all necessary permissions
    2. Dynamic roles were an anti-pattern (role explosion)
    3. Forward-only migration is safer for RBAC systems
    """
    print("\n⚠️  WARNING: Downgrade not supported for cleanup_dynamic_workspace_roles migration")
    print("   Dynamic workspace roles cannot be recreated as original mappings are lost.")
    print("   The workspace_owner system role provides all necessary permissions.")
    pass
