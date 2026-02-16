"""assign_new_permissions_to_roles

Assign the newly created permissions to appropriate roles:
- super_admin: All new permissions (10)
- workspace_owner: All new permissions (10)
- workspace_admin: Content workflow + member management (8, no billing/ownership)
- editor: Only submit_for_review (1)

Revision ID: 064f9978fc69
Revises: d0f311c36ace
Create Date: 2025-10-20 11:09:51.068470

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone
import uuid

# revision identifiers, used by Alembic.
revision: str = '064f9978fc69'
down_revision: Union[str, Sequence[str], None] = 'd0f311c36ace'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

Base = declarative_base()


# Lightweight models for migration
class Role(Base):
    __tablename__ = 'roles'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(100), unique=True, nullable=False)


class Permission(Base):
    __tablename__ = 'permissions'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(150), unique=True, nullable=False)


class RolePermission(Base):
    __tablename__ = 'role_permissions'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    role_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    permission_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    created_at = sa.Column(sa.TIMESTAMP, nullable=False)


def upgrade() -> None:
    """Assign new permissions to existing roles."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    try:
        print("\n" + "="*80)
        print("ASSIGNING NEW PERMISSIONS TO ROLES")
        print("="*80)

        # Define permission assignments per role
        role_permissions_map = {
            "super_admin": [
                # ALL new permissions (10)
                "content.submit_for_review", "content.approve", "content.reject", "content.publish",
                "workspace.transfer_ownership", "workspace.manage_billing",
                "member.read", "member.invite", "member.remove", "member.update_role"
            ],
            "workspace_owner": [
                # ALL new permissions (10) - full control of workspace
                "content.submit_for_review", "content.approve", "content.reject", "content.publish",
                "workspace.transfer_ownership", "workspace.manage_billing",
                "member.read", "member.invite", "member.remove", "member.update_role"
            ],
            "workspace_admin": [
                # Content workflow + member management (8)
                # NO transfer_ownership, NO manage_billing
                "content.submit_for_review", "content.approve", "content.reject", "content.publish",
                "member.read", "member.invite", "member.remove", "member.update_role"
            ],
            "editor": [
                # Only submit for review (1)
                # Can create/edit content, but cannot approve/publish
                "content.submit_for_review"
            ],
            # viewer and user roles get no new permissions
        }

        total_assigned = 0
        total_skipped = 0

        for role_name, permission_names in role_permissions_map.items():
            print(f"\n→ Processing role: {role_name}")

            # Get role
            role = session.query(Role).filter_by(name=role_name).first()
            if not role:
                print(f"  ⚠️  WARNING: Role '{role_name}' not found, skipping")
                continue

            print(f"  Found role ID: {role.id}")
            assigned_count = 0
            skipped_count = 0

            for perm_name in permission_names:
                # Get permission
                permission = session.query(Permission).filter_by(name=perm_name).first()
                if not permission:
                    print(f"    ⚠️  WARNING: Permission '{perm_name}' not found")
                    continue

                # Check if already assigned
                existing = session.query(RolePermission).filter_by(
                    role_id=role.id,
                    permission_id=permission.id
                ).first()

                if existing:
                    skipped_count += 1
                    total_skipped += 1
                    continue

                # Assign permission to role
                role_perm = RolePermission(
                    id=uuid.uuid4(),
                    role_id=role.id,
                    permission_id=permission.id,
                    created_at=datetime.now(timezone.utc)
                )
                session.add(role_perm)
                assigned_count += 1
                total_assigned += 1
                print(f"    ✓ Assigned '{perm_name}'")

            if skipped_count > 0:
                print(f"  ⊘ Skipped {skipped_count} already assigned permissions")
            print(f"  ✓ Assigned {assigned_count} new permissions to '{role_name}'")

        session.commit()

        print("\n" + "="*80)
        print(f"✓ ROLE PERMISSION ASSIGNMENT COMPLETE!")
        print(f"  Total assigned: {total_assigned} permissions")
        print(f"  Total skipped: {total_skipped} (already assigned)")
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
    """Remove new permission assignments from roles."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    try:
        print("\n" + "="*80)
        print("REMOVING NEW PERMISSION ASSIGNMENTS")
        print("="*80)

        # Define the same permission list
        permission_names = [
            "content.submit_for_review", "content.approve", "content.reject", "content.publish",
            "workspace.transfer_ownership", "workspace.manage_billing",
            "member.read", "member.invite", "member.remove", "member.update_role"
        ]

        # Get all permissions
        permissions = session.query(Permission).filter(
            Permission.name.in_(permission_names)
        ).all()

        permission_ids = [p.id for p in permissions]

        if not permission_ids:
            print("  No permissions found to remove")
            session.close()
            return

        # Delete all role_permissions for these permissions
        deleted_count = session.query(RolePermission).filter(
            RolePermission.permission_id.in_(permission_ids)
        ).delete(synchronize_session=False)

        session.commit()

        print(f"\n✓ Removed {deleted_count} permission assignments")
        print("="*80 + "\n")

    except Exception as e:
        session.rollback()
        print(f"\n❌ ERROR: Downgrade failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        session.close()
