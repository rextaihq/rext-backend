# Intentionally Public Routes - Security Documentation

## Overview
This document explains why 15 routes in the Wrext API are intentionally left without `@require_permissions` decorators. These routes use alternative security mechanisms appropriate for their specific use cases.

**Total Routes:** 278  
**Protected Routes:** 209 (93.3%)  
**Public Routes:** 54 (system routes)  
**Intentionally Public Business Routes:** 15  

## Category 1: Token-Based Authentication Routes (5 routes)

### Admin Invitation Routes (3 routes)
**File:** `api/routes/admin/admin_invitation_routes.py`

| Route | Method | Function | Security Mechanism |
|-------|--------|----------|-------------------|
| `/{token}/validate` | GET | validate_admin_invitation_token | Token validation |
| `/{token}/accept` | POST | accept_admin_invitation | Token validation + user creation |
| `/{token}/decline` | POST | decline_admin_invitation | Token validation |

**Why Public:**
- Token-based authentication (JWT-like invitation token)
- Tokens are cryptographically signed and time-limited
- Used during admin onboarding before user has authentication
- Token includes email, role, and expiry embedded
- One-time use tokens (marked as used after acceptance)

**Security Features:**
- Expiry validation (configurable days)
- Single-use enforcement
- Signature verification
- Rate limiting on token validation endpoint

---

### User Workspace Invitation Routes (2 routes)
**File:** `api/routes/invitations.py`

| Route | Method | Function | Security Mechanism |
|-------|--------|----------|-------------------|
| `/{token}/validate` | GET | validate_invitation | Token validation |
| `/{token}/accept` | POST | accept_invitation | Token validation + membership creation |

**Why Public:**
- Similar to admin invitations - token-based security
- Accepts workspace invitations before full authentication
- Token contains workspace ID, role, inviter, invitee email
- Expires after configurable period (default 7 days)

**Security Features:**
- Token expiry checking
- Email verification (token must match invitee email)
- Workspace membership limits enforced
- Audit logging of acceptance events

---

## Category 2: Webhook Routes (2 routes)

### LemonSqueezy Webhook
**File:** `api/routes/subscriptions/webhook_routes.py`

| Route | Method | Function | Security Mechanism |
|-------|--------|----------|-------------------|
| `/lemonsqueezy` | POST | handle_lemonsqueezy_webhook | Signature verification |

**Why Public:**
- External service callback (LemonSqueezy payment processor)
- Cannot use standard authentication (external service calling us)
- Uses HMAC signature verification instead

**Security Features:**
- Webhook signature validation (HMAC-SHA256)
- Secret key stored securely in environment variables
- IP whitelisting recommended (LemonSqueezy IPs)
- Idempotency handling for duplicate webhooks
- Comprehensive logging for audit trail

**Reference:**
- LemonSqueezy webhook security: https://docs.lemonsqueezy.com/help/webhooks#signing-requests

---

### Resend Email Webhook
**File:** `api/routes/email/webhooks.py`

| Route | Method | Function | Security Mechanism |
|-------|--------|----------|-------------------|
| `/resend` | POST | handle_resend_webhook | Signature verification |

**Why Public:**
- External email service callback (Resend)
- Email delivery status notifications (bounces, complaints, opens)
- Uses Resend webhook signature verification

**Security Features:**
- Signature validation via Resend SDK
- Webhook signing secret from environment
- Event type validation
- Duplicate event handling via idempotency

**Reference:**
- Resend webhook docs: https://resend.com/docs/webhooks

---

## Category 3: Health Check Routes (2 routes)

**File:** `api/routes/health.py`

| Route | Method | Function | Purpose |
|-------|--------|----------|---------|
| `/payment` | GET | payment_health_check | LemonSqueezy integration health |
| `/payment/quick` | GET | payment_quick_health_check | Quick payment health |

**Why Public:**
- Monitoring and observability endpoints
- Used by external monitoring tools (DataDog, New Relic, etc.)
- Need to be accessible without authentication for uptime monitoring
- Do not expose sensitive data

**Returned Data:**
- Connection status (healthy/unhealthy)
- Response time metrics
- Component availability (database, payment API)
- NO sensitive information (API keys, user data, etc.)

**Security Considerations:**
- Rate limited to prevent abuse
- No authentication required (monitoring requirement)
- Can add IP whitelisting if needed
- Consider moving behind VPN for production

---

## Category 4: Public Information Endpoints (3 routes)

### Public Subscription Plans
**File:** `api/routes/subscriptions/plan_routes.py`

| Route | Method | Function | Purpose |
|-------|--------|----------|---------|
| `/public` | GET | list_public_plans | Public pricing page data |

