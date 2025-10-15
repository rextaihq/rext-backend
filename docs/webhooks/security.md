# Webhook Security Guide

**Last Updated:** October 15, 2025
**Status:** Active
**Applies To:** WREXT Backend v0.1.0+

---

## Overview

This document describes webhook security implementation for WREXT. Webhooks are external POST requests from third-party services (payment providers, email providers) that notify our backend of events.

**Security is critical** because webhooks can trigger:
- Subscription activations (monetary transactions)
- Email delivery tracking
- Payment processing
- Account modifications

Without proper security, attackers could:
- Activate subscriptions without payment
- Forge email delivery reports
- Trigger unauthorized actions
- Replay captured webhooks

---

## Security Principles

### 1. Signature Verification

**Every webhook MUST verify the signature before processing.**

```python
# ✅ CORRECT: Verify first, process second
signature_valid = verify_webhook_signature(request)
if not signature_valid:
    raise HTTPException(status_code=401, detail="Invalid signature")

# Now safe to process
payload = json.loads(request.body)
process_webhook(payload)
```

```python
# ❌ WRONG: Processing before verification
payload = json.loads(request.body)
process_webhook(payload)  # ❌ Attacker can forge this!

if not verify_webhook_signature(request):
    # Too late - already processed malicious webhook
    raise HTTPException(status_code=401)
```

### 2. Constant-Time Comparison

**Always use `hmac.compare_digest()` for signature comparison.**

```python
import hmac

# ✅ CORRECT: Constant-time comparison (prevents timing attacks)
if hmac.compare_digest(expected_signature, actual_signature):
    # Signature valid

# ❌ WRONG: Vulnerable to timing attacks
if expected_signature == actual_signature:
    # Attacker can measure response time to guess signature
```

**Why?** String comparison (`==`) compares character-by-character and returns early on mismatch. Attackers can measure response times to determine correct characters.

### 3. Fail-Closed in Production

**If webhook secret is missing, reject webhooks in production.**

```python
# ✅ CORRECT: Fail-closed
if not webhook_secret:
    if environment == "production":
        raise HTTPException(status_code=500, detail="Webhook secret not configured")
    logger.warning("Webhook secret missing - dev mode only")
    return  # Allow in dev

# ❌ WRONG: Fail-open (accepts unverified webhooks)
if not webhook_secret:
    logger.warning("No webhook secret - skipping verification")
    return  # ❌ Accepts forged webhooks!
```

### 4. Idempotent Processing

**Process webhooks idempotently to prevent duplicate actions.**

```python
# ✅ CORRECT: Check for duplicate event ID
event_id = payload.get("id")
if await db.exists(WebhookEvent, event_id=event_id):
    logger.info(f"Duplicate webhook event {event_id} - ignoring")
    return {"status": "ok", "message": "Duplicate event"}

# Process event
await process_event(payload)

# Store event ID
await db.insert(WebhookEvent(event_id=event_id, processed_at=now()))
```

### 5. Use Raw Request Body

**Verify signatures against raw bytes, not parsed JSON.**

```python
# ✅ CORRECT: Use raw body for signature
body = await request.body()  # bytes
verify_signature(body, signature_header)

# Then parse
payload = json.loads(body)

# ❌ WRONG: Parse first, then verify
payload = await request.json()  # Parsed
body = json.dumps(payload).encode()  # ❌ Formatting may differ!
verify_signature(body, signature_header)  # ❌ Signature mismatch!
```

**Why?** JSON formatting (whitespace, key ordering) can differ between parser and original. Signatures are computed on exact bytes.

---

## Provider-Specific Implementation

### Resend (Email Webhooks)

**Status:** ✅ Implemented
**Signature Method:** Svix (cryptographic signing service)
**Headers:** `svix-id`, `svix-timestamp`, `svix-signature`

#### Implementation

```python
from svix.webhooks import Webhook, WebhookVerificationError

def verify_resend_webhook(body: bytes, headers: dict) -> bool:
    \"\"\"Verify Resend webhook signature using Svix.\"\"\"
    # Get webhook secret from config
    webhook_secret = settings.RESEND_WEBHOOK_SECRET

    if not webhook_secret:
        if settings.ENVIRONMENT == "production":
            raise HTTPException(status_code=500, detail="Webhook secret not configured")
        return True  # Allow in dev

    # Extract Svix headers
    svix_id = headers.get("svix-id")
    svix_timestamp = headers.get("svix-timestamp")
    svix_signature = headers.get("svix-signature")

    if not all([svix_id, svix_timestamp, svix_signature]):
        raise HTTPException(status_code=401, detail="Missing Svix headers")

    # Verify signature
    try:
        wh = Webhook(webhook_secret)
        wh.verify(body, {
            "svix-id": svix_id,
            "svix-timestamp": svix_timestamp,
            "svix-signature": svix_signature
        })
        return True
    except WebhookVerificationError:
        raise HTTPException(status_code=401, detail="Invalid signature")
```

#### Configuration

