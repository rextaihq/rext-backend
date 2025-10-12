# Phase 5: Migration - Deep Verification Checklist

**Date:** 2025-10-12
**Status:** IN PROGRESS - Deep Verification

---

## Critical Fixes Applied

### ✅ 1. Missing `get_async_db_context()` Function
**Issue:** All migrated files referenced `get_async_db_context()` but it didn't exist!  
**Fix:** Implemented in [src/api/database/async_database.py](src/api/database/async_database.py:52-68)  
**Test:** Import and use in background tasks

### ✅ 2. Trial Manager Email Notifications  
**Issue:** Placeholder email functions found in [src/utils/trial_manager.py](src/utils/trial_manager.py:348-392)  
**Fix:** Implemented async email functions using EmailService  
**New Template Types:** `trial_expiring`, `trial_expired`

---

## Verification Matrix

### A. Import Verification

| File | Old Import Removed | New Import Added | UUID Import | Status |
|------|-------------------|------------------|-------------|--------|
| auth.py | ✅ | ✅ | ✅ | PASS |
| password.py | ✅ | ✅ | ✅ | PASS |
| management.py | ✅ | ✅ | ✅ | PASS |
| workspace_invitations.py | ✅ | ✅ | ✅ | PASS |
| invitation_create.py | ✅ | ✅ | ✅ | PASS |
| trial_manager.py | N/A | ✅ | ✅ | PASS |

**Command to verify:**
```bash
# Should return nothing:
grep -r "from src.api.tasks.send_mail import send_email" src/ --include="*.py"

# Should find new imports:
grep -r "from src.services.email_service import EmailService" src/ --include="*.py"
```

---

### B. Template Types Inventory

| Template Type | Location | Purpose | workspace_id | user_id |
|--------------|----------|---------|--------------|---------|
| `email_verification` | auth.py | User registration | No | Yes |
| `password_reset` | password.py | Password reset | No | Yes |
| `data_export` | management.py | GDPR export | No | Yes |
| `workspace_invitation` | workspace_invitations.py | Workspace invite | Yes | No |
| `workspace_invitation` | invitation_create.py | Alt workspace invite | Yes | No |
| `trial_expiring` | trial_manager.py | Trial expiring soon | No | Yes |
| `trial_expired` | trial_manager.py | Trial ended | No | Yes |

**Total:** 7 template types (5 routes + 2 trial notifications)

---

### C. Database Schema Validation

**email_logs table columns:**
```sql
-- Required fields
id (UUID, PK)
workspace_id (UUID, FK workspace.id, nullable, indexed)
user_id (UUID, FK users.id, nullable, indexed)
template_type (VARCHAR(100), nullable)
provider (VARCHAR(50), NOT NULL)
provider_message_id (VARCHAR(255), nullable, indexed)
to_email (VARCHAR(255), NOT NULL, indexed)
from_email (VARCHAR(255), NOT NULL)
subject (VARCHAR(500), NOT NULL)
status (VARCHAR(50), NOT NULL, DEFAULT 'queued', indexed)
error_message (TEXT, nullable)
sent_at (TIMESTAMP, nullable)
delivered_at (TIMESTAMP, nullable)
failed_at (TIMESTAMP, nullable)
provider_response (JSONB, nullable)
tags (JSONB, nullable)
created_at (TIMESTAMP, NOT NULL, indexed)
updated_at (TIMESTAMP, NOT NULL)
```

**Indexes:**
- workspace_id
- user_id
- provider_message_id
- to_email
- status
- created_at

---

### D. Background Task Pattern Validation

**Pattern used in ALL migrated files:**
```python
async def send_<type>_email_task(email, subject, html, context_id):
    from src.api.database.async_database import get_async_db_context
    try:
        async with get_async_db_context() as db:
            email_service = EmailService(db)
            await email_service.send_email(...)
    except Exception as e:
        logger.error(...)

# Usage:
background_tasks.add_task(send_<type>_email_task, ...)
```

**Files using this pattern:**
1. ✅ auth.py - `send_verification_email_task()`
2. ✅ password.py - `send_password_reset_email_task()`
3. ✅ management.py - `send_data_export_email_task()`
4. ✅ workspace_invitations.py - `send_workspace_invitation_email_task()`
5. ✅ invitation_create.py - `send_invitation_email_task()`
6. ✅ trial_manager.py - `send_trial_expiring_notification_async()`, `send_trial_expired_notification_async()`

---

### E. Error Handling Validation

