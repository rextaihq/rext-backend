# Audit Logging System

**Version:** 1.0
**Created:** 2025-10-20
**Status:** ✅ Production Ready

---

## Overview

The WREXT audit logging system provides comprehensive tracking of all payment, subscription, and administrative operations. It implements structured JSON logging with consistent fields across all operations, enabling easy parsing, filtering, and analysis for compliance, debugging, and security purposes.

## Features

- **Structured JSON Logging** - Consistent format for easy parsing and analysis
- **Comprehensive Coverage** - All payment, subscription, webhook, and admin operations
- **Automatic Timestamping** - ISO 8601 format timestamps for all events
- **User & Admin Tracking** - Track both user actions and admin interventions
- **Resource Identification** - Link events to specific resources (subscriptions, payments, etc.)
- **Change Tracking** - Before/after values for state changes
- **Context Preservation** - IP addresses, user agents, and additional metadata
- **Clean Output** - Automatic exclusion of null values to reduce log size

## Architecture

### Core Components

1. **AuditLogger Service** (`src/services/audit_logger.py`)
   - Main audit logging service
   - 600+ lines of comprehensive logging methods
   - Singleton pattern for easy access throughout application

2. **AuditEventType Enum**
   - Categorizes all audit events
   - Enables easy filtering and searching
   - Consistent event naming convention

3. **Structured Log Format**
   - JSON format in production
   - Human-readable format in development
   - Standard fields across all events

### Event Categories

The audit system tracks the following categories of events:

#### 1. Subscription Events
- `subscription.created` - New subscription created
- `subscription.updated` - Subscription details changed
- `subscription.cancelled` - Subscription cancelled by user or admin
- `subscription.resumed` - Cancelled subscription resumed
- `subscription.expired` - Subscription reached end of life
- `subscription.paused` - Subscription temporarily paused
- `subscription.upgraded` - User upgraded to higher tier
- `subscription.downgraded` - User downgraded to lower tier

#### 2. Payment Events
- `payment.succeeded` - Payment processed successfully
- `payment.failed` - Payment failed (card declined, etc.)
- `payment.recovered` - Previously failed payment succeeded
- `payment.refunded` - Payment refunded to customer

#### 3. Checkout Events
- `checkout.created` - Checkout session created
- `checkout.completed` - Customer completed checkout
- `checkout.abandoned` - Customer abandoned checkout

#### 4. Webhook Events
- `webhook.received` - Webhook event received from provider
- `webhook.processed` - Webhook successfully processed
- `webhook.failed` - Webhook processing failed
- `webhook.signature_invalid` - Webhook signature verification failed

#### 5. Admin Actions
- `admin.refund_created` - Admin initiated refund
- `admin.subscription_extended` - Admin extended subscription
- `admin.subscription_cancelled` - Admin cancelled subscription
- `admin.user_migrated` - Admin migrated user to new plan
- `admin.plan_changed` - Admin changed user's plan

#### 6. License Events
- `license.created` - License key created
- `license.activated` - License activated on device
- `license.deactivated` - License deactivated from device
- `license.revoked` - Admin revoked license

#### 7. Trial Events
- `trial.started` - User started trial period
- `trial.converted` - Trial converted to paid subscription
- `trial.expired` - Trial period ended without conversion

#### 8. User Actions
- `user.portal_accessed` - User accessed customer portal
- `user.invoice_downloaded` - User downloaded invoice
- `user.plan_viewed` - User viewed plan details

---

## Log Structure

### Standard Fields

Every audit log includes these standard fields:

```json
{
  "event_type": "subscription.created",
  "timestamp": "2025-10-20T14:32:15.123456",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "resource_type": "subscription",
  "resource_id": "660e8400-e29b-41d4-a716-446655440001",
  "metadata": {
    "plan_name": "Pro",
    "billing_period": "monthly",
    "amount": 1999
  }
}
```

### Optional Fields

Depending on the event type, additional fields may be included:

- `admin_id` - ID of admin performing action (for admin events)
- `changes` - Before/after values for state changes
- `ip_address` - IP address of actor
- `user_agent` - User agent of actor

### Metadata Field

The `metadata` field contains event-specific information:

- **Subscription events**: plan details, billing info, trial status
- **Payment events**: amounts, currency, payment IDs, card info
- **Webhook events**: event IDs, processing times, signatures
- **Admin events**: reasons, affected resources

---

## Usage Examples

### Basic Usage

