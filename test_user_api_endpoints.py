#!/usr/bin/env python3
"""
Test script for User API endpoints.

This script validates that all required user API endpoints are properly defined
and accessible. It performs structural validation without requiring a running server.
"""

import sys
import importlib.util
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))


def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")

    try:
        from src.api.models.user_models.users import Users
        from src.api.models.user_models.notification_preferences import NotificationPreferences
        from src.api.routes.users.profile import router as profile_router
        from src.api.routes.users.preferences import router as preferences_router
        from src.api.routes.users.management import router as management_router
        from src.api.schema.user_schema import (
            UpdateProfileRequest,
            DeactivateAccountRequest,
            DataExportRequest
        )
        from src.api.schema.notification_schema import (
            NotificationPreferencesResponse,
            UpdateNotificationPreferencesRequest
        )
        print("✅ All imports successful")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False


def test_user_model():
    """Test that Users model has bio field."""
    print("\nTesting Users model...")

    try:
        from src.api.models.user_models.users import Users

        # Check if bio column exists
        if hasattr(Users, 'bio'):
            print("✅ Users model has bio field")
            return True
        else:
            print("❌ Users model missing bio field")
            return False
    except Exception as e:
        print(f"❌ Users model test failed: {e}")
        return False


def test_notification_preferences_model():
    """Test that NotificationPreferences model has new fields."""
    print("\nTesting NotificationPreferences model...")

    try:
        from src.api.models.user_models.notification_preferences import NotificationPreferences

        required_fields = [
            'digest_enabled',
            'email_content_updates',
            'in_app_content_updates',
            'email_team_activity',
            'in_app_team_activity',
            'email_security_alerts',
            'in_app_security_alerts',
            'email_billing_updates',
            'in_app_billing_updates',
            'email_product_updates',
            'in_app_product_updates'
        ]

        missing_fields = []
        for field in required_fields:
            if not hasattr(NotificationPreferences, field):
                missing_fields.append(field)

        if not missing_fields:
            print("✅ NotificationPreferences model has all required fields")
            return True
        else:
            print(f"❌ NotificationPreferences model missing fields: {missing_fields}")
            return False
    except Exception as e:
        print(f"❌ NotificationPreferences model test failed: {e}")
        return False


def test_profile_routes():
    """Test that profile routes are properly defined."""
    print("\nTesting profile routes...")

    try:
        from src.api.routes.users.profile import router

        # Get all route paths
        routes = [route.path for route in router.routes]

        required_routes = [
            '/profile',
            '/avatar/upload',
            '/avatar',
            '/preferences/notifications',
            '/deactivate'
        ]

        missing_routes = []
        for route in required_routes:
            if route not in routes:
                missing_routes.append(route)

        if not missing_routes:
            print(f"✅ All required profile routes exist: {required_routes}")
            return True
        else:
            print(f"❌ Missing profile routes: {missing_routes}")
            return False
    except Exception as e:
        print(f"❌ Profile routes test failed: {e}")
        return False


def test_preferences_routes():
    """Test that preferences routes are properly defined."""
    print("\nTesting preferences routes...")

    try:
        from src.api.routes.users.preferences import router

        routes = [route.path for route in router.routes]

        required_routes = ['/preferences']

        missing_routes = []
        for route in required_routes:
            if route not in routes:
                missing_routes.append(route)

        if not missing_routes:
            print(f"✅ All required preferences routes exist: {required_routes}")
            return True
        else:
            print(f"❌ Missing preferences routes: {missing_routes}")
            return False
    except Exception as e:
        print(f"❌ Preferences routes test failed: {e}")
        return False


def test_management_routes():
    """Test that management routes are properly defined."""
    print("\nTesting management routes...")

    try:
        from src.api.routes.users.management import router

        routes = [route.path for route in router.routes]

        required_routes = ['/export-data']

        missing_routes = []
        for route in required_routes:
            if route not in routes:
                missing_routes.append(route)

        if not missing_routes:
            print(f"✅ All required management routes exist: {required_routes}")
            return True
        else:
            print(f"❌ Missing management routes: {missing_routes}")
            return False
    except Exception as e:
        print(f"❌ Management routes test failed: {e}")
        return False


def test_schemas():
    """Test that required schemas are properly defined."""
    print("\nTesting schemas...")

    try:
        from src.api.schema.user_schema import UpdateProfileRequest
        from src.api.schema.notification_schema import UpdateNotificationPreferencesRequest

        # Test UpdateProfileRequest has bio field
        if 'bio' in UpdateProfileRequest.model_fields:
            print("✅ UpdateProfileRequest has bio field")
        else:
            print("❌ UpdateProfileRequest missing bio field")
            return False

        # Test UpdateNotificationPreferencesRequest has required fields
        required_fields = ['email_enabled', 'in_app_enabled', 'digest_enabled', 'categories']
        missing_fields = []
        for field in required_fields:
            if field not in UpdateNotificationPreferencesRequest.model_fields:
                missing_fields.append(field)

        if not missing_fields:
            print("✅ UpdateNotificationPreferencesRequest has all required fields")
            return True
        else:
            print(f"❌ UpdateNotificationPreferencesRequest missing fields: {missing_fields}")
            return False
    except Exception as e:
        print(f"❌ Schemas test failed: {e}")
        return False


def test_migration_exists():
    """Test that migration file exists."""
    print("\nTesting migration file...")

    migration_path = Path("/home/user/wrext-backend/alembic/versions/20251111_add_bio_and_expand_notifications.py")

    if migration_path.exists():
        print(f"✅ Migration file exists: {migration_path.name}")
        return True
    else:
        print(f"❌ Migration file not found: {migration_path}")
        return False


def main():
    """Run all tests."""
    print("=" * 80)
    print("User API Endpoints Test Suite")
    print("=" * 80)

    tests = [
        test_imports,
        test_user_model,
        test_notification_preferences_model,
        test_profile_routes,
        test_preferences_routes,
        test_management_routes,
        test_schemas,
        test_migration_exists
    ]

    results = []
    for test in tests:
        results.append(test())

    print("\n" + "=" * 80)
    print("Test Summary")
    print("=" * 80)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("✅ All tests passed!")
        return 0
    else:
        print(f"❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
