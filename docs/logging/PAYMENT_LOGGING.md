# Payment Logging Architecture

**Phase 4, Task 4.2.2** - Comprehensive logging system for LemonSqueezy payment operations

## Overview

The payment logging system provides structured, traceable logs for all payment operations including API calls, webhook processing, subscription state changes, and customer actions. It integrates with Structlog for structured logging and Sentry for error tracking.

## Key Features

- **Structured Logging**: All payment logs use consistent structured format with JSON in production
- **Correlation IDs**: Unique tracking IDs for tracing operations across systems
- **Timing Metrics**: Automatic performance timing for all payment operations
- **Context Binding**: Payment context automatically attached to all logs in scope
- **Sanitization**: Sensitive data automatically redacted from logs
- **Integration**: Works seamlessly with Sentry monitoring (Task 4.2.1)

## Architecture

### Components

1. **Logging Configuration** (`src/api/lib/logging_config.py`)
   - Payment-specific logging utilities
   - Correlation ID generation
   - Context binding and timing helpers

2. **Provider Logging** (`src/providers/payment/providers/lemonsqueezy.py`)
   - API request/response logging
   - Operation timing
   - Error logging with context

3. **Webhook Logging** (`src/services/webhook_handlers/subscription_handlers.py`)
   - Event processing logs
   - State transition tracking
   - Error handling

4. **Service Logging** (`src/services/subscription_service.py`)
   - Business logic operations
   - State changes
   - User actions

## Log Levels

### DEBUG
- **When**: Development and troubleshooting
- **Examples**:
  - API request/response details
  - Detailed state transitions
  - Validation steps

### INFO
- **When**: Normal operations, success cases
- **Examples**:
  - Checkout session created
  - Subscription state changes
  - Webhook processing completed
  - Timing metrics

### WARNING
- **When**: Recoverable issues, deprecations
- **Examples**:
  - Retry attempts
  - Missing optional data
  - Validation failures (non-critical)
  - Rate limit warnings

### ERROR
- **When**: Operation failures
- **Examples**:
  - API errors from LemonSqueezy
  - Webhook signature verification failures
  - Database errors
  - Failed subscription operations

## Structured Log Format

### Standard Fields

Every payment log includes these fields:

```json
{
  "timestamp": "2025-10-20T15:30:45.123Z",
  "level": "info",
  "event": "Log message here",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "operation": "checkout|webhook|update|cancel",
  "provider": "lemonsqueezy",
  "correlation_id": "pay_abc123def456",
  "duration_ms": 234
}
```

### Payment-Specific Fields

Additional fields based on operation:

```json
{
  "user_id": "uuid",
  "subscription_id": "sub_xxx",
  "customer_id": "cus_xxx",
  "plan_id": "uuid",
  "variant_id": "xxx",
  "status": "active|cancelled|...",
  "amount": 2999,
  "currency": "USD",
  "event_type": "subscription_created",
  "session_id": "ses_xxx"
}
```

## Usage Examples

### 1. Generating Correlation IDs

```python
from src.api.lib.logging_config import generate_payment_correlation_id

# Generate unique ID for tracking
correlation_id = generate_payment_correlation_id()
# Returns: "pay_abc123def456" (20 chars)
```

### 2. Binding Payment Context

```python
from src.api.lib.logging_config import bind_payment_context

# Bind context that applies to all subsequent logs
bind_payment_context(
    operation="checkout",
    user_id="user_123",
    plan_id="plan_456",
    correlation_id=correlation_id
)

# All logs in this scope will include these fields
logger.info("Creating checkout session")
# Output includes: operation, user_id, plan_id, correlation_id
```

### 3. Logging with Timing

```python
from src.api.lib.logging_config import log_payment_timing

# Automatic timing for operations
with log_payment_timing(
    logger,
    operation="checkout",
    message="Creating checkout session",
    variant_id="var_123"
) as ctx:
    # Perform operation
    session = await create_session()

    # Update context with results
    ctx["session_id"] = session.id
    ctx["checkout_url"] = session.url

# Automatically logs:
# - Start (DEBUG): "Creating checkout session - started"
# - Complete (INFO): "Creating checkout session - completed" + duration_ms
# - On error (ERROR): "Creating checkout session - failed" + error details
```

### 4. Simple Payment Operation Logging

```python
from src.api.lib.logging_config import log_payment_operation

# Convenience function for one-off logs
log_payment_operation(
    logger,
    "info",
    "Subscription activated",
    operation="webhook",
    subscription_id="sub_123",
    user_id="user_456",
    plan_id="plan_789"
)
```

### 5. Clearing Context

```python
from src.api.lib.logging_config import clear_payment_context

# Clear context after operation completes
clear_payment_context()
```

## Common Log Queries

### Query by Operation Type

**Find all checkout operations:**
```
operation:checkout
```

**Find all webhook processing:**
```
operation:webhook_*
```

### Query by User

```
user_id:550e8400-e29b-41d4-a716-446655440000
```

### Query by Subscription

```
subscription_id:sub_123
```

### Query by Correlation ID

```
correlation_id:pay_abc123def456
```

### Query for Errors

```
level:error operation:checkout
```

### Query for Slow Operations

```
operation:api_request duration_ms:>5000
```

## Integration with Sentry

Payment logs integrate with Sentry (Task 4.2.1) for error tracking:

### Error Capture

