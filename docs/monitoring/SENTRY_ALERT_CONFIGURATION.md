# Sentry Alert Configuration for Payment Failures

**Phase 4, Task 4.2.3** - Critical payment failure alerting system

## Overview

This document provides step-by-step instructions for configuring Sentry alerts for critical payment failures in the WREXT application. These alerts ensure immediate notification of revenue-impacting issues.

## Alert System Architecture

### Components

1. **Alert Helper Functions** (`src/api/lib/sentry_config.py`)
   - `trigger_payment_alert()` - Generic alert trigger
   - `alert_webhook_signature_failure()` - Webhook security alerts
   - `alert_api_error()` - LemonSqueezy API error alerts
   - `alert_subscription_creation_failure()` - Subscription creation alerts
   - `alert_checkout_failure()` - Checkout failure alerts
   - `alert_cancellation_error()` - Cancellation error alerts

2. **Integration Points**
   - LemonSqueezy Provider (`src/providers/payment/providers/lemonsqueezy.py`)
   - Webhook Handlers (`src/services/webhook_handlers/subscription_handlers.py`)
   - Subscription Service (`src/services/subscription_service.py`)

3. **Alert Tags**
   - `alert` = "true" - Identifies alert events
   - `alert_type` - Type of failure
   - `alert_severity` - critical, high, medium, low
   - `payment_operation` - Operation that failed
   - `payment_provider` = "lemonsqueezy"

## Alert Rules Configuration

### 1. Webhook Signature Verification Failures

**Severity:** HIGH
**Alert Type:** `webhook_signature_failure`
**Revenue Impact:** Potential
**Customer Impact:** Medium

**Trigger Condition:**
```
alert_type:webhook_signature_failure AND alert:true
```

**Threshold:**
- 3+ failures in 5 minutes

**Notification Routing:**
- Email: payments-team@example.com
- Slack: #payments-alerts
- PagerDuty: No

**Sentry Dashboard Configuration:**
1. Navigate to Alerts > Create Alert Rule
2. Select "Issues" alert type
3. Set conditions:
   - Tags: `alert_type` equals `webhook_signature_failure`
   - Tags: `alert` equals `true`
4. Set "When" condition: 3 events in 5 minutes
5. Add actions:
   - Send email to payments team
   - Send Slack notification to #payments-alerts

---

### 2. LemonSqueezy API Errors (5xx)

**Severity:** CRITICAL
**Alert Type:** `api_error`
**Revenue Impact:** Direct
**Customer Impact:** High

**Trigger Condition:**
```
alert_type:api_error AND alert_severity:critical AND alert:true
```

**Threshold:**
- 5+ errors in 10 minutes

**Notification Routing:**
- Email: payments-team@example.com
- Slack: #payments-alerts
- PagerDuty: Yes (On-call engineer)

**Sentry Dashboard Configuration:**
1. Navigate to Alerts > Create Alert Rule
2. Select "Issues" alert type
3. Set conditions:
   - Tags: `alert_type` equals `api_error`
   - Tags: `alert_severity` equals `critical`
   - Tags: `alert` equals `true`
4. Set "When" condition: 5 events in 10 minutes
5. Add actions:
   - Send email to payments team
   - Send Slack notification to #payments-alerts
   - Trigger PagerDuty incident (critical severity)

---

### 3. Failed Subscription Creations

**Severity:** CRITICAL
**Alert Type:** `subscription_creation_failure`
**Revenue Impact:** Direct
**Customer Impact:** High

**Trigger Condition:**
```
alert_type:subscription_creation_failure AND alert:true
```

**Threshold:**
- 2+ failures in 15 minutes

**Notification Routing:**
- Email: payments-team@example.com
- Slack: #payments-critical
- PagerDuty: Yes (On-call engineer)

**Sentry Dashboard Configuration:**
1. Navigate to Alerts > Create Alert Rule
2. Select "Issues" alert type
3. Set conditions:
   - Tags: `alert_type` equals `subscription_creation_failure`
   - Tags: `alert` equals `true`
4. Set "When" condition: 2 events in 15 minutes
5. Add actions:
   - Send email to payments team
   - Send Slack notification to #payments-critical
   - Trigger PagerDuty incident (critical severity)

---

### 4. Checkout Session Creation Failures

**Severity:** HIGH
**Alert Type:** `checkout_failure`
**Revenue Impact:** Direct
**Customer Impact:** High

**Trigger Condition:**
```
alert_type:checkout_failure AND alert:true
```

**Threshold:**
- 3+ failures in 10 minutes

**Notification Routing:**
- Email: payments-team@example.com
- Slack: #payments-alerts

**Sentry Dashboard Configuration:**
1. Navigate to Alerts > Create Alert Rule
2. Select "Issues" alert type
3. Set conditions:
   - Tags: `alert_type` equals `checkout_failure`
   - Tags: `alert` equals `true`
4. Set "When" condition: 3 events in 10 minutes
5. Add actions:
   - Send email to payments team
   - Send Slack notification to #payments-alerts

---

### 5. Subscription Cancellation Errors

**Severity:** MEDIUM
**Alert Type:** `cancellation_error`
**Revenue Impact:** Indirect
**Customer Impact:** Medium

**Trigger Condition:**
```
alert_type:cancellation_error AND alert:true
```

**Threshold:**
- 5+ errors in 30 minutes

**Notification Routing:**
- Email: payments-team@example.com

**Sentry Dashboard Configuration:**
1. Navigate to Alerts > Create Alert Rule
2. Select "Issues" alert type
3. Set conditions:
   - Tags: `alert_type` equals `cancellation_error`
   - Tags: `alert` equals `true`
4. Set "When" condition: 5 events in 30 minutes
5. Add actions:
   - Send email to payments team

