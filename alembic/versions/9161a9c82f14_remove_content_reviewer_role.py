"""remove_content_reviewer_role

Remove the content_reviewer role from the system as it's no longer needed.

The content_reviewer role was originally created for approval workflows but is not
being used in the current implementation. All approval workflow functionality is
handled by workspace_admin and workspace_owner roles.

This migration:
- Removes content_reviewer role from the roles table
- Removes all role_permissions for content_reviewer
- Removes any user_roles assignments (should be 0)
- Checks for invitations using this role (should be 0)

Revision ID: 9161a9c82f14
Revises: e69e4f63e096
Create Date: 2025-10-24 15:29:13.778384

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '9161a9c82f14'
down_revision: Union[str, Sequence[str], None] = 'e69e4f63e096'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

Base = declarative_base()


class Role(Base):
    __tablename__ = 'roles'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(100))


class RolePermission(Base):
    __tablename__ = 'role_permissions'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    role_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))


class UserRole(Base):
    __tablename__ = 'user_roles'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    role_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))


def upgrade() -> None:
    """Remove content_reviewer role and all its assignments."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    try:
        print("\n" + "="*80)
        print("REMOVING CONTENT_REVIEWER ROLE")
        print("="*80)

        # Find the role
        reviewer_role = session.query(Role).filter_by(name='content_reviewer').first()

        if not reviewer_role:
            print("\n✓ content_reviewer role not found - already removed or never existed")
            print("="*80 + "\n")
            return

        role_id = reviewer_role.id
        print(f"\n→ Found content_reviewer role: {role_id}")

        # 1. Check for any user assignments (should be 0)
        user_assignments = session.query(UserRole).filter_by(role_id=role_id).count()
        if user_assignments > 0:
            print(f"\n⚠️  WARNING: {user_assignments} users have this role!")
            print("   Removing user assignments...")
            deleted_users = session.query(UserRole).filter_by(role_id=role_id).delete(synchronize_session=False)
            print(f"  ✓ Removed {deleted_users} user role assignments")
        else:
            print("  ✓ No user assignments found")

        # 2. Check for any invitation assignments (should be 0)
        invitation_count = session.execute(
            text("SELECT COUNT(*) FROM user_invitations WHERE role_id = :role_id"),
            {"role_id": str(role_id)}
        ).scalar()

        if invitation_count and invitation_count > 0:
            print(f"\n⚠️  WARNING: {invitation_count} invitations reference this role!")
            print("   Note: You may want to manually update these invitations to use a different role.")
            print("   Invitations will remain but won't be usable until role_id is updated.")
        else:
            print("  ✓ No invitations reference this role")

        # 3. Delete role_permissions
        deleted_perms = session.query(RolePermission).filter_by(
            role_id=role_id
        ).delete(synchronize_session=False)
        print(f"  ✓ Deleted {deleted_perms} role permissions")

        # 4. Delete the role
        session.delete(reviewer_role)
        session.commit()

        print(f"  ✓ Deleted content_reviewer role")
        print("\n" + "="*80)
        print("✓ CONTENT_REVIEWER ROLE REMOVAL COMPLETE!")
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
    """Restore content_reviewer role.

    Note: This is a no-op downgrade. If you need to restore the content_reviewer role,
    you can re-apply migration a973deb06456_add_content_reviewer_role.py manually.

    To restore:
    1. Downgrade past this migration
    2. Re-run migration a973deb06456
    """
    print("\n" + "="*80)
    print("DOWNGRADE: CONTENT_REVIEWER ROLE RESTORATION")
    print("="*80)
    print("\n⚠️  This is a no-op downgrade.")
    print("   To restore content_reviewer role, you need to:")
    print("   1. Downgrade to before migration a973deb06456")
    print("   2. Re-run migration a973deb06456_add_content_reviewer_role.py")
    print("\n" + "="*80 + "\n")
    pass
