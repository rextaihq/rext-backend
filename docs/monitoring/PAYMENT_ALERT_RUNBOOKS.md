# Payment Alert Response Runbooks

**Phase 4, Task 4.2.3** - Response procedures for critical payment alerts

## Overview

This document provides step-by-step response procedures for each payment alert type. Follow these runbooks when alerts are triggered to quickly diagnose and resolve issues.

---

## General Response Procedure

For ALL payment alerts:

1. **Acknowledge Alert** (within 5 minutes)
   - Mark alert as acknowledged in Sentry/PagerDuty
   - Post in Slack that you're investigating

2. **Assess Impact**
   - Check alert context for affected users/subscriptions
   - Determine revenue impact
   - Identify if issue is ongoing or resolved

3. **Investigate**
   - Follow alert-specific runbook below
   - Check Sentry for full error details and breadcrumbs
   - Review logs using correlation IDs

4. **Resolve or Escalate**
   - Apply fix if root cause identified
   - Escalate to engineering if complex issue
   - Document resolution in alert comments

5. **Post-Incident**
   - Update affected users if needed
   - Document lessons learned
   - Update runbook if new issue pattern identified

---

## Runbook 1: Webhook Signature Verification Failures

**Alert Type:** `webhook_signature_failure`
**Severity:** HIGH
**Typical Causes:** Misconfigured webhook secret, replay attacks, LemonSqueezy configuration mismatch

### Symptoms

- Webhooks rejected with signature verification failures
- Subscriptions not activating after successful checkout
- Payment events not processing

### Investigation Steps

1. **Check Alert Context:**
   ```
   - payload_length: Size of rejected payload
   - endpoint: /webhooks/lemonsqueezy
   - category: security
   ```

2. **Verify Webhook Secret:**
   ```bash
   # Check environment variable
   echo $LEMONSQUEEZY_WEBHOOK_SECRET
   ```

3. **Check LemonSqueezy Dashboard:**
   - Navigate to Settings > Webhooks
   - Verify webhook secret matches environment variable
   - Check webhook URL is correct

4. **Review Recent Webhooks:**
   - Check LemonSqueezy dashboard for webhook delivery history
   - Look for 401/403 responses

5. **Check Logs:**
   ```
   operation:webhook_verification level:warning
   ```

### Common Causes & Solutions

| Cause | Solution | Prevention |
|-------|----------|------------|
| Wrong webhook secret | Update `LEMONSQUEEZY_WEBHOOK_SECRET` to match dashboard | Document secret rotation procedure |
| Secret rotation not completed | Rollback or complete rotation | Use blue-green deployment for secret changes |
| Replay attack | Block suspicious IPs | Implement request rate limiting |
| LemonSqueezy configuration mismatch | Verify webhook URL and secret in dashboard | Add webhook validation to deployment checklist |

### Resolution Steps

**If Secret Mismatch:**
1. Get correct secret from LemonSqueezy dashboard
2. Update environment variable
3. Restart application
4. Test with webhook resend from dashboard

**If Replay Attack:**
1. Block suspicious IPs in firewall
2. Review webhook event IDs for duplicates
3. Consider implementing event ID deduplication

### Escalation

Escalate to security team if:
- Multiple IPs attempting webhook injection
- Pattern suggests coordinated attack
- Unable to verify legitimacy of requests

---

## Runbook 2: LemonSqueezy API Errors

**Alert Type:** `api_error`
**Severity:** CRITICAL
**Typical Causes:** LemonSqueezy service outage, rate limiting, API key issues, network problems

### Symptoms

- Checkouts failing to create
- Subscriptions failing to cancel/update
- High error rates in payment operations

### Investigation Steps

1. **Check Alert Context:**
   ```
   - method: HTTP method (GET, POST, etc.)
   - endpoint: API endpoint that failed
   - status_code: HTTP status (500, 502, 429, etc.)
   - error_message: Error from LemonSqueezy
   ```

2. **Check LemonSqueezy Status:**
   - Visit https://status.lemonsqueezy.com
   - Check for ongoing incidents

3. **Check Rate Limits:**
   ```
   # Query logs for rate limit errors
   alert_type:api_error status_code:429
   ```

4. **Verify API Key:**
   ```bash
   # Test API key
   curl -H "Authorization: Bearer $LEMONSQUEEZY_API_KEY" \
        https://api.lemonsqueezy.com/v1/stores
   ```