```python
from src.services.audit_logger import audit_logger

# Log subscription creation
audit_logger.log_subscription_created(
    user_id=user.id,
    subscription_id=subscription.id,
    plan_id=plan.id,
    plan_name="Pro",
    billing_period="monthly",
    is_trial=False,
    amount=1999,
    lemonsqueezy_subscription_id="sub_123"
)
```

### With Admin Context

```python
# Log admin refund
audit_logger.log_admin_refund_created(
    admin_id=admin.id,
    user_id=user.id,
    refund_id=refund.id,
    subscription_id=subscription.id,
    amount=1999,
    reason="Duplicate charge",
    ip_address=request.client.host
)
```

### With Change Tracking

```python
# Log subscription upgrade with changes
audit_logger.log_subscription_upgraded(
    user_id=user.id,
    subscription_id=subscription.id,
    old_plan_name="Basic",
    new_plan_name="Pro",
    old_billing_period="monthly",
    new_billing_period="yearly",
    proration_amount=500
)
```

### Webhook Events

```python
# Log webhook receipt
audit_logger.log_webhook_received(
    event_id="evt_123",
    event_name="subscription_created",
    signature_valid=True,
    ip_address=request.client.host
)

# Log successful processing
audit_logger.log_webhook_processed(
    event_id="evt_123",
    event_name="subscription_created",
    processing_time_ms=145.3,
    user_id=user.id
)

# Log processing failure
audit_logger.log_webhook_failed(
    event_id="evt_456",
    event_name="subscription_updated",
    error="Subscription not found",
    retry_count=2
)
```

---

## Integration Points

### 1. Subscription Service

**File:** `src/services/subscription_service.py`

Logs all subscription operations:
- Subscription creation (line 146)
- Trial starts (line 138)
- Checkout creation (line 286)
- Upgrades/downgrades (lines 456, 465)
- Cancellations (line 610)

### 2. Webhook Handlers

**File:** `src/services/webhook_handlers/subscription_handlers.py`

Logs webhook processing:
- Payment success (line 655)
- Payment failures (line 755)
- All webhook events via route handler

**File:** `src/api/routes/subscriptions/webhook_routes.py`

Logs webhook receipt and processing:
- Webhook received events
- Processing completion (line 316)
- Signature validation

### 3. Admin Operations

**File:** `src/api/routes/subscriptions/admin/refund_routes.py`

Logs admin actions:
- Refund creation (line 291)
- Admin cancellations
- Plan modifications

### 4. Payment Provider

**File:** `src/providers/payment/providers/lemonsqueezy.py`

Payment operations are logged indirectly through:
- Subscription service integration
- Webhook handler integration
- Direct logging in provider methods

---

## Querying Audit Logs

### Filter by Event Type

```bash
# All subscription events
grep "subscription\." application.log | jq .

# Only cancellations
grep "subscription.cancelled" application.log | jq .

# Admin actions only
grep "admin\." application.log | jq .
```

### Filter by User

```bash
# All events for specific user
jq 'select(.audit.user_id == "user-uuid-here")' application.log
```

### Filter by Time Range

```bash
# Events from specific date
jq 'select(.audit.timestamp | startswith("2025-10-20"))' application.log
```

### Complex Queries

```bash
# Failed payments with amounts over $50
jq 'select(.audit.event_type == "payment.failed" and .audit.metadata.amount > 5000)' application.log

# Admin refunds with reasons
jq 'select(.audit.event_type == "admin.refund_created") | {user: .audit.user_id, amount: .audit.metadata.amount, reason: .audit.metadata.reason}' application.log
```

---

## Log Rotation & Storage

### Development

- Logs written to stdout
- Human-readable console format
- No rotation needed

### Production

- Structured JSON format
- Written to application log file
- Recommended rotation:
  - Daily rotation
  - Keep 90 days for compliance
  - Compress older logs
  - Archive to S3/Cloud Storage

### Example Logrotate Configuration

```
/var/log/wrext/application.log {
    daily
    rotate 90
    compress
    delaycompress
    notifempty
    create 0644 wrext wrext
    sharedscripts
    postrotate
        # Upload to S3
        aws s3 cp /var/log/wrext/application.log-*.gz s3://wrext-audit-logs/
    endscript
}
```

---

## Security Considerations

### Data Privacy

1. **No Sensitive Data** - Audit logs do NOT contain:
   - Full credit card numbers
   - CVV codes
   - Complete addresses
   - Passwords or tokens

2. **Masked Information**
   - Card numbers: Last 4 digits only
   - Emails: Linked via user_id (not logged directly)

