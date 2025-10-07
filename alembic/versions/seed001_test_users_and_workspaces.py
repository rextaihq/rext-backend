"""seed_test_users_and_workspaces

Revision ID: seed001
Revises: g1h2i3j4k5l6
Create Date: 2025-10-03 09:00:00.000000

Comprehensive seed data for testing:
- 5 test users with different roles
- 3 workspaces with different owners
- Workspace memberships
- Proper role assignments
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy as sa
import uuid
from datetime import datetime
import bcrypt

# revision identifiers, used by Alembic.
revision: str = 'seed001'
down_revision: Union[str, Sequence[str], None] = '23b403658069'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

Base = declarative_base()


# Lightweight models for seeding
class Users(Base):
    __tablename__ = 'users'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    email = sa.Column(sa.String(255), unique=True, nullable=False)
    username = sa.Column(sa.String(100), unique=True, nullable=False)
    password_hash = sa.Column(sa.String(255), nullable=False)
    first_name = sa.Column(sa.String(100))
    last_name = sa.Column(sa.String(100))
    display_name = sa.Column(sa.String(200))
    status = sa.Column(sa.String(20), default="active")
    email_verified = sa.Column(sa.Boolean, default=False)
    email_verified_at = sa.Column(sa.TIMESTAMP)
    language = sa.Column(sa.String(10), default="en")
    timezone = sa.Column(sa.String(50), default="UTC")
    created_at = sa.Column(sa.TIMESTAMP, nullable=False)
    updated_at = sa.Column(sa.TIMESTAMP)


class Role(Base):
    __tablename__ = 'roles'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(100), unique=True, nullable=False)
    display_name = sa.Column(sa.String(150), nullable=False)
    description = sa.Column(sa.Text)
    hierarchy_level = sa.Column(sa.Integer, default=0)
    is_system_role = sa.Column(sa.Boolean, default=True)


class WorkspaceModel(Base):
    __tablename__ = 'workspace'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    user_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    name = sa.Column(sa.String, nullable=False)
    description = sa.Column(sa.Text)
    url = sa.Column(sa.String)
    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False)
    updated_at = sa.Column(sa.DateTime(timezone=True))


class UserRole(Base):
    __tablename__ = 'user_roles'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    user_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    role_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    workspace_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))
    assigned_by_user_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))
    assigned_at = sa.Column(sa.TIMESTAMP, nullable=False)


class WorkspaceMembers(Base):
    __tablename__ = 'workspace_members'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    user_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    workspace_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    status = sa.Column(sa.String(20), default="active")
    is_default = sa.Column(sa.Boolean, default=False)
    joined_at = sa.Column(sa.TIMESTAMP)
    last_activity_at = sa.Column(sa.TIMESTAMP)


def upgrade() -> None:
    """Seed test users and workspaces for development/testing."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    try:
        # Get existing roles for assignment
        admin_role = session.query(Role).filter_by(name='admin').first()
        workspace_owner_role = session.query(Role).filter_by(name='workspace_owner').first()
        workspace_admin_role = session.query(Role).filter_by(name='workspace_admin').first()
        editor_role = session.query(Role).filter_by(name='editor').first()
        viewer_role = session.query(Role).filter_by(name='viewer').first()

        # Create predefined UUIDs for consistency
        user1_id = uuid.UUID('11111111-1111-1111-1111-111111111111')
        user2_id = uuid.UUID('22222222-2222-2222-2222-222222222222')
        user3_id = uuid.UUID('33333333-3333-3333-3333-333333333333')
        user4_id = uuid.UUID('44444444-4444-4444-4444-444444444444')
        user5_id = uuid.UUID('55555555-5555-5555-5555-555555555555')

        workspace1_id = uuid.UUID('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa')
        workspace2_id = uuid.UUID('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb')
        workspace3_id = uuid.UUID('cccccccc-cccc-cccc-cccc-cccccccccccc')

        # Default password for all test users: "Test1234!"
        password_hash = bcrypt.hashpw("Test1234!".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        now = datetime.utcnow()

        # ============================================================================
        # CREATE TEST USERS
        # ============================================================================
        print("Creating test users...")

        users_data = [
            {
                "id": user1_id,
                "email": "admin@wrext.com",
                "username": "admin",
                "first_name": "Super",
                "last_name": "Admin",
                "display_name": "Super Admin",
                "email_verified": True,
                "email_verified_at": now,
            },
            {
                "id": user2_id,
                "email": "john.doe@wrext.com",
                "username": "johndoe",
                "first_name": "John",
                "last_name": "Doe",
                "display_name": "John Doe",
                "email_verified": True,
                "email_verified_at": now,
            },
            {
                "id": user3_id,
                "email": "jane.smith@wrext.com",
                "username": "janesmith",
                "first_name": "Jane",
                "last_name": "Smith",
                "display_name": "Jane Smith",
                "email_verified": True,
                "email_verified_at": now,
            },
            {
                "id": user4_id,
                "email": "bob.wilson@wrext.com",
                "username": "bobwilson",
                "first_name": "Bob",
                "last_name": "Wilson",
                "display_name": "Bob Wilson",
                "email_verified": True,
                "email_verified_at": now,
            },
            {
                "id": user5_id,
                "email": "alice.johnson@wrext.com",
                "username": "alicejohnson",
                "first_name": "Alice",
                "last_name": "Johnson",
                "display_name": "Alice Johnson",
                "email_verified": True,
                "email_verified_at": now,
            },
        ]

        for user_data in users_data:
            # Check if user already exists
            existing = session.query(Users).filter_by(email=user_data["email"]).first()
            if existing:
                print(f"  User {user_data['email']} already exists, skipping...")
                continue

            user = Users(
                id=user_data["id"],
                email=user_data["email"],
                username=user_data["username"],
                password_hash=password_hash,
                first_name=user_data["first_name"],
                last_name=user_data["last_name"],
                display_name=user_data["display_name"],
                status="active",
                email_verified=user_data["email_verified"],
                email_verified_at=user_data["email_verified_at"],
                language="en",
                timezone="UTC",
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            print(f"  ✓ Created user: {user_data['email']} ({user_data['display_name']})")

        session.flush()

        # ============================================================================
        # ASSIGN GLOBAL ROLES TO USERS
        # ============================================================================
        print("\nAssigning global roles...")

        # Admin user gets admin role
        if admin_role:
            existing = session.query(UserRole).filter_by(
                user_id=user1_id,
                role_id=admin_role.id,
                workspace_id=None
            ).first()
            if not existing:
                session.add(UserRole(
                    id=uuid.uuid4(),
                    user_id=user1_id,
                    role_id=admin_role.id,
                    workspace_id=None,
                    assigned_by_user_id=user1_id,
                    assigned_at=now,
                ))
                print(f"  ✓ Assigned 'admin' role to admin@wrext.com")

        # ============================================================================
        # CREATE TEST WORKSPACES
        # ============================================================================
        print("\nCreating test workspaces...")

        workspaces_data = [
            {
                "id": workspace1_id,
                "user_id": user2_id,  # John Doe's workspace
                "name": "Acme Corporation",
                "slug": "acme-corporation",
                "description": "Marketing and content workspace for Acme Corp",
                "url": "https://acmecorp.com",
            },
            {
                "id": workspace2_id,
                "user_id": user3_id,  # Jane Smith's workspace
                "name": "TechStartup Inc",
                "slug": "techstartup-inc",
                "description": "Product content and technical documentation",
                "url": "https://techstartup.io",
            },
            {
                "id": workspace3_id,
                "user_id": user2_id,  # John Doe's second workspace
                "name": "Personal Blog",
                "slug": "personal-blog",
                "description": "Personal blog and portfolio workspace",
                "url": "https://johndoe.blog",
            },
        ]

        for ws_data in workspaces_data:
            existing = session.query(WorkspaceModel).filter_by(id=ws_data["id"]).first()
            if existing:
                print(f"  Workspace {ws_data['name']} already exists, skipping...")
                continue

            workspace = WorkspaceModel(
                id=ws_data["id"],
                user_id=ws_data["user_id"],
                name=ws_data["name"],
                slug=ws_data["slug"],
                description=ws_data["description"],
                url=ws_data["url"],
                created_at=now,
                updated_at=now,
            )
            session.add(workspace)
            print(f"  ✓ Created workspace: {ws_data['name']}")

        session.flush()

        # ============================================================================
        # ASSIGN WORKSPACE ROLES
        # ============================================================================
        print("\nAssigning workspace roles...")

        workspace_roles_data = [
            # Workspace 1: Acme Corporation
            {"user_id": user2_id, "workspace_id": workspace1_id, "role": workspace_owner_role, "role_name": "workspace_owner"},
            {"user_id": user3_id, "workspace_id": workspace1_id, "role": workspace_admin_role, "role_name": "workspace_admin"},
            {"user_id": user4_id, "workspace_id": workspace1_id, "role": editor_role, "role_name": "editor"},
            {"user_id": user5_id, "workspace_id": workspace1_id, "role": viewer_role, "role_name": "viewer"},

            # Workspace 2: TechStartup Inc
            {"user_id": user3_id, "workspace_id": workspace2_id, "role": workspace_owner_role, "role_name": "workspace_owner"},
            {"user_id": user2_id, "workspace_id": workspace2_id, "role": editor_role, "role_name": "editor"},
            {"user_id": user4_id, "workspace_id": workspace2_id, "role": viewer_role, "role_name": "viewer"},

            # Workspace 3: Personal Blog
            {"user_id": user2_id, "workspace_id": workspace3_id, "role": workspace_owner_role, "role_name": "workspace_owner"},
        ]

        for wr_data in workspace_roles_data:
            if not wr_data["role"]:
                print(f"  ⚠ Role {wr_data['role_name']} not found, skipping assignment")
                continue

            existing = session.query(UserRole).filter_by(
                user_id=wr_data["user_id"],
                role_id=wr_data["role"].id,
                workspace_id=wr_data["workspace_id"]
            ).first()
            if not existing:
                session.add(UserRole(
                    id=uuid.uuid4(),
                    user_id=wr_data["user_id"],
                    role_id=wr_data["role"].id,
                    workspace_id=wr_data["workspace_id"],
                    assigned_by_user_id=user1_id,  # Assigned by admin
                    assigned_at=now,
                ))
                print(f"  ✓ Assigned '{wr_data['role_name']}' to workspace {wr_data['workspace_id']}")

        session.flush()

        # ============================================================================
        # CREATE WORKSPACE MEMBERSHIPS
        # ============================================================================
        print("\nCreating workspace memberships...")

        memberships_data = [
            # Workspace 1: Acme Corporation
            {"user_id": user2_id, "workspace_id": workspace1_id, "is_default": True},
            {"user_id": user3_id, "workspace_id": workspace1_id, "is_default": False},
            {"user_id": user4_id, "workspace_id": workspace1_id, "is_default": False},
            {"user_id": user5_id, "workspace_id": workspace1_id, "is_default": False},

            # Workspace 2: TechStartup Inc
            {"user_id": user3_id, "workspace_id": workspace2_id, "is_default": True},
            {"user_id": user2_id, "workspace_id": workspace2_id, "is_default": False},
            {"user_id": user4_id, "workspace_id": workspace2_id, "is_default": False},

            # Workspace 3: Personal Blog
            {"user_id": user2_id, "workspace_id": workspace3_id, "is_default": False},
        ]

        for mem_data in memberships_data:
            existing = session.query(WorkspaceMembers).filter_by(
                user_id=mem_data["user_id"],
                workspace_id=mem_data["workspace_id"]
            ).first()
            if not existing:
                session.add(WorkspaceMembers(
                    id=uuid.uuid4(),
                    user_id=mem_data["user_id"],
                    workspace_id=mem_data["workspace_id"],
                    status="active",
                    is_default=mem_data["is_default"],
                    joined_at=now,
                    last_activity_at=now,
                ))
                print(f"  ✓ Added membership for workspace {mem_data['workspace_id']}")

        session.commit()

        print("\n" + "="*80)
        print("✅ SEED DATA CREATED SUCCESSFULLY!")
        print("="*80)
        print("\nTest Users Created:")
        print("-" * 80)
        print("| Email                    | Password    | Role              | Default Workspace |")
        print("|" + "-"*78 + "|")
        print("| admin@wrext.com          | Test1234!   | Admin             | -                 |")
        print("| john.doe@wrext.com       | Test1234!   | User              | Acme Corporation  |")
        print("| jane.smith@wrext.com     | Test1234!   | User              | TechStartup Inc   |")
        print("| bob.wilson@wrext.com     | Test1234!   | User              | -                 |")
        print("| alice.johnson@wrext.com  | Test1234!   | User              | -                 |")
        print("-" * 80)
        print("\nWorkspaces Created:")
        print("-" * 80)
        print("| Name               | Owner              | Members                              |")
        print("|" + "-"*78 + "|")
        print("| Acme Corporation   | John Doe           | John, Jane, Bob, Alice               |")
        print("| TechStartup Inc    | Jane Smith         | Jane, John, Bob                      |")
        print("| Personal Blog      | John Doe           | John                                 |")
        print("-" * 80)
        print("\nWorkspace Access:")
        print("-" * 80)
        print("| User      | Acme Corporation | TechStartup Inc | Personal Blog |")
        print("|" + "-"*78 + "|")
        print("| John Doe  | Owner            | Editor          | Owner         |")
        print("| Jane      | Admin            | Owner           | -             |")
        print("| Bob       | Editor           | Viewer          | -             |")
        print("| Alice     | Viewer           | -               | -             |")
        print("-" * 80)
        print("\nTo log in, use any email above with password: Test1234!")
        print("="*80)

    except Exception as e:
        session.rollback()
        print(f"\n❌ ERROR: Failed to seed data: {str(e)}")
        raise
    finally:
        session.close()


def downgrade() -> None:
    """Remove seed data."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    try:
        print("Removing seed data...")

        # Remove in reverse order of dependencies
        user_ids = [
            uuid.UUID('11111111-1111-1111-1111-111111111111'),
            uuid.UUID('22222222-2222-2222-2222-222222222222'),
            uuid.UUID('33333333-3333-3333-3333-333333333333'),
            uuid.UUID('44444444-4444-4444-4444-444444444444'),
            uuid.UUID('55555555-5555-5555-5555-555555555555'),
        ]

        workspace_ids = [
            uuid.UUID('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'),
            uuid.UUID('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'),
            uuid.UUID('cccccccc-cccc-cccc-cccc-cccccccccccc'),
        ]

        # Delete workspace memberships
        session.query(WorkspaceMembers).filter(
            WorkspaceMembers.workspace_id.in_(workspace_ids)
        ).delete(synchronize_session=False)

        # Delete user roles
        session.query(UserRole).filter(
            UserRole.user_id.in_(user_ids)
        ).delete(synchronize_session=False)

        # Delete workspaces
        session.query(WorkspaceModel).filter(
            WorkspaceModel.id.in_(workspace_ids)
        ).delete(synchronize_session=False)

        # Delete users
        session.query(Users).filter(
            Users.id.in_(user_ids)
        ).delete(synchronize_session=False)

        session.commit()
        print("✅ Seed data removed successfully")

    except Exception as e:
        session.rollback()
        print(f"❌ ERROR: Failed to remove seed data: {str(e)}")
        raise
    finally:
        session.close()