5. **Check Network Connectivity:**
   ```bash
   # Test DNS and connectivity
   ping api.lemonsqueezy.com
   curl -I https://api.lemonsqueezy.com/v1
   ```

### Common Causes & Solutions

| Status Code | Cause | Solution |
|-------------|-------|----------|
| 500, 502, 503 | LemonSqueezy service issue | Wait for recovery, monitor status page |
| 429 | Rate limiting | Implement backoff, reduce request rate |
| 401, 403 | API key invalid/expired | Rotate API key |
| 404 | Resource not found | Verify resource IDs, check configuration |
| Network timeout | DNS/connectivity issue | Check network, verify DNS |

### Resolution Steps

**If Service Outage (5xx):**
1. Confirm outage on LemonSqueezy status page
2. Communicate to users via status page/social media
3. Monitor for resolution
4. Test operations once resolved

**If Rate Limiting (429):**
1. Check request volume in logs
2. Implement exponential backoff
3. Reduce concurrent requests
4. Contact LemonSqueezy to increase limits if needed

**If API Key Issue (401/403):**
1. Generate new API key in LemonSqueezy dashboard
2. Update `LEMONSQUEEZY_API_KEY` environment variable
3. Restart application
4. Test checkout flow

### Escalation

Escalate to engineering lead if:
- Outage persists > 30 minutes
- Multiple API errors across different operations
- Unable to identify root cause
- Rate limiting cannot be resolved with backoff

---

## Runbook 3: Failed Subscription Creations

**Alert Type:** `subscription_creation_failure`
**Severity:** CRITICAL
**Typical Causes:** User not found, plan configuration mismatch, database errors, webhook processing failures

### Symptoms

- Users paid but subscription not activated
- Webhook processing errors
- User complaints about access after payment

### Investigation Steps

1. **Check Alert Context:**
   ```
   - user_id: Affected user
   - variant_id: LemonSqueezy variant ID
   - error_message: Failure reason
   - event_id: Webhook event ID
   ```

2. **Verify User Exists:**
   ```sql
   SELECT * FROM users WHERE id = '<user_id>';
   ```

3. **Check Plan Configuration:**
   ```sql
   SELECT * FROM subscription_plans
   WHERE lemonsqueezy_variant_id_monthly = '<variant_id>'
      OR lemonsqueezy_variant_id_yearly = '<variant_id>';
   ```

4. **Review Webhook Event:**
   ```sql
   SELECT * FROM webhook_events WHERE event_id = '<event_id>';
   ```

5. **Check LemonSqueezy Order:**
   - Navigate to LemonSqueezy dashboard
   - Find order by event ID or customer email
   - Verify payment was successful

### Common Causes & Solutions

| Cause | Solution | Prevention |
|-------|----------|------------|
| User not found | Manual subscription creation | Improve user identification in webhooks |
| Plan mismatch | Update plan variant IDs | Add variant ID validation in deployment |
| Database constraint violation | Fix data integrity issue | Add database migration tests |
| Webhook processing timeout | Retry webhook processing | Optimize webhook handler performance |

### Resolution Steps

**If User Not Found:**
1. Locate user by email in LemonSqueezy order
2. Verify user exists in database
3. If user exists, manually create subscription:
   ```python
   # Admin script to create subscription
   python scripts/manual_subscription_create.py \
       --user-id=<user_id> \
       --variant-id=<variant_id> \
       --order-id=<order_id>
   ```
4. Send confirmation email to user

**If Plan Mismatch:**
1. Identify correct plan for variant ID
2. Update database plan configuration
3. Trigger webhook replay for failed event
4. Verify subscription created successfully

**If Database Error:**
1. Check database logs for constraint violations
2. Fix data integrity issue
3. Retry webhook processing
4. Monitor for additional failures

### User Communication Template

```
Subject: Your WREXT Subscription Activation

Hi [User Name],

We noticed an issue activating your subscription after payment.
Our team has resolved the issue and your subscription is now active.

You now have full access to [Plan Name] features.

We apologize for the inconvenience. If you have any questions,
please reply to this email.

Best regards,
WREXT Team
```

### Escalation

Escalate immediately if:
- Multiple subscription creation failures (> 5 in 1 hour)
- Unable to manually create subscription
- Data corruption suspected
- Payment taken but cannot fulfill service

---

## Runbook 4: Checkout Session Creation Failures

**Alert Type:** `checkout_failure`
**Severity:** HIGH
**Typical Causes:** API errors, configuration issues, invalid plan/variant IDs

### Investigation Steps

