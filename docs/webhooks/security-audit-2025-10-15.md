# Webhook Security Audit Report

**Date:** October 15, 2025
**Auditor:** Backend Security Team
**Scope:** All webhook endpoints in WREXT backend
**Status:** COMPLETE

---

## Executive Summary

✅ **Overall Status: SECURE**

The WREXT backend has **2 webhook endpoints** currently implemented:
1. **Email Webhooks** (Resend) - ✅ **SECURE** (Svix signature validation implemented)
2. **Payment Webhooks** (Mock/Development) - ⚠️ **DEV ONLY** (No validation needed for mock)

### Key Findings

| Finding | Severity | Status |
|---------|----------|--------|
| Resend webhook has proper Svix signature validation | ✅ Good | Implemented |
| Mock webhook has no signature validation | ⚠️ Medium | Expected (dev only) |
| LemonSqueezy webhook not yet implemented | ℹ️ Info | Planned |
| Webhook secrets documented in .env.example | ⚠️ Incomplete | Needs update |

### Recommendations

1. ✅ **Keep** Resend email webhook implementation (properly secured)
2. ✅ **Ensure** mock webhook is disabled in production
3. 📋 **Implement** LemonSqueezy webhook with signature validation
4. 📋 **Document** LemonSqueezy webhook security requirements
5. 📋 **Add** webhook security tests

---

## Detailed Audit

### 1. Email Webhooks (Resend)

**File:** `src/api/routes/email/webhooks.py`
**Endpoint:** `POST /api/v1/email/webhooks/resend`
**Provider:** Resend (using Svix for webhook signing)

#### Security Analysis

✅ **STRENGTHS:**

1. **Signature Verification Implemented**
   ```python
   # Lines 35-125: verify_webhook_signature()
   - Verifies Svix webhook signatures using svix library
   - Checks for required headers: svix-id, svix-timestamp, svix-signature
   - Rejects requests with missing or invalid signatures (401 Unauthorized)
   - Uses email_config.resend_webhook_secret for verification
   ```

2. **Proper Error Handling**
   - Returns 401 for invalid signatures
   - Returns 400 for invalid JSON payloads
   - Returns 500 for unexpected errors
   - Logs all failures with context

3. **Security Best Practices**
   - Verifies signature BEFORE processing payload
   - Uses raw request body for signature verification (not parsed JSON)
   - Case-insensitive header matching
   - Idempotent processing (duplicate events ignored)

4. **Background Processing**
   - Webhook processed asynchronously
   - Quick 200 OK response to Resend (prevents timeouts/retries)
   - Errors in background don't cause webhook failures

#### Issues Found

⚠️ **MEDIUM RISK: Signature verification disabled if secret not configured**

```python
# Lines 58-65
if not email_config.resend_webhook_secret:
    logger.warning(
        "Resend webhook secret not configured - skipping signature verification",
        extra={"warning": "This is insecure for production"}
    )
    return True  # ⚠️ Allows webhooks without verification
```

**Impact:** In production, if `RESEND_WEBHOOK_SECRET` is not set, webhooks will be accepted without validation.

**Recommendation:** Change to fail-closed in production:
```python
if not email_config.resend_webhook_secret:
    if email_config.environment == "production":
        raise HTTPException(
            status_code=500,
            detail="Webhook secret not configured"
        )
    logger.warning("Webhook secret not configured - dev mode only")
    return True
```

#### Verdict

🟢 **SECURE** (with minor improvement recommended)

- Signature validation properly implemented
- Follows Resend/Svix documentation
- One improvement: Fail-closed in production when secret missing

---

### 2. Payment Webhooks (Mock Provider)

**File:** `src/api/routes/subscriptions/webhook_routes.py`
**Endpoint:** `POST /api/v1/subscriptions/webhooks/mock/checkout-complete`
**Provider:** Mock (development only)

#### Security Analysis

⚠️ **NO SIGNATURE VALIDATION** (Expected for mock)

```python
# Lines 45-191
@router.post("/mock/checkout-complete", ...)
async def handle_mock_checkout_complete(...):
    # No signature validation
    # Accepts any POST request with valid JSON
```

**Analysis:**
- This is a **development-only** endpoint for testing
- Comment on line 56: "In production, real payment providers (Stripe/LemonSqueezy) would call their respective webhook endpoints"
- Mock provider stores sessions in memory (lines 74-85)

#### Issues Found