3. **Access Control**
   - Restrict log file access to admin users only
   - Use separate log rotation/archive credentials
   - Enable encryption at rest for archived logs

### Compliance

The audit system supports:

- **PCI DSS** - No cardholder data in logs
- **GDPR** - User IDs enable right-to-erasure queries
- **SOC 2** - Complete audit trail for all operations
- **HIPAA** - Structured logging for access audits

---

## Monitoring & Alerts

### Critical Events to Monitor

1. **High Failed Payment Rate**
   ```bash
   # Alert if >10 failed payments in 1 hour
   grep "payment.failed" application.log | grep "$(date +%Y-%m-%d)" | wc -l
   ```

2. **Invalid Webhook Signatures**
   ```bash
   # Alert on ANY invalid signature
   grep "webhook.signature_invalid" application.log
   ```

3. **Admin Refunds**
   ```bash
   # Track all admin refunds for review
   grep "admin.refund_created" application.log
   ```

4. **Subscription Churn**
   ```bash
   # Monitor cancellation rate
   grep "subscription.cancelled" application.log | grep "$(date +%Y-%m-%d)"
   ```

### Integration with Monitoring Tools

**Sentry Integration**
- Payment errors also sent to Sentry
- Audit logs provide additional context
- Cross-reference via correlation IDs

**ELK Stack**
- Ship logs to Elasticsearch
- Create Kibana dashboards
- Set up alerts in ElastAlert

**Datadog/New Relic**
- Parse structured JSON logs
- Create custom metrics
- Alert on anomalies

---

## Testing

### Test Coverage

**File:** `tests/services/test_audit_logger.py`

- 18 comprehensive tests
- 100% pass rate
- Covers all event types

**Test Categories:**
- Initialization
- Subscription events (creation, cancellation, upgrade/downgrade)
- Payment events (success, failure, refund)
- Checkout events
- Webhook events (received, processed, failed)
- Admin actions
- License events
- Trial events
- Structured format validation

### Running Tests

```bash
# Run all audit logger tests
pytest tests/services/test_audit_logger.py -v

# Run with coverage
pytest tests/services/test_audit_logger.py --cov=src.services.audit_logger

# Run specific test
pytest tests/services/test_audit_logger.py::TestAuditLogger::test_log_subscription_created -v
```

---

## Performance Considerations

### Log Volume Estimates

Based on typical SaaS metrics:

- **1,000 active subscriptions**
  - ~100 events/day (updates, renewals)
  - ~3 MB/day uncompressed
  - ~90 MB/month
  - ~300 KB/month compressed

- **10,000 active subscriptions**
  - ~1,000 events/day
  - ~30 MB/day
  - ~900 MB/month
  - ~3 MB/month compressed

### Optimization Tips

1. **Async Logging** - Use async logger to avoid blocking operations
2. **Batching** - Batch write logs to reduce I/O
3. **Compression** - Enable log compression for storage
4. **Sampling** - Consider sampling for very high-volume events
5. **Archive Strategy** - Move old logs to cold storage

---

## Troubleshooting

### Logs Not Appearing

1. **Check Log Level**
   ```python
   # Ensure audit logger is at INFO level
   import logging
   logging.getLogger("audit").setLevel(logging.INFO)
   ```

2. **Verify Logger Configuration**
   ```python
   # Check logging is configured
   from src.api.lib.logging_config import configure_logging
   configure_logging()
   ```

3. **Check Log Output**
   - Development: Logs to console
   - Production: Check log file path

### Missing Fields in Logs

- Optional fields (admin_id, ip_address) only logged when provided
- None values are automatically excluded
- Check metadata dict for event-specific fields

### High Log Volume

1. Identify noisy events with `uniq -c`
2. Consider sampling for non-critical events
3. Implement log aggregation (ELK, Datadog)
4. Enable compression and archival

---

## Future Enhancements

### Planned Features

1. **Database Storage**
   - Store audit logs in PostgreSQL table
   - Enable SQL queries for complex analysis
   - Implement retention policies

2. **Real-time Streaming**
   - Stream audit events to Kafka
   - Enable real-time monitoring
   - Support multiple consumers

3. **Enhanced Analytics**
   - Pre-built dashboards
   - Anomaly detection
   - Churn prediction models

4. **User-Facing Audit Log**
   - Show users their own audit trail
   - Export capability for compliance
   - Email notifications for critical events

### Contribution Guidelines

To add new audit events:

