# Sentry Payment Error Monitoring

**Version:** 1.0
**Last Updated:** 2025-10-20
**Phase:** Phase 4, Task 4.2.1
**Status:** ✅ Complete

---

## Overview

This document describes the comprehensive Sentry integration for payment error tracking in WREXT. All payment operations are instrumented with rich context, custom tags, and breadcrumbs to enable effective monitoring, debugging, and alerting for revenue-critical operations.

## Features

### 🎯 Payment-Specific Error Tracking
- **Automatic error capture** for all payment operations
- **Rich context** with user ID, subscription ID, customer ID, plan ID, amounts
- **Custom tags** for easy filtering in Sentry dashboard
- **Breadcrumb tracking** for debugging complex payment flows
- **Intelligent error grouping** by provider, operation, and error type

### 📊 Enhanced Sampling Rates
- **Checkout endpoints**: 100% sampling (critical revenue operations)
- **Webhook endpoints**: 100% sampling (critical state synchronization)
- **Other payment endpoints**: 80% sampling
- **Standard endpoints**: Configurable (default 10%)

### 🔍 Error Grouping
- LemonSqueezy API errors grouped by: provider + operation + error type + status code
- Payment operation errors grouped by: provider + operation + error type
- Better issue tracking and prioritization

---

## Payment Operations Tracked

### 1. **Checkout Operations**
```python
capture_payment_exception(
    exception,
    operation="checkout",
    user_id="user_123",
    plan_id="plan_456",
    amount=29.99,
    context={
        "variant_id": "variant_789",
        "discount_code": "SAVE20"
    }
)
```

**Tags:**
- `payment_operation`: `checkout`
- `payment_provider`: `lemonsqueezy`
- `plan_id`: Plan UUID
- `user_id`: User UUID (if available)

**Context:**
- Amount, variant ID, discount code
- Success/cancel URLs
- Custom metadata

### 2. **Subscription Updates**
```python
capture_payment_exception(
    exception,
    operation="update_subscription",
    user_id="user_123",
    subscription_id="sub_456",
    plan_id="new_plan_789",
    context={
        "old_plan": "Basic",
        "new_plan": "Pro",
        "new_variant_id": "variant_xxx"
    }
)
```

**Tags:**
- `payment_operation`: `update_subscription`
- `subscription_id`: Subscription UUID
- `plan_id`: New plan UUID

**Context:**
- Old plan name, new plan name
- Variant IDs
- Billing period changes

### 3. **Subscription Cancellation**
```python
capture_payment_exception(
    exception,
    operation="cancel_subscription",
    user_id="user_123",
    subscription_id="sub_456",
    context={
        "cancel_immediately": False,
        "at_period_end": True,
        "reason": "User requested"
    }
)
```

**Tags:**
- `payment_operation`: `cancel_subscription`
- `subscription_id`: Subscription UUID

**Context:**
- Cancellation timing (immediate vs at period end)
- Cancellation reason
- User context

### 4. **Customer Portal Access**
```python
capture_payment_exception(
    exception,
    operation="customer_portal",
    user_id="user_123",
    customer_id="cus_456",
    context={
        "return_url": "https://app.wrext.com/settings"
    }
)
```

**Tags:**
- `payment_operation`: `customer_portal`
- `customer_id`: LemonSqueezy customer ID

**Context:**
- Return URL
- Portal access method

### 5. **Webhook Processing**
```python
set_payment_context(
    operation="webhook_subscription_created",
    subscription_id="sub_123",
    customer_id="cus_456",
    metadata={
        "event_id": "evt_789",
        "event_type": "subscription_created"
    }
)

add_payment_breadcrumb(
    "Processing subscription_created webhook",
    operation="webhook",
    data={
        "event_id": "evt_789",
        "subscription_id": "sub_123"
    }
)
```

**Tags:**
- `payment_operation`: `webhook_subscription_created` (or other webhook types)
- `subscription_id`: Subscription UUID
- `customer_id`: Customer ID

**Context:**
- Event type, event ID
- Webhook payload metadata
- Processing stage

### 6. **LemonSqueezy API Requests**
All API requests to LemonSqueezy are automatically tracked with breadcrumbs:

```python
add_payment_breadcrumb(
    f"LemonSqueezy API: POST /checkouts",
    operation="api_request",
    data={
        "method": "POST",
        "endpoint": "/checkouts",
        "has_data": True
    }
)
```

---

## Querying Payment Errors in Sentry

