# Webhook Performance Monitoring

**Phase 4, Task 4.2.4** - Monitoring for webhook processing delays

## Overview

This document describes the monitoring system for webhook processing performance to ensure timely payment event processing and prevent revenue delays.

## Key Metrics

### 1. Processing Time (Duration)
- **Metric**: `processing_time_ms`
- **Target**: < 2000ms (2 seconds)
- **Warning Threshold**: > 3000ms (3 seconds)
- **Critical Threshold**: > 5000ms (5 seconds)

### 2. Webhook Queue Depth
- **Metric**: Unprocessed webhook events count
- **Target**: < 10 pending events
- **Warning Threshold**: > 50 pending events
- **Critical Threshold**: > 100 pending events

### 3. Processing Success Rate
- **Metric**: Successful vs failed webhook processing
- **Target**: > 99%
- **Warning Threshold**: < 98%
- **Critical Threshold**: < 95%

## Monitoring Implementation

### 1. Processing Time Tracking

Webhook processing time is automatically tracked in `webhook_routes.py`:

```python
# Processing time is captured automatically
result = await webhook_service.process_webhook(body, signature)

# Logged to audit system with timing
audit_logger.log_webhook_processed(
    event_id=result.get("event_id"),
    event_name=result.get("event_type"),
    processing_time_ms=result.get("processing_time_ms", 0),
    metadata={"status": "success"}
)
```

### 2. Sentry Performance Monitoring

Webhook processing is tracked in Sentry with 100% sampling rate (configured in `sentry_config.py`):

```python
def traces_sampler(sampling_context: Dict[str, Any]) -> float:
    """
    Determine sampling rate for performance traces.
    """
    if "webhook" in path:
        return 1.0  # 100% sampling for webhooks
```

### 3. Structured Logging

All webhook operations include timing metrics:

```python
logger.info(
    "Webhook processed successfully",
    operation="webhook_processing",
    event_type="subscription_created",
    processing_time_ms=result.get("processing_time_ms"),
    duration_ms=duration
)
```

## Alert Configuration

### Alert 1: Slow Webhook Processing

**Trigger**: Webhook processing time > 5 seconds

**Sentry Query**:
```
transaction:"/api/v1/webhooks/lemonsqueezy"
AND transaction.duration:>5000
```

**Configuration**:
1. Navigate to Sentry > Alerts > Create Alert Rule
2. Select "Metric Alert" type
3. Set conditions:
   - Metric: `transaction.duration`
   - Transaction: `/api/v1/webhooks/lemonsqueezy`
   - Threshold: > 5000ms
4. Set "When" condition: 3 events in 5 minutes
5. Add actions:
   - Send email to engineering team
   - Send Slack notification to #payments-alerts

**Severity**: HIGH
**Notification**: Email + Slack
**Response Time**: 15 minutes

---

### Alert 2: High Webhook Queue Depth

**Trigger**: > 100 unprocessed webhook events

**Database Query**:
```sql
SELECT COUNT(*)
FROM webhook_events
WHERE processed = false
  AND created_at > NOW() - INTERVAL '1 hour'
```

**Monitoring Script** (`scripts/monitor_webhook_queue.py`):
```python
#!/usr/bin/env python3
"""Monitor webhook queue depth and alert if too high."""
import asyncio
from sqlalchemy import func, select
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.api.database.async_database import get_async_session
from src.api.lib.sentry_config import trigger_payment_alert

async def check_webhook_queue():
    async with get_async_session() as db:
        # Count unprocessed webhooks from last hour
        stmt = select(func.count(WebhookEvent.id)).where(
            WebhookEvent.processed == False,
            WebhookEvent.created_at > datetime.utcnow() - timedelta(hours=1)
        )
        result = await db.execute(stmt)
        count = result.scalar()

        if count > 100:
            trigger_payment_alert(
                alert_type="high_webhook_queue",
                message=f"Webhook queue depth critical: {count} unprocessed events",
                severity="critical",
                context={"queue_depth": count}
            )
        elif count > 50:
            trigger_payment_alert(
                alert_type="elevated_webhook_queue",
                message=f"Webhook queue depth elevated: {count} unprocessed events",
                severity="high",
                context={"queue_depth": count}
            )

if __name__ == "__main__":
    asyncio.run(check_webhook_queue())
```

