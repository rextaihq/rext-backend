# Webhook Security - Production Deployment Guide

**Document Version:** 1.0
**Last Updated:** 2025-10-20
**Phase:** Phase 4, Task 4.1.3 - Webhook Signature Verification Hardening

---

## Overview

This document provides comprehensive guidance for deploying and operating webhook signature verification in production. It covers configuration, monitoring, alerting, and incident response.

### Security Features Implemented

✅ **Signature Verification** - HMAC-SHA256 validation of all webhook requests
✅ **Production Config Validation** - Application fails to start if webhook secret missing
✅ **Enhanced Security Logging** - Structured logging with IP addresses and context
✅ **Failure Tracking** - Automatic detection of attack patterns
✅ **Sentry Alerting** - Critical security alerts sent to Sentry
✅ **Comprehensive Testing** - 21 tests covering all security scenarios

---

## Table of Contents

1. [Environment Configuration](#environment-configuration)
2. [Production Deployment](#production-deployment)
3. [Security Monitoring](#security-monitoring)
4. [Alert Response](#alert-response)
5. [Troubleshooting](#troubleshooting)
6. [Security Best Practices](#security-best-practices)

---

## Environment Configuration

### Required Environment Variables

```bash
# LemonSqueezy Webhook Secret (REQUIRED in production)
LEMONSQUEEZY_WEBHOOK_SECRET=your_webhook_signing_secret_here

# Environment (determines security checks)
ENVIRONMENT=production

# Payment Provider (must be lemonsqueezy or lemonsqueezy_sandbox)
PAYMENT_PROVIDER=lemonsqueezy
```

### Getting Your Webhook Secret

1. **Login to LemonSqueezy Dashboard**
   - Navigate to: Settings → Webhooks
   - Find your webhook endpoint
   - Copy the "Signing Secret"

2. **Secure Storage**
   - ❌ Never commit secrets to git
   - ✅ Use environment variables
   - ✅ Use secret management (AWS Secrets Manager, HashiCorp Vault, etc.)
   - ✅ Rotate secrets periodically (every 90 days)

3. **Validation**
   ```bash
   # Check secret is set
   echo $LEMONSQUEEZY_WEBHOOK_SECRET

   # Verify it's not empty
   if [ -z "$LEMONSQUEEZY_WEBHOOK_SECRET" ]; then
       echo "ERROR: Webhook secret not configured!"
   fi
   ```

### Example `.env` Configuration

```bash
# ============================================
# PRODUCTION ENVIRONMENT VARIABLES
# ============================================

# Environment
ENVIRONMENT=production

# LemonSqueezy Payment Provider
PAYMENT_PROVIDER=lemonsqueezy
LEMONSQUEEZY_API_KEY=your_api_key_here
LEMONSQUEEZY_STORE_ID=your_store_id_here
LEMONSQUEEZY_WEBHOOK_SECRET=your_webhook_signing_secret_here  # CRITICAL

# Sentry Error Monitoring (for security alerts)
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1

# Logging
LOG_LEVEL=INFO  # Set to WARNING in production for less noise
```

---

## Production Deployment

### Pre-Deployment Checklist

- [ ] Webhook secret configured in environment
- [ ] Sentry DSN configured (for security alerts)
- [ ] Environment set to "production"
- [ ] Payment provider set to "lemonsqueezy"
- [ ] Webhook endpoint registered in LemonSqueezy dashboard
- [ ] SSL/TLS certificate valid
- [ ] Firewall allows LemonSqueezy IPs (if applicable)

### Deployment Steps

#### 1. Configure Environment

```bash
# Set environment variables
export ENVIRONMENT=production
export LEMONSQUEEZY_WEBHOOK_SECRET="your_secret_here"
export SENTRY_DSN="your_sentry_dsn"
```

#### 2. Start Application

```bash
# The application will validate webhook secret at startup
# If secret is missing in production, it will FAIL TO START

python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000
```

**Expected Startup Logs:**
```
INFO: Starting Wrext API server...
INFO: Environment: production
INFO: ✅ LemonSqueezy webhook secret configured
INFO: Uvicorn running on http://0.0.0.0:8000
```

**Error if Secret Missing:**
```
CRITICAL: LEMONSQUEEZY_WEBHOOK_SECRET is not configured in production.
RuntimeError: Webhook signature verification will fail.
Set LEMONSQUEEZY_WEBHOOK_SECRET environment variable before starting.
```

#### 3. Verify Webhook Endpoint

```bash
# Test webhook endpoint is accessible
curl -X POST https://your-api.com/api/v1/subscriptions/webhooks/lemonsqueezy \
  -H "Content-Type: application/json" \
  -H "X-Signature: test" \
  -d '{"test": true}'

# Expected: 401 Unauthorized (invalid signature - this is correct!)
```

#### 4. Register Webhook in LemonSqueezy

1. Go to: LemonSqueezy Dashboard → Settings → Webhooks
2. Click "Add Endpoint"
3. Enter URL: `https://your-api.com/api/v1/subscriptions/webhooks/lemonsqueezy`
4. Select events to monitor (subscription_*, order_*, license_key_*)
5. Save and copy the signing secret
6. Update `LEMONSQUEEZY_WEBHOOK_SECRET` in your environment
7. Restart application

#### 5. Test with Real Webhook

**Option A: Test Mode (Safe)**
```bash
# Trigger a test event from LemonSqueezy dashboard
# Dashboard → Webhooks → Your Endpoint → Send Test Event
```

**Option B: Create Test Subscription**
```bash
# Create a test subscription in LemonSqueezy test mode
# Webhook should fire and process successfully
```

---

## Security Monitoring

### Logging

All webhook security events are logged with structured data for easy filtering and alerting.

#### Successful Verification
```json
{
  "level": "DEBUG",
  "message": "LemonSqueezy webhook signature verified successfully",
  "extra": {
    "event": "webhook_verified",
    "signature_prefix": "a1b2c3d4"
  }
}
```

#### Failed Verification
```json
{
  "level": "WARNING",
  "message": "SECURITY: LemonSqueezy webhook signature verification FAILED",
  "extra": {
    "event": "webhook_verification_failed",
    "severity": "SECURITY",
    "expected_prefix": "a1b2c3d4",
    "received_prefix": "x9y8z7w6",
    "signature_length": 64,
    "payload_size": 1024
  }
}
```

#### Security Alert (Multiple Failures)
```json
{
  "level": "CRITICAL",
  "message": "SECURITY ALERT: Multiple webhook verification failures detected",
  "extra": {
    "event": "webhook_security_alert",
    "severity": "CRITICAL",
    "ip_address": "192.168.1.100",
    "failure_count": 5,
    "time_window_minutes": 5,
    "first_failure": "2025-10-20T10:00:00Z",
    "last_failure": "2025-10-20T10:04:30Z"
  }
}
```

### Alert Thresholds

The webhook security monitor automatically alerts when suspicious patterns are detected:

| Metric | Threshold | Action |
|--------|-----------|--------|
| Verification failures (same IP) | 5 in 5 minutes | CRITICAL alert to logs + Sentry |
| Alert cooldown | 15 minutes | Prevents alert spam |
| Time window for counting | 5 minutes | Rolling window |

### Sentry Integration

Security alerts are automatically sent to Sentry with full context:

```python
# Example Sentry event
{
  "message": "Webhook Security Alert: 5 verification failures from 192.168.1.100",
  "level": "error",
  "tags": {
    "security_event": "webhook_verification_failures",
    "ip_address": "192.168.1.100"
  },
  "contexts": {
    "webhook_security": {
      "ip_address": "192.168.1.100",
      "failure_count": 5,
      "time_window_minutes": 5,
      "threshold": 5
    }
  }
}
```

### Monitoring Dashboards

**Recommended Metrics to Track:**

1. **Webhook Success Rate**
   - Query: `event:webhook_verified` / `all webhook requests`
   - Target: >99.9%

2. **Verification Failure Rate**
   - Query: `event:webhook_verification_failed`
   - Alert if: >1% of requests

3. **Security Alerts**
   - Query: `event:webhook_security_alert`
   - Alert on: ANY occurrence

4. **Failed IPs**
   - Query: `GROUP BY ip_address WHERE event:webhook_verification_failed`
   - Track: Top 10 failing IPs

### Log Queries

**Find all verification failures:**
```bash
grep "webhook_verification_failed" /var/log/wrext/app.log | jq .
```

**Find security alerts:**
```bash
grep "webhook_security_alert" /var/log/wrext/app.log | jq .
```

**Count failures by IP:**
```bash
grep "webhook_verification_failed" /var/log/wrext/app.log | \
  jq -r '.extra.ip_address' | \
  sort | uniq -c | sort -rn
```

---

## Alert Response

### Security Alert Workflow

When you receive a webhook security alert, follow this workflow:

#### 1. Assess Severity

**Check Sentry/Logs for:**
- IP address(es) involved
- Number of failures
- Time window
- Event types attempted
- Signature prefixes

#### 2. Determine Attack Type

**Legitimate Issue:**
- Webhook secret was recently rotated
- LemonSqueezy system issue
- Your backend was restarted mid-delivery

**Actual Attack:**
- Random IP addresses
- Varying event types
- Invalid signature formats
- High volume rapid-fire requests

#### 3. Take Action

**If Legitimate:**
```bash
# Verify webhook secret matches LemonSqueezy
echo $LEMONSQUEEZY_WEBHOOK_SECRET

# Check LemonSqueezy dashboard for secret
# Update if needed and restart application

# Clear failures for legitimate IP
# (This requires adding an admin endpoint or manual DB update)
```

**If Attack:**
```bash
# 1. Block IP at firewall level
sudo ufw deny from 192.168.1.100

# 2. Report to security team
# Document: IP, timestamps, attack pattern

# 3. Review logs for other suspicious activity
grep "192.168.1.100" /var/log/wrext/app.log

# 4. Consider rate limiting at CDN/WAF level
```

#### 4. Post-Incident

- Document incident in security log
- Update firewall rules if needed
- Review attack patterns for prevention
- Consider adjusting alert thresholds

---

## Troubleshooting

### Issue: Application Won't Start (Production)

**Error:**
```
RuntimeError: LEMONSQUEEZY_WEBHOOK_SECRET is not configured in production
```

**Solution:**
```bash
# 1. Verify environment variable is set
echo $LEMONSQUEEZY_WEBHOOK_SECRET

# 2. If empty, set it
export LEMONSQUEEZY_WEBHOOK_SECRET="your_secret_here"

# 3. Restart application
systemctl restart wrext-backend
```

### Issue: All Webhooks Failing Verification

**Symptoms:**
- HTTP 401 responses for all webhooks
- Log: "webhook signature verification failed"

**Diagnosis:**
```bash
# 1. Check webhook secret is correct
echo $LEMONSQUEEZY_WEBHOOK_SECRET

# 2. Compare with LemonSqueezy dashboard
# Dashboard → Webhooks → Your Endpoint → Signing Secret

# 3. Check environment
echo $ENVIRONMENT  # Should be "production"
echo $PAYMENT_PROVIDER  # Should be "lemonsqueezy"
```

**Solution:**
```bash
# Update webhook secret
export LEMONSQUEEZY_WEBHOOK_SECRET="correct_secret_from_dashboard"

# Restart application
systemctl restart wrext-backend

# Test with LemonSqueezy test event
```

### Issue: False Positive Security Alerts

**Symptoms:**
- Alerts for legitimate IPs
- Alerts during deployment/restart

**Solution:**
```bash
# Adjust alert thresholds in code if needed
# File: src/services/webhook_security_monitor.py

# Increase threshold or time window:
FAILURE_THRESHOLD = 10  # Increase from 5
TIME_WINDOW_MINUTES = 10  # Increase from 5

# Redeploy application
```

### Issue: Missing Sentry Alerts

**Diagnosis:**
```bash
# Check Sentry is configured
echo $SENTRY_DSN

# Check Sentry integration is working
python -c "
import sentry_sdk
sentry_sdk.init(dsn='your_dsn_here')
sentry_sdk.capture_message('Test webhook security alert')
"
```

---

## Security Best Practices

### 1. Webhook Secret Management

✅ **DO:**
- Rotate secrets every 90 days
- Use secret management systems (AWS Secrets Manager, etc.)
- Never log the full webhook secret
- Restrict access to secrets (principle of least privilege)

❌ **DON'T:**
- Commit secrets to git
- Share secrets via email/Slack
- Reuse secrets across environments
- Log full webhook signatures

### 2. Network Security

✅ **Implement:**
- HTTPS only (TLS 1.2+)
- Restrict webhook endpoint to LemonSqueezy IPs (if possible)
- Use CDN/WAF for DDoS protection
- Rate limiting at network level

### 3. Monitoring & Alerting

✅ **Monitor:**
- Webhook success rate (>99.9%)
- Verification failure rate (<0.1%)
- Security alert frequency (0 expected)
- Response time (p95 <500ms)

✅ **Alert on:**
- Any security alert (critical)
- Success rate drop (<95%)
- Unusual failure spike (>10 in 1 minute)

### 4. Incident Response

✅ **Prepare:**
- Documented runbooks (this guide)
- On-call rotation for security alerts
- Firewall block automation
- Regular security drills

### 5. Compliance

✅ **Maintain:**
- Audit logs (retain 90+ days)
- Security incident documentation
- Webhook secret rotation schedule
- Regular security reviews

---

## Related Documentation

- [Webhook Security Monitor Implementation](../../src/services/webhook_security_monitor.py)
- [LemonSqueezy Webhook Handler](../../src/api/routes/subscriptions/webhook_routes.py)
- [Signature Verification Utility](../../src/utils/lemonsqueezy_webhook.py)
- [Test Suite](../../tests/services/test_webhook_security_monitor.py)
- [CSRF Protection Decision](./CSRF_PROTECTION_DECISION.md)

---

## Support & Contact

**Security Issues:**
- Email: security@wrext.com
- Emergency: On-call engineer via PagerDuty

**General Support:**
- Documentation: https://docs.wrext.com
- GitHub Issues: https://github.com/wrext/wrext/issues

---

**Document History:**

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2025-10-20 | Initial production deployment guide | Engineering Team |

---

**Status:** ✅ Production Ready
**Last Security Review:** 2025-10-20
**Next Review:** 2026-01-20