**Each background task must have:**
- ✅ try/except block
- ✅ `logger.error()` with `exc_info=True`
- ✅ Graceful failure (don't crash background task)
- ✅ Specific exception message

**Verification:**
```bash
# Check all background task functions have try/except
grep -A 20 "async def send_.*_email_task" src/api/routes/**/*.py src/utils/*.py
```

---

### F. Tags and Metadata Validation

**Tags structure (all files):**
```python
tags = {
    "type": "<category>",    # auth, workspace, subscription, user_management
    "action": "<action>",    # verify, password_reset, invitation, data_export
    # Optional contextual tags:
    "days_remaining": "...", # for trial emails
    "invitation_id": "...",  # for invitations
    "downgraded": "..."      # for trial expired
}
```

**Metadata tracking:**
| Email Type | workspace_id | user_id | template_type | tags.type |
|------------|--------------|---------|---------------|-----------|
| Registration | No | ✅ | email_verification | auth |
| Password Reset | No | ✅ | password_reset | auth |
| Data Export | No | ✅ | data_export | user_management |
| Workspace Invite | ✅ | No | workspace_invitation | workspace |
| Trial Expiring | No | ✅ | trial_expiring | subscription |
| Trial Expired | No | ✅ | trial_expired | subscription |

---

### G. Circular Import Check

**Potential circular import risks:**
- EmailService imports providers
- Providers don't import EmailService ✅
- Routes import EmailService (top-level) ✅
- Background tasks import EmailService (inside function) ✅
- trial_manager imports EmailService (inside function) ✅

**Test command:**
```bash
python -c "from src.services.email_service import EmailService; print('OK')"
python -c "from src.api.routes.users.auth import router; print('OK')"
python -c "from src.utils.trial_manager import send_trial_expiring_notification_async; print('OK')"
```

---

### H. Async Context Manager Test

**Test that get_async_db_context() works:**
```python
import asyncio
from src.api.database.async_database import get_async_db_context

async def test_context():
    async with get_async_db_context() as db:
        # Should not raise exception
        print("Context manager works!")
        return True

asyncio.run(test_context())
```

---

## Testing Commands

### 1. Syntax and Import Validation
```bash
cd wrext-backend

# Test all Python files for syntax errors
python -m py_compile src/api/routes/users/auth.py
python -m py_compile src/api/routes/users/password.py
python -m py_compile src/api/routes/users/management.py
python -m py_compile src/api/routes/workspaces/workspace_invitations.py
python -m py_compile src/api/routes/workspaces/invitations.py/modules/invitation_create.py
python -m py_compile src/utils/trial_manager.py
python -m py_compile src/api/database/async_database.py

# Test imports
python -c "from src.services.email_service import EmailService; print('EmailService OK')"
python -c "from src.api.database.async_database import get_async_db_context; print('Context manager OK')"
python -c "from src.utils.trial_manager import send_trial_expiring_notification_async; print('Trial manager OK')"
```

### 2. Database Connection Test
```bash
python << 'PYEOF'
import asyncio
from src.api.database.async_database import get_async_db_context, async_engine

async def test_db():
    # Test engine
    async with async_engine.begin() as conn:
        result = await conn.execute("SELECT 1")
        print(f"✅ Database connection: {result.scalar()}")
    
    # Test context manager
    async with get_async_db_context() as db:
        print("✅ Context manager works!")
    
    print("✅ All database tests passed!")

asyncio.run(test_db())
PYEOF
```

### 3. EmailService Integration Test
```bash
python << 'PYEOF'
import asyncio
import os
from src.services.email_service import EmailService
from src.api.database.async_database import get_async_db_context
from uuid import uuid4

async def test_email_service():
    # Check config
    from src.config.email_config import email_config
    print(f"Email enabled: {email_config.email_enabled}")
    print(f"Provider: {email_config.email_provider}")
    print(f"From: {email_config.resend_from_email}")
    
    # Test EmailService instantiation
    async with get_async_db_context() as db:
        service = EmailService(db)
        print(f"✅ EmailService initialized")
        print(f"✅ Primary provider: {service.primary_provider.get_provider_name()}")
        print(f"✅ Has fallback: {service.fallback_provider is not None}")

asyncio.run(test_email_service())
PYEOF
```

### 4. Background Task Pattern Test
```bash
python << 'PYEOF'
import asyncio
from uuid import uuid4

# Test the exact pattern used in auth.py
async def send_verification_email_task(email, first_name, verification_link, user_id):
    from src.services.email_service import EmailService
    from src.api.database.async_database import get_async_db_context
    from uuid import UUID
    
    try:
        async with get_async_db_context() as async_db:
            email_service = EmailService(async_db)
            print(f"✅ Background task pattern works!")
            print(f"✅ Context manager created")
            print(f"✅ EmailService initialized")
            # Don't actually send email in test
            return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

result = asyncio.run(send_verification_email_task(
    "test@example.com",
    "Test",
    "https://example.com/verify",
    str(uuid4())
))
print(f"✅ Background task test: {'PASSED' if result else 'FAILED'}")
PYEOF
```

### 5. Template Type Consistency Check
```bash
# Extract all template_type values
grep -r 'template_type=' src/api/routes src/utils --include="*.py" | grep -v ".pyc" | sed 's/.*template_type="\([^"]*\)".*/\1/' | sort -u

# Expected output:
# data_export
# email_verification
# password_reset
# trial_expired
# trial_expiring
# workspace_invitation
```

---

## Manual Testing Checklist

### Test 1: Registration Flow
- [ ] Start server: `PYTHONPATH=. python src/api/server.py`
- [ ] Register user via API
- [ ] Check logs for "Email sent successfully"
- [ ] Check no errors in background task
- [ ] Verify email logged to database
- [ ] Confirm template_type="email_verification"
- [ ] Confirm user_id populated

### Test 2: Password Reset Flow
- [ ] Request password reset via API
- [ ] Check logs for "Email sent successfully"
- [ ] Verify email logged to database
- [ ] Confirm template_type="password_reset"
- [ ] Confirm user_id populated

### Test 3: Data Export Flow
- [ ] Request data export via API (authenticated)
- [ ] Check logs for "Email sent successfully"
- [ ] Verify email logged to database
- [ ] Confirm template_type="data_export"
- [ ] Confirm user_id populated

### Test 4: Workspace Invitation Flow
- [ ] Create workspace invitation via API
- [ ] Check logs for "Email sent successfully"
- [ ] Verify email logged to database
- [ ] Confirm template_type="workspace_invitation"
- [ ] Confirm workspace_id populated

### Test 5: Trial Notification (Manual Trigger)
```python
import asyncio
from src.utils.trial_manager import send_trial_expiring_notification_async
from uuid import uuid4

asyncio.run(send_trial_expiring_notification_async(
    user_email="test@example.com",
    user_id=str(uuid4()),
    days_remaining=3,
    plan_name="Premium"
))
```
- [ ] Check logs for "Trial expiring notification sent"
- [ ] Verify email logged to database
- [ ] Confirm template_type="trial_expiring"

---

## Edge Cases to Test

### 1. Email Service Failure
- [ ] Set invalid Resend API key
- [ ] Try sending email
- [ ] Verify fallback to SMTP attempted
- [ ] Check error logged to database

### 2. Database Session Handling
- [ ] Send multiple emails in parallel (stress test)
- [ ] Verify no session leaks
- [ ] Check all sessions properly closed

### 3. Missing User ID
- [ ] Try sending email without user_id (workspace emails)
- [ ] Verify email still sent
- [ ] Check user_id is NULL in database

### 4. Missing Workspace ID
- [ ] Try sending user email (should have no workspace_id)
- [ ] Verify email sent
- [ ] Check workspace_id is NULL in database

---

## Success Criteria

### Code Quality
- [x] No old `send_mail` imports
- [x] All files use EmailService
- [x] UUID imports present
- [x] Error handling in all background tasks
- [x] Async context manager exists
- [x] Trial notifications implemented

### Functionality
- [ ] All 5 main email flows work
- [ ] Trial notifications work
- [ ] Database logging works
- [ ] Metadata tracked correctly
- [ ] Error handling works
- [ ] Fallback provider works

### Database
- [ ] email_logs table has all columns
- [ ] Indexes created
- [ ] Foreign keys work
- [ ] JSONB fields work (tags, provider_response)

### Performance
- [ ] Background tasks don't block requests
- [ ] Sessions properly closed
- [ ] No memory leaks
- [ ] Reasonable response times

---

## Known Limitations

1. **Email Templates:** Still inline HTML, need React Email migration (Phase 3)
2. **Attachments:** Not supported yet
3. **Scheduling:** No delayed email support
4. **Batch Sending:** Not optimized for bulk emails
5. **Rate Limiting:** Relies on Resend limits, not enforced at app level

---

## Next Actions

1. ✅ Fix critical issues (get_async_db_context, trial_manager)
2. ⏳ Run all testing commands above
3. ⏳ Perform manual testing for all 5+ flows
4. ⏳ Check database logging
5. ⏳ Test error scenarios
6. ⏳ Document any remaining issues