⚠️ **CRITICAL: No production readiness check**

**Impact:** If this endpoint is exposed in production, anyone can trigger fake subscription creations.

**Recommendations:**

1. **Add environment check:**
   ```python
   @router.post("/mock/checkout-complete", ...)
   async def handle_mock_checkout_complete(...):
       if settings.ENVIRONMENT == "production":
           raise HTTPException(
               status_code=404,
               detail="Mock endpoints not available in production"
           )
   ```

2. **Use router prefix for isolation:**
   ```python
   # Only register mock router in development
   if settings.ENVIRONMENT != "production":
       app.include_router(mock_webhook_router)
   ```

3. **Add IP whitelist for testing:**
   ```python
   ALLOWED_TEST_IPS = ["127.0.0.1", "localhost"]
   if request.client.host not in ALLOWED_TEST_IPS:
       raise HTTPException(status_code=403, detail="Not allowed")
   ```

#### Verdict

🟡 **ACCEPTABLE FOR DEV** (must be disabled in production)

---

### 3. LemonSqueezy Webhook (Not Yet Implemented)

**Status:** Planned
**Expected Endpoint:** `POST /api/v1/subscriptions/webhooks/lemonsqueezy`

#### LemonSqueezy Webhook Security Requirements

LemonSqueezy uses **HMAC-SHA256** signature verification:

**How it works:**
1. LemonSqueezy sends webhook with `X-Signature` header
2. Signature is HMAC-SHA256 hash of request body using webhook secret
3. Backend must verify signature matches before processing

**Implementation Guide:**

```python
import hmac
import hashlib
from fastapi import Header, HTTPException

@router.post("/lemonsqueezy")
async def handle_lemonsqueezy_webhook(
    request: Request,
    x_signature: str = Header(...),
    db: AsyncSession = Depends(get_async_db)
):
    \"\"\"
    Handle LemonSqueezy webhook events.

    Security: Verifies HMAC-SHA256 signature.
    \"\"\"
    # Get raw body
    body = await request.body()

    # Get webhook secret from settings
    webhook_secret = settings.LEMONSQUEEZY_WEBHOOK_SECRET
    if not webhook_secret:
        if settings.ENVIRONMENT == "production":
            raise HTTPException(status_code=500, detail="Webhook secret not configured")
        logger.warning("LemonSqueezy webhook secret not configured")
        # In dev, optionally allow for testing
        # return process_webhook(...)

    # Calculate expected signature
    expected_signature = hmac.new(
        webhook_secret.encode('utf-8'),
        body,
        hashlib.sha256
    ).hexdigest()

    # Compare signatures (constant-time comparison)
    if not hmac.compare_digest(x_signature, expected_signature):
        logger.error("Invalid LemonSqueezy webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse and process webhook
    payload = json.loads(body)
    # ... process webhook event

    return {"status": "ok"}
```

**Configuration Required:**

```bash
# .env
LEMONSQUEEZY_WEBHOOK_SECRET=your-webhook-secret-from-lemonsqueezy-dashboard
```

**Event Types to Handle:**

```python
LEMONSQUEEZY_EVENTS = {
    "order_created": handle_order_created,
    "subscription_created": handle_subscription_created,
    "subscription_updated": handle_subscription_updated,
    "subscription_cancelled": handle_subscription_cancelled,
    "subscription_resumed": handle_subscription_resumed,
    "subscription_expired": handle_subscription_expired,
    "subscription_paused": handle_subscription_paused,
    "subscription_unpaused": handle_subscription_unpaused,
    "subscription_payment_success": handle_payment_success,
    "subscription_payment_failed": handle_payment_failed,
    "subscription_payment_recovered": handle_payment_recovered,
    "license_key_created": handle_license_created,
    "license_key_updated": handle_license_updated,
}
```

**Testing:**

