# Data Retention Policy Implementation

**Version:** 1.0
**Last Updated:** 2025-10-20
**Status:** Production Ready

---

## Table of Contents

1. [Overview](#overview)
2. [Retention Policies](#retention-policies)
3. [Architecture](#architecture)
4. [Automated Cleanup](#automated-cleanup)
5. [Manual Cleanup](#manual-cleanup)
6. [Compliance](#compliance)
7. [Monitoring](#monitoring)
8. [Configuration](#configuration)
9. [Testing](#testing)
10. [Troubleshooting](#troubleshooting)

---

## Overview

WREXT implements automated data retention policies to:
- ✅ Comply with GDPR, CCPA, and other privacy regulations
- ✅ Manage database growth and performance
- ✅ Protect user privacy (anonymize old data)
- ✅ Meet financial record retention requirements (7 years)

**Key Principle:**
> Delete what we don't need, anonymize what must be retained, keep what's required by law.

---

## Retention Policies

### Summary Table

| Data Type | Active Status | Cancelled/Expired | Retention Period | Action |
|-----------|--------------|------------------|------------------|--------|
| **Subscriptions** | Indefinite | 7 years | Financial records | Anonymize after 90 days |
| **Webhook Events** | 90 days | 90 days | Debugging | Delete |
| **Audit Logs** | 1 year | 1 year | Security/compliance | Delete |
| **Email Logs** | 90 days | 90 days | Debugging | Delete (with events) |
| **User Sessions** | Until expiry | 30 days inactive | Session management | Delete |
| **Transaction Data** | Indefinite | 7 years | Financial records | Keep (anonymized) |

### Detailed Policies

#### 1. Subscription Records

**Policy:**
- **Active subscriptions:** Retained indefinitely (required for service delivery)
- **Cancelled/expired subscriptions:** Retained for **7 years** (tax compliance, financial regulations)
- **User link (user_id):** Anonymized after **90 days** of cancellation/expiry

**Rationale:**
- Financial records must be retained for 7 years (IRS, EU VAT, HMRC requirements)
- User privacy protected by anonymizing personal link after 90 days
- Subscription metadata (amounts, dates, plan details) kept for financial audits

**Implementation:**
```python
# After 90 days, subscriptions are anonymized (user_id set to NULL)
# Subscription record kept for 7 years for tax compliance
await cleanup_service.anonymize_cancelled_subscriptions(retention_days=90)
```

**Example:**
- User cancels subscription on January 1st
- Until March 31st (90 days): Full subscription record with user_id
- After April 1st: Subscription record anonymized (user_id = NULL)
- For 7 years: Anonymous financial record retained
- After 7 years: Record eligible for deletion (manual process, requires legal review)

#### 2. Webhook Events

**Policy:**
- **Processed events:** Retained for **90 days** after processing
- **Unprocessed events:** Retained indefinitely (until processed or manually resolved)

**Rationale:**
- Webhook events needed for debugging payment issues
- 90 days provides sufficient window for issue investigation
- Failed/unprocessed events retained until resolved (may indicate system issue)

**Implementation:**
```python
# Delete processed webhook events older than 90 days
await cleanup_service.cleanup_webhook_events(retention_days=90)
```

**Fields Retained:**
- event_id, event_name, payload, processed status, error messages, timestamps

#### 3. Audit Logs

**Policy:**
- **All audit logs:** Retained for **1 year** (365 days)

**Rationale:**
- Audit logs needed for security investigations and compliance (PCI DSS Requirement 10)
- 1 year balances security needs with storage costs
- Older logs can be archived (not implemented, manual export if needed)

**Implementation:**
```python
# Delete audit logs older than 1 year
await cleanup_service.cleanup_audit_logs(retention_days=365)
```

**Audit Log Types:**
- Payment operations (subscription created, payment succeeded, etc.)
- Admin actions (refund created, subscription extended, etc.)
- Security events (webhook signature failures, login attempts, etc.)

#### 4. Email Logs & Events

**Policy:**
- **Email logs:** Retained for **90 days**
- **Email events:** Retained for **90 days** (or deleted via CASCADE when email_log deleted)
- **Orphaned events:** Deleted after 90 days (email_log_id = NULL)

**Rationale:**
- Email logs useful for debugging delivery issues
- 90 days sufficient for user support inquiries
- Events (opens, clicks, bounces) deleted with parent email_log

**Implementation:**
```python
# Delete email logs older than 90 days (events deleted via CASCADE)
await cleanup_service.cleanup_email_logs(retention_days=90)

# Clean up orphaned email events (no parent email_log)
await cleanup_service.cleanup_email_events(retention_days=90)
```

#### 5. User Sessions

**Policy:**
- **Active sessions:** Retained until expiry (typically 24 hours)
- **Inactive sessions:** Deleted after **30 days** of inactivity
- **Expired/revoked sessions:** Deleted immediately (next cleanup run)

**Rationale:**
- Old sessions pose security risk (session fixation, hijacking)
- 30-day grace period allows for "remember me" functionality
- Expired sessions serve no purpose (deleted proactively)

**Implementation:**
```python
# Delete inactive, expired, or revoked sessions
await cleanup_service.cleanup_inactive_sessions(inactive_days=30)
```

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                   Scheduled Task Manager                    │
│  (APScheduler - Daily at 2 AM UTC)                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│               Data Cleanup Service                          │
│  (src/services/data_cleanup_service.py)                     │
├─────────────────────────────────────────────────────────────┤
│  • cleanup_audit_logs()                                     │
│  • cleanup_email_logs()                                     │
│  • cleanup_email_events()                                   │
│  • cleanup_inactive_sessions()                              │
│  • cleanup_webhook_events()                 ⭐ NEW          │
│  • anonymize_cancelled_subscriptions()      ⭐ NEW          │
│  • cleanup_all()                                            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   Database Tables                           │
│  • audit_logs                                               │
│  • email_logs (CASCADE to email_events)                     │
│  • user_sessions                                            │
│  • webhook_events                           ⭐ NEW          │
│  • subscriptions (anonymize user_id)        ⭐ NEW          │
└─────────────────────────────────────────────────────────────┘
```

### Data Cleanup Service

**Location:** `src/services/data_cleanup_service.py`

**Key Features:**
- **Batch processing:** Deletes records in batches (default 1000) to avoid long-running transactions
- **Dry-run mode:** Preview what would be deleted without actually deleting
- **Comprehensive logging:** All cleanup operations logged with counts and timestamps
- **Error handling:** Graceful error handling with rollback on failure
- **Idempotent:** Safe to run multiple times (no duplicate deletions)

**Methods:**

1. **`cleanup_webhook_events(retention_days=90)`**
   - Deletes processed webhook events older than retention period
   - Keeps unprocessed events (may indicate issues)

2. **`anonymize_cancelled_subscriptions(retention_days=90)`**
   - Anonymizes user_id from cancelled/expired subscriptions
   - Keeps subscription data for financial records (7-year requirement)
   - NOT a deletion (just removes personal link)

3. **`cleanup_all()`**
   - Runs all cleanup tasks in sequence
   - Returns summary of records deleted/anonymized

---

## Automated Cleanup

### Scheduled Task

**Schedule:** Daily at **2:00 AM UTC** (configurable)

**Configuration:**
```python
# Environment variables
CLEANUP_ENABLED=true          # Enable/disable cleanup (default: false)
CLEANUP_HOUR=2                # Hour to run cleanup (0-23, default: 2)
CLEANUP_MINUTE=0              # Minute to run cleanup (0-59, default: 0)
CLEANUP_DRY_RUN=false         # Dry-run mode (default: false)
CLEANUP_BATCH_SIZE=1000       # Batch size for deletions (default: 1000)
```

**Location:** `src/tasks/scheduled_tasks.py`

**Startup Integration:**
```python
# In src/api/server.py (on application startup)
from src.tasks.scheduled_tasks import start_scheduled_tasks

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    start_scheduled_tasks()  # Starts background scheduler
    yield
    # Shutdown
    shutdown_scheduled_tasks()  # Graceful shutdown
```

### Logging

**All cleanup operations are logged:**

```json
{
  "timestamp": "2025-10-20T02:00:05.123Z",
  "level": "INFO",
  "message": "Data cleanup completed: 1523 total records deleted/anonymized",
  "extra": {
    "results": {
      "audit_logs": 450,
      "email_logs": 230,
      "email_events": 120,
      "user_sessions": 680,
      "webhook_events": 35,
      "cancelled_subscriptions_anonymized": 8
    },
    "total": 1523
  }
}
```

**Log Levels:**
- **INFO:** Successful cleanup operations
- **DEBUG:** Batch-level progress (e.g., "Deleted batch of 1000 audit logs")
- **WARNING:** No records to clean up (expected)
- **ERROR:** Cleanup failures (with exception details)

---

## Manual Cleanup

### CLI Command

**Run cleanup manually via CLI:**

```bash
# From wrext-backend directory
python -c "
import asyncio
from src.tasks.scheduled_tasks import run_cleanup_manually

# Dry run (preview only, no deletions)
results = asyncio.run(run_cleanup_manually(dry_run=True))
print(results)

# Actual cleanup (deletes data)
results = asyncio.run(run_cleanup_manually(dry_run=False))
print(results)
"
```

### Python Script

**Create a standalone cleanup script:**

```python
#!/usr/bin/env python3
"""
Manual data cleanup script.

Usage:
  python scripts/manual_cleanup.py --dry-run        # Preview
  python scripts/manual_cleanup.py                  # Execute
"""

import asyncio
import argparse
from src.api.database.async_database import AsyncSessionLocal
from src.services.data_cleanup_service import DataCleanupService

async def main(dry_run: bool = False):
    print(f"{'[DRY RUN] ' if dry_run else ''}Running data cleanup...")

    async with AsyncSessionLocal() as db:
        cleanup_service = DataCleanupService(db=db, dry_run=dry_run)
        results = await cleanup_service.cleanup_all()

    print("\nCleanup Results:")
    for table, count in results.items():
        print(f"  {table}: {count}")
    print(f"\nTotal: {sum(results.values())}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run data cleanup")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no deletions")
    args = parser.parse_args()

    asyncio.run(main(dry_run=args.dry_run))
```

**Save as:** `wrext-backend/scripts/manual_cleanup.py`

**Usage:**
```bash
# Make executable
chmod +x scripts/manual_cleanup.py

# Dry run (preview)
python scripts/manual_cleanup.py --dry-run

# Execute cleanup
python scripts/manual_cleanup.py
```

---

## Compliance

### GDPR (General Data Protection Regulation)

**Relevant Articles:**
- **Article 5(1)(e):** Storage limitation - "kept in a form which permits identification of data subjects for no longer than is necessary"
- **Article 17:** Right to erasure ("right to be forgotten")
- **Article 30:** Records of processing activities (retention documentation)

**WREXT Compliance:**
- ✅ Automated data retention policies implemented
- ✅ User data anonymized after 90 days (personal link removed)
- ✅ Financial records retained for legitimate interest (7-year tax requirement)
- ✅ User can request account deletion (triggers immediate anonymization)

**Documentation:**
- Privacy Policy: [PRIVACY_POLICY_PAYMENTS.md](PRIVACY_POLICY_PAYMENTS.md)
- Data deletion process: Anonymize user_id after 90 days, delete account data on request

### CCPA (California Consumer Privacy Act)

**Relevant Sections:**
- **§1798.105:** Right to deletion (consumer can request deletion of personal information)

**WREXT Compliance:**
- ✅ User can request deletion via support@wrext.com
- ✅ Deletion completed within 30 days (CCPA requirement)
- ✅ Financial records exempt (business purpose exception)

### PCI DSS (Payment Card Industry Data Security Standard)

**Requirement 3.1:** Keep cardholder data storage to a minimum

**WREXT Compliance:**
- ✅ No cardholder data stored (only reference IDs)
- ✅ Webhook events (no card data) deleted after 90 days
- ✅ Audit logs retained for 1 year (Requirement 10.7)

**Documentation:** [COMPLIANCE.md](COMPLIANCE.md)

### Tax & Financial Regulations

**Requirements:**
- **IRS (US):** 7 years for income tax records
- **HMRC (UK):** 6 years for VAT records
- **EU VAT:** 10 years for electronic invoices (some countries)

**WREXT Compliance:**
- ✅ Subscription records retained for **7 years** (exceeds most requirements)
- ✅ Anonymized after 90 days (privacy-first approach)
- ✅ Transaction metadata preserved (amounts, dates, plan details)

---

## Monitoring

### Health Checks

**Verify cleanup is running:**

```bash
# Check logs for recent cleanup runs
grep "Data cleanup completed" /var/log/wrext-backend.log | tail -5

# Expected output (every 24 hours):
# 2025-10-20T02:00:05Z INFO Data cleanup completed: 1523 total records deleted/anonymized
# 2025-10-19T02:00:05Z INFO Data cleanup completed: 1402 total records deleted/anonymized
```

### Alerts

**Set up alerts for cleanup failures:**

```python
# In Sentry or monitoring system
# Alert: "Data Cleanup Failed"
# Condition: Error log with message "Scheduled data cleanup failed"
# Severity: MEDIUM
# Notification: Email + Slack
```

### Metrics

**Track cleanup metrics over time:**

1. **Records deleted per day:**
   - Audit logs: ~500/day
   - Email logs: ~200/day
   - Webhook events: ~30/day
   - User sessions: ~600/day

2. **Database growth:**
   - Monitor table sizes before/after cleanup
   - Alert if tables grow despite cleanup (may indicate retention period too long)

3. **Cleanup duration:**
   - Should complete within 5-10 minutes
   - Alert if exceeds 30 minutes (may indicate large backlog)

---

## Configuration

### Environment Variables

```bash
# Enable/disable cleanup
CLEANUP_ENABLED=true

# Schedule (UTC)
CLEANUP_HOUR=2          # 2 AM UTC
CLEANUP_MINUTE=0

# Dry-run mode (for testing)
CLEANUP_DRY_RUN=false

# Batch size (larger = faster but more memory)
CLEANUP_BATCH_SIZE=1000

# Retention periods (in days)
AUDIT_LOG_RETENTION_DAYS=365
EMAIL_LOG_RETENTION_DAYS=90
EMAIL_EVENT_RETENTION_DAYS=90
USER_SESSION_INACTIVE_DAYS=30
# Webhook and subscription retention hardcoded in service (90 days)
```

### Configuration File

**Location:** `src/config/cleanup_config.py`

```python
class CleanupConfig:
    """Configuration for data cleanup tasks."""

    CLEANUP_ENABLED = os.getenv("CLEANUP_ENABLED", "false").lower() == "true"
    CLEANUP_HOUR = int(os.getenv("CLEANUP_HOUR", "2"))
    CLEANUP_MINUTE = int(os.getenv("CLEANUP_MINUTE", "0"))
    CLEANUP_DRY_RUN = os.getenv("CLEANUP_DRY_RUN", "false").lower() == "true"
    CLEANUP_BATCH_SIZE = int(os.getenv("CLEANUP_BATCH_SIZE", "1000"))

    # Retention periods
    AUDIT_LOG_RETENTION_DAYS = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "365"))
    EMAIL_LOG_RETENTION_DAYS = int(os.getenv("EMAIL_LOG_RETENTION_DAYS", "90"))
    EMAIL_EVENT_RETENTION_DAYS = int(os.getenv("EMAIL_EVENT_RETENTION_DAYS", "90"))
    USER_SESSION_INACTIVE_DAYS = int(os.getenv("USER_SESSION_INACTIVE_DAYS", "30"))
```

---

## Testing

### Unit Tests

**Create tests for cleanup service:**

```python
# tests/services/test_data_cleanup_service.py

import pytest
from datetime import datetime, timezone, timedelta
from src.services.data_cleanup_service import DataCleanupService

@pytest.mark.asyncio
async def test_cleanup_webhook_events(db_session):
    """Test webhook event cleanup."""
    # Create old processed webhook event (100 days old)
    old_event = WebhookEvent(
        event_id="evt_old_123",
        event_name="subscription_created",
        payload={"test": "data"},
        processed=True,
        created_at=datetime.now(timezone.utc) - timedelta(days=100)
    )
    db_session.add(old_event)
    await db_session.commit()

    # Create recent webhook event (10 days old)
    recent_event = WebhookEvent(
        event_id="evt_recent_456",
        event_name="subscription_updated",
        payload={"test": "data"},
        processed=True,
        created_at=datetime.now(timezone.utc) - timedelta(days=10)
    )
    db_session.add(recent_event)
    await db_session.commit()

    # Run cleanup (90-day retention)
    cleanup_service = DataCleanupService(db=db_session, dry_run=False)
    deleted_count = await cleanup_service.cleanup_webhook_events(retention_days=90)

    # Verify old event deleted, recent event kept
    assert deleted_count == 1

    old_event_check = await db_session.get(WebhookEvent, old_event.id)
    assert old_event_check is None  # Deleted

    recent_event_check = await db_session.get(WebhookEvent, recent_event.id)
    assert recent_event_check is not None  # Kept
```

### Integration Tests

**Test full cleanup flow:**

```bash
# Set up test environment
export CLEANUP_ENABLED=true
export CLEANUP_DRY_RUN=true

# Run application and wait for scheduled task
# (or trigger manually)

# Verify logs show cleanup ran
grep "Data cleanup completed" logs/test.log
```

---

## Troubleshooting

### Cleanup Not Running

**Symptom:** No cleanup logs appear

**Possible Causes:**
1. `CLEANUP_ENABLED=false` (disabled)
2. APScheduler not installed
3. Scheduler failed to start (check startup logs)

**Solution:**
```bash
# Check environment variable
echo $CLEANUP_ENABLED  # Should be "true"

# Install APScheduler
pip install apscheduler

# Check startup logs
grep "Scheduled tasks" logs/wrext-backend.log
# Expected: "Scheduled tasks started. Data cleanup will run daily at 02:00"
```

### Cleanup Failing

**Symptom:** Error logs during cleanup

**Possible Causes:**
1. Database connection issues
2. Insufficient permissions (DELETE privilege)
3. Foreign key constraints (unexpected)
4. Transaction timeout (batch size too large)

**Solution:**
```python
# Enable debug logging
import logging
logging.getLogger("src.services.data_cleanup_service").setLevel(logging.DEBUG)

# Run manually with dry-run first
from src.tasks.scheduled_tasks import run_cleanup_manually
results = await run_cleanup_manually(dry_run=True)

# Check database permissions
GRANT DELETE ON audit_logs, email_logs, email_events, user_sessions, webhook_events TO wrext_app;

# Reduce batch size if timeout occurs
export CLEANUP_BATCH_SIZE=500
```

### Excessive Deletions

**Symptom:** Too many records deleted (unexpected)

**Possible Causes:**
1. Retention period too short (misconfigured)
2. Clock skew (server time incorrect)
3. Logic error in cleanup service

**Solution:**
```bash
# Always run with dry-run first
export CLEANUP_DRY_RUN=true

# Check server time
date -u  # Should match UTC

# Verify retention periods
echo $AUDIT_LOG_RETENTION_DAYS  # Should be 365
echo $EMAIL_LOG_RETENTION_DAYS  # Should be 90

# Review dry-run results before enabling
python scripts/manual_cleanup.py --dry-run
```

---

## Related Documentation

- [Privacy Policy (Payments)](PRIVACY_POLICY_PAYMENTS.md) - User privacy and data handling
- [Compliance Documentation](COMPLIANCE.md) - GDPR, CCPA, PCI DSS compliance
- [Refund Policy](REFUND_POLICY.md) - User account deletion and data retention
- [Audit Logging](AUDIT_LOGGING.md) - Audit log structure and retention

---

## Version History

| Version | Date | Summary of Changes |
|---------|------|-------------------|
| 1.0 | 2025-10-20 | Initial implementation - Webhook event cleanup, subscription anonymization, documentation |

---

**Data Retention Status:** ✅ **Production Ready - Automated Cleanup Enabled**

**Next Review:** 2026-01-20 (Quarterly review of retention periods)