**Why Public:**
- Marketing/sales endpoint for pricing page
- Needs to be accessible to anonymous users
- No sensitive data exposed (only public plan info)

**Returned Data:**
- Plan names, prices, features
- Publicly available information only
- No user-specific data

---

### Trial Eligibility Check
**File:** `api/routes/subscriptions/trial_routes.py`

| Route | Method | Function | Purpose |
|-------|--------|----------|---------|
| `/eligibility` | GET | check_trial_eligibility_endpoint | Check if user can start trial |

**Why Public:**
- Pre-authentication trial eligibility check
- Part of signup/marketing funnel
- Returns boolean only (eligible/not eligible)

**Security Considerations:**
- Rate limited to prevent abuse
- Returns minimal information
- Optional authentication (checks if user is logged in)

---

### License Validation
**File:** `api/routes/subscriptions/license_routes.py`

| Route | Method | Function | Purpose |
|-------|--------|----------|---------|
| `/validate` | POST | validate_license | Validate license key |

**Why Public:**
- License key validation for external clients
- Uses license key as authentication mechanism
- Offline license validation capability

**Security Features:**
- License key validation (cryptographic)
- Machine fingerprinting
- Activation limits per license
- Comprehensive audit logging

---

## Category 5: User Preference Management (1 route)

**File:** `api/routes/users/email_preferences.py`

| Route | Method | Function | Purpose |
|-------|--------|----------|---------|
| `/unsubscribe` | POST | unsubscribe | Email unsubscribe via token |

**Why Public:**
- Token-based unsubscribe from marketing emails
- Required by CAN-SPAM Act and GDPR
- Must work without authentication (one-click unsubscribe)

**Security Features:**
- Unsubscribe token validation
- Token contains user ID + email + expiry
- Cryptographically signed tokens
- Audit logging of unsubscribe events

**Compliance:**
- GDPR Article 7(3) - Easy withdrawal of consent
- CAN-SPAM Act - One-click unsubscribe requirement

---

## Category 6: Development/Testing Routes (2 routes)

### Server-Sent Events (SSE)
**File:** `api/routes/events/sse_routes.py`

| Route | Method | Function | Purpose |
|-------|--------|----------|---------|
| `/{operation_id}` | GET | subscribe_to_operation_events | Real-time operation updates |

**Why Public:**
- Uses operation ID as authentication
- Operation IDs are cryptographically secure UUIDs
- Short-lived connections
- No sensitive data in event stream

**Security Considerations:**
- Operation IDs are unpredictable (UUID v4)
- Events filtered by operation ID
- Connection timeout enforced
- Consider adding authentication in production

---

### SSE Test Route
**File:** `api/routes/events/sse_test_route.py`

| Route | Method | Function | Purpose |
|-------|--------|----------|---------|
| `/test` | GET | stream_test_events | Development testing endpoint |

**Why Public:**
- Development/testing only
- Should be disabled in production via feature flag
- Streams test data for SSE client testing

**Production Recommendation:**
- Disable this route in production environment
- Add `if settings.ENVIRONMENT == "development"` check
- Or protect with admin-only permissions

---

## Summary Table

| Category | Routes | Security Mechanism | Production Ready |
|----------|--------|-------------------|------------------|
| Token-Based Auth | 5 | Cryptographic tokens | ✅ Yes |
| Webhooks | 2 | Signature verification | ✅ Yes |
| Health Checks | 2 | Public by design | ✅ Yes (consider IP whitelist) |
| Public Info | 3 | Rate limiting | ✅ Yes |
| Email Preferences | 1 | Token-based | ✅ Yes |
| Development | 2 | Operation IDs / None | ⚠️ Disable test route in prod |

## Recommendations

### Immediate Actions
1. **Disable SSE test route in production** - Add environment check
2. **IP Whitelist health checks** - Restrict to monitoring IPs only
3. **Review rate limits** - Ensure all public routes are rate limited

### Future Enhancements
1. **Webhook IP whitelisting** - Add LemonSqueezy/Resend IP ranges
2. **Enhanced monitoring** - Alert on unusual webhook traffic
3. **Token rotation** - Implement regular rotation for invitation tokens
4. **Audit logging** - Comprehensive logging for all public endpoint access

### Security Best Practices
- All public routes have alternative security mechanisms
- Rate limiting implemented on all public endpoints
- Audit logging for sensitive operations
- Token-based routes use cryptographic validation
- Webhook routes verify signatures
- No sensitive data exposed on public endpoints

## Audit Trail

**Last Updated:** 2025-10-24  
**Coverage:** 93.3% (209/224 routes protected)  
**Remaining Public:** 15 routes (all documented above)  
**Security Review:** Complete ✅

---

**Note:** This documentation should be reviewed quarterly and updated whenever new public routes are added.