### By Operation Type
```
is:unresolved payment_operation:checkout
is:unresolved payment_operation:cancel_subscription
is:unresolved payment_operation:webhook
```

### By Error Severity
```
level:error payment_operation:*
level:warning payment_operation:webhook_email_*
```

### By Subscription/Customer
```
subscription_id:sub_123
customer_id:cus_456
plan_id:plan_789
```

### By Time Range
```
is:unresolved payment_operation:checkout firstSeen:-24h
payment_operation:* firstSeen:-7d
```

### Complex Queries
```
# Failed checkouts in last 24 hours
is:unresolved payment_operation:checkout firstSeen:-24h

# Webhook failures for specific subscription
is:unresolved payment_operation:webhook_* subscription_id:sub_123

# All payment errors affecting a specific user
user.id:user_123 payment_operation:*

# High-value failed checkouts
payment_operation:checkout amount:>100
```

---

## Alert Configuration Examples

### 1. **Critical: Checkout Failures**
- **Condition**: `payment_operation:checkout` AND `level:error`
- **Threshold**: 5 errors in 10 minutes
- **Priority**: P1 (Critical)
- **Notification**: PagerDuty + Slack #revenue-alerts
- **Action**: Immediate investigation required

### 2. **High: Subscription Update Failures**
- **Condition**: `payment_operation:update_subscription` AND `level:error`
- **Threshold**: 3 errors in 15 minutes
- **Priority**: P2 (High)
- **Notification**: Slack #eng-payments
- **Action**: Investigate within 1 hour

### 3. **Medium: Webhook Processing Errors**
- **Condition**: `payment_operation:webhook_*` AND `level:error`
- **Threshold**: 10 errors in 5 minutes
- **Priority**: P3 (Medium)
- **Notification**: Slack #eng-payments
- **Action**: Investigate within 4 hours
- **Note**: Single webhook failures are expected (retry logic handles)

### 4. **Low: Email Send Failures**
- **Condition**: `payment_operation:webhook_email_*` AND `level:warning`
- **Threshold**: 20 errors in 1 hour
- **Priority**: P4 (Low)
- **Notification**: Slack #eng-ops (summary)
- **Action**: Review in next sprint
- **Note**: Non-critical, user still gets subscription

### 5. **Watch: API Errors by Status Code**
- **Condition**: `LemonSqueezyAPIError` AND `http.status_code:4**`
- **Threshold**: 20 errors in 30 minutes
- **Priority**: P3 (Medium)
- **Notification**: Slack #eng-payments
- **Note**: May indicate API key issues or configuration problems

---

## Dashboard Metrics

### Key Metrics to Track

1. **Payment Error Rate**
   - `count_unique(issue.id)` where `payment_operation:*`
   - Grouped by `payment_operation`
   - Time range: Last 7 days

2. **Checkout Success Rate**
   - `(total_checkouts - checkout_errors) / total_checkouts * 100`
   - Track: Aim for >99.5% success rate

3. **Webhook Processing Health**
   - `count(payment_operation:webhook_*)` by `level`
   - Track failures vs. successes
   - Aim for <0.1% failure rate

4. **Revenue Impact**
   - Sum of `amount` in failed checkouts
   - Track daily/weekly trends
   - Alert on anomalies

5. **User Impact**
   - `count_unique(user.id)` affected by payment errors
   - Track unique users with failed operations

### Sample Sentry Dashboard

```markdown
┌─────────────────────────────────────────────────────────┐
│ Payment Operations Health (Last 24h)                    │
├─────────────────────────────────────────────────────────┤
│ ✅ Checkout Success Rate:        99.2% (1,234 / 1,244)│
│ ⚠️  Subscription Updates:        2 failures            │
│ ✅ Webhook Processing:           99.8% (9,998 / 10,000)│
│ 💰 Revenue at Risk:              $89.97 (3 failed)     │
│ 👥 Users Affected:               3 unique users        │
├─────────────────────────────────────────────────────────┤
│ Top Errors (Last 24h)                                   │
│ 1. LemonSqueezyAPIError (404) - 8 occurrences          │
│ 2. ValueError: Invalid variant - 3 occurrences         │
│ 3. RuntimeError: Webhook timeout - 2 occurrences       │
└─────────────────────────────────────────────────────────┘
```

---

## Breadcrumb Trail Examples

### Successful Checkout Flow
```
1. [info] Creating checkout session (operation: checkout, plan_id: plan_456)
2. [info] LemonSqueezy API: POST /checkouts
3. [info] Checkout session created (session_id: checkout_789)
4. [info] Processing subscription_created webhook (event_id: evt_123)
5. [info] Subscription activated (subscription_id: sub_456)
```

