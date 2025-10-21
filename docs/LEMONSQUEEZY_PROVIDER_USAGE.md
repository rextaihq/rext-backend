# LemonSqueezy Provider Usage Guide

**Status:** ✅ Production Ready
**Version:** 1.0.0
**Last Updated:** 2025-10-17

## Overview

The LemonSqueezy provider implements the `PaymentProvider` interface for real payment processing through LemonSqueezy's API. This document provides complete usage instructions for developers.

## Table of Contents

- [Configuration](#configuration)
- [Basic Usage](#basic-usage)
- [API Methods](#api-methods)
- [Webhook Handling](#webhook-handling)
- [Error Handling](#error-handling)
- [Testing](#testing)
- [Best Practices](#best-practices)

---

## Configuration

### Environment Variables

Add these variables to your `.env` file:

```bash
# Required
LEMONSQUEEZY_API_KEY=your_api_key_here
LEMONSQUEEZY_STORE_ID=your_store_id_here

# Optional
LEMONSQUEEZY_WEBHOOK_SECRET=your_webhook_secret_here

# Provider selection (only lemonsqueezy supported)
PAYMENT_PROVIDER=lemonsqueezy
LEMONSQUEEZY_SANDBOX_MODE=true  # Use false for production
```

### Getting Your Credentials

1. **API Key**: Settings → API → Create New API Key
2. **Store ID**: Available in dashboard URL or API responses
3. **Webhook Secret**: Settings → Webhooks → Configure webhook → Secret

### Provider Factory

The provider is automatically instantiated via the factory:

```python
from src.providers.payment.provider_factory import get_payment_provider

# Get configured provider (uses .env settings)
provider = get_payment_provider()

# Or get singleton instance (recommended)
from src.providers.payment.provider_factory import get_payment_provider_singleton
provider = get_payment_provider_singleton()
```

### Manual Instantiation

For testing or custom use cases:

```python
from src.providers.payment.providers.lemonsqueezy import LemonSqueezyProvider

provider = LemonSqueezyProvider(
    api_key="your_api_key",
    store_id="12345",
    webhook_secret="your_secret",
    sandbox_mode=True  # Use test mode
)
```

---

## Basic Usage

### Creating a Checkout Session

```python
# Create checkout for a subscription
checkout = await provider.create_checkout_session(
    customer_id="cust_123",  # Can be temp ID from create_customer
    price_id="variant_456",   # LemonSqueezy variant ID
    success_url="https://yourapp.com/success",
    cancel_url="https://yourapp.com/cancel",
    metadata={"user_id": "789", "plan": "pro"}
)

# Use checkout URL with LemonSqueezy overlay
checkout_url = checkout.checkout_url
# Example: https://yourstore.lemonsqueezy.com/checkout/buy/abc123
```

### Managing Customers

```python
# Create customer reference (actual customer created at checkout)
customer_id = await provider.create_customer(
    email="user@example.com",
    name="John Doe",
    metadata={"user_id": "123"}
)
# Returns: "temp_user@example.com"

# Get customer details (after they've made a purchase)
customer = await provider.get_customer("cust_real_id_123")
print(f"Customer: {customer.name} ({customer.email})")
```

### Managing Subscriptions

```python
# Get subscription details
subscription = await provider.get_subscription("sub_123")
print(f"Status: {subscription.status}")
print(f"Renews: {subscription.current_period_end}")

# Update subscription to new plan
updated = await provider.update_subscription(
    subscription_id="sub_123",
    price_id="new_variant_789"
)

# Cancel subscription
cancelled = await provider.cancel_subscription(
    subscription_id="sub_123",
    at_period_end=True  # Cancel at end of billing period
)
```

### Customer Portal

```python
# Generate customer portal URL
portal_url = await provider.create_portal_session(
    customer_id="cust_123",
    return_url="https://yourapp.com/dashboard"
)

# Redirect user to portal_url
# They can manage subscription, update payment, view invoices
```

---

## API Methods

### Customer Management

#### `create_customer(email, name, metadata=None) -> str`

Creates a customer reference. Note: LemonSqueezy creates actual customers during checkout.

**Parameters:**
- `email` (str): Customer email
- `name` (str): Customer name
- `metadata` (dict, optional): Additional metadata

**Returns:** Temporary customer ID (format: `temp_{email}`)

**Example:**
```python
customer_id = await provider.create_customer(
    email="john@example.com",
    name="John Doe"
)
```

#### `get_customer(customer_id) -> CustomerData`

Retrieves customer details from LemonSqueezy.

**Parameters:**
- `customer_id` (str): LemonSqueezy customer ID

**Returns:** `CustomerData` object with id, email, name, metadata

**Example:**
```python
customer = await provider.get_customer("cust_123")
```

### Checkout

#### `create_checkout_session(...) -> CheckoutSession`

Creates a checkout session for subscription or one-time purchase.

**Parameters:**
- `customer_id` (str): Customer ID (can be temp ID)
- `price_id` (str): LemonSqueezy variant ID
- `success_url` (str): Redirect URL on success
- `cancel_url` (str): Redirect URL on cancellation
- `metadata` (dict, optional): Custom data to attach

**Returns:** `CheckoutSession` with session_id, checkout_url, customer_id, metadata

**Example:**
```python
session = await provider.create_checkout_session(
    customer_id="cust_123",
    price_id="variant_456",
    success_url="https://app.com/success",
    cancel_url="https://app.com/cancel"
)
```

### Subscription Management

#### `get_subscription(subscription_id) -> SubscriptionData`

Fetches subscription details.

**Parameters:**
- `subscription_id` (str): LemonSqueezy subscription ID

**Returns:** `SubscriptionData` object with full subscription details

**Status Mapping:**
- `on_trial` → `trialing`
- `active` → `active`
- `paused` → `paused`
- `past_due` → `past_due`
- `unpaid` → `past_due`
- `cancelled` → `cancelled`
- `expired` → `expired`

#### `cancel_subscription(subscription_id, at_period_end=True) -> SubscriptionData`

Cancels a subscription.

**Parameters:**
- `subscription_id` (str): Subscription ID
- `at_period_end` (bool): If True, cancel at period end; if False, immediate (future)

**Returns:** Updated `SubscriptionData`

#### `update_subscription(subscription_id, price_id) -> SubscriptionData`

Updates subscription to new plan/variant.

**Parameters:**
- `subscription_id` (str): Subscription ID
- `price_id` (str): New variant ID

**Returns:** Updated `SubscriptionData`

### Portal

#### `create_portal_session(customer_id, return_url) -> str`

Generates customer portal URL for subscription management.

**Parameters:**
- `customer_id` (str): Customer ID
- `return_url` (str): URL to return after portal session

**Returns:** Portal URL string

---

## Webhook Handling

### Signature Verification

**CRITICAL:** Always verify webhook signatures to prevent unauthorized requests.

```python
# In your webhook endpoint
@app.post("/webhooks/lemonsqueezy")
async def handle_webhook(request: Request):
    # Get raw body and signature
    payload = await request.body()
    signature = request.headers.get("X-Signature")

    # Verify signature (timing-safe comparison)
    is_valid = await provider.verify_webhook_signature(
        payload=payload,
        signature=signature
    )

    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse event
    event = await provider.parse_webhook_event(payload)

    # Handle event
    await handle_event(event)
```

### Event Structure

```python
{
    "event_type": "subscription_created",  # Event name
    "event_id": "webhook_123",             # Unique webhook ID
    "data": {                              # Event data
        "id": "sub_123",
        "type": "subscriptions",
        "attributes": {...}
    },
    "timestamp": datetime(...)              # Event timestamp
}
```

### Supported Events

- `subscription_created` - New subscription
- `subscription_updated` - Subscription changed
- `subscription_cancelled` - Subscription cancelled
- `subscription_expired` - Subscription expired
- `subscription_payment_success` - Payment succeeded
- `subscription_payment_failed` - Payment failed
- `subscription_payment_recovered` - Payment recovered after failure
- `order_created` - One-time purchase
- `order_refunded` - Order refunded
- `license_key_created` - License key created

---

## Error Handling

### Exception Types

```python
from src.providers.payment.providers.lemonsqueezy import (
    LemonSqueezyError,          # Base exception
    LemonSqueezyAPIError        # API request failed
)
```

### Handling Errors

```python
try:
    subscription = await provider.get_subscription("sub_123")
except LemonSqueezyAPIError as e:
    print(f"API Error: {e.status_code} - {e.message}")
    print(f"Details: {e.details}")
except LemonSqueezyError as e:
    print(f"Provider Error: {str(e)}")
```

### Common Error Codes

- `401` - Invalid API key or authentication failed
- `404` - Resource not found (subscription, customer, etc.)
- `422` - Validation error (invalid parameters)
- `429` - Rate limit exceeded (300 req/min)
- `500` - LemonSqueezy server error

---

## Testing

### Unit Tests

Comprehensive unit tests available at:
```
tests/unit/providers/payment/test_lemonsqueezy_provider.py
```

Run tests:
```bash
pytest tests/unit/providers/payment/test_lemonsqueezy_provider.py -v
```

### Manual Testing

Use sandbox mode for testing:

```python
provider = LemonSqueezyProvider(
    api_key="your_test_api_key",
    store_id="your_test_store",
    webhook_secret="test_secret",
    sandbox_mode=True
)
```

### Testing Webhooks

1. Use ngrok or similar tool to expose local endpoint
2. Configure webhook URL in LemonSqueezy dashboard
3. Test with real events or use LemonSqueezy webhook simulator

---

## Best Practices

### 1. Always Use Singleton Provider

```python
from src.providers.payment.provider_factory import get_payment_provider_singleton

provider = get_payment_provider_singleton()
```

This reuses the HTTP client connection pool and is more efficient.

### 2. Always Verify Webhook Signatures

```python
is_valid = await provider.verify_webhook_signature(payload, signature)
if not is_valid:
    raise HTTPException(401, "Invalid signature")
```

The provider uses timing-safe comparison to prevent timing attacks.

### 3. Handle Idempotency

Store webhook events in database to prevent duplicate processing:

```python
from src.api.models.subscription_models.webhooks import WebhookEvent

# Check if already processed
existing = await db.query(WebhookEvent).filter_by(event_id=event_id).first()
if existing and existing.processed:
    return {"status": "already_processed"}

# Process and mark as processed
await process_webhook(event)
await db.commit()
```

### 4. Close Provider Connections

When shutting down application:

```python
await provider.close()
```

### 5. Use Appropriate Logging

The provider uses structured logging. Configure log level:

```python
import logging
logging.getLogger("src.providers.payment.providers.lemonsqueezy").setLevel(logging.INFO)
```

### 6. Handle Rate Limits

LemonSqueezy allows 300 requests/minute. Implement retry logic with exponential backoff for rate limit errors (429).

### 7. Store LemonSqueezy IDs

Always store LemonSqueezy IDs in your database:
- `lemonsqueezy_customer_id`
- `lemonsqueezy_subscription_id`
- `lemonsqueezy_order_id`
- `lemonsqueezy_variant_id`

This enables reconciliation and debugging.

---

## Troubleshooting

### Issue: "Invalid API key"
**Solution:** Verify `LEMONSQUEEZY_API_KEY` in .env matches your LemonSqueezy dashboard API key.

### Issue: "Customer not found"
**Solution:** Remember that LemonSqueezy creates customers during checkout, not via API. Use temp IDs until first purchase.

### Issue: "Webhook signature invalid"
**Solution:**
1. Verify `LEMONSQUEEZY_WEBHOOK_SECRET` matches dashboard
2. Ensure you're passing raw request body (not parsed JSON)
3. Check signature header name is `X-Signature`

### Issue: "Rate limit exceeded"
**Solution:** Implement exponential backoff retry logic. LemonSqueezy allows 300 req/min.

---

## Additional Resources

- **LemonSqueezy API Docs:** https://docs.lemonsqueezy.com/api
- **Webhook Guide:** https://docs.lemonsqueezy.com/guides/developer-guide/webhooks
- **Checkout Overlay:** https://docs.lemonsqueezy.com/help/checkout/checkout-overlay
- **Provider Implementation:** `src/providers/payment/providers/lemonsqueezy.py`
- **Unit Tests:** `tests/unit/providers/payment/test_lemonsqueezy_provider.py`

---

## Support

For issues or questions:
1. Check this documentation
2. Review LemonSqueezy API documentation
3. Check provider implementation source code
4. Review unit tests for usage examples

---

**Document Version:** 1.0.0
**Last Updated:** 2025-10-17
**Status:** ✅ Production Ready
