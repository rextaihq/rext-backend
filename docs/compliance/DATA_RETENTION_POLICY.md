# Data Retention Policy

**Document Version:** 1.0
**Last Updated:** 2025-10-20
**Review Schedule:** Annual (October)
**Owner:** Engineering & Compliance Team
**Status:** Active

---

## Table of Contents

1. [Policy Overview](#policy-overview)
2. [Legal & Regulatory Basis](#legal--regulatory-basis)
3. [Data Retention Schedules](#data-retention-schedules)
4. [Automated Cleanup System](#automated-cleanup-system)
5. [User Account Deletion](#user-account-deletion)
6. [Financial Records Retention](#financial-records-retention)
7. [Implementation Details](#implementation-details)
8. [Compliance Verification](#compliance-verification)
9. [Policy Exceptions](#policy-exceptions)
10. [Contact Information](#contact-information)

---

## Policy Overview

### Purpose

This Data Retention Policy defines how long WREXT retains different types of data and establishes automated processes for deleting or anonymizing data that has exceeded its retention period.

### Scope

This policy applies to all data stored in WREXT systems, including:
- Payment and subscription data
- User account data
- Audit logs and security logs
- Webhook events and integration data
- Email logs and communication records
- Session data and temporary data

### Objectives

1. **Compliance**: Meet legal requirements (GDPR, CCPA, tax laws, financial regulations)
2. **Privacy**: Minimize data retention to respect user privacy
3. **Security**: Reduce attack surface by deleting unnecessary data
4. **Efficiency**: Improve system performance by removing old data
5. **Cost**: Reduce storage costs

### Principles

- **Minimal Retention**: Data is only retained as long as necessary
- **Automated Deletion**: Cleanup processes run automatically (no manual intervention required)
- **Transparency**: Users are informed about retention periods
- **Compliance-First**: Legal requirements override other considerations
- **Secure Deletion**: Data is permanently deleted (not just marked as deleted)

---

## Legal & Regulatory Basis

### Applicable Laws & Regulations

| Law/Regulation | Jurisdiction | Key Requirement | WREXT Compliance |
|----------------|--------------|-----------------|------------------|
| **GDPR** | EU/EEA | Art. 5(1)(e): Storage limitation | ✅ Data deleted after purpose fulfilled |
| **GDPR** | EU/EEA | Art. 17: Right to erasure | ✅ User account deletion with grace period |
| **CCPA** | California, US | Right to deletion | ✅ Account deletion functionality |
| **UK GDPR** | United Kingdom | Data minimization | ✅ Automated cleanup of old data |
| **IRS** | United States | 7-year financial records | ✅ Subscriptions anonymized (not deleted) for 7 years |
| **EU VAT** | European Union | 7-year financial records | ✅ Subscription data retained 7 years (anonymized) |
| **SOX** | United States (if applicable) | 7-year record retention | ✅ Financial records retained |
| **PCI DSS** | Global (payment processing) | Cardholder data not stored | ✅ No cardholder data stored (see PCI_COMPLIANCE.md) |

### Data Minimization (GDPR Article 5)

GDPR requires that personal data be:
- **Adequate**: Sufficient for the purpose
- **Relevant**: Necessary for the purpose
- **Limited**: Not excessive

**WREXT Implementation:**
- ✅ Audit logs: 1 year (adequate for security investigations)
- ✅ Webhook events: 90 days (adequate for debugging)
- ✅ Email logs: 30 days (adequate for delivery troubleshooting)
- ✅ Sessions: 7 days (adequate for user experience)
- ✅ Cancelled subscriptions: Anonymized after 90 days, retained 7 years for tax compliance

---

## Data Retention Schedules

### 1. Payment & Subscription Data

#### Active Subscriptions

| Data Type | Retention Period | Reason | Deletion Method |
|-----------|------------------|--------|-----------------|
| Subscription records | Indefinite (while active) | Service delivery | Not deleted (active) |
| Transaction history | Indefinite (while active) | Billing, support | Not deleted (active) |
| Usage metrics | Indefinite (while active) | Plan enforcement | Not deleted (active) |
| Customer portal data | Indefinite (while active) | User access | Not deleted (active) |

**Notes:**
- Active subscriptions are NOT subject to deletion
- Data is required for ongoing service delivery
- Users can view/export data anytime via billing dashboard

#### Cancelled/Expired Subscriptions

| Data Type | Retention Period | Reason | Deletion Method |
|-----------|------------------|--------|-----------------|
| Subscription records | 7 years after cancellation | Tax compliance (IRS, EU VAT) | Anonymized after 90 days, deleted after 7 years |
| Transaction history | 7 years after cancellation | Financial regulations | Anonymized after 90 days, deleted after 7 years |
| Invoice records | 7 years after cancellation | Tax audits | Retained on LemonSqueezy (external) |
| User link (user_id) | 90 days after cancellation | User support | Set to NULL (anonymized) |
| Plan/pricing metadata | 7 years after cancellation | Financial records | Retained (non-personal data) |

**Notes:**
- **90-day anonymization**: After 90 days, `user_id` is set to NULL (subscription anonymized)
- **7-year retention**: Anonymized subscription data is retained for tax compliance
- **No deletion before 7 years**: Financial records MUST be retained per IRS/EU regulations
- **External data**: LemonSqueezy retains invoice data per their own retention policies

#### Refund Records

| Data Type | Retention Period | Reason | Deletion Method |
|-----------|------------------|--------|-----------------|
| Refund records | 7 years after refund | Financial regulations | Anonymized after 90 days, deleted after 7 years |
| Dispute records | 7 years after resolution | Legal requirements | Anonymized after 90 days, deleted after 7 years |

### 2. Webhook Events

| Data Type | Retention Period | Reason | Deletion Method |
|-----------|------------------|--------|-----------------|
| Processed webhook events | 90 days | Debugging, audit trail | Automated deletion (daily job) |
| Failed webhook events | 90 days | Error investigation | Automated deletion (daily job) |
| Webhook payload (JSONB) | 90 days | Replay, troubleshooting | Deleted with event |
| Idempotency records | 90 days | Prevent duplicates | Deleted with event |

**Configuration:**
- **Default**: 90 days (configurable via env var)
- **Rationale**: 90 days provides sufficient time for debugging and audit reviews
- **Query**: `created_at < NOW() - INTERVAL '90 days' AND processed = true`

**Notes:**
- Only **processed** webhook events are deleted (failed events retained for investigation)
- Webhook events do NOT contain cardholder data (safe to delete)
- Deletion runs daily at 2 AM UTC (configurable)

### 3. Audit Logs

| Data Type | Retention Period | Reason | Deletion Method |
|-----------|------------------|--------|-----------------|
| Payment audit logs | 1 year (365 days) | Security compliance, investigations | Automated deletion (daily job) |
| Admin action logs | 1 year (365 days) | Accountability, compliance | Automated deletion (daily job) |
| Authentication logs | 1 year (365 days) | Security monitoring | Automated deletion (daily job) |
| System logs | 1 year (365 days) | Troubleshooting | Automated deletion (daily job) |

**Configuration:**
- **Default**: 365 days (configurable via `AUDIT_LOG_RETENTION_DAYS`)
- **Rationale**: 1 year balances security needs with privacy requirements
- **Query**: `created_at < NOW() - INTERVAL '365 days'`

**Notes:**
- Audit logs contain user actions, timestamps, and metadata
- Required for security incident investigations and compliance audits
- 1-year retention exceeds most regulatory requirements (typically 90 days)
- Longer retention (2-3 years) may be required for regulated industries

### 4. Email Logs

| Data Type | Retention Period | Reason | Deletion Method |
|-----------|------------------|--------|-----------------|
| Email delivery logs | 30 days | Troubleshooting delivery issues | Automated deletion (daily job) |
| Email events (open, click) | 30 days | Support investigations | Automated deletion (cascade with logs) |
| Orphaned email events | 30 days | Cleanup | Automated deletion (daily job) |

**Configuration:**
- **Default**: 30 days (configurable via env vars)
- **Rationale**: 30 days sufficient for delivery troubleshooting
- **Query**: `created_at < NOW() - INTERVAL '30 days'`

**Notes:**
- Email logs contain: recipient email, subject, status, timestamps
- Email events (open, click) are deleted via CASCADE when log is deleted
- Orphaned events (email_log_id = NULL) are cleaned up separately

### 5. User Sessions

| Data Type | Retention Period | Reason | Deletion Method |
|-----------|------------------|--------|-----------------|
| Inactive sessions | 7 days since last activity | Security, performance | Automated deletion (daily job) |
| Expired sessions | Immediate (on expiration) | Security | Automated deletion (daily job) |
| Revoked sessions | 7 days after revocation | Audit trail | Automated deletion (daily job) |

**Configuration:**
- **Default**: 7 days inactive (configurable via `USER_SESSION_INACTIVE_DAYS`)
- **Rationale**: Balance between user experience and security
- **Query**: `last_activity_at < NOW() - INTERVAL '7 days' OR expires_at < NOW() OR revoked_at IS NOT NULL`

**Notes:**
- Sessions are deleted based on last activity (not creation date)
- Expired sessions are deleted immediately (no retention needed)
- Revoked sessions (explicit logout) are retained for 7 days for audit trail

### 6. Temporary Data

| Data Type | Retention Period | Reason | Deletion Method |
|-----------|------------------|--------|-----------------|
| Password reset tokens | 1 hour after creation | Security | Automatic expiration |
| Email verification tokens | 24 hours after creation | Security | Automatic expiration |
| OAuth state tokens | 10 minutes after creation | Security | Automatic expiration |

**Notes:**
- Temporary data uses TTL (time-to-live) expiration
- No cleanup job needed (expired tokens ignored)

---

## Automated Cleanup System

### Overview

WREXT implements an automated data cleanup system that runs daily to delete or anonymize data that has exceeded its retention period.

**Key Components:**
1. **DataCleanupService** - Core cleanup logic (`src/services/data_cleanup_service.py`)
2. **Scheduled Task Manager** - APScheduler for daily execution (`src/tasks/scheduled_tasks.py`)
3. **Cleanup Configuration** - Retention periods and settings (`src/config/cleanup_config.py`)

### Schedule

**Default Schedule:**
- **Frequency**: Daily
- **Time**: 2:00 AM UTC (configurable via `CLEANUP_HOUR` env var)
- **Duration**: 5-30 minutes (depending on data volume)
- **Overlap Prevention**: Max 1 concurrent execution (APScheduler config)

**Configuration:**
```bash
# Enable/disable cleanup (default: true)
CLEANUP_ENABLED=true

# Schedule (default: 2 AM UTC)
CLEANUP_HOUR=2
CLEANUP_MINUTE=0

# Batch size (default: 1000 records per batch)
CLEANUP_BATCH_SIZE=1000

# Dry run mode (for testing, default: false)
CLEANUP_DRY_RUN=false
```

### Cleanup Operations

Each cleanup operation:

1. **Calculates cutoff date** based on retention period
2. **Counts eligible records** for logging/monitoring
3. **Deletes in batches** (default: 1000 records) to avoid long transactions
4. **Commits after each batch** for database performance
5. **Logs results** (success, failure, record counts)

**Cleanup Order:**
1. Audit logs (oldest first)
2. Email logs and events (oldest first)
3. Inactive user sessions (oldest first)
4. Processed webhook events (oldest first)
5. Cancelled subscriptions (anonymization only)

### Batch Deletion Logic

**Why Batch Deletion?**
- Avoids long-running database transactions
- Reduces lock contention on tables
- Allows for incremental progress (can resume if interrupted)
- Better monitoring (progress logs per batch)

**Batch Size:**
- Default: 1000 records per batch
- Configurable via `CLEANUP_BATCH_SIZE` environment variable
- Trade-off: Larger batches = fewer transactions but longer locks

**Example (Webhook Cleanup):**
```python
while True:
    # Delete a batch of 1000 webhook events
    result = DELETE FROM webhook_events
             WHERE created_at < cutoff_date AND processed = true
             LIMIT 1000
             RETURNING id

    if result.count == 0:
        break  # No more records to delete

    await db.commit()  # Commit batch

    if result.count < 1000:
        break  # Last batch (partial)
```

### Monitoring & Logging

**Log Output (Daily Cleanup):**
```
[INFO] Starting scheduled data cleanup task...
[INFO] Cleaning audit logs older than 2024-10-20T02:00:00Z (retention: 365 days)
[INFO] Deleted 2,341 audit logs
[INFO] Cleaning email logs older than 2025-09-20T02:00:00Z (retention: 30 days)
[INFO] Deleted 15,234 email logs (events deleted via CASCADE)
[INFO] Cleaning webhook events older than 2025-07-22T02:00:00Z (retention: 90 days)
[INFO] Deleted 8,765 processed webhook events
[INFO] Anonymizing cancelled subscriptions older than 2025-07-22T02:00:00Z
[INFO] Anonymized 23 cancelled subscriptions (user_id set to NULL)
[INFO] Data cleanup completed: 26,363 total records deleted/anonymized
```

**Structured Logging:**
- All cleanup operations log structured JSON with:
  - `retention_days`: Configured retention period
  - `cutoff_date`: Calculated deletion cutoff
  - `deleted_count`: Number of records deleted
  - `duration_ms`: Operation duration

**Sentry Integration:**
- Cleanup failures are automatically sent to Sentry
- Alert triggered if cleanup fails
- Full exception trace and context included

### Dry Run Mode

**For testing without actual deletion:**

```bash
# Enable dry run mode
CLEANUP_DRY_RUN=true

# Run cleanup (counts only, no deletion)
# Output: "[DRY RUN] Would delete 1,234 audit logs"
```

**Use Cases:**
- Testing retention configuration before production
- Estimating cleanup impact (record counts)
- Verifying queries and logic
- Training and documentation

### Manual Execution

**Run cleanup manually (outside schedule):**

```python
# Via Python script
from src.tasks.scheduled_tasks import run_cleanup_manually

results = await run_cleanup_manually(dry_run=False)
print(f"Deleted {sum(results.values())} records")

# Via management CLI (if implemented)
python manage.py cleanup --dry-run
python manage.py cleanup --execute
```

**Use Cases:**
- Immediate cleanup after configuration changes
- One-time bulk cleanup (e.g., after data import)
- Testing before production deployment
- Emergency cleanup (storage space issues)

---

## User Account Deletion

### Deletion Request Process

When a user requests account deletion:

1. **User initiates deletion**
   - Via Account Settings → "Delete My Account" button
   - Must confirm deletion (prevent accidental deletion)

2. **Grace period begins (7 days)**
   - Account marked with `deleted_at` timestamp
   - User can still log in during grace period
   - "Your account deletion is scheduled" banner displayed
   - User can cancel deletion during grace period

3. **After grace period (Day 8)**
   - Account permanently deleted
   - Personal data deleted (name, email, profile)
   - Subscription data anonymized (user_id → NULL)
   - Associated data handled per retention policies

4. **Long-term retention (7 years)**
   - Anonymized financial records (no link to user identity)
   - Aggregated analytics data (no personal identifiers)

### Data Handling on Account Deletion

| Data Type | Immediate (Day 1) | After Grace Period (Day 8) | Long-Term (7 years) |
|-----------|-------------------|----------------------------|---------------------|
| **User Profile** | Account deactivated | Deleted | Deleted |
| **Authentication** | Login disabled | Password hash deleted | Deleted |
| **Email Address** | Retained (for reversal) | Deleted | Deleted |
| **Personal Info** | Retained (for reversal) | Deleted | Deleted |
| **Active Subscription** | Cancelled | Anonymized (user_id → NULL) | Anonymized subscription retained |
| **Transaction History** | No change | Anonymized (user_id → NULL) | Anonymized records retained |
| **User-Created Content** | No change | Deleted or anonymized (configurable) | Deleted |
| **Audit Logs** | No change | user_id → NULL (anonymized) | Retained per policy (365 days) |
| **Sessions** | All sessions revoked | Deleted | Deleted |

**Implementation:**
- Account deletion is handled by `AccountCleanupService` (see `src/utils/account_cleanup.py`)
- Grace period tracked via `deleted_at` timestamp
- Cleanup job runs daily to process expired grace periods

### User Cancellation

**Users can cancel deletion during grace period:**

1. User logs in (still permitted during grace period)
2. Banner: "Your account deletion is scheduled for [date]. Cancel deletion?"
3. User clicks "Cancel Deletion"
4. `deleted_at` timestamp is cleared
5. Account returns to normal active status

**Implementation:**
```python
# Cancel deletion
user.deleted_at = None
await db.commit()
```

### GDPR Right to Erasure Compliance

**GDPR Article 17 Requirements:**
- ✅ User can request deletion
- ✅ Deletion executed within 30 days
- ✅ Personal data permanently deleted
- ✅ Exceptions documented (legal obligations, financial records)
- ✅ User notified of deletion completion (email sent)

**Exceptions (Legal Basis for Retention):**
- Financial records (7 years) - Tax compliance (GDPR Art. 17(3)(e))
- Audit logs (1 year) - Legal obligations (GDPR Art. 17(3)(b))
- Anonymized data - Not personal data (GDPR does not apply)

---

## Financial Records Retention

### Legal Requirements

**United States (IRS):**
- **Requirement**: 7 years for tax records
- **Scope**: All income, expenses, and transactions
- **Penalty**: Fines, interest, potential criminal prosecution
- **Reference**: IRS Publication 583

**European Union (VAT):**
- **Requirement**: 7 years for VAT records (varies by member state)
- **Scope**: Invoices, receipts, VAT filings
- **Penalty**: Fines, interest, VAT assessment adjustments
- **Reference**: EU VAT Directive 2006/112/EC

**United Kingdom (HMRC):**
- **Requirement**: 6 years for tax records (7 years recommended)
- **Scope**: Business records, invoices, VAT records
- **Penalty**: Fines, potential tax investigation
- **Reference**: UK HMRC guidelines

**Sarbanes-Oxley Act (SOX - if applicable):**
- **Requirement**: 7 years for audit-related records
- **Scope**: Financial statements, audit reports, supporting documents
- **Penalty**: Criminal penalties (fines, imprisonment)
- **Reference**: SOX Section 802

### WREXT Implementation

**Subscription Data (Financial Records):**

1. **Active subscriptions**: Retained indefinitely (required for service delivery)
2. **Cancelled subscriptions**:
   - 90 days: User link removed (`user_id` → NULL) - **Anonymization**
   - 7 years: Anonymized subscription data retained - **Tax Compliance**
   - After 7 years: Permanently deleted

**What is Retained (Anonymized):**
- Subscription ID (internal reference)
- Plan ID and pricing (financial amounts)
- Billing period (monthly, yearly)
- Transaction dates and amounts
- LemonSqueezy subscription ID (external reference)
- Status history (active, cancelled, expired)

**What is Deleted (Anonymized):**
- User ID (link to user identity) → **NULL**
- User email, name, personal info → **Deleted from users table**
- No way to identify which user the subscription belonged to

**Example (Anonymized Subscription Record):**
```json
{
  "id": "sub_abc123",
  "user_id": null,  // ← Anonymized
  "plan_id": "plan_pro",
  "amount": 29.99,
  "currency": "USD",
  "billing_period": "monthly",
  "status": "cancelled",
  "start_date": "2023-01-15",
  "cancelled_at": "2024-05-10",
  "lemonsqueezy_subscription_id": "ls_sub_xyz789"
}
```

**Compliance:**
- ✅ Meets 7-year financial record retention (IRS, EU VAT, SOX)
- ✅ Respects user privacy (anonymized after 90 days)
- ✅ GDPR compliant (anonymized data is not personal data)
- ✅ Audit trail for tax purposes (amounts, dates, plan details)

### LemonSqueezy Data Retention

**External Data (Stored by LemonSqueezy):**
- Invoices and receipts
- Payment card details (tokenized)
- Customer portal data
- Refund records

**LemonSqueezy Retention:**
- LemonSqueezy maintains their own retention policies (independent of WREXT)
- See: https://www.lemonsqueezy.com/privacy

**User Requests:**
- If user requests deletion of LemonSqueezy data, they must contact LemonSqueezy directly
- WREXT cannot delete data in LemonSqueezy systems
- User notified of this during account deletion process

---

## Implementation Details

### Database Schema Support

**Tables with Retention-Related Fields:**

```sql
-- Webhook Events
CREATE TABLE webhook_events (
    id UUID PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,  -- ← Used for retention
    processed BOOLEAN NOT NULL,      -- ← Only delete processed events
    ...
);
CREATE INDEX idx_webhook_created ON webhook_events(created_at);

-- Audit Logs
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,  -- ← Used for retention
    ...
);
CREATE INDEX idx_audit_created ON audit_logs(created_at);

-- User Subscriptions
CREATE TABLE user_subscriptions (
    id UUID PRIMARY KEY,
    user_id UUID,                    -- ← Set to NULL for anonymization
    updated_at TIMESTAMP NOT NULL,   -- ← Used for anonymization cutoff
    status VARCHAR(50) NOT NULL,     -- ← Check for 'cancelled', 'expired'
    ...
);
CREATE INDEX idx_subscription_user ON user_subscriptions(user_id);
CREATE INDEX idx_subscription_status ON user_subscriptions(status);

-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY,
    deleted_at TIMESTAMP,            -- ← Grace period tracking
    ...
);
CREATE INDEX idx_users_deleted ON users(deleted_at);
```

### Performance Considerations

**Query Optimization:**

1. **Indexes**: All retention queries use indexed columns (`created_at`, `user_id`, `status`)
2. **Batch deletion**: Deletes in batches (1000 records) to avoid long transactions
3. **Off-peak execution**: Runs at 2 AM UTC (low traffic period)
4. **LIMIT clause**: Prevents full table scans

**Example Query (Optimized):**
```sql
-- Efficient: Uses index on created_at
DELETE FROM webhook_events
WHERE created_at < '2025-07-22' AND processed = true
LIMIT 1000;

-- Avoid: Full table scan (no index on payload)
DELETE FROM webhook_events
WHERE payload->>'event_type' = 'subscription_created';
```

**Database Load:**
- Cleanup runs during low-traffic hours (2 AM UTC)
- Batch commits reduce transaction size
- Query planner uses indexes (verified with EXPLAIN ANALYZE)

### Error Handling

**Cleanup Failures:**

1. **Database connection error**
   - Retry with exponential backoff
   - Alert sent to Sentry
   - Next scheduled run will retry

2. **Batch deletion error**
   - Current batch rolled back
   - Error logged with context
   - Next batch attempted
   - Partial progress is acceptable

3. **Transaction timeout**
   - Reduce batch size (via `CLEANUP_BATCH_SIZE`)
   - Increase query timeout
   - Consider archiving before deletion

**Monitoring:**
- Cleanup success/failure tracked in logs
- Sentry alerts on failures
- Metrics: deleted_count, duration_ms, error_rate

---

## Compliance Verification

### Annual Review Checklist

**Review Schedule:** October (annually)

- [ ] Verify retention periods still meet legal requirements
- [ ] Check for new regulatory requirements (GDPR updates, new laws)
- [ ] Review cleanup logs for errors or anomalies
- [ ] Verify automated cleanup is running (check last execution date)
- [ ] Test manual cleanup execution (dry run)
- [ ] Verify anonymization is working (check cancelled subscriptions)
- [ ] Review storage metrics (database size, cleanup effectiveness)
- [ ] Update documentation if retention periods changed
- [ ] Communicate changes to users (if applicable)

### Audit Evidence

**For Compliance Audits:**

1. **Policy Documentation** (this document)
2. **Configuration Files** (`cleanup_config.py`)
3. **Cleanup Logs** (past 12 months)
4. **Database Queries** (retention query verification)
5. **Test Results** (dry run output, test coverage)
6. **User Communication** (privacy policy, deletion confirmations)

**Retention of Audit Evidence:**
- Policy documents: 7 years
- Cleanup logs: 1 year
- Test results: 1 year

### GDPR Article 30 - Records of Processing

**Required Documentation:**
- ✅ Retention periods documented (this policy)
- ✅ Legal basis for retention (tax compliance, legal obligations)
- ✅ Deletion procedures documented (automated cleanup)
- ✅ Data subject rights supported (account deletion, data export)

---

## Policy Exceptions

### When Retention Periods May Be Extended

1. **Legal Hold (Litigation)**
   - If involved in active litigation, retention periods are suspended
   - Data relevant to the case is preserved until litigation concludes
   - Legal team provides written notice of legal hold

2. **Regulatory Investigation**
   - If under investigation by regulatory authority (FTC, ICO, tax authority)
   - Relevant data preserved until investigation concludes
   - Compliance team provides written notice

3. **Fraud Investigation**
   - If suspicious activity or fraud is detected
   - Related data preserved until investigation concludes
   - Security team provides written notice

4. **User Request**
   - User may request longer retention (e.g., for tax purposes)
   - Request must be explicit and documented
   - Retention extended only for specific data types

**Process:**
1. Exception request submitted to compliance team
2. Legal review and approval
3. Data marked with retention exception flag
4. Cleanup job skips flagged data
5. Exception reviewed periodically (quarterly)
6. Exception removed when no longer needed

### Emergency Deletion

**When data must be deleted immediately:**

1. **Data breach** - Compromised data deleted to prevent further exposure
2. **Legal order** - Court order requiring immediate deletion
3. **Critical security issue** - Data posing active security risk

**Process:**
1. Emergency deletion request to security team
2. Approval from engineering lead and legal counsel
3. Manual deletion executed (bypass scheduled cleanup)
4. Deletion verified and documented
5. Incident report filed

---

## Contact Information

### Policy Questions

**Email:** compliance@wrext.com
**Response Time:** 2 business days

### Technical Questions (Implementation)

**Email:** engineering@wrext.com
**Response Time:** 1 business day

### Data Subject Requests (Deletion, Export)

**Email:** privacy@wrext.com
**Response Time:** 30 days (GDPR requirement)

### Legal Questions

**Email:** legal@wrext.com
**Response Time:** 3 business days

---

## Related Documentation

- [PCI DSS Compliance](PCI_COMPLIANCE.md) - Payment data retention and security
- [Privacy Policy for Payments](../PRIVACY_POLICY_PAYMENTS.md) - User-facing retention policy
- [Data Cleanup Service](../../src/services/data_cleanup_service.py) - Implementation code
- [Cleanup Configuration](../../src/config/cleanup_config.py) - Retention periods config
- [Account Cleanup Utility](../../src/utils/account_cleanup.py) - User deletion logic

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-20 | Engineering Team | Initial comprehensive data retention policy |

---

## Approval

**This policy has been reviewed and approved:**

**Approved By:**
Engineering Lead: _________________ Date: _________
Compliance Lead: _________________ Date: _________
Legal Counsel: ___________________ Date: _________

**Next Review Date:** October 2026

---

**Document Classification:** Internal - Confidential
**Distribution:** Engineering, Compliance, Legal, Leadership

---

## Summary

**Key Retention Periods:**
- Webhook events: **90 days**
- Audit logs: **1 year (365 days)**
- Email logs: **30 days**
- Sessions: **7 days** (inactive)
- Cancelled subscriptions: **Anonymized after 90 days, retained 7 years**
- User account deletion: **7-day grace period**, then permanent deletion

**Automated Cleanup:**
- Runs **daily at 2 AM UTC**
- Deletes in **batches of 1000** records
- Logs results to **structured logging + Sentry**
- **Dry run mode** available for testing

**Compliance:**
- ✅ GDPR Article 5(1)(e) - Storage limitation
- ✅ GDPR Article 17 - Right to erasure
- ✅ CCPA - Right to deletion
- ✅ IRS/EU VAT - 7-year financial records
- ✅ PCI DSS - No cardholder data stored

**For more information:** compliance@wrext.com