1. **Check Alert Context:**
   ```
   - user_id: User attempting checkout
   - variant_id: Plan variant ID
   - error_message: Failure reason
   - correlation_id: Tracking ID
   ```

2. **Verify Plan Configuration:**
   ```sql
   SELECT * FROM subscription_plans WHERE id = '<plan_id>';
   ```

3. **Check LemonSqueezy Product:**
   - Navigate to LemonSqueezy dashboard > Products
   - Verify variant ID exists and is active

4. **Test Checkout Creation:**
   ```bash
   # Test API call
   curl -X POST https://api.lemonsqueezy.com/v1/checkouts \
        -H "Authorization: Bearer $LEMONSQUEEZY_API_KEY" \
        -d '{"data": {"type": "checkouts", ...}}'
   ```

5. **Review Logs:**
   ```
   correlation_id:<correlation_id> operation:checkout
   ```

### Resolution Steps

**If Invalid Variant ID:**
1. Update subscription plan with correct variant ID
2. Deploy configuration update
3. Test checkout flow
4. Notify affected users of resolution

**If API Error:**
1. Follow Runbook 2 (API Errors)
2. Test checkout after resolution

### Escalation

Escalate if:
- Checkout failures > 10% of attempts
- Configuration appears correct but still failing
- Issue affects multiple plans

---

## Runbook 5: Subscription Cancellation Errors

**Alert Type:** `cancellation_error`
**Severity:** MEDIUM
**Typical Causes:** API errors, subscription not found, concurrent modification

### Investigation Steps

1. **Check Alert Context:**
   ```
   - subscription_id: Subscription being cancelled
   - user_id: User requesting cancellation
   - error_message: Failure reason
   ```

2. **Verify Subscription:**
   ```sql
   SELECT * FROM user_subscriptions
   WHERE id = '<subscription_id>';
   ```

3. **Check LemonSqueezy Subscription:**
   - Navigate to LemonSqueezy dashboard
   - Find subscription by ID
   - Check current status

4. **Review Recent Changes:**
   ```
   subscription_id:<subscription_id> operation:*
   ```

### Resolution Steps

**If Subscription Not Found:**
1. Check if subscription already cancelled
2. Update local database to match LemonSqueezy state
3. Inform user of current status

**If API Error:**
1. Retry cancellation
2. If retry fails, follow Runbook 2

**If Already Cancelled:**
1. Update database status
2. No user communication needed

### User Communication

Usually no communication needed unless user contacts support.

If user reports issue:
```
We've confirmed your subscription cancellation. Your access
will continue until [end date] and you will not be charged again.
```

### Escalation

Escalate if:
- User charged after cancellation request
- Multiple cancellation failures
- Data synchronization issues between LemonSqueezy and database

---

## Post-Incident Review Template

After resolving any CRITICAL alert:

### Incident Summary
- Alert Type:
- Time Detected:
- Time Resolved:
- Duration:
- Users Affected:

### Root Cause
- What happened:
- Why it happened:
- How it was detected:

### Resolution
- Steps taken:
- Workarounds applied:
- Permanent fix deployed:

### Prevention
- How to prevent recurrence:
- Monitoring improvements:
- Documentation updates:
- Runbook updates:

### Action Items
- [ ] Update monitoring thresholds
- [ ] Improve error messages
- [ ] Add automated tests
- [ ] Update documentation

---

## Emergency Contacts

**Payment Issues (Critical):**
- On-Call Engineer: PagerDuty escalation
- Engineering Lead: [Contact info]
- Product Manager: [Contact info]

**LemonSqueezy Support:**
- Dashboard: https://app.lemonsqueezy.com
- Support: support@lemonsqueezy.com
- Status Page: https://status.lemonsqueezy.com

**Internal Resources:**
- Sentry: [Sentry URL]
- Logging: [Logging system URL]
- Database: [Database admin URL]

---

## Related Documentation

- **Alert Configuration:** `docs/monitoring/SENTRY_ALERT_CONFIGURATION.md`
- **Alert Metrics:** `docs/monitoring/ALERT_METRICS.md`
- **Payment Logging:** `docs/logging/PAYMENT_LOGGING.md`
- **Sentry Monitoring:** `docs/monitoring/SENTRY_PAYMENT_MONITORING.md`

---

## Changelog

**2025-10-20** - Phase 4, Task 4.2.3
- Initial runbooks for 5 alert types
- Response procedures and escalation paths
- User communication templates
- Post-incident review template