---

### 6. High Error Rate (Metric Alert)

**Severity:** HIGH
**Revenue Impact:** Direct
**Customer Impact:** High

**Trigger Condition:**
```
Payment operation error rate > 5%
```

**Threshold:**
- Error rate exceeds 5% for 15 minutes

**Notification Routing:**
- Email: payments-team@example.com
- Slack: #payments-alerts

**Sentry Dashboard Configuration:**
1. Navigate to Alerts > Create Alert Rule
2. Select "Metric" alert type
3. Set metric: Error rate
4. Set filter: `payment_operation:*`
5. Set threshold: > 5% for 15 minutes
6. Add actions:
   - Send email to payments team
   - Send Slack notification to #payments-alerts

---

## Alert Tags Reference

All payment alerts include these tags for filtering:

| Tag | Values | Purpose |
|-----|--------|---------|
| `alert` | `true` | Identifies alert events |
| `alert_type` | See alert types below | Categorize failure type |
| `alert_severity` | `critical`, `high`, `medium`, `low` | Priority level |
| `payment_operation` | `checkout`, `webhook_*`, `api_request`, etc. | Operation that failed |
| `payment_provider` | `lemonsqueezy` | Payment provider |
| `user_id` | UUID | Affected user (when available) |
| `subscription_id` | Subscription ID | Affected subscription (when available) |

**Alert Types:**
- `webhook_signature_failure`
- `api_error`
- `subscription_creation_failure`
- `checkout_failure`
- `cancellation_error`

---

## Notification Channel Setup

### Email Notifications

1. Navigate to Settings > Integrations > Email
2. Add email addresses:
   - `payments-team@example.com` - Primary notification list
   - Add individual email addresses as needed

### Slack Integration

1. Navigate to Settings > Integrations > Slack
2. Click "Add Workspace"
3. Authorize WREXT Sentry app
4. Configure channels:
   - `#payments-alerts` - High/Medium severity alerts
   - `#payments-critical` - Critical alerts only

### PagerDuty Integration

1. Navigate to Settings > Integrations > PagerDuty
2. Click "Add Integration"
3. Enter PagerDuty API key
4. Configure services:
   - Use "Payments On-Call" service for critical alerts
5. Set escalation policy for immediate escalation

---

## Alert Context

Each alert includes rich context for debugging:

```json
{
  "alert_type": "subscription_creation_failure",
  "severity": "critical",
  "timestamp": "2025-10-20T15:30:45Z",
  "variant_id": "123456",
  "error_message": "User not found for subscription sub_xxx",
  "event_id": "evt_xxx",
  "category": "subscription_failure",
  "revenue_impact": "direct",
  "customer_impact": "high"
}
```

---

## Testing Alerts

### Manual Testing

1. **Trigger Test Alert:**
   ```python
   from src.api.lib.sentry_config import trigger_payment_alert

   trigger_payment_alert(
       alert_type="api_error",
       message="TEST: LemonSqueezy API error",
       severity="high",
       context={"test": True, "method": "POST", "endpoint": "/test"}
   )
   ```

2. **Verify in Sentry:**
   - Check Issues tab for new event
   - Verify tags are set correctly
   - Confirm alert context is present

3. **Check Notifications:**
   - Verify email received
   - Check Slack channel for message
   - Confirm PagerDuty incident (for critical tests)

### Automated Testing

See `tests/lib/test_payment_alerts.py` for comprehensive test suite.

---

## Alert Maintenance

### Tuning Thresholds

Monitor alert frequency and adjust thresholds to prevent alert fatigue:

1. **Too Many Alerts:**
   - Increase threshold count
   - Increase time window
   - Add conditions to filter noise

2. **Missing Critical Issues:**
   - Decrease threshold count
   - Decrease time window
   - Broaden filter conditions

### Alert Metrics

Track these metrics monthly:

- **Alert Volume:** Total alerts triggered
- **False Positive Rate:** Alerts without actual issues
- **Mean Time to Response (MTTR):** Time from alert to acknowledgment
- **Resolution Time:** Time from alert to issue resolution

### Alert Review Schedule

- **Weekly:** Review alert volume and adjust noisy rules
- **Monthly:** Analyze alert effectiveness and false positive rate
- **Quarterly:** Review and update runbooks based on common issues

---

## Troubleshooting

### Alerts Not Triggering

1. Check Sentry is enabled: `SENTRY_DSN` configured
2. Verify alert rule is active in Sentry dashboard
3. Check tag filters match alert tags
4. Review threshold settings

### Too Many False Positives

1. Review alert context to understand root cause
2. Add additional filter conditions
3. Increase threshold count
4. Consider moving to lower severity

### Missing Notifications

1. Verify notification channels are configured
2. Check email/Slack/PagerDuty integration status
3. Review notification routing in alert rules
4. Check spam folders for email notifications

---

## Related Documentation

- **Alert Runbooks:** `docs/monitoring/PAYMENT_ALERT_RUNBOOKS.md`
- **Alert Metrics:** `docs/monitoring/ALERT_METRICS.md`
- **Sentry Monitoring:** `docs/monitoring/SENTRY_PAYMENT_MONITORING.md`
- **Payment Logging:** `docs/logging/PAYMENT_LOGGING.md`

---

## Support

For alert configuration issues:
1. Check Sentry dashboard for error details
2. Review alert tags and context
3. Consult alert runbooks for response procedures
4. Escalate to engineering team if needed

---

## Changelog

**2025-10-20** - Phase 4, Task 4.2.3
- Initial alert system implementation
- 5 alert types configured
- Integration with LemonSqueezy provider and webhook handlers
- Alert helper functions in sentry_config.py
- Notification routing setup