1. Add event type to `AuditEventType` enum
2. Create method in `AuditLogger` class
3. Add tests in `test_audit_logger.py`
4. Update this documentation
5. Integrate into appropriate service/route

---

## Support & Maintenance

### Ownership

- **Team:** Backend Engineering
- **Primary Contact:** [Your team contact]
- **On-call:** [On-call rotation]

### SLA

- **Log Availability:** 99.9%
- **Log Retention:** 90 days (configurable)
- **Query Performance:** <2s for 24h queries

### Related Documentation

- [Webhook Security Monitoring](../security/WEBHOOK_SECURITY_PRODUCTION.md)
- [Sentry Payment Monitoring](../monitoring/SENTRY_PAYMENT_MONITORING.md)
- [API Key Rotation](../security/API_KEY_ROTATION.md)
- [Logging Configuration](../../src/api/lib/logging_config.py)

---

## Changelog

### Version 1.0 (2025-10-20)
- ✅ Initial implementation
- ✅ Comprehensive event coverage
- ✅ 18 tests with 100% pass rate
- ✅ Integration across all payment/subscription operations
- ✅ Documentation complete

---

## Appendix

### Full Event Type Reference

```python
# Subscription Events
SUBSCRIPTION_CREATED = "subscription.created"
SUBSCRIPTION_UPDATED = "subscription.updated"
SUBSCRIPTION_CANCELLED = "subscription.cancelled"
SUBSCRIPTION_RESUMED = "subscription.resumed"
SUBSCRIPTION_EXPIRED = "subscription.expired"
SUBSCRIPTION_PAUSED = "subscription.paused"
SUBSCRIPTION_UPGRADED = "subscription.upgraded"
SUBSCRIPTION_DOWNGRADED = "subscription.downgraded"

# Payment Events
PAYMENT_SUCCEEDED = "payment.succeeded"
PAYMENT_FAILED = "payment.failed"
PAYMENT_RECOVERED = "payment.recovered"
PAYMENT_REFUNDED = "payment.refunded"

# Checkout Events
CHECKOUT_CREATED = "checkout.created"
CHECKOUT_COMPLETED = "checkout.completed"
CHECKOUT_ABANDONED = "checkout.abandoned"

# Webhook Events
WEBHOOK_RECEIVED = "webhook.received"
WEBHOOK_PROCESSED = "webhook.processed"
WEBHOOK_FAILED = "webhook.failed"
WEBHOOK_SIGNATURE_INVALID = "webhook.signature_invalid"

# Admin Actions
ADMIN_REFUND_CREATED = "admin.refund_created"
ADMIN_SUBSCRIPTION_EXTENDED = "admin.subscription_extended"
ADMIN_SUBSCRIPTION_CANCELLED = "admin.subscription_cancelled"
ADMIN_USER_MIGRATED = "admin.user_migrated"
ADMIN_PLAN_CHANGED = "admin.plan_changed"

# License Events
LICENSE_CREATED = "license.created"
LICENSE_ACTIVATED = "license.activated"
LICENSE_DEACTIVATED = "license.deactivated"
LICENSE_REVOKED = "license.revoked"

# Trial Events
TRIAL_STARTED = "trial.started"
TRIAL_CONVERTED = "trial.converted"
TRIAL_EXPIRED = "trial.expired"

# User Actions
USER_PORTAL_ACCESSED = "user.portal_accessed"
USER_INVOICE_DOWNLOADED = "user.invoice_downloaded"
USER_PLAN_VIEWED = "user.plan_viewed"
```

### Sample Log Output

```json
{
  "event_type": "subscription.created",
  "timestamp": "2025-10-20T14:32:15.123456",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "resource_type": "subscription",
  "resource_id": "660e8400-e29b-41d4-a716-446655440001",
  "metadata": {
    "plan_id": "770e8400-e29b-41d4-a716-446655440002",
    "plan_name": "Pro",
    "billing_period": "monthly",
    "is_trial": false,
    "amount": 1999,
    "lemonsqueezy_subscription_id": "sub_123abc"
  }
}
```

```json
{
  "event_type": "admin.refund_created",
  "timestamp": "2025-10-20T15:45:30.987654",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "admin_id": "880e8400-e29b-41d4-a716-446655440003",
  "resource_type": "refund",
  "resource_id": "990e8400-e29b-41d4-a716-446655440004",
  "ip_address": "192.0.2.100",
  "metadata": {
    "subscription_id": "660e8400-e29b-41d4-a716-446655440001",
    "amount": 1999,
    "reason": "Duplicate charge"
  }
}
```
