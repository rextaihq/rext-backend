# Email System Deployment Guide

**Last Updated:** 2025-10-12
**System:** WREXT Email Integration (Resend-based)
**Version:** 1.0.0

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Environment Configuration](#environment-configuration)
4. [Database Setup](#database-setup)
5. [Resend Configuration](#resend-configuration)
6. [Webhook Setup](#webhook-setup)
7. [Deployment Steps](#deployment-steps)
8. [Verification](#verification)
9. [Rollback Procedures](#rollback-procedures)
10. [Troubleshooting](#troubleshooting)

---

## Overview

The WREXT email system uses **Resend** as the primary email provider with **SMTP as a fallback**. The system includes:

- **Provider abstraction** for easy switching between email services
- **Database logging** for all email sends and events
- **Webhook integration** for real-time delivery tracking
- **Python-based HTML templates** for consistent branding
- **Retry mechanism** with automatic fallback

**Architecture:**
```
Routes → EmailService → EmailProvider (Resend/SMTP/Mock)
                ↓
         Database Logging
                ↓
         Webhook Events
```

---

## Prerequisites

### Required Accounts & Access

1. **Resend Account**
   - Sign up at [resend.com](https://resend.com)
   - Verify your domain (for production)
   - Generate API key

2. **Database Access**
   - PostgreSQL 14+ with UUID extension
   - Migration permissions (CREATE TABLE, ALTER TABLE)
   - Connection string with async support

3. **Domain Configuration**
   - Access to DNS records for your domain
   - Ability to add TXT, CNAME, and MX records

### Software Requirements

- **Python:** 3.11 or higher
- **PostgreSQL:** 14+
- **Dependencies:** Listed in `pyproject.toml`
  - `resend>=2.16.0`
  - `svix>=1.17.0`
  - `pydantic-settings>=2.0.0`

---

## Environment Configuration

### Step 1: Configure Environment Variables

Create or update your `.env` file with the following email-related variables:

```bash
# ============================================
# EMAIL CONFIGURATION
# ============================================

# Provider Selection
# Options: "resend" (primary), "smtp" (fallback), "mock" (testing)
EMAIL_PROVIDER=resend
EMAIL_FALLBACK_PROVIDER=smtp

# Master Email Switch
EMAIL_ENABLED=true

# ============================================
# RESEND CONFIGURATION
# ============================================

# API Key (get from https://resend.com/api-keys)
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# From Address (must be verified domain)
RESEND_FROM_EMAIL=noreply@wrext.com
RESEND_FROM_NAME=WREXT

# Webhook Secret (get from webhook configuration)
RESEND_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ============================================
# SMTP FALLBACK CONFIGURATION (Optional)
# ============================================

SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp-username@gmail.com
SMTP_PASSWORD=your-app-specific-password
SMTP_USE_TLS=true

# ============================================
# EMAIL FEATURES
# ============================================

EMAIL_RETRY_ENABLED=true
EMAIL_RETRY_MAX_ATTEMPTS=3
EMAIL_RETRY_DELAY_SECONDS=5
```

### Step 2: Validate Configuration

Run the configuration validator:

```bash
cd wrext-backend

# Test email configuration loads correctly
python3 -c "from src.config.email_config import email_config; print(f'Provider: {email_config.email_provider}'); print(f'From: {email_config.resend_from_email}')"
```

Expected output:
```
Provider: resend
From: noreply@wrext.com
```

---

## Database Setup

### Step 3: Run Database Migrations

The email system requires two database tables: `email_logs` and `email_events`.

#### Check Current Migration Status

```bash
cd wrext-backend

# Check current Alembic revision
alembic current

# View pending migrations
alembic heads
```

#### Apply Email Migrations

```bash
# Apply all pending migrations (includes email tables)
alembic upgrade head
```

The following migrations will be applied:

1. **`90e8f4da90df_create_email_logs_table.py`**
   - Creates `email_logs` table
   - Adds indexes on `workspace_id`, `user_id`, `provider`, `status`

2. **`48016a71eb87_create_email_events_table.py`**
   - Creates `email_events` table
   - Adds indexes for event lookups and deduplication

#### Verify Tables Created

```bash
# Connect to PostgreSQL
psql $DATABASE_URL

# List email tables
\dt email_*

# Check email_logs schema
\d email_logs

# Check email_events schema
\d email_events

# Exit
\q
```

Expected output:
```
              List of relations
 Schema |     Name      | Type  |  Owner
--------+---------------+-------+---------
 public | email_events  | table | postgres
 public | email_logs    | table | postgres
```

### Step 4: Test Database Connection

```python
# Test database connectivity
python3 << 'EOF'
import asyncio
from src.api.database.async_database import get_async_db
from src.api.models.email_models.email_log import EmailLog
from sqlalchemy import select

async def test():
    async for db in get_async_db():
        result = await db.execute(select(EmailLog).limit(1))
        print("✓ Database connection successful")
        print("✓ Email tables accessible")
        break

asyncio.run(test())
EOF
```

---

## Resend Configuration

### Step 5: Domain Verification

#### Add Domain to Resend

1. Log in to [Resend Dashboard](https://resend.com/domains)
2. Click **"Add Domain"**
3. Enter your domain: `wrext.com`
4. Copy the DNS records provided

#### Configure DNS Records

Add the following DNS records to your domain:

**SPF Record (TXT):**
```
Type: TXT
Name: @
Value: v=spf1 include:amazonses.com ~all
TTL: 3600
```

**DKIM Records (CNAME):**
```
Type: CNAME
Name: resend._domainkey
Value: resend._domainkey.amazonses.com
TTL: 3600
```

**DMARC Record (TXT):**
```
Type: TXT
Name: _dmarc
Value: v=DMARC1; p=none; rua=mailto:postmaster@wrext.com
TTL: 3600
```

#### Verify Domain

```bash
# Check DNS propagation
dig TXT wrext.com +short
dig CNAME resend._domainkey.wrext.com +short

# Or use online tool
# https://mxtoolbox.com/SuperTool.aspx
```

Wait 5-10 minutes for DNS propagation, then click **"Verify"** in Resend dashboard.

### Step 6: Generate API Key

1. Go to [API Keys](https://resend.com/api-keys)
2. Click **"Create API Key"**
3. Name: `WREXT Production`
4. Permissions: **Full Access** (or restrict to "Send emails" + "Webhooks")
5. Copy the API key (starts with `re_`)
6. Add to `.env`: `RESEND_API_KEY=re_xxxxx...`

**⚠️ Security Note:** Never commit API keys to version control!

### Step 7: Test Email Sending

```python
# Test Resend integration
python3 << 'EOF'
import resend
from src.config.email_config import email_config

resend.api_key = email_config.resend_api_key

params = {
    "from": f"{email_config.resend_from_name} <{email_config.resend_from_email}>",
    "to": ["your-test-email@example.com"],
    "subject": "WREXT Email System Test",
    "html": "<h1>Email system is working!</h1><p>This is a test from the deployment process.</p>"
}

try:
    email = resend.Emails.send(params)
    print(f"✓ Test email sent successfully!")
    print(f"  Message ID: {email['id']}")
except Exception as e:
    print(f"✗ Failed to send test email: {e}")
EOF
```

---

## Webhook Setup

### Step 8: Configure Webhook Endpoint

#### Get Your Webhook URL

Your webhook endpoint will be:
```
https://your-domain.com/api/v1/email/webhooks/resend
```

For staging:
```
https://staging.wrext.com/api/v1/email/webhooks/resend
```

#### Add Webhook in Resend Dashboard

1. Go to [Webhooks](https://resend.com/webhooks)
2. Click **"Add Endpoint"**
3. **Endpoint URL:** Your webhook URL
4. **Events to send:** Select all:
   - ✅ `email.sent`
   - ✅ `email.delivered`
   - ✅ `email.delivery_delayed`
   - ✅ `email.bounced`
   - ✅ `email.complained`
   - ✅ `email.opened`
   - ✅ `email.clicked`
5. Click **"Add Endpoint"**
6. Copy the **Signing Secret** (starts with `whsec_`)
7. Add to `.env`: `RESEND_WEBHOOK_SECRET=whsec_xxxxx...`

#### Test Webhook Endpoint

```bash
# Test webhook health endpoint
curl https://your-domain.com/api/v1/email/webhooks/health

# Expected response:
# {
#   "status": "healthy",
#   "service": "resend-webhooks",
#   "webhook_secret_configured": true
# }
```

#### Send Test Webhook

In Resend dashboard:
1. Go to your webhook endpoint
2. Click **"Send Test Event"**
3. Select event type: `email.delivered`
4. Click **"Send Test"**

Check your application logs:
```bash
tail -f logs/app.log | grep -i webhook
```

Expected log output:
```
INFO: Received webhook from Resend
INFO: Webhook signature verified successfully
INFO: Processing webhook event event_type=email.delivered
INFO: Background webhook processing completed
```

---

## Deployment Steps

### Step 9: Deploy to Staging

#### Pre-Deployment Checklist

- [ ] All environment variables configured in staging `.env`
- [ ] Database migrations applied
- [ ] Resend domain verified
- [ ] Resend API key added to environment
- [ ] Webhook endpoint created and tested
- [ ] Dependencies installed (`resend`, `svix`)

#### Deployment Commands

```bash
# 1. Pull latest code
cd wrext-backend
git pull origin main

# 2. Install dependencies
uv sync

# 3. Run migrations
alembic upgrade head

# 4. Restart application
# (Depends on your deployment method)

# Docker:
docker-compose restart backend

# Systemd:
sudo systemctl restart wrext-backend

# PM2:
pm2 restart wrext-backend
```

#### Verify Deployment

```bash
# 1. Check health endpoint
curl https://staging.wrext.com/api/v1/health

# 2. Check email webhook health
curl https://staging.wrext.com/api/v1/email/webhooks/health

# 3. Send test email via API
curl -X POST https://staging.wrext.com/api/v1/email/test-send \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to": "test@example.com",
    "subject": "Staging Test",
    "html": "<p>Test from staging</p>"
  }'

# 4. Check database logs
psql $DATABASE_URL -c "SELECT id, to_email, status, provider FROM email_logs ORDER BY created_at DESC LIMIT 5;"
```

### Step 10: Deploy to Production

#### Additional Production Checks

- [ ] Staging deployment successful and tested
- [ ] Production domain verified in Resend
- [ ] Production API key generated (separate from staging)
- [ ] Production webhook endpoint configured
- [ ] Monitoring and alerting configured
- [ ] Rollback plan reviewed

#### Production Deployment

```bash
# 1. Backup database
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql

# 2. Deploy code
git checkout production
git pull origin production

# 3. Install dependencies
uv sync --frozen

# 4. Run migrations (if any)
alembic upgrade head

# 5. Restart with zero-downtime (blue-green deployment)
# ... your deployment process ...

# 6. Monitor logs
tail -f logs/app.log | grep -E "email|Email"
```

#### Post-Deployment Verification

```bash
# 1. Send real user email (e.g., password reset)
# Login to your app and trigger password reset

# 2. Check email was logged
psql $DATABASE_URL -c "
  SELECT
    id,
    to_email,
    subject,
    status,
    provider,
    created_at
  FROM email_logs
  WHERE created_at > NOW() - INTERVAL '5 minutes'
  ORDER BY created_at DESC;
"

# 3. Check webhook events received
psql $DATABASE_URL -c "
  SELECT
    event_type,
    COUNT(*)
  FROM email_events
  WHERE created_at > NOW() - INTERVAL '1 hour'
  GROUP BY event_type;
"

# 4. Monitor error rates
psql $DATABASE_URL -c "
  SELECT
    status,
    COUNT(*),
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as percentage
  FROM email_logs
  WHERE created_at > NOW() - INTERVAL '24 hours'
  GROUP BY status;
"
```

---

## Verification

### Test All Email Flows

#### 1. Email Verification Flow

```bash
# Register new user
curl -X POST https://your-domain.com/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "password": "SecurePassword123!",
    "name": "Test User"
  }'

# Check email_logs for verification email
psql $DATABASE_URL -c "
  SELECT * FROM email_logs
  WHERE to_email = 'newuser@example.com'
  AND template_type = 'email_verification'
  ORDER BY created_at DESC LIMIT 1;
"
```

#### 2. Password Reset Flow

```bash
# Request password reset
curl -X POST https://your-domain.com/api/v1/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email": "existing@example.com"}'

# Verify email sent
psql $DATABASE_URL -c "
  SELECT * FROM email_logs
  WHERE template_type = 'password_reset'
  ORDER BY created_at DESC LIMIT 1;
"
```

#### 3. Workspace Invitation Flow

```bash
# Invite user to workspace
curl -X POST https://your-domain.com/api/v1/workspaces/{workspace_id}/invitations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "invite@example.com",
    "role": "member"
  }'

# Check invitation email
psql $DATABASE_URL -c "
  SELECT * FROM email_logs
  WHERE template_type = 'workspace_invitation'
  ORDER BY created_at DESC LIMIT 1;
"
```

### Monitor Webhook Processing

```bash
# Check webhook event processing
psql $DATABASE_URL -c "
  SELECT
    el.to_email,
    el.subject,
    el.status as email_status,
    ee.event_type,
    ee.created_at as event_time
  FROM email_events ee
  JOIN email_logs el ON ee.email_log_id = el.id
  WHERE ee.created_at > NOW() - INTERVAL '1 hour'
  ORDER BY ee.created_at DESC
  LIMIT 10;
"
```

---

## Rollback Procedures

### Scenario 1: Email Sending Failures

**Symptoms:** High failure rate, emails not being delivered

**Quick Fix:**
```bash
# Switch to SMTP fallback immediately
# Update environment variable:
EMAIL_PROVIDER=smtp

# Restart application
sudo systemctl restart wrext-backend

# Verify emails sending via SMTP
tail -f logs/app.log | grep "provider=smtp"
```

### Scenario 2: Webhook Processing Errors

**Symptoms:** Webhooks failing, events not being logged

**Quick Fix:**
```bash
# Webhooks are non-critical - emails still send
# Investigate logs:
tail -f logs/app.log | grep -i "webhook"

# Check for missing webhook secret:
echo $RESEND_WEBHOOK_SECRET

# Temporarily disable webhook processing if needed:
# The webhook endpoint will return 200 but processing can be debugged
```

### Scenario 3: Database Migration Issues

**Rollback migration:**
```bash
# Rollback last 2 migrations (email_logs and email_events)
alembic downgrade -2

# Verify tables removed
psql $DATABASE_URL -c "\dt email_*"

# Re-deploy previous version
git checkout <previous-commit>
sudo systemctl restart wrext-backend
```

### Scenario 4: Complete System Rollback

**Full rollback to old SMTP system:**
```bash
# 1. Set email provider to SMTP
EMAIL_PROVIDER=smtp
EMAIL_FALLBACK_PROVIDER=null

# 2. Restart application
sudo systemctl restart wrext-backend

# 3. Monitor - old routes still work
# No code changes needed, just provider switch

# 4. (Optional) Rollback database migrations
alembic downgrade -2
```

---

## Troubleshooting

### Issue: "RESEND_API_KEY not configured"

**Cause:** Missing or invalid API key in environment

**Fix:**
```bash
# Check if API key is set
echo $RESEND_API_KEY

# Verify it starts with 're_'
# Add to .env if missing
echo 'RESEND_API_KEY=re_xxxxx' >> .env

# Restart application
```

### Issue: "Invalid webhook signature"

**Cause:** Wrong webhook secret or headers missing

**Fix:**
```bash
# 1. Check webhook secret is set
echo $RESEND_WEBHOOK_SECRET

# 2. Verify secret in Resend dashboard matches
# Go to: Webhooks → Your Endpoint → Signing Secret

# 3. Update .env with correct secret
RESEND_WEBHOOK_SECRET=whsec_xxxxx

# 4. Restart application
```

### Issue: Emails stuck in "queued" status

**Cause:** Provider not sending, or send_email not awaited

**Fix:**
```bash
# 1. Check recent logs
psql $DATABASE_URL -c "
  SELECT status, COUNT(*)
  FROM email_logs
  WHERE created_at > NOW() - INTERVAL '1 hour'
  GROUP BY status;
"

# 2. Check provider health
python3 -c "
from src.providers.email.factory import EmailProviderFactory
provider = EmailProviderFactory.get_provider()
print(f'Provider: {provider.get_provider_name()}')
"

# 3. Test provider directly
python3 -c "
import asyncio
from src.providers.email.factory import EmailProviderFactory
from src.providers.email.base import EmailMessage, EmailRecipient

async def test():
    provider = EmailProviderFactory.get_provider()
    msg = EmailMessage(
        to=[EmailRecipient(email='test@example.com')],
        subject='Test',
        html='<p>Test</p>',
        from_email='noreply@wrext.com'
    )
    result = await provider.send_email(msg)
    print(f'Success: {result.success}')
    print(f'Error: {result.error}')

asyncio.run(test())
"
```

### Issue: Domain not verified

**Cause:** DNS records not configured or not propagated

**Fix:**
```bash
# 1. Check DNS records
dig TXT wrext.com +short
dig CNAME resend._domainkey.wrext.com +short

# 2. Wait for propagation (up to 48 hours, usually 5-10 minutes)

# 3. Use Resend sandbox domain for testing
# Sandbox: onboarding@resend.dev
# Update RESEND_FROM_EMAIL temporarily for testing
```

---

## Next Steps

1. **Set up monitoring** - See [OPERATIONS_RUNBOOK.md](./OPERATIONS_RUNBOOK.md)
2. **Configure alerting** - Track email delivery rates
3. **Review analytics** - Monitor open rates, bounce rates
4. **Optimize templates** - A/B test subject lines and content

---

## Support

- **Documentation:** [API_REFERENCE.md](./API_REFERENCE.md)
- **Operations:** [OPERATIONS_RUNBOOK.md](./OPERATIONS_RUNBOOK.md)
- **Resend Docs:** https://resend.com/docs
- **Support:** Create issue in repository