```bash
# .env
RESEND_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxx
```

Get the secret from:
1. Resend Dashboard → Webhooks
2. Add endpoint: `https://yourdomain.com/api/v1/email/webhooks/resend`
3. Copy the signing secret

#### Testing

```bash
# Resend provides webhook testing in dashboard
# Or use Svix CLI to generate test signatures
```

---

### LemonSqueezy (Payment Webhooks)

**Status:** 📋 Planned (Not yet implemented)
**Signature Method:** HMAC-SHA256
**Header:** `X-Signature`

#### Implementation Guide

```python
import hmac
import hashlib
import json

def verify_lemonsqueezy_webhook(body: bytes, signature: str) -> bool:
    \"\"\"
    Verify LemonSqueezy webhook signature.

    LemonSqueezy sends:
    - X-Signature header with hex-encoded HMAC-SHA256
    - Signature is computed on raw request body

    Args:
        body: Raw request body (bytes)
        signature: X-Signature header value

    Returns:
        True if signature is valid

    Raises:
        HTTPException: If signature is invalid or secret not configured
    \"\"\"
    # Get webhook secret from config
    webhook_secret = settings.LEMONSQUEEZY_WEBHOOK_SECRET

    if not webhook_secret:
        if settings.ENVIRONMENT == "production":
            raise HTTPException(
                status_code=500,
                detail="LemonSqueezy webhook secret not configured"
            )
        logger.warning("LemonSqueezy webhook secret not configured - dev mode")
        return True  # Allow in dev (or reject for stricter security)

    # Calculate expected signature
    expected_signature = hmac.new(
        webhook_secret.encode('utf-8'),
        body,
        hashlib.sha256
    ).hexdigest()

    # Compare using constant-time comparison
    if not hmac.compare_digest(expected_signature, signature):
        logger.error("Invalid LemonSqueezy webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    return True


@router.post("/lemonsqueezy")
async def handle_lemonsqueezy_webhook(
    request: Request,
    x_signature: str = Header(..., alias="X-Signature"),
    db: AsyncSession = Depends(get_async_db)
):
    \"\"\"
    Handle LemonSqueezy webhook events.

    Events:
    - subscription_created: New subscription
    - subscription_updated: Subscription changed
    - subscription_cancelled: Subscription cancelled
    - subscription_payment_success: Payment succeeded
    - subscription_payment_failed: Payment failed
    - order_created: One-time purchase

    Security:
    - Verifies HMAC-SHA256 signature
    - Rejects invalid signatures with 401
    - Processes idempotently using event ID
    \"\"\"
    # Get raw body for signature verification
    body = await request.body()

    # Verify signature
    verify_lemonsqueezy_webhook(body, x_signature)

    # Parse payload (safe after verification)
    payload = json.loads(body)

    # Extract event info
    event_name = payload.get("meta", {}).get("event_name")
    event_id = payload.get("meta", {}).get("webhook_id")

    logger.info(f"Processing LemonSqueezy webhook: {event_name} ({event_id})")

    # Check for duplicate (idempotency)
    if await db.exists(WebhookEvent, event_id=event_id):
        logger.info(f"Duplicate webhook {event_id} - ignoring")
        return {"status": "ok", "message": "Duplicate event"}

    # Process based on event type
    if event_name == "subscription_created":
        await handle_subscription_created(payload, db)
    elif event_name == "subscription_updated":
        await handle_subscription_updated(payload, db)
    elif event_name == "subscription_cancelled":
        await handle_subscription_cancelled(payload, db)
    elif event_name == "subscription_payment_success":
        await handle_payment_success(payload, db)
    elif event_name == "subscription_payment_failed":
        await handle_payment_failed(payload, db)
    else:
        logger.warning(f"Unknown LemonSqueezy event: {event_name}")

    # Store event as processed
    await db.insert(WebhookEvent(
        event_id=event_id,
        provider="lemonsqueezy",
        event_type=event_name,
        payload=payload,
        processed_at=datetime.utcnow()
    ))

    return {"status": "ok"}
```

#### Configuration

```bash
# .env
LEMONSQUEEZY_WEBHOOK_SECRET=your_webhook_secret_from_lemonsqueezy_dashboard
```

Get the secret from:
1. LemonSqueezy Dashboard → Settings → Webhooks
2. Add endpoint: `https://yourdomain.com/api/v1/subscriptions/webhooks/lemonsqueezy`
3. Select events to listen for
4. Copy the signing secret

#### Testing LemonSqueezy Webhooks

```python
# tests/api/routes/test_lemonsqueezy_webhook.py
import hmac
import hashlib
import json

def test_lemonsqueezy_webhook_valid_signature():
    \"\"\"Test LemonSqueezy webhook with valid HMAC signature.\"\"\"
    payload = {
        "meta": {
            "event_name": "subscription_created",
            "webhook_id": "test_123"
        },
        "data": {
            "type": "subscriptions",
            "id": "sub_456",
            "attributes": {"status": "active"}
        }
    }

    body = json.dumps(payload).encode('utf-8')
    secret = "test_webhook_secret"

    # Generate valid signature
    signature = hmac.new(
        secret.encode('utf-8'),
        body,
        hashlib.sha256
    ).hexdigest()

    # Send webhook
    response = client.post(
        "/api/v1/subscriptions/webhooks/lemonsqueezy",
        data=body,
        headers={
            "X-Signature": signature,
            "Content-Type": "application/json"
        }
    )

    assert response.status_code == 200
```