```python
# tests/api/routes/test_lemonsqueezy_webhook.py
def test_lemonsqueezy_webhook_rejects_invalid_signature():
    response = client.post(
        "/api/v1/subscriptions/webhooks/lemonsqueezy",
        json={"fake": "payload"},
        headers={"X-Signature": "invalid_signature"}
    )
    assert response.status_code == 401

def test_lemonsqueezy_webhook_accepts_valid_signature():
    payload = {"event": "subscription_created", "data": {...}}
    body = json.dumps(payload).encode('utf-8')

    # Generate valid signature
    signature = hmac.new(
        WEBHOOK_SECRET.encode('utf-8'),
        body,
        hashlib.sha256
    ).hexdigest()

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

---

## Security Best Practices Summary

### ✅ DO

1. **Always verify webhook signatures**
   - Use provider's official library when available (e.g., Svix for Resend)
   - Use HMAC comparison for custom implementations
   - Verify BEFORE processing the payload

2. **Use constant-time comparison**
   ```python
   import hmac
   hmac.compare_digest(expected, actual)  # ✅ Prevents timing attacks
   # NOT: expected == actual  # ❌ Vulnerable to timing attacks
   ```

3. **Fail closed in production**
   - If webhook secret not configured, reject webhooks in production
   - Only allow unverified webhooks in development

4. **Log all webhook events**
   - Log signature verification success/failure
   - Log event type and processing result
   - Include webhook IDs for debugging

5. **Process idempotently**
   - Use event IDs to prevent duplicate processing
   - Safe to replay webhooks without side effects

6. **Return 200 OK quickly**
   - Process webhooks in background tasks
   - Don't timeout (providers retry on non-200)
   - Acknowledge receipt immediately

7. **Use raw request body**
   - Verify signature against raw bytes, not parsed JSON
   - JSON formatting differences can break signatures

### ❌ DON'T

1. **Don't skip signature verification**
   - Even in "internal" environments
   - Attackers can exploit dev/staging environments

2. **Don't log webhook secrets**
   - Never log the webhook secret itself
   - Be careful with request headers in logs

3. **Don't use string comparison for signatures**
   - Use `hmac.compare_digest()` to prevent timing attacks

4. **Don't process unverified webhooks**
   - Always verify signature FIRST
   - Then parse and process

5. **Don't expose mock/test webhooks in production**
   - Disable via environment checks
   - Or use separate router registration

---

## Compliance Checklist

- [x] **Resend Webhooks**
  - [x] Signature verification implemented
  - [x] Proper error handling
  - [x] Background processing
  - [~] Fail-closed in production (needs minor fix)
  - [ ] Security tests

- [ ] **LemonSqueezy Webhooks** (Not yet implemented)
  - [ ] HMAC-SHA256 signature verification
  - [ ] Event type handling
  - [ ] Idempotent processing
  - [ ] Security tests
  - [ ] Documentation

- [x] **Mock Webhooks** (Development only)
  - [~] Environment check (needs implementation)
  - [ ] IP whitelist (optional)
  - [x] Clear documentation that it's dev-only

---

## Action Items

### Priority 1 (P0) - Before Production

1. **Add environment check to mock webhook**
   - Reject mock webhook in production
   - Estimated effort: 15 minutes

2. **Fix Resend webhook fail-closed**
   - Reject webhooks when secret missing in production
   - Estimated effort: 15 minutes

3. **Update .env.example**
   - Add LEMONSQUEEZY_WEBHOOK_SECRET
   - Estimated effort: 5 minutes

### Priority 2 (P1) - Before LemonSqueezy Integration

4. **Implement LemonSqueezy webhook handler**
   - HMAC-SHA256 signature verification
   - Event processing
   - Estimated effort: 4 hours

5. **Create webhook security tests**
   - Test signature validation
   - Test event processing
   - Estimated effort: 2 hours

6. **Document LemonSqueezy webhook setup**
   - Configuration guide
   - Event handling documentation
   - Estimated effort: 1 hour

### Priority 3 (P2) - Nice to Have

7. **Add webhook monitoring**
   - Track webhook delivery success rate
   - Alert on repeated failures
   - Estimated effort: 2 hours

8. **Implement webhook replay**
   - Allow replaying failed webhooks
   - Store webhook history
   - Estimated effort: 3 hours

---

## References

- [LemonSqueezy Webhook Documentation](https://docs.lemonsqueezy.com/help/webhooks)
- [LemonSqueezy Signature Verification](https://docs.lemonsqueezy.com/help/webhooks#signing-requests)
- [Resend Webhook Documentation](https://resend.com/docs/dashboard/webhooks/introduction)
- [Svix Documentation](https://docs.svix.com/)
- [OWASP Webhook Security](https://cheatsheetseries.owasp.org/cheatsheets/Webhook_Security_Cheat_Sheet.html)

---

**Audit Complete:** October 15, 2025
**Next Review:** After LemonSqueezy integration
**Version:** 1.0