```python
from src.api.lib.sentry_config import capture_payment_exception

try:
    result = await payment_operation()
except Exception as e:
    # Log error
    logger.error(
        "Payment operation failed",
        operation="checkout",
        error=str(e)
    )

    # Capture to Sentry with context
    capture_payment_exception(
        e,
        operation="checkout",
        context={...}
    )
    raise
```

### Breadcrumbs

```python
from src.api.lib.sentry_config import add_payment_breadcrumb

# Add breadcrumb before operation
add_payment_breadcrumb(
    "Creating checkout session",
    operation="checkout",
    data={"variant_id": "var_123"}
)

# Breadcrumbs appear in Sentry if error occurs
```

## Monitoring Dashboard Queries

### Payment Success Rate

```sql
SELECT
  COUNT(*) FILTER (WHERE level = 'info' AND event LIKE '%completed%') as success,
  COUNT(*) FILTER (WHERE level = 'error') as errors
FROM logs
WHERE operation LIKE 'checkout%'
  AND timestamp > NOW() - INTERVAL '24 hours'
```

### Average Operation Duration

```sql
SELECT
  operation,
  AVG(duration_ms) as avg_duration,
  P50(duration_ms) as p50,
  P95(duration_ms) as p95
FROM logs
WHERE duration_ms IS NOT NULL
  AND timestamp > NOW() - INTERVAL '24 hours'
GROUP BY operation
```

### Error Rate by Operation

```sql
SELECT
  operation,
  COUNT(*) FILTER (WHERE level = 'error') * 100.0 / COUNT(*) as error_rate
FROM logs
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY operation
ORDER BY error_rate DESC
```

## Debugging Workflows

### 1. Debugging Failed Checkout

**Step 1**: Find the correlation ID
```
level:error operation:checkout user_id:USER_ID
```

**Step 2**: Get all logs for that correlation
```
correlation_id:pay_abc123def456
```

**Step 3**: Review Sentry for full context
- Check breadcrumbs
- Review stack trace
- Check captured context

### 2. Debugging Webhook Processing

**Step 1**: Find webhook event
```
operation:webhook_* event_id:EVENT_ID
```

**Step 2**: Check timing
```
operation:webhook_* duration_ms:>5000
```

**Step 3**: Check for errors
```
level:error operation:webhook_*
```

### 3. Tracking User Journey

**Step 1**: Find user's payment operations
```
user_id:USER_ID operation:*
```

**Step 2**: Order by timestamp
Sort logs chronologically to see the full journey

**Step 3**: Check state transitions
Look for status changes in subscription operations

## Performance Considerations

### Log Sampling

- **Development**: All logs at DEBUG level
- **Production**: INFO and above
- **High-Traffic**: Consider sampling DEBUG logs

### Storage

- **Retention**: Keep payment logs for 90 days
- **Hot Storage**: Last 30 days for fast queries
- **Cold Storage**: 31-90 days for compliance

### Volume Estimates

- **API requests**: ~50-100 lines per request
- **Webhooks**: ~100-200 lines per event
- **Subscriptions**: ~20-50 lines per state change

## Testing

Comprehensive test suite in `tests/lib/test_payment_logging.py`:

```bash
# Run logging tests
pytest tests/lib/test_payment_logging.py -v

# Results: 21/21 tests passing
# - Correlation ID generation
# - Context binding
# - Timing metrics
# - Error handling
# - Integration flows
```

## Security

### Sensitive Data Handling

The logging system automatically redacts:
- API keys and secrets
- Payment card numbers (N/A - handled by LemonSqueezy)
- Authentication tokens
- Webhook signatures

### Sanitization

Use the built-in sanitization from `src/api/lib/logger.py`:

```python
from src.api.lib.logger import sanitize_dict

# Sanitize dict before logging
safe_data = sanitize_dict(request_data)
logger.debug("Request data", data=safe_data)
```

## Best Practices

### DO:
- ✅ Generate correlation IDs for all user-initiated operations
- ✅ Use timing context for operations >100ms
- ✅ Log state transitions (before/after)
- ✅ Include user_id and subscription_id when available
- ✅ Use appropriate log levels
- ✅ Clear context after operations

### DON'T:
- ❌ Log sensitive data (API keys, tokens, card numbers)
- ❌ Use ERROR level for expected failures
- ❌ Log at DEBUG level in production hot paths
- ❌ Create correlation IDs for system-initiated operations
- ❌ Forget to log operation completion

## Migration from Old Logging

### Before
```python
logger.info(f"Checkout created: {session_id}")
```

### After
```python
logger.info(
    "Checkout session created",
    operation="checkout",
    session_id=session_id,
    variant_id=variant_id,
    user_id=user_id,
    correlation_id=correlation_id
)
```

## Related Documentation

- **Sentry Monitoring**: `docs/monitoring/SENTRY_PAYMENT_MONITORING.md`
- **Webhook Processing**: `docs/webhooks/WEBHOOK_PROCESSING.md`
- **API Documentation**: `docs/api/PAYMENT_API.md`

## Support

For questions or issues:
1. Check this documentation
2. Review test examples in `tests/lib/test_payment_logging.py`
3. Check Sentry for error patterns
4. Review actual logs in production

## Changelog

**2025-10-20** - Phase 4, Task 4.2.2
- Initial implementation
- Added correlation ID support
- Added timing context manager
- Added context binding
- Comprehensive test suite (21 tests)
- Integration with existing Sentry monitoring
