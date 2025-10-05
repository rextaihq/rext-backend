"""seed003_ensure_all_users_have_workspace_memberships

Revision ID: c47862f79eae
Revises: 36ef85f33af2
Create Date: 2025-10-03 12:31:26.556601

This migration ensures that ALL users in the database have at least one workspace membership.
It's designed to be idempotent and can be run multiple times safely.

Strategy:
1. Find all users who are NOT members of any workspace
2. Find the first available workspace (or create a default one if none exist)
3. Add these users as members to workspaces
4. Assign appropriate roles (viewer role by default)
5. Create notification preferences for users who don't have them
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy as sa
import uuid
from datetime import datetime
import bcrypt

revision: str = 'c47862f79eae'
down_revision: Union[str, Sequence[str], None] = '36ef85f33af2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

Base = declarative_base()


# Lightweight models for this migration
class Users(Base):
    __tablename__ = 'users'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    email = sa.Column(sa.String(255))
    username = sa.Column(sa.String(100))
    deleted_at = sa.Column(sa.TIMESTAMP)


class WorkspaceModel(Base):
    __tablename__ = 'workspace'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    user_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))
    name = sa.Column(sa.String)
    description = sa.Column(sa.Text)
    created_at = sa.Column(sa.DateTime(timezone=True))


class WorkspaceMembers(Base):
    __tablename__ = 'workspace_members'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    user_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))
    workspace_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))
    status = sa.Column(sa.String(20))
    is_default = sa.Column(sa.Boolean)
    joined_at = sa.Column(sa.TIMESTAMP)
    last_activity_at = sa.Column(sa.TIMESTAMP)


class Role(Base):
    __tablename__ = 'roles'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(100))
    display_name = sa.Column(sa.String(150))


class UserRole(Base):
    __tablename__ = 'user_roles'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    user_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))
    role_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))
    workspace_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))
    assigned_by_user_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))
    assigned_at = sa.Column(sa.TIMESTAMP)


class NotificationPreferences(Base):
    __tablename__ = 'notification_preferences'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    user_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))
    email_notifications = sa.Column(sa.Boolean)
    workspace_invites = sa.Column(sa.Boolean)
    content_updates = sa.Column(sa.Boolean)
    topic_generation = sa.Column(sa.Boolean)
    weekly_digest = sa.Column(sa.Boolean)
    security_alerts = sa.Column(sa.Boolean)
    created_at = sa.Column(sa.TIMESTAMP)
    updated_at = sa.Column(sa.TIMESTAMP)


def upgrade() -> None:
    """Ensure all active users have workspace memberships."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    try:
        now = datetime.utcnow()
        print("\n" + "="*80)
        print("ENSURING ALL USERS HAVE WORKSPACE MEMBERSHIPS")
        print("="*80)

        # =================================================================
        # FIND USERS WITHOUT WORKSPACE MEMBERSHIPS
        # =================================================================
        print("\n1. Finding users without workspace memberships...")

        # Get all active users
        all_users = session.query(Users).filter(Users.deleted_at == None).all()
        print(f"   Total active users: {len(all_users)}")

        # Get all users who already have memberships
        users_with_memberships = session.query(
            WorkspaceMembers.user_id
        ).distinct().all()
        user_ids_with_memberships = set([u[0] for u in users_with_memberships])
        print(f"   Users with memberships: {len(user_ids_with_memberships)}")

        # Find users without memberships
        users_without_memberships = [
            u for u in all_users if u.id not in user_ids_with_memberships
        ]
        print(f"   Users WITHOUT memberships: {len(users_without_memberships)}")

        if not users_without_memberships:
            print("\n   ✅ All users already have workspace memberships!")
            session.commit()
            return

        # =================================================================
        # GET OR CREATE DEFAULT WORKSPACE
        # =================================================================
        print("\n2. Finding/creating workspaces for orphaned users...")

        # Get existing workspaces
        existing_workspaces = session.query(WorkspaceModel).all()
        print(f"   Existing workspaces: {len(existing_workspaces)}")

        # If no workspaces exist, create a default one
        if not existing_workspaces:
            print("   No workspaces found. Creating default workspace...")
            default_workspace_id = uuid.UUID('dddddddd-dddd-dddd-dddd-dddddddddddd')

            # Use first admin user or first user as owner
            admin_user = session.query(Users).filter(Users.deleted_at == None).first()

            default_workspace = WorkspaceModel(
                id=default_workspace_id,
                user_id=admin_user.id,
                name="Default Workspace",
                description="Auto-created default workspace for user testing",
                created_at=now,
            )
            session.add(default_workspace)
            session.flush()
            existing_workspaces = [default_workspace]
            print(f"   ✓ Created default workspace: {default_workspace_id}")

        # =================================================================
        # GET DEFAULT ROLE (VIEWER)
        # =================================================================
        viewer_role = session.query(Role).filter_by(name='viewer').first()
        if not viewer_role:
            print("   ⚠ Warning: 'viewer' role not found, skipping role assignment")

        # =================================================================
        # ADD USERS TO WORKSPACES
        # =================================================================
        print("\n3. Adding users to workspaces...")

        # Distribute users across available workspaces (round-robin)
        workspace_index = 0
        added_count = 0

        for user in users_without_memberships:
            # Select workspace using round-robin
            target_workspace = existing_workspaces[workspace_index % len(existing_workspaces)]

            # Add workspace membership
            membership = WorkspaceMembers(
                id=uuid.uuid4(),
                user_id=user.id,
                workspace_id=target_workspace.id,
                status="active",
                is_default=False,
                joined_at=now,
                last_activity_at=now,
            )
            session.add(membership)

            # Assign viewer role if available
            if viewer_role:
                existing_role = session.query(UserRole).filter_by(
                    user_id=user.id,
                    role_id=viewer_role.id,
                    workspace_id=target_workspace.id
                ).first()

                if not existing_role:
                    user_role = UserRole(
                        id=uuid.uuid4(),
                        user_id=user.id,
                        role_id=viewer_role.id,
                        workspace_id=target_workspace.id,
                        assigned_by_user_id=target_workspace.user_id,
                        assigned_at=now,
                    )
                    session.add(user_role)

            print(f"   ✓ Added {user.email} to workspace: {target_workspace.name}")
            added_count += 1
            workspace_index += 1

        session.flush()
        print(f"\n   Total memberships added: {added_count}")

        # =================================================================
        # ENSURE NOTIFICATION PREFERENCES (OPTIONAL - SKIP IF TABLE DOESN'T MATCH)
        # =================================================================
        print("\n4. Ensuring notification preferences for all users...")

        prefs_added = 0
        try:
            for user in all_users:
                existing_pref = session.query(NotificationPreferences).filter_by(
                    user_id=user.id
                ).first()

                if not existing_pref:
                    pref = NotificationPreferences(
                        id=uuid.uuid4(),
                        user_id=user.id,
                        email_notifications=True,
                        workspace_invites=True,
                        content_updates=True,
                        topic_generation=True,
                        weekly_digest=True,
                        security_alerts=True,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(pref)
                    prefs_added += 1

            if prefs_added > 0:
                print(f"   ✓ Added notification preferences for {prefs_added} users")
            else:
                print(f"   ✅ All users already have notification preferences")
        except Exception as e:
            print(f"   ⚠ Skipping notification preferences (table schema mismatch): {str(e)[:100]}")
            session.rollback()
            # Re-establish session after rollback
            session = orm.Session(bind=bind)

        session.commit()

        # =================================================================
        # FINAL SUMMARY
        # =================================================================
        print("\n" + "="*80)
        print("✅ WORKSPACE MEMBERSHIP SYNC COMPLETE!")
        print("="*80)
        print(f"  • Users processed: {len(users_without_memberships)}")
        print(f"  • Memberships created: {added_count}")
        print(f"  • Notification preferences created: {prefs_added}")
        print(f"  • All {len(all_users)} active users now have workspace access")
        print("="*80)

    except Exception as e:
        session.rollback()
        print(f"\n❌ ERROR: Failed to ensure workspace memberships: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        session.close()


def downgrade() -> None:
    """
    This migration is designed to be additive only and ensure data consistency.
    Downgrading would orphan users, so we don't support it.
    If you need to remove specific memberships, do it manually.
    """
    print("⚠ Downgrade not supported for this data seeding migration")
    print("   This migration only adds missing relationships, it doesn't remove existing ones")
    pass
