# Audit Logging System

## Overview

The WREXT backend implements comprehensive audit logging for all payment, subscription, webhook, and administrative operations. This provides a complete audit trail for compliance, debugging, and security monitoring.

## Architecture

### Components

1. **AuditLogger Service** (`src/services/audit_logger.py`)
   - Centralized audit logging service
   - Structured JSON logging format
   - Event type categorization
   - Consistent timestamp and metadata tracking

2. **AuditEventType Enum**
   - Predefined event types for categorization
   - Easy filtering and querying
   - Type-safe event logging

3. **Integration Points**
   - Subscription service
   - Payment handlers
   - Webhook handlers
   - Admin routes
   - License management

## Event Types

### Subscription Events
- `subscription.created` - New subscription created
- `subscription.updated` - Subscription modified
- `subscription.cancelled` - Subscription cancelled
- `subscription.resumed` - Paused subscription resumed
- `subscription.expired` - Subscription expired
- `subscription.paused` - Subscription paused
- `subscription.upgraded` - Plan upgraded
- `subscription.downgraded` - Plan downgraded

### Payment Events
- `payment.succeeded` - Successful payment processed
- `payment.failed` - Payment failed
- `payment.recovered` - Failed payment recovered
- `payment.refunded` - Payment refunded

### Checkout Events
- `checkout.created` - Checkout session created
- `checkout.completed` - Checkout completed
- `checkout.abandoned` - Checkout abandoned

### Webhook Events
- `webhook.received` - Webhook event received
- `webhook.processed` - Webhook processed successfully
- `webhook.failed` - Webhook processing failed
- `webhook.signature_invalid` - Invalid webhook signature

### Admin Actions
- `admin.refund_created` - Admin created refund
- `admin.subscription_extended` - Admin extended subscription
- `admin.subscription_cancelled` - Admin cancelled subscription
- `admin.user_migrated` - Admin migrated user
- `admin.plan_changed` - Admin changed user plan

### License Events
- `license.created` - License created
- `license.activated` - License activated on device
- `license.deactivated` - License deactivated
- `license.revoked` - License revoked

### Trial Events
- `trial.started` - Trial subscription started
- `trial.converted` - Trial converted to paid
- `trial.expired` - Trial expired

### User Actions
- `user.portal_accessed` - User accessed customer portal
- `user.invoice_downloaded` - User downloaded invoice
- `user.plan_viewed` - User viewed plan details

## Log Format

All audit logs follow a consistent structured JSON format:

```json
{
  "event_type": "subscription.created",
  "timestamp": "2025-10-20T15:30:45.123456",
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "admin_id": null,
  "resource_type": "subscription",
  "resource_id": "789e4567-e89b-12d3-a456-426614174999",
  "changes": {},
  "metadata": {
    "plan_id": "456e4567-e89b-12d3-a456-426614174555",
    "plan_name": "Pro",
    "billing_period": "monthly",
    "is_trial": false,
    "amount": 1999
  },
  "ip_address": "203.0.113.45",
  "user_agent": "Mozilla/5.0..."
}
```

### Standard Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event_type` | string | Yes | Event type from AuditEventType enum |
| `timestamp` | ISO 8601 | Yes | UTC timestamp of event |
| `user_id` | UUID | Conditional | User affected by the action |
| `admin_id` | UUID | No | Admin who performed the action |
| `resource_type` | string | No | Type of resource (subscription, payment, etc.) |
| `resource_id` | UUID | No | ID of the affected resource |
| `changes` | object | No | Before/after values for updates |
| `metadata` | object | No | Event-specific additional data |
| `ip_address` | string | No | IP address of actor |
| `user_agent` | string | No | User agent of actor |

### Metadata Structure

Metadata fields vary by event type but commonly include:

**Subscription Events:**
- `plan_id`, `plan_name`
- `billing_period`
- `is_trial`, `trial_days`
- `proration_amount`

**Payment Events:**
- `amount`, `currency`
- `card_brand`, `card_last_four`
- `lemonsqueezy_payment_id`
- `failure_reason`

**Webhook Events:**
- `event_id`, `event_name`
- `signature_valid`
- `processing_time_ms`
- `retry_count`

**Admin Actions:**
- `reason` (for cancellations, refunds)
- `cancel_immediately`
- `original_amount` (for partial refunds)

## Usage

### Basic Usage

```python
from src.services.audit_logger import audit_logger

# Log subscription creation
audit_logger.log_subscription_created(
    user_id=user.id,
    subscription_id=subscription.id,
    plan_id=plan.id,
    plan_name=plan.name,
    billing_period="monthly",
    is_trial=False,
    amount=1999,
)

# Log payment success
audit_logger.log_payment_succeeded(
    user_id=user.id,
    subscription_id=subscription.id,
    amount=1999,
    currency="USD",
    lemonsqueezy_payment_id="pay_123",
    card_brand="Visa",
    card_last_four="4242",
)

# Log admin action
audit_logger.log_admin_refund_created(
    admin_id=admin.id,
    user_id=user.id,
    refund_id=refund.id,
    subscription_id=subscription.id,
    amount=1999,
    reason="Duplicate charge",
    ip_address=request.client.host,
)
```

### With Change Tracking

```python
# Track subscription updates
old_status = subscription.status
subscription.status = SubscriptionStatus.ACTIVE

audit_logger.log_subscription_updated(
    user_id=user.id,
    subscription_id=subscription.id,
    changes={
        "status": {
            "from": old_status.value,
            "to": subscription.status.value
        }
    },
)
```

### In Webhook Handlers

