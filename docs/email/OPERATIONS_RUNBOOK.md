# Email System Operations Runbook

**Last Updated:** 2025-10-12
**System:** WREXT Email Integration
**On-Call Reference:** Quick troubleshooting and maintenance guide

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Monitoring & Alerting](#monitoring--alerting)
3. [Common Issues](#common-issues)
4. [Database Queries](#database-queries)
5. [Performance Optimization](#performance-optimization)
6. [Maintenance Procedures](#maintenance-procedures)
7. [Incident Response](#incident-response)
8. [Analytics & Reporting](#analytics--reporting)

---

## System Overview

### Architecture

```
┌─────────────┐
│   Routes    │  FastAPI endpoints
└──────┬──────┘
       │
┌──────▼──────┐
│EmailService │  Business logic, retry, logging
└──────┬──────┘
       │
┌──────▼──────────────┐
│ Provider Factory    │  Provider selection
└──────┬──────────────┘
       │
   ┌───┴───┬────────┬──────┐
   │       │        │      │
┌──▼──┐ ┌─▼──┐  ┌──▼──┐ ┌─▼──┐
│Resend│ │SMTP│  │Mock │ │...│
└──────┘ └────┘  └─────┘ └────┘
```

### Key Components

- **EmailService** (`src/services/email_service.py`)
  - Send emails with retry and fallback
  - Database logging
  - Background task processing

- **EmailEventService** (`src/services/email_event_service.py`)
  - Process webhook events
  - Update email status
  - Deduplication

- **Providers**
  - `ResendEmailProvider`: Primary production provider
  - `SMTPEmailProvider`: Fallback provider
  - `MockEmailProvider`: Testing only

### Database Tables

- **`email_logs`**: All email send attempts
- **`email_events`**: Webhook events (delivered, opened, bounced, etc.)

---

## Monitoring & Alerting

### Key Metrics to Track

#### 1. Email Delivery Rate

**Target:** >95% delivery rate (sent → delivered)

**Query:**
```sql
SELECT
  COUNT(*) FILTER (WHERE status = 'delivered') * 100.0 / NULLIF(COUNT(*), 0) as delivery_rate,
  COUNT(*) as total_emails
FROM email_logs
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND status IN ('sent', 'delivered', 'bounced', 'failed');
```

**Alert if:** Delivery rate < 90%

#### 2. Email Failure Rate

**Target:** <5% failure rate

**Query:**
```sql
SELECT
  COUNT(*) FILTER (WHERE status IN ('failed', 'bounced')) * 100.0 / NULLIF(COUNT(*), 0) as failure_rate,
  COUNT(*) FILTER (WHERE status IN ('failed', 'bounced')) as failed_count
FROM email_logs
WHERE created_at > NOW() - INTERVAL '1 hour';
```

**Alert if:** Failure rate > 10% in last hour

#### 3. Provider Health

**Query:**
```sql
SELECT
  provider,
  status,
  COUNT(*) as count,
  COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY provider) as percentage
FROM email_logs
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY provider, status
ORDER BY provider, status;
```

**Alert if:** Primary provider (resend) failing >20%

#### 4. Webhook Processing Lag

**Target:** Events processed within 1 minute

**Query:**
```sql
SELECT
  AVG(EXTRACT(EPOCH FROM (ee.created_at - el.sent_at))) as avg_lag_seconds,
  MAX(EXTRACT(EPOCH FROM (ee.created_at - el.sent_at))) as max_lag_seconds
FROM email_events ee
JOIN email_logs el ON ee.email_log_id = el.id
WHERE ee.created_at > NOW() - INTERVAL '1 hour'
  AND ee.event_type = 'email.delivered';
```

**Alert if:** avg_lag > 120 seconds

#### 5. Email Queue Depth

**Target:** No emails stuck in "queued" for >5 minutes

**Query:**
```sql
SELECT
  COUNT(*) as stuck_emails,
  MIN(created_at) as oldest_queued
FROM email_logs
WHERE status = 'queued'
  AND created_at < NOW() - INTERVAL '5 minutes';
```

**Alert if:** stuck_emails > 10

### Recommended Alerts

#### Critical Alerts (Page On-Call)

1. **Email system down**
   - Trigger: 100% failure rate for 5 minutes
   - Action: Check provider status, switch to fallback

2. **Database unavailable**
   - Trigger: Connection errors
   - Action: Check database health, restart if needed

3. **Webhook endpoint down**
   - Trigger: 5xx errors from webhook endpoint
   - Action: Check application health, restart if needed

#### Warning Alerts (Slack/Email)

1. **High failure rate**
   - Trigger: >10% failure rate for 15 minutes
   - Action: Investigate logs, check provider status

2. **Slow email delivery**
   - Trigger: Average delivery time >2 minutes
   - Action: Check provider performance, consider scaling

3. **Webhook processing lag**
   - Trigger: Events delayed >5 minutes
   - Action: Check background task queue

### Monitoring Dashboards

#### Grafana/Datadog Queries

**Email Volume (per hour):**
```sql
SELECT
  DATE_TRUNC('hour', created_at) as hour,
  COUNT(*) as email_count
FROM email_logs
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY hour
ORDER BY hour;
```

**Success Rate by Template Type:**
```sql
SELECT
  template_type,
  COUNT(*) FILTER (WHERE status = 'delivered') * 100.0 / COUNT(*) as success_rate,
  COUNT(*) as total
FROM email_logs
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY template_type
HAVING COUNT(*) > 10
ORDER BY success_rate ASC;
```

**Provider Performance Comparison:**
```sql
SELECT
  provider,
  AVG(EXTRACT(EPOCH FROM (sent_at - created_at))) as avg_send_time_seconds,
  COUNT(*) FILTER (WHERE status = 'sent') * 100.0 / COUNT(*) as success_rate
FROM email_logs
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY provider;
```

---

## Common Issues

### Issue 1: Emails Not Sending

#### Symptoms
- Status stuck on "queued"
- No errors in logs
- Users not receiving emails

#### Diagnosis

**Step 1: Check provider configuration**
```bash
# Verify provider is set
python3 -c "from src.config.email_config import email_config; print(f'Provider: {email_config.email_provider}, API Key Set: {bool(email_config.resend_api_key)}')"
```

**Step 2: Check recent failures**
```sql
SELECT
  id,
  to_email,
  status,
  error_message,
  created_at
FROM email_logs
WHERE status = 'failed'
  AND created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC
LIMIT 10;
```

**Step 3: Test provider directly**
```python
import asyncio
from src.providers.email.factory import EmailProviderFactory
from src.providers.email.base import EmailMessage, EmailRecipient

async def test():
    provider = EmailProviderFactory.get_provider()
    print(f"Testing provider: {provider.get_provider_name()}")

    result = await provider.send_email(EmailMessage(
        to=[EmailRecipient(email="test@example.com")],
        subject="Test",
        html="<p>Test</p>",
        from_email="noreply@wrext.com"
    ))

    print(f"Success: {result.success}")
    if not result.success:
        print(f"Error: {result.error}")

asyncio.run(test())
```

#### Resolution

**If API key issue:**
```bash
# Regenerate API key in Resend dashboard
# Update .env
export RESEND_API_KEY=re_new_key_xxxxx

# Restart application
sudo systemctl restart wrext-backend
```

**If provider issue:**
```bash
# Switch to SMTP fallback temporarily
export EMAIL_PROVIDER=smtp

# Restart
sudo systemctl restart wrext-backend

# Monitor
tail -f logs/app.log | grep "provider=smtp"
```

**If database issue:**
```bash
# Check database connectivity
psql $DATABASE_URL -c "SELECT COUNT(*) FROM email_logs;"

# Check table locks
psql $DATABASE_URL -c "SELECT * FROM pg_locks WHERE relation = 'email_logs'::regclass;"
```

---

### Issue 2: High Bounce Rate

#### Symptoms
- Many emails with `status = 'bounced'`
- Users complaining about not receiving emails

#### Diagnosis

**Check bounce types:**
```sql
SELECT
  event_data->>'bounce_type' as bounce_type,
  COUNT(*) as count
FROM email_events
WHERE event_type = 'email.bounced'
  AND created_at > NOW() - INTERVAL '7 days'
GROUP BY bounce_type
ORDER BY count DESC;
```

**Check affected domains:**
```sql
SELECT
  SUBSTRING(el.to_email FROM '@(.*)$') as domain,
  COUNT(*) as bounces
FROM email_logs el
JOIN email_events ee ON el.id = ee.email_log_id
WHERE ee.event_type = 'email.bounced'
  AND ee.created_at > NOW() - INTERVAL '7 days'
GROUP BY domain
ORDER BY bounces DESC
LIMIT 20;
```

#### Resolution

**Hard bounces (permanent):**
- Invalid email addresses
- Domain doesn't exist
- **Action:** Mark email as invalid, prevent future sends

```sql
-- Find users with hard bounces
SELECT DISTINCT
  el.to_email,
  ee.event_data->>'reason' as reason
FROM email_logs el
JOIN email_events ee ON el.id = ee.email_log_id
WHERE ee.event_type = 'email.bounced'
  AND ee.event_data->>'bounce_type' = 'hard'
  AND ee.created_at > NOW() - INTERVAL '30 days';
```

**Soft bounces (temporary):**
- Mailbox full
- Temporary server issues
- **Action:** Retry after delay

**Deliverability issues:**
- Check domain reputation: https://mxtoolbox.com/
- Verify SPF/DKIM/DMARC records
- Review email content for spam triggers

---

### Issue 3: Webhook Signature Verification Failing

#### Symptoms
- Webhook events returning 401 Unauthorized
- Logs show "Invalid webhook signature"

#### Diagnosis

```bash
# Check if secret is configured
echo $RESEND_WEBHOOK_SECRET

# Check recent webhook errors
tail -f logs/app.log | grep -i "webhook.*signature"
```

#### Resolution

**Step 1: Get correct secret from Resend**
```
1. Log in to Resend dashboard
2. Go to Webhooks → Your endpoint
3. Click "Show Signing Secret"
4. Copy the secret (starts with whsec_)
```

**Step 2: Update environment**
```bash
# Update .env
echo 'RESEND_WEBHOOK_SECRET=whsec_xxxxx' >> .env

# Restart application
sudo systemctl restart wrext-backend
```

**Step 3: Test webhook**
```bash
# Send test webhook from Resend dashboard
# Check logs for success
tail -f logs/app.log | grep -i "webhook.*verified"
```

---

### Issue 4: Duplicate Webhook Events

#### Symptoms
- Same event processed multiple times
- Duplicate entries in `email_events` table

#### Diagnosis

**Check for duplicates:**
```sql
SELECT
  provider_event_id,
  COUNT(*) as duplicate_count
FROM email_events
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY provider_event_id
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;
```

#### Resolution

This should NOT happen - the system has idempotency built in.

**If duplicates found:**
```python
# Check idempotency logic in EmailEventService
# The provider_event_id should be unique
# Format: {email_id}_{event_type}_{timestamp}

# Verify unique constraint exists:
```

```sql
-- Check constraints on email_events
SELECT
  conname,
  contype,
  pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'email_events'::regclass;
```

---

### Issue 5: Slow Email Delivery

#### Symptoms
- Emails taking >5 seconds to send
- Users reporting delays

#### Diagnosis

**Check average send time:**
```sql
SELECT
  template_type,
  AVG(EXTRACT(EPOCH FROM (sent_at - created_at))) as avg_send_time_seconds,
  MAX(EXTRACT(EPOCH FROM (sent_at - created_at))) as max_send_time_seconds,
  COUNT(*) as total
FROM email_logs
WHERE sent_at IS NOT NULL
  AND created_at > NOW() - INTERVAL '1 hour'
GROUP BY template_type
ORDER BY avg_send_time_seconds DESC;
```

**Check database performance:**
```sql
-- Check slow queries
SELECT
  query,
  mean_exec_time,
  calls
FROM pg_stat_statements
WHERE query LIKE '%email_logs%'
ORDER BY mean_exec_time DESC
LIMIT 10;
```

#### Resolution

**If provider is slow:**
- Check Resend status page: https://resend.com/status
- Consider rate limiting adjustments
- Switch to fallback provider temporarily

**If database is slow:**
```sql
-- Rebuild indexes
REINDEX TABLE email_logs;
REINDEX TABLE email_events;

-- Analyze tables
ANALYZE email_logs;
ANALYZE email_events;

-- Check index usage
SELECT
  schemaname,
  tablename,
  indexname,
  idx_scan,
  idx_tup_read
FROM pg_stat_user_indexes
WHERE tablename IN ('email_logs', 'email_events')
ORDER BY idx_scan DESC;
```

**If template rendering is slow:**
- Review template complexity
- Consider caching rendered templates
- Profile template rendering time

---

## Database Queries

### Useful Operational Queries

#### Recent Email Activity
```sql
SELECT
  id,
  to_email,
  subject,
  status,
  provider,
  template_type,
  created_at,
  sent_at
FROM email_logs
ORDER BY created_at DESC
LIMIT 50;
```

#### Emails for Specific User
```sql
SELECT
  el.to_email,
  el.subject,
  el.status,
  el.created_at,
  COALESCE(
    (SELECT event_type
     FROM email_events ee
     WHERE ee.email_log_id = el.id
     ORDER BY ee.created_at DESC
     LIMIT 1),
    'no_events'
  ) as latest_event
FROM email_logs el
WHERE el.to_email = 'user@example.com'
ORDER BY el.created_at DESC
LIMIT 20;
```

#### Emails for Workspace
```sql
SELECT
  to_email,
  subject,
  status,
  template_type,
  created_at
FROM email_logs
WHERE workspace_id = 'workspace-uuid-here'
ORDER BY created_at DESC
LIMIT 50;
```

#### Failed Emails with Errors
```sql
SELECT
  to_email,
  subject,
  error_message,
  failed_at,
  provider,
  template_type
FROM email_logs
WHERE status = 'failed'
  AND created_at > NOW() - INTERVAL '24 hours'
ORDER BY failed_at DESC;
```

#### Email Engagement (Opens & Clicks)
```sql
SELECT
  el.subject,
  el.to_email,
  COUNT(DISTINCT CASE WHEN ee.event_type = 'email.opened' THEN ee.id END) as opens,
  COUNT(DISTINCT CASE WHEN ee.event_type = 'email.clicked' THEN ee.id END) as clicks,
  el.created_at
FROM email_logs el
LEFT JOIN email_events ee ON el.id = ee.email_log_id
WHERE el.created_at > NOW() - INTERVAL '7 days'
  AND el.template_type = 'workspace_invitation'
GROUP BY el.id
HAVING COUNT(DISTINCT CASE WHEN ee.event_type = 'email.opened' THEN ee.id END) > 0
ORDER BY opens DESC, clicks DESC
LIMIT 50;
```

#### Retry Failed Email
```python
# Retry specific failed email
import asyncio
from src.services.email_service import EmailService
from src.api.database.async_database import get_async_db
from uuid import UUID

async def retry_email(email_log_id: str):
    async for db in get_async_db():
        service = EmailService(db)
        result = await service.retry_failed_email(UUID(email_log_id))
        print(f"Retry result: {result.status}")
        break

# Usage:
asyncio.run(retry_email("email-log-uuid-here"))
```

---

## Performance Optimization

### Database Optimization

#### 1. Index Maintenance

**Check index health:**
```sql
SELECT
  schemaname,
  tablename,
  indexname,
  idx_scan as scans,
  idx_tup_read as tuples_read,
  idx_tup_fetch as tuples_fetched,
  pg_size_pretty(pg_relation_size(indexrelid)) as size
FROM pg_stat_user_indexes
WHERE tablename IN ('email_logs', 'email_events')
ORDER BY idx_scan DESC;
```

**Unused indexes (consider removing):**
```sql
SELECT
  schemaname,
  tablename,
  indexname,
  pg_size_pretty(pg_relation_size(indexrelid)) as size
FROM pg_stat_user_indexes
WHERE tablename IN ('email_logs', 'email_events')
  AND idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;
```

#### 2. Table Bloat

**Check table size:**
```sql
SELECT
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size,
  pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as table_size,
  pg_size_pretty(pg_indexes_size(schemaname||'.'||tablename)) as indexes_size
FROM pg_tables
WHERE tablename IN ('email_logs', 'email_events')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

**Vacuum and analyze:**
```sql
-- Regular maintenance
VACUUM ANALYZE email_logs;
VACUUM ANALYZE email_events;

-- Full vacuum (requires table lock - do during maintenance window)
VACUUM FULL email_logs;
```

#### 3. Partition Old Data

For high-volume systems, consider partitioning by created_at:

```sql
-- Example: Partition email_logs by month
CREATE TABLE email_logs_2025_10 PARTITION OF email_logs
FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');

CREATE TABLE email_logs_2025_11 PARTITION OF email_logs
FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');
```

### Application Optimization

#### 1. Connection Pooling

Verify database connection pool settings:

```python
# Check in src/api/database/async_database.py
# Recommended settings for production:
# - pool_size: 20
# - max_overflow: 10
# - pool_timeout: 30
# - pool_recycle: 3600
```

#### 2. Background Task Queue

Monitor background task execution:

```python
# Check if background tasks are backing up
# Consider using Celery for better task management
```

#### 3. Caching

Consider caching:
- Email templates (already rendered)
- User email preferences
- Workspace settings

---

## Maintenance Procedures

### Weekly Maintenance

**Every Monday:**

1. **Review email metrics**
```sql
-- Past week summary
SELECT
  DATE(created_at) as date,
  COUNT(*) as total_emails,
  COUNT(*) FILTER (WHERE status = 'delivered') as delivered,
  COUNT(*) FILTER (WHERE status = 'failed') as failed,
  COUNT(*) FILTER (WHERE status = 'bounced') as bounced
FROM email_logs
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY date;
```

2. **Check for stuck emails**
```sql
SELECT COUNT(*)
FROM email_logs
WHERE status = 'queued'
  AND created_at < NOW() - INTERVAL '1 day';
```

3. **Cleanup old logs (optional)**
```sql
-- Archive emails older than 90 days
-- Only if storage is a concern
DELETE FROM email_events
WHERE created_at < NOW() - INTERVAL '90 days';

DELETE FROM email_logs
WHERE created_at < NOW() - INTERVAL '90 days';
```

### Monthly Maintenance

**First day of month:**

1. **Review deliverability metrics**
```sql
-- Monthly summary by template
SELECT
  template_type,
  COUNT(*) as total,
  COUNT(*) FILTER (WHERE status = 'delivered') * 100.0 / COUNT(*) as delivery_rate,
  COUNT(*) FILTER (WHERE status = 'bounced') * 100.0 / COUNT(*) as bounce_rate
FROM email_logs
WHERE created_at > DATE_TRUNC('month', NOW() - INTERVAL '1 month')
  AND created_at < DATE_TRUNC('month', NOW())
GROUP BY template_type
ORDER BY total DESC;
```

2. **Database maintenance**
```sql
-- Rebuild statistics
ANALYZE email_logs;
ANALYZE email_events;

-- Check table bloat
SELECT
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
  n_live_tup,
  n_dead_tup,
  n_dead_tup * 100.0 / NULLIF(n_live_tup + n_dead_tup, 0) as dead_tup_percent
FROM pg_stat_user_tables
WHERE tablename IN ('email_logs', 'email_events');
```

3. **Review provider costs**
- Check Resend usage dashboard
- Compare with free tier limits
- Forecast next month's usage

---

## Incident Response

### Incident Classification

**P0 - Critical (< 15 min response)**
- Email system completely down
- All emails failing
- Database corruption

**P1 - High (< 1 hour response)**
- >50% email failure rate
- Webhook endpoint down
- Provider degraded

**P2 - Medium (< 4 hours)**
- Specific template failing
- Slow email delivery (>5 min)
- High bounce rate

**P3 - Low (Next business day)**
- Individual email failures
- Cosmetic template issues
- Non-critical log errors

### Incident Response Playbook

#### P0: Email System Down

**1. Immediate actions (0-5 min):**
```bash
# Check application status
systemctl status wrext-backend

# Check logs
tail -f logs/app.log | grep -i "error\|critical"

# Check database connectivity
psql $DATABASE_URL -c "SELECT 1;"
```

**2. Failover (5-10 min):**
```bash
# Switch to SMTP fallback
export EMAIL_PROVIDER=smtp
sudo systemctl restart wrext-backend

# Verify emails sending
tail -f logs/app.log | grep "Email sent"
```

**3. Root cause analysis (10-60 min):**
- Check Resend status page
- Review recent deployments
- Check provider API key validity
- Review error logs

**4. Communication:**
- Update status page
- Notify stakeholders
- Create incident report

#### P1: High Failure Rate

**1. Assess impact:**
```sql
SELECT
  COUNT(*) FILTER (WHERE status = 'failed') * 100.0 / COUNT(*) as failure_rate,
  COUNT(*) as total_last_hour
FROM email_logs
WHERE created_at > NOW() - INTERVAL '1 hour';
```

**2. Identify cause:**
```sql
SELECT
  error_message,
  COUNT(*) as occurrences
FROM email_logs
WHERE status = 'failed'
  AND created_at > NOW() - INTERVAL '1 hour'
GROUP BY error_message
ORDER BY occurrences DESC;
```

**3. Mitigate:**
- If provider issue: Switch to fallback
- If rate limiting: Reduce send rate
- If API key issue: Rotate key

---

## Analytics & Reporting

### Daily Email Report

```sql
-- Daily summary for stakeholders
SELECT
  DATE(created_at) as date,
  COUNT(*) as total_sent,
  COUNT(*) FILTER (WHERE status = 'delivered') as delivered,
  COUNT(*) FILTER (WHERE status = 'delivered') * 100.0 / COUNT(*) as delivery_rate,
  COUNT(DISTINCT workspace_id) as active_workspaces,
  COUNT(DISTINCT to_email) as unique_recipients
FROM email_logs
WHERE created_at > CURRENT_DATE - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

### Engagement Metrics

```sql
-- Open and click rates by template
SELECT
  el.template_type,
  COUNT(DISTINCT el.id) as emails_sent,
  COUNT(DISTINCT CASE WHEN ee.event_type = 'email.opened' THEN el.id END) as opened,
  COUNT(DISTINCT CASE WHEN ee.event_type = 'email.clicked' THEN el.id END) as clicked,
  COUNT(DISTINCT CASE WHEN ee.event_type = 'email.opened' THEN el.id END) * 100.0 / COUNT(DISTINCT el.id) as open_rate,
  COUNT(DISTINCT CASE WHEN ee.event_type = 'email.clicked' THEN el.id END) * 100.0 / COUNT(DISTINCT el.id) as click_rate
FROM email_logs el
LEFT JOIN email_events ee ON el.id = ee.email_log_id
WHERE el.created_at > NOW() - INTERVAL '30 days'
GROUP BY el.template_type
ORDER BY emails_sent DESC;
```

---

## Contact & Escalation

**On-Call Rotation:** See PagerDuty schedule

**Escalation Path:**
1. On-call engineer (15 min)
2. Backend team lead (30 min)
3. Engineering manager (1 hour)

**External Support:**
- **Resend Support:** support@resend.com
- **Documentation:** https://resend.com/docs
- **Status Page:** https://resend.com/status

**Internal Resources:**
- Slack: `#engineering-alerts`
- Wiki: Email System Documentation
- Runbooks: `/docs/email/`
