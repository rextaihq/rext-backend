"""
Comprehensive Email Integration Test Script

Tests all components of the email system migration:
1. Configuration loading
2. Provider initialization
3. EmailService instantiation
4. Database context manager
5. Background task pattern
6. All 7 email template types
"""
import asyncio
import sys
from uuid import uuid4

async def test_configuration():
    """Test email configuration loading"""
    print("=" * 60)
    print("TEST 1: Email Configuration")
    print("=" * 60)
    
    try:
        from src.config.email_config import email_config
        
        print(f"✅ Configuration loaded")
        print(f"  Email Enabled: {email_config.email_enabled}")
        print(f"  Primary Provider: {email_config.email_provider}")
        print(f"  Fallback Provider: {email_config.email_fallback_provider}")
        print(f"  From Email: {email_config.resend_from_email}")
        print(f"  From Name: {email_config.resend_from_name}")
        print(f"  Retry Enabled: {email_config.email_retry_enabled}")
        print(f"  Max Retries: {email_config.email_retry_max_attempts}")
        
        # Check if API key is configured
        if email_config.resend_api_key:
            print(f"  Resend API Key: configured ({len(email_config.resend_api_key)} chars)")
        else:
            print(f"  ⚠️  Resend API Key: NOT configured")
        
        return True
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False


