"""add_content_reviewer_role

Create the content_reviewer role for approval workflows.

This role can:
- Review and approve content created by editors
- Reject content with feedback
- Publish approved content
- View content, topics, knowledge, users, media (read-only)

Cannot:
- Create or edit content
- Manage workspace or members

Hierarchy: 20 (between editor:30 and viewer:10)

Revision ID: a973deb06456
Revises: 064f9978fc69
Create Date: 2025-10-20 11:11:52.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone
import uuid

# revision identifiers, used by Alembic.
revision: str = 'a973deb06456'
down_revision: Union[str, Sequence[str], None] = '064f9978fc69'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

Base = declarative_base()


# Lightweight models for migration
class Role(Base):
    __tablename__ = 'roles'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(100), unique=True, nullable=False)
    display_name = sa.Column(sa.String(150))
    description = sa.Column(sa.Text)
    hierarchy_level = sa.Column(sa.Integer, default=0)
    is_system_role = sa.Column(sa.Boolean, default=False)
    created_at = sa.Column(sa.TIMESTAMP, nullable=False)
    updated_at = sa.Column(sa.TIMESTAMP)


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
    """Create content_reviewer role with appropriate permissions."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    try:
        print("\n" + "="*80)
        print("CREATING CONTENT_REVIEWER ROLE")
        print("="*80)

        # Check if role already exists
        existing_role = session.query(Role).filter_by(name='content_reviewer').first()
        if existing_role:
            print("\n⚠️  content_reviewer role already exists")
            print(f"   Role ID: {existing_role.id}")
            print(f"   Hierarchy: {existing_role.hierarchy_level}")
            reviewer_role = existing_role
        else:
            # Create role
            reviewer_role = Role(
                id=uuid.uuid4(),
                name="content_reviewer",
                display_name="Content Reviewer",
                description="Review and approve content created by editors. Cannot create or edit content themselves.",
                hierarchy_level=20,  # Between editor (30) and viewer (10)
                is_system_role=True,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                updated_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
            session.add(reviewer_role)
            session.flush()
            print(f"\n✓ Created content_reviewer role")
            print(f"   Role ID: {reviewer_role.id}")
            print(f"   Hierarchy: {reviewer_role.hierarchy_level}")

        # Define permissions for content_reviewer
        reviewer_permissions = [
            # Workspace (read-only)
            "workspace.read",

            # Content (review and publish, NO create/edit)
            "content.read",
            "content.approve",
            "content.reject",
            "content.publish",

            # Topic/Knowledge (read-only)
            "topic.read",
            "knowledge.read",

            # User (read-only, to see who created content)
            "user.read",

            # Media (read-only)
            "media.read"
        ]

        print(f"\n→ Assigning {len(reviewer_permissions)} permissions to content_reviewer:")

        assigned_count = 0
        skipped_count = 0

        for perm_name in reviewer_permissions:
            # Get permission
            permission = session.query(Permission).filter_by(name=perm_name).first()
            if not permission:
                print(f"  ⚠️  WARNING: Permission '{perm_name}' not found")
                continue

            # Check if already assigned
            existing = session.query(RolePermission).filter_by(
                role_id=reviewer_role.id,
                permission_id=permission.id
            ).first()

            if existing:
                skipped_count += 1
                continue

            # Assign permission
            role_perm = RolePermission(
                id=uuid.uuid4(),
                role_id=reviewer_role.id,
                permission_id=permission.id,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
            session.add(role_perm)
            assigned_count += 1
            print(f"  ✓ {perm_name}")

        session.commit()

        print("\n" + "="*80)
        print(f"✓ CONTENT_REVIEWER ROLE CREATION COMPLETE!")
        print(f"  Assigned: {assigned_count} permissions")
        if skipped_count > 0:
            print(f"  Skipped: {skipped_count} (already assigned)")
        print("\n  Role Details:")
        print(f"    Name: {reviewer_role.name}")
        print(f"    Display Name: {reviewer_role.display_name}")
        print(f"    Hierarchy: {reviewer_role.hierarchy_level}")
        print(f"    System Role: {reviewer_role.is_system_role}")
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
    """Remove content_reviewer role."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    try:
        print("\n" + "="*80)
        print("REMOVING CONTENT_REVIEWER ROLE")
        print("="*80)

        # Get role
        reviewer_role = session.query(Role).filter_by(name='content_reviewer').first()

        if not reviewer_role:
            print("\n⚠️  content_reviewer role not found, nothing to remove")
            session.close()
            return

        print(f"\n→ Found content_reviewer role: {reviewer_role.id}")

        # Delete role_permissions (cascade should handle this, but explicit is better)
        deleted_perms = session.query(RolePermission).filter_by(
            role_id=reviewer_role.id
        ).delete(synchronize_session=False)

        print(f"  ✓ Deleted {deleted_perms} role permissions")

        # Delete role
        session.delete(reviewer_role)
        session.commit()

        print(f"  ✓ Deleted content_reviewer role")
        print("\n" + "="*80)
        print("✓ DOWNGRADE COMPLETE!")
        print("="*80 + "\n")

    except Exception as e:
        session.rollback()
        print(f"\n❌ ERROR: Downgrade failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        session.close()
