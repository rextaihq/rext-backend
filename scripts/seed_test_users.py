#!/usr/bin/env python3
"""
Seed Test Users for RBAC Testing

Creates 5 test users with different roles for automated testing:
- owner@test.com (workspace_owner)
- admin@test.com (workspace_admin)
- editor@test.com (editor)
- viewer@test.com (viewer)
- superadmin@test.com (super_admin)
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.database.async_database import get_async_db
from src.api.models.user_models.users import Users as User
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.workspace_models.workspace_model import WorkspaceModel as Workspace
from src.api.models.workspace_models.workspace_member import WorkspaceMembers as WorkspaceMember
from src.services.auth_service import AuthService
from src.api.security.token_utils import hash_password
import uuid
from datetime import datetime, UTC


async def seed_test_users():
    """Create test users for RBAC testing"""

    async for db in get_async_db():
        print("🌱 Starting test user seeding...")

        # Test password (same for all test users)
        test_password = "TestPassword123!"
        password_hashed = hash_password(test_password)

        # Test users configuration
        test_users_config = [
            {
                "email": "owner@test.com",
                "name": "Test Owner",
                "role_name": "workspace_owner",
                "is_workspace_role": True,
            },
            {
                "email": "admin@test.com",
                "name": "Test Admin",
                "role_name": "workspace_admin",
                "is_workspace_role": True,
            },
            {
                "email": "editor@test.com",
                "name": "Test Editor",
                "role_name": "editor",
                "is_workspace_role": True,
            },
            {
                "email": "viewer@test.com",
                "name": "Test Viewer",
                "role_name": "viewer",
                "is_workspace_role": True,
            },
            {
                "email": "superadmin@test.com",
                "name": "Test Super Admin",
                "role_name": "super_admin",
                "is_workspace_role": False,  # Platform role
            },
        ]

        created_users = []

        # Step 1: Create or find test workspace
        print("\n📦 Step 1: Creating test workspace...")

        workspace_result = await db.execute(
            select(Workspace).where(Workspace.slug == "test-workspace")
        )
        test_workspace = workspace_result.scalar_one_or_none()

        if not test_workspace:
            # We'll create workspace after we have an owner user
            print("   ⏳ Will create workspace after owner user is created")
        else:
            print(f"   ✅ Test workspace exists: {test_workspace.id}")

        # Step 2: Create test users
        print("\n👥 Step 2: Creating test users...")

        for user_config in test_users_config:
            email = user_config["email"]

            # Check if user already exists
            result = await db.execute(
                select(User).where(User.email == email)
            )
            existing_user = result.scalar_one_or_none()

            if existing_user:
                print(f"   ⚠️  User {email} already exists (ID: {existing_user.id})")
                created_users.append({
                    "user": existing_user,
                    "role_name": user_config["role_name"],
                    "is_workspace_role": user_config["is_workspace_role"],
                })
                continue

            # Create new user
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                name=user_config["name"],
                password_hash=password_hashed,
                is_active=True,
                is_verified=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            db.add(user)
            await db.flush()

            print(f"   ✅ Created user: {email} (ID: {user.id})")

            created_users.append({
                "user": user,
                "role_name": user_config["role_name"],
                "is_workspace_role": user_config["is_workspace_role"],
            })

        await db.commit()

        # Step 3: Create test workspace if it doesn't exist
        if not test_workspace:
            print("\n📦 Step 3: Creating test workspace...")

            # Find owner user
            owner_data = next(u for u in created_users if u["role_name"] == "workspace_owner")
            owner_user = owner_data["user"]

            test_workspace = Workspace(
                id=str(uuid.uuid4()),
                slug="test-workspace",
                name="Test Workspace",
                description="Workspace for automated RBAC testing",
                owner_id=owner_user.id,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            db.add(test_workspace)
            await db.flush()
            await db.commit()

            print(f"   ✅ Created test workspace: {test_workspace.id}")

        # Step 4: Assign roles to users
        print("\n🎭 Step 4: Assigning roles to users...")

        for user_data in created_users:
            user = user_data["user"]
            role_name = user_data["role_name"]
            is_workspace_role = user_data["is_workspace_role"]

            # Find role
            role_result = await db.execute(
                select(Role).where(Role.name == role_name)
            )
            role = role_result.scalar_one_or_none()

            if not role:
                print(f"   ❌ Role '{role_name}' not found! Run seed_permissions.py first.")
                continue

            # Check if user already has this role
            if is_workspace_role:
                # Workspace-scoped role
                existing_role_result = await db.execute(
                    select(UserRole).where(
                        UserRole.user_id == user.id,
                        UserRole.role_id == role.id,
                        UserRole.workspace_id == test_workspace.id
                    )
                )
            else:
                # Global role
                existing_role_result = await db.execute(
                    select(UserRole).where(
                        UserRole.user_id == user.id,
                        UserRole.role_id == role.id,
                        UserRole.workspace_id.is_(None)
                    )
                )

            existing_role = existing_role_result.scalar_one_or_none()

            if existing_role:
                print(f"   ⚠️  User {user.email} already has role '{role_name}'")
                continue

            # Assign role
            user_role = UserRole(
                id=str(uuid.uuid4()),
                user_id=user.id,
                role_id=role.id,
                workspace_id=test_workspace.id if is_workspace_role else None,
                created_at=datetime.now(UTC),
            )

            db.add(user_role)

            scope = f"workspace:{test_workspace.slug}" if is_workspace_role else "global"
            print(f"   ✅ Assigned '{role_name}' to {user.email} ({scope})")

        await db.flush()

        # Step 5: Create workspace memberships for workspace roles
        print("\n🏢 Step 5: Creating workspace memberships...")

        for user_data in created_users:
            if not user_data["is_workspace_role"]:
                continue  # Skip platform roles

            user = user_data["user"]

            # Check if already a member
            member_result = await db.execute(
                select(WorkspaceMember).where(
                    WorkspaceMember.user_id == user.id,
                    WorkspaceMember.workspace_id == test_workspace.id
                )
            )
            existing_member = member_result.scalar_one_or_none()

            if existing_member:
                print(f"   ⚠️  {user.email} is already a workspace member")
                continue

            # Create membership
            member = WorkspaceMember(
                id=str(uuid.uuid4()),
                user_id=user.id,
                workspace_id=test_workspace.id,
                status="active",
                is_default=True,
                joined_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            db.add(member)
            print(f"   ✅ Added {user.email} to workspace")

        await db.commit()

        # Summary
        print("\n" + "="*60)
        print("✅ Test User Seeding Complete!")
        print("="*60)
        print(f"\nTest Workspace: test-workspace (ID: {test_workspace.id})")
        print(f"\nTest Users Created/Updated:")
        print(f"  📧 Email                | 🎭 Role              | 🔑 Password")
        print(f"  {'-'*23} | {'-'*20} | {'-'*20}")

        for user_data in created_users:
            user = user_data["user"]
            role = user_data["role_name"]
            print(f"  {user.email:23} | {role:20} | {test_password}")

        print("\n" + "="*60)
        print("🧪 Ready for RBAC testing!")
        print("="*60)
        print("\nNext steps:")
        print("  1. cd wrext-admin")
        print("  2. npm run test:rbac        # Run Jest tests")
        print("  3. npm run test:rbac:e2e    # Run E2E tests")
        print()

        break  # Only need one session


async def verify_test_setup():
    """Verify test users can authenticate"""

    async for db in get_async_db():
        print("\n🔍 Verifying test setup...")

        test_emails = [
            "owner@test.com",
            "admin@test.com",
            "editor@test.com",
            "viewer@test.com",
            "superadmin@test.com",
        ]

        for email in test_emails:
            # Check user exists
            result = await db.execute(
                select(User).where(User.email == email)
            )
            user = result.scalar_one_or_none()

            if not user:
                print(f"   ❌ User {email} not found!")
                continue

            # Check roles
            roles_result = await db.execute(
                select(Role)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user.id)
            )
            roles = roles_result.scalars().all()

            role_names = [r.name for r in roles]
            print(f"   ✅ {email}: {', '.join(role_names)}")

        break  # Only need one session


if __name__ == "__main__":
    print("🌱 RBAC Test User Seeding Script")
    print("="*60)

    try:
        asyncio.run(seed_test_users())
        asyncio.run(verify_test_setup())
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