**Cron Schedule**: Every 5 minutes
```bash
*/5 * * * * /path/to/venv/bin/python /path/to/scripts/monitor_webhook_queue.py
```

**Severity**: CRITICAL
**Notification**: Email + Slack + PagerDuty
**Response Time**: Immediate

---

### Alert 3: Webhook Processing Failures

**Trigger**: > 5% failure rate in last 10 minutes

**Sentry Query**:
```
transaction:"/api/v1/webhooks/lemonsqueezy"
AND status:error
```

**Configuration**:
1. Navigate to Sentry > Alerts > Create Alert Rule
2. Select "Metric Alert" type
3. Set conditions:
   - Metric: `count()`
   - Transaction: `/api/v1/webhooks/lemonsqueezy`
   - Status: `error`
   - Threshold: > 5 errors in 10 minutes
4. Add actions:
   - Send email to engineering team
   - Send Slack notification to #payments-critical
   - Trigger PagerDuty incident

**Severity**: CRITICAL
**Notification**: Email + Slack + PagerDuty
**Response Time**: Immediate

## Performance Queries

### 1. Average Processing Time (Last 24 Hours)

**Sentry Discover Query**:
```
SELECT
  avg(transaction.duration) as avg_duration,
  p50(transaction.duration) as p50,
  p95(transaction.duration) as p95,
  p99(transaction.duration) as p99
WHERE
  transaction = "/api/v1/webhooks/lemonsqueezy"
  AND timestamp > NOW() - 24h
```

### 2. Slow Webhook Events

**Sentry Discover Query**:
```
SELECT
  event.type,
  timestamp,
  transaction.duration,
  tags[event_type]
WHERE
  transaction = "/api/v1/webhooks/lemonsqueezy"
  AND transaction.duration > 3000
ORDER BY transaction.duration DESC
LIMIT 100
```

### 3. Webhook Queue Status

**Database Query** (via admin API `/api/v1/admin/webhooks/stats`):
```sql
SELECT
  COUNT(*) as total_events,
  COUNT(*) FILTER (WHERE processed = true) as processed,
  COUNT(*) FILTER (WHERE processed = false) as pending,
  COUNT(*) FILTER (WHERE error_message IS NOT NULL) as failed,
  AVG(EXTRACT(EPOCH FROM (processed_at - created_at)) * 1000) as avg_processing_time_ms
FROM webhook_events
WHERE created_at > NOW() - INTERVAL '24 hours';
```

### 4. Event Type Breakdown

**Database Query**:
```sql
SELECT
  event_name,
  COUNT(*) as count,
  AVG(EXTRACT(EPOCH FROM (processed_at - created_at)) * 1000) as avg_processing_time_ms,
  COUNT(*) FILTER (WHERE processed = false) as pending_count
FROM webhook_events
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY event_name
ORDER BY count DESC;
```

## Dashboard Configuration

### Sentry Performance Dashboard

Create a custom dashboard with these widgets:

1. **Webhook Processing Time (P50, P95, P99)**
   - Type: Line chart
   - Query: Transaction duration percentiles
   - Time range: Last 24 hours

2. **Webhook Throughput**
   - Type: Line chart
   - Query: Count of webhook transactions per minute
   - Time range: Last 24 hours

3. **Error Rate**
   - Type: Line chart
   - Query: Percentage of failed webhooks
   - Time range: Last 24 hours

4. **Slow Webhooks (>3s)**
   - Type: Table
   - Query: Events with duration > 3000ms
   - Columns: Event type, Duration, Timestamp