```python
async def handle_subscription_created(webhook_data, webhook_event, db):
    # ... process webhook ...

    # Log webhook processing
    audit_logger.log_webhook_processed(
        event_id=webhook_data["event_id"],
        event_name=webhook_data["event_name"],
        processing_time_ms=processing_time,
        user_id=subscription.user_id,
    )
```

## Log Storage and Retention

### Current Setup

- **Storage**: All audit logs are written to application logs via Python's logging module
- **Logger Name**: `audit` (separate from general application logs)
- **Level**: INFO
- **Format**: JSON structured logging via `extra` parameter

### Production Recommendations

1. **Centralized Logging**
   - Forward audit logs to centralized logging system (e.g., ELK, Splunk, Datadog)
   - Use log shipping agents (Filebeat, Fluentd, etc.)
   - Configure separate indices/streams for audit logs

2. **Log Retention**
   - Retain audit logs for minimum 1 year (compliance requirement)
   - Consider archival storage for logs > 1 year
   - Implement automated retention policies

3. **Log Protection**
   - Restrict write access to audit logs
   - Implement log integrity verification
   - Regular backups of audit logs
   - Monitor for log tampering

## Querying Audit Logs

### Example Queries

**Filter by Event Type:**
```bash
# Using grep
grep '"event_type":"subscription.created"' audit.log

# Using jq
cat audit.log | jq 'select(.audit.event_type == "subscription.created")'
```

**Filter by User:**
```bash
cat audit.log | jq 'select(.audit.user_id == "123e4567-e89b-12d3-a456-426614174000")'
```

**Filter by Date Range:**
```bash
cat audit.log | jq 'select(.audit.timestamp >= "2025-10-01" and .audit.timestamp < "2025-11-01")'
```

**Admin Actions:**
```bash
cat audit.log | jq 'select(.audit.admin_id != null)'
```

**Failed Events:**
```bash
cat audit.log | jq 'select(.audit.event_type | startswith("webhook.failed") or startswith("payment.failed"))'
```

## Compliance Considerations

### PCI DSS Compliance

The audit logging system supports PCI DSS requirements:

- **Requirement 10.2**: Implements audit trail for all system components
- **Requirement 10.3**: Records required audit trail entries:
  - User identification (user_id, admin_id)
  - Type of event (event_type)
  - Date and time (timestamp)
  - Success or failure indication (implicit in event_type)
  - Origination of event (ip_address, user_agent)
  - Identity/name of affected data/resource (resource_id, resource_type)

### GDPR Compliance

- Audit logs may contain PII (user_id, ip_address)
- Implement data retention and deletion policies
- Provide audit log access for data subject access requests
- Document audit logging in privacy policy

## Security Considerations

### What to Log

✅ **DO Log:**
- All subscription state changes
- All payment operations
- All administrative actions
- All webhook events
- All access to sensitive resources

❌ **DO NOT Log:**
- Full credit card numbers
- CVV codes
- Passwords or authentication tokens
- Full webhook payload (sanitize first)
- Unencrypted PII beyond user_id

### Log Protection

1. **Access Control**
   - Restrict access to audit logs to authorized personnel only
   - Implement role-based access control
   - Audit access to audit logs (meta-logging)

2. **Integrity**
   - Use write-once storage where possible
   - Implement log signing/hashing
   - Regular integrity checks

3. **Encryption**
   - Encrypt logs at rest
   - Use TLS for log transmission
   - Encrypt sensitive fields in metadata

## Monitoring and Alerting

### Key Metrics to Monitor

1. **Security Events**
   - Failed webhook signature verifications
   - Multiple failed payments from same user
   - Admin actions outside business hours
   - Unusual refund patterns

2. **Operational Events**
   - Webhook processing delays
   - Payment failure rate spikes
   - Subscription churn rate changes

3. **Anomaly Detection**
   - Unusual admin activity patterns
   - Spike in cancellations
   - Geographic anomalies (IP addresses)

### Alert Examples

```python
# Example: Alert on multiple failed webhooks
if webhook_failed_count > 5 in last_5_minutes:
    send_alert("Multiple webhook failures detected")

# Example: Alert on suspicious refund
if refund.amount > 10000 or refund_count > 5 in last_hour:
    send_alert("Suspicious refund activity")
```

## Testing

Comprehensive test suite available at `tests/services/test_audit_logger.py`:

- 18 test cases covering all event types
- Structured logging format validation
- None value exclusion tests
- ISO timestamp format validation

Run tests:
```bash
.venv/bin/pytest tests/services/test_audit_logger.py -v
```

## Future Enhancements

### Planned Features

1. **Database Storage**
   - Optional database table for audit logs
   - Faster querying and reporting
   - Built-in retention policies

2. **Audit Log API**
   - REST API for querying audit logs
   - Admin dashboard for audit log viewing
   - Export functionality (CSV, JSON)

3. **Advanced Analytics**
   - Audit log analytics dashboard
   - Anomaly detection algorithms
   - Predictive alerts

4. **Integration**
   - SIEM system integration
   - Automated compliance reporting
   - Real-time streaming to analytics platforms

## References

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [PCI DSS Requirement 10](https://www.pcisecuritystandards.org/)
- [GDPR Article 30 - Records of Processing](https://gdpr-info.eu/art-30-gdpr/)
- [NIST SP 800-92 - Guide to Computer Security Log Management](https://csrc.nist.gov/publications/detail/sp/800-92/final)

## Support

For questions or issues:
- Technical: Review code at `src/services/audit_logger.py`
- Compliance: Consult with legal/compliance team
- Implementation: Contact engineering team

---

**Last Updated**: 2025-10-20
**Version**: 1.0.0
**Status**: Production Ready