#### LemonSqueezy Event Types

```python
LEMONSQUEEZY_EVENTS = {
    # Subscriptions
    "subscription_created": "New subscription created",
    "subscription_updated": "Subscription details changed (plan, billing, etc.)",
    "subscription_cancelled": "Subscription cancelled by customer",
    "subscription_resumed": "Cancelled subscription reactivated",
    "subscription_expired": "Subscription expired (not renewed)",
    "subscription_paused": "Subscription temporarily paused",
    "subscription_unpaused": "Paused subscription resumed",

    # Payments
    "subscription_payment_success": "Recurring payment succeeded",
    "subscription_payment_failed": "Recurring payment failed",
    "subscription_payment_recovered": "Failed payment recovered",

    # One-time purchases
    "order_created": "One-time purchase completed",

    # Licenses
    "license_key_created": "License key generated",
    "license_key_updated": "License key modified",
}
```

---

## Development vs Production

### Development Mode

In development, you may want to:
- Skip signature verification for local testing
- Log webhook payloads for debugging
- Use mock webhook endpoints

```python
if settings.ENVIRONMENT == "development":
    if not webhook_secret:
        logger.warning("Webhook secret not configured - allowing for local testing")
        return True  # Skip verification
```

### Production Mode

In production, you MUST:
- ✅ Require webhook secrets
- ✅ Reject webhooks with invalid signatures
- ✅ Never skip verification
- ✅ Use HTTPS endpoints only
- ✅ Log security events (invalid signatures)

```python
if settings.ENVIRONMENT == "production":
    if not webhook_secret:
        # Fail immediately - don't process
        raise HTTPException(
            status_code=500,
            detail="Webhook secret not configured"
        )
```

---

## Monitoring & Alerting

### Metrics to Track

1. **Webhook delivery rate**
   - Success rate (200 OK responses)
   - Failure rate (4xx, 5xx responses)
   - Average processing time

2. **Security events**
   - Invalid signature attempts
   - Missing signature headers
   - Unknown event types

3. **Duplicate events**
   - How often duplicates are received
   - Time between duplicates

### Alerts

Set up alerts for:
- **High failure rate** (> 5% failures)
- **Signature verification failures** (potential attack)
- **Webhook secret not configured** (in production)
- **Processing time > 5 seconds** (provider may timeout and retry)

---

## Troubleshooting

### Webhook Returns 401 (Invalid Signature)

**Possible causes:**
1. Wrong webhook secret in `.env`
2. Signature header name mismatch (check case-sensitivity)
3. Request body modified (parse before verification)
4. Wrong signature algorithm

**Debug steps:**
```python
logger.debug(f"Expected signature: {expected_signature}")
logger.debug(f"Received signature: {actual_signature}")
logger.debug(f"Request body (hex): {body.hex()}")
```

### Webhook Times Out

**Possible causes:**
1. Processing takes too long (> 30 seconds)
2. Database query slow
3. External API call blocking

**Solution:** Process in background
```python
background_tasks.add_task(process_webhook, payload)
return {"status": "ok"}  # Return immediately
```

### Duplicate Webhooks

**Cause:** Providers retry on timeout or non-200 response

**Solution:** Idempotent processing
```python
if await webhook_event_exists(event_id):
    return {"status": "ok"}  # Already processed
```

---

## Security Checklist

Before deploying to production:

- [ ] Webhook secrets configured in `.env`
- [ ] Signature verification implemented
- [ ] Fail-closed when secret missing (production)
- [ ] Using `hmac.compare_digest()` for signature comparison
- [ ] Verifying signature BEFORE processing payload
- [ ] Using raw request body for verification
- [ ] Processing webhooks idempotently
- [ ] Returning 200 OK quickly (background processing)
- [ ] Logging security events (invalid signatures)
- [ ] HTTPS endpoint URLs only
- [ ] Mock webhooks disabled in production
- [ ] Tests written for signature validation
- [ ] Monitoring and alerts configured

---

## References

- [LemonSqueezy Webhook Docs](https://docs.lemonsqueezy.com/help/webhooks)
- [Resend Webhook Docs](https://resend.com/docs/dashboard/webhooks/introduction)
- [Svix Documentation](https://docs.svix.com/)
- [OWASP Webhook Security](https://cheatsheetseries.owasp.org/cheatsheets/Webhook_Security_Cheat_Sheet.html)
- [HMAC Security](https://en.wikipedia.org/wiki/HMAC)

---

**Document Version:** 1.0
**Next Review:** After LemonSqueezy integration