### Grafana Dashboard (Optional)

If using Grafana with database metrics:

```json
{
  "dashboard": {
    "title": "Webhook Performance",
    "panels": [
      {
        "title": "Queue Depth",
        "targets": [{
          "rawSql": "SELECT COUNT(*) FROM webhook_events WHERE processed = false"
        }]
      },
      {
        "title": "Processing Time",
        "targets": [{
          "rawSql": "SELECT AVG(processing_time_ms) FROM webhook_events WHERE processed_at > NOW() - INTERVAL '1 hour'"
        }]
      }
    ]
  }
}
```

## Troubleshooting Slow Webhooks

### Common Causes

1. **Database Slowness**
   - Check database connection pool
   - Review slow query logs
   - Check for missing indexes

2. **External API Calls**
   - LemonSqueezy API rate limits
   - Network latency
   - Timeout issues

3. **Resource Contention**
   - High CPU usage
   - Memory pressure
   - Disk I/O bottleneck

4. **Large Payloads**
   - Complex webhook payloads
   - JSON parsing overhead

### Debugging Steps

1. **Identify Slow Events**
   ```bash
   # Query Sentry for slow transactions
   # Check event_type tag to identify which webhook types are slow
   ```

2. **Check Database Performance**
   ```sql
   -- Find slow queries
   SELECT query, mean_exec_time
   FROM pg_stat_statements
   WHERE query LIKE '%webhook%'
   ORDER BY mean_exec_time DESC;
   ```

3. **Review Application Logs**
   ```bash
   # Filter for slow webhook processing
   grep "processing_time_ms" /var/log/app.log | awk '$NF > 3000'
   ```

4. **Profile Code**
   ```python
   # Add timing breakpoints in webhook handlers
   with log_payment_timing(logger, "webhook_step", "Processing step"):
       # ... code ...
   ```

## Performance Optimization

### Best Practices

1. **Minimize Database Queries**
   - Use batch operations where possible
   - Optimize joins and indexes
   - Consider read replicas for heavy queries

2. **Async Processing**
   - Use background tasks for non-critical operations
   - Queue email sending
   - Defer analytics updates

3. **Caching**
   - Cache subscription plans
   - Cache user data
   - Use Redis for frequently accessed data

4. **Connection Pooling**
   - Maintain adequate database connection pool
   - Monitor connection usage
   - Tune pool size based on load

### Optimization Checklist

- [ ] Database indexes on frequently queried fields
- [ ] Connection pool sized appropriately
- [ ] Background tasks for non-critical operations
- [ ] Webhook payload validation is minimal
- [ ] Error handling doesn't slow happy path
- [ ] Logging is async and non-blocking
- [ ] External API calls have timeouts
- [ ] Redis caching for hot data

## SLA Targets

### Processing Time SLA

- **P50**: < 500ms (50th percentile)
- **P95**: < 2000ms (95th percentile)
- **P99**: < 5000ms (99th percentile)

### Queue Depth SLA

- **Normal**: < 10 pending events
- **Acceptable**: < 50 pending events
- **Critical**: > 100 pending events (alert immediately)

### Success Rate SLA

- **Target**: > 99.5% success rate
- **Minimum**: > 98% success rate
- **Critical**: < 95% success rate (alert immediately)

## Related Documentation

- **Webhook Security**: `docs/security/WEBHOOK_SECURITY_PRODUCTION.md`
- **Webhook Monitoring**: `docs/monitoring/WEBHOOK_MONITORING.md`
- **Payment Logging**: `docs/logging/PAYMENT_LOGGING.md`
- **Sentry Configuration**: `docs/monitoring/SENTRY_PAYMENT_MONITORING.md`

## Changelog

**2025-10-20** - Phase 4, Task 4.2.4
- Initial webhook performance monitoring documentation
- Added Sentry alert configurations
- Created queue depth monitoring script
- Defined SLA targets and thresholds
- Added performance optimization guidelines