### Failed Checkout Flow
```
1. [info] Creating checkout session (operation: checkout, plan_id: plan_456)
2. [info] LemonSqueezy API: POST /checkouts
3. [error] LemonSqueezy API Error (400): Invalid variant_id
   ↳ Exception captured with full context
```

### Webhook Processing with Email Failure
```
1. [info] Processing subscription_created webhook (event_id: evt_123)
2. [info] Subscription activated (subscription_id: sub_456)
3. [info] Sending welcome email
4. [warning] Failed to send welcome email (non-critical)
   ↳ Email failure captured as warning (non-blocking)
```

---

## Testing Sentry Integration

Run the comprehensive test suite:

```bash
# Run all Sentry payment tracking tests
pytest tests/lib/test_sentry_payment_tracking.py -v

# Run specific test categories
pytest tests/lib/test_sentry_payment_tracking.py::TestCapturePaymentException -v
pytest tests/lib/test_sentry_payment_tracking.py::TestPaymentErrorGrouping -v
pytest tests/lib/test_sentry_payment_tracking.py::TestPaymentTracesSampling -v
```

**Test Coverage:**
- ✅ 21 tests
- ✅ 100% pass rate
- ✅ All payment operations covered
- ✅ Error grouping verified
- ✅ Sampling rates verified
- ✅ Integration flows tested

---

## Configuration

### Environment Variables

```bash
# Sentry DSN (required for Sentry)
SENTRY_DSN=https://xxx@yyy.ingest.sentry.io/zzz

# Sentry environment
SENTRY_ENVIRONMENT=production

# Sampling rates
SENTRY_TRACES_SAMPLE_RATE=0.1  # Default for non-payment endpoints
SENTRY_ENABLE_TRACING=true

# PII handling
SENTRY_SEND_DEFAULT_PII=false  # Do NOT send email/username to Sentry

# Debug
SENTRY_DEBUG=false
```

### Sampling Rate Override

Payment endpoints override the default sampling rate:
- **Critical** (checkout, webhook): 100%
- **High priority** (subscriptions, licenses, trials): 80%
- **Standard**: Configured via `SENTRY_TRACES_SAMPLE_RATE`

---

## Best Practices

### ✅ DO:
1. **Always use `capture_payment_exception()`** for payment-related errors
2. **Add breadcrumbs** at key decision points in payment flows
3. **Set payment context** at the start of payment operations
4. **Include amounts** when capturing checkout/payment errors
5. **Use appropriate log levels** (error for failures, warning for non-critical)
6. **Test Sentry integration** before deploying

### ❌ DON'T:
1. **Don't capture PII** (credit cards, passwords) in error context
2. **Don't use generic `capture_exception()`** for payment errors
3. **Don't set critical alerts** for expected errors (e.g., invalid discount codes)
4. **Don't ignore the `operation` parameter** - it's critical for filtering
5. **Don't forget to include context** when known (user_id, subscription_id)

---

## Troubleshooting

### No Errors Appearing in Sentry

1. Check `SENTRY_DSN` is configured correctly
2. Verify `SENTRY_ENVIRONMENT` matches your setup
3. Check network connectivity to Sentry
4. Look for Sentry initialization errors in application logs

### Too Many Errors

1. Review alert thresholds
2. Check if errors are expected (e.g., invalid user input)
3. Consider filtering out specific error types in `before_send_filter`
4. Verify rate limiting is working correctly

### Missing Context

1. Ensure `set_payment_context()` is called before operations
2. Check that all parameters are passed to `capture_payment_exception()`
3. Verify breadcrumbs are added at key points
4. Review test coverage for the specific flow

---

## Related Documentation

- [Phase 4 Implementation Plan](../lemonsqueezy-integration-plan.md#phase-4-security--compliance)
- [Sentry Configuration](../../src/api/lib/sentry_config.py)
- [Payment Provider Implementation](../../src/providers/payment/providers/lemonsqueezy.py)
- [Subscription Service](../../src/services/subscription_service.py)
- [Webhook Handlers](../../src/services/webhook_handlers/subscription_handlers.py)

---

## Support

For issues or questions about Sentry payment monitoring:
- **Slack**: #eng-payments
- **Email**: eng-team@wrext.com
- **Runbook**: See operational playbooks in `/docs/runbooks/`

---

**Document Owner**: Engineering Team
**Last Review**: 2025-10-20
**Next Review**: 2025-11-20