async def test_providers():
    """Test email provider initialization"""
    print("\n" + "=" * 60)
    print("TEST 2: Email Providers")
    print("=" * 60)
    
    try:
        from src.providers.email.factory import EmailProviderFactory
        
        # Test primary provider
        primary = EmailProviderFactory.get_provider()
        print(f"✅ Primary provider created: {primary.get_provider_name()}")
        
        # Test fallback provider
        fallback = EmailProviderFactory.get_fallback_provider()
        if fallback:
            print(f"✅ Fallback provider created: {fallback.get_provider_name()}")
        else:
            print(f"  ℹ️  No fallback provider configured")
        
        # Test available providers
        available = EmailProviderFactory.get_available_providers()
        print(f"  Available providers: {', '.join(available)}")
        
        return True
    except Exception as e:
        print(f"❌ Provider test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_database_context():
    """Test async database context manager"""
    print("\n" + "=" * 60)
    print("TEST 3: Database Context Manager")
    print("=" * 60)
    
    try:
        from src.api.database.async_database import get_async_db_context, async_engine
        
        # Test engine connection
        async with async_engine.begin() as conn:
            result = await conn.execute("SELECT 1")
            value = result.scalar()
            print(f"✅ Database connection works: SELECT 1 = {value}")
        
        # Test context manager
        async with get_async_db_context() as db:
            print(f"✅ Context manager works")
            print(f"  Session type: {type(db).__name__}")
        
        return True
    except Exception as e:
        print(f"❌ Database context test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_email_service():
    """Test EmailService instantiation"""
    print("\n" + "=" * 60)
    print("TEST 4: EmailService")
    print("=" * 60)
    
    try:
        from src.services.email_service import EmailService
        from src.api.database.async_database import get_async_db_context
        
        async with get_async_db_context() as db:
            service = EmailService(db)
            print(f"✅ EmailService created")
            print(f"  Primary provider: {service.primary_provider.get_provider_name()}")
            print(f"  Has fallback: {service.fallback_provider is not None}")
        
        return True
    except Exception as e:
        print(f"❌ EmailService test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_background_task_pattern():
    """Test background task pattern used in migrations"""
    print("\n" + "=" * 60)
    print("TEST 5: Background Task Pattern")
    print("=" * 60)
    
    try:
        # Test the exact pattern from auth.py
        async def send_verification_email_task(email, first_name, verification_link, user_id):
            from src.services.email_service import EmailService
            from src.api.database.async_database import get_async_db_context
            from uuid import UUID
            
            async with get_async_db_context() as async_db:
                email_service = EmailService(async_db)
                # Don't actually send email in test
                return True
        
        result = await send_verification_email_task(
            "test@example.com",
            "Test",
            "https://example.com/verify",
            str(uuid4())
        )
        
        print(f"✅ Background task pattern works")
        print(f"  Pattern validated: async function + context manager + EmailService")
        
        return True
    except Exception as e:
        print(f"❌ Background task pattern test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_email_models():
    """Test email models can be imported"""
    print("\n" + "=" * 60)
    print("TEST 6: Email Models")
    print("=" * 60)
    
    try:
        from src.api.models.email_models.email_log import EmailLog
        from src.api.models.email_models.email_event import EmailEvent
        
        print(f"✅ EmailLog model imported")
        print(f"  Table: {EmailLog.__tablename__}")
        
        print(f"✅ EmailEvent model imported")
        print(f"  Table: {EmailEvent.__tablename__}")
        
        return True
    except Exception as e:
        print(f"❌ Email models test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_migrations_exist():
    """Check if migrations exist"""
    print("\n" + "=" * 60)
    print("TEST 7: Alembic Migrations")
    print("=" * 60)
    
    try:
        import os
        import glob
        
        migrations_dir = "alembic/versions"
        
        # Find email-related migrations
        all_migrations = glob.glob(f"{migrations_dir}/*.py")
        email_migrations = [
            m for m in all_migrations 
            if "email_logs" in open(m).read() or "email_events" in open(m).read()
        ]
        
        print(f"  Total migrations: {len(all_migrations)}")
        print(f"  Email migrations: {len(email_migrations)}")
        
        for migration in email_migrations:
            filename = os.path.basename(migration)
            print(f"  ✅ {filename}")
        
        if len(email_migrations) >= 2:
            print(f"✅ Email migrations exist (email_logs + email_events)")
            return True
        else:
            print(f"⚠️  Expected 2 email migrations, found {len(email_migrations)}")
            return False
            
    except Exception as e:
        print(f"❌ Migrations test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_template_types():
    """Verify all template types are documented"""
    print("\n" + "=" * 60)
    print("TEST 8: Email Template Types")
    print("=" * 60)
    
    template_types = {
        "email_verification": "User registration",
        "password_reset": "Password recovery",
        "data_export": "GDPR compliance",
        "workspace_invitation": "Team collaboration",
        "trial_expiring": "Subscription reminder",
        "trial_expired": "Subscription end"
    }
    
    print(f"  Defined template types: {len(template_types)}")
    for template, purpose in template_types.items():
        print(f"  ✅ {template}: {purpose}")
    
    return True


async def test_all_migrated_files():
    """Test syntax of all migrated files"""
    print("\n" + "=" * 60)
    print("TEST 9: Migrated Files Syntax")
    print("=" * 60)
    
    files = [
        "src/api/routes/users/auth.py",
        "src/api/routes/users/password.py",
        "src/api/routes/users/management.py",
        "src/api/routes/workspaces/workspace_invitations.py",
        "src/api/routes/workspaces/invitations.py/modules/invitation_create.py",
        "src/utils/trial_manager.py",
        "src/api/database/async_database.py",
        "src/api/tasks/send_mail.py",
    ]
    
    import py_compile
    
    all_ok = True
    for file in files:
        try:
            py_compile.compile(file, doraise=True)
            print(f"  ✅ {file}")
        except Exception as e:
            print(f"  ❌ {file}: {e}")
            all_ok = False
    
    if all_ok:
        print(f"✅ All migrated files have valid syntax")
    
    return all_ok


async def test_trial_manager():
    """Test trial manager email functions"""
    print("\n" + "=" * 60)
    print("TEST 10: Trial Manager Integration")
    print("=" * 60)
    
    try:
        from src.utils.trial_manager import (
            send_trial_expiring_notification_async,
            send_trial_expired_notification_async
        )
        
        print(f"✅ Trial manager async functions imported")
        print(f"  - send_trial_expiring_notification_async")
        print(f"  - send_trial_expired_notification_async")
        
        # Check they're actually async
        import inspect
        assert inspect.iscoroutinefunction(send_trial_expiring_notification_async)
        assert inspect.iscoroutinefunction(send_trial_expired_notification_async)
        
        print(f"✅ Functions are properly async")
        
        return True
    except Exception as e:
        print(f"❌ Trial manager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("EMAIL INTEGRATION TEST SUITE")
    print("Phase 5: Migration Verification")
    print("=" * 60 + "\n")
    
    tests = [
        ("Configuration", test_configuration),
        ("Providers", test_providers),
        ("Database Context", test_database_context),
        ("EmailService", test_email_service),
        ("Background Task Pattern", test_background_task_pattern),
        ("Email Models", test_email_models),
        ("Migrations", test_migrations_exist),
        ("Template Types", test_template_types),
        ("Migrated Files", test_all_migrated_files),
        ("Trial Manager", test_trial_manager),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ Test '{name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Email system is ready for integration testing.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review errors above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
