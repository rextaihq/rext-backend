#!/usr/bin/env python3
"""
Alembic Integration Test Suite

Tests the complete Alembic integration including:
- Migration application
- Database operations
- Application functionality
"""

import os
import sys
import subprocess
from sqlalchemy import text
from src.api.database.database import SessionLocal

# Import all models to ensure relationships are properly initialized
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.knowledge_models.knowledge_model import (
    BrandVoice, Website, KnowledgeFiles, TextKnowledge
)
from src.api.models.topic_models.topic_models import TopicsModel


def test_alembic_installed():
    """Test 1: Verify Alembic is installed."""
    result = subprocess.run(['alembic', '--version'], capture_output=True)
    assert result.returncode == 0, "Alembic not installed"
    print("✅ Test 1: Alembic installed")


def test_migration_status():
    """Test 2: Check migration status."""
    result = subprocess.run(['alembic', 'current'], capture_output=True, text=True)
    assert result.returncode == 0, "Cannot check migration status"
    assert '(head)' in result.stdout, "Database not at head revision"
    print("✅ Test 2: Database at head revision")


def test_alembic_version_table():
    """Test 3: Verify alembic_version table exists."""
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT * FROM alembic_version"))
        row = result.fetchone()
        assert row is not None, "alembic_version table empty"
        print(f"✅ Test 3: alembic_version table exists (revision: {row[0]})")
    finally:
        db.close()


def test_all_tables_exist():
    """Test 4: Verify all application tables exist."""
    db = SessionLocal()
    expected_tables = {
        'users', 'roles', 'permissions', 'user_roles', 'role_permissions',
        'user_invitations', 'workspace', 'workspace_members',
        'brand_voice', 'website', 'knowledge_files', 'text_knowledge', 'topics'
    }
    try:
        result = db.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name != 'alembic_version'"
        ))
        tables = {row[0] for row in result.fetchall()}
        missing = expected_tables - tables
        assert len(missing) == 0, f"Missing tables: {missing}"
        print(f"✅ Test 4: All {len(tables)} application tables exist")
    finally:
        db.close()


def test_permissions_seeded():
    """Test 5: Verify default permissions were seeded."""
    db = SessionLocal()
    try:
        count = db.query(Permission).count()
        assert count == 6, f"Expected 6 permissions, found {count}"
        print("✅ Test 5: Default permissions seeded (6 permissions)")
    finally:
        db.close()


def test_database_operations():
    """Test 6: Test basic database operations."""
    db = SessionLocal()
    try:
        # Test query
        perms = db.query(Permission).all()
        assert len(perms) > 0, "Cannot query permissions"

        # Test filter
        content_perms = db.query(Permission).filter(
            Permission.resource == 'content'
        ).all()
        assert len(content_perms) == 3, f"Expected 3 content permissions, found {len(content_perms)}"

        print("✅ Test 6: Database operations working")
    finally:
        db.close()


def main():
    """Run all tests."""
    print("🧪 Running Alembic Integration Tests...\n")

    tests = [
        test_alembic_installed,
        test_migration_status,
        test_alembic_version_table,
        test_all_tables_exist,
        test_permissions_seeded,
        test_database_operations,
    ]

    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"❌ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ {test.__name__}: Unexpected error: {e}")
            failed += 1

    print(f"\n{'='*50}")
    if failed == 0:
        print("✅ All tests passed!")
        return 0
    else:
        print(f"❌ {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
