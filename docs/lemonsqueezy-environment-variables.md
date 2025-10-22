# LemonSqueezy Integration - Environment Variables Checklist

**Created:** 2025-10-17
**Phase:** Phase 0 - Discovery & Analysis
**Task:** 0.3.2 - Environment Variables Planning
**Status:** ✅ Complete

---

## Executive Summary

This document provides a comprehensive checklist of all environment variables required for the LemonSqueezy payment integration. It covers backend, frontend, testing, and production configurations with security guidelines and migration instructions.

### Quick Stats

| Category | New Variables | Modified Variables | Total |
|----------|--------------|-------------------|--------|
| **Backend** | 3 | 0 | 3 |
| **Frontend** | 1 | 0 | 1 |
| **Testing** | 3 | 0 | 3 |
| **TOTAL** | **7** | **0** | **7** |

---

## Table of Contents

1. [Backend Variables (wrext-backend)](#backend-variables-wrext-backend)
2. [Frontend Variables (wrext-admin)](#frontend-variables-wrext-admin)
3. [Testing & Development Variables](#testing--development-variables)
4. [Environment-Specific Configuration](#environment-specific-configuration)
5. [Security Guidelines](#security-guidelines)
6. [Validation Requirements](#validation-requirements)
7. [Migration Guide](#migration-guide)
8. [Troubleshooting](#troubleshooting)

---

## Backend Variables (wrext-backend)

### LemonSqueezy API Configuration

#### 1. LEMONSQUEEZY_API_KEY

**Purpose:** API key for authenticating with LemonSqueezy API

**Required:** Yes (Production), Optional (Development with mock provider)

**Security:** 🔴 **SECRET** - Never commit to version control

**Format:** String (typically starts with `eyJ0...`)

**Example:**
```bash
LEMONSQUEEZY_API_KEY=eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...
```

**How to Obtain:**
1. Log into [LemonSqueezy Dashboard](https://app.lemonsqueezy.com/)
2. Navigate to **Settings** → **API**
3. Click **Create API Key**
4. Name it (e.g., "WREXT Production API Key")
5. Copy the generated key immediately (only shown once)

**Validation:**
- Must not be empty when using LemonSqueezy provider
- Must be a valid JWT format
- Test with API call before deployment

**Used By:**
- `src/providers/payment/lemonsqueezy_provider.py`
- All LemonSqueezy API operations

---

#### 2. LEMONSQUEEZY_STORE_ID

**Purpose:** Unique identifier for your LemonSqueezy store

**Required:** Yes (Production), Optional (Development with mock provider)

**Security:** 🟡 **INTERNAL** - Not secret but not public

**Format:** Numeric string

**Example:**
```bash
LEMONSQUEEZY_STORE_ID=12345
```

**How to Obtain:**
1. Log into [LemonSqueezy Dashboard](https://app.lemonsqueezy.com/)
2. Navigate to **Settings** → **General**
3. Find **Store ID** in the store information section
4. Copy the numeric ID

**Validation:**
- Must be numeric
- Must not be empty when using LemonSqueezy provider
- Must match the store associated with your API key

**Used By:**
- `src/providers/payment/lemonsqueezy_provider.py`
- Subscription plan creation
- Product/variant validation

---

#### 3. LEMONSQUEEZY_WEBHOOK_SECRET

**Purpose:** Secret key for verifying webhook signatures from LemonSqueezy

**Required:** Yes (Production), Optional (Development)

**Security:** 🔴 **SECRET** - Critical for webhook security

**Format:** String (typically starts with `whsec_`)

**Example:**
```bash
LEMONSQUEEZY_WEBHOOK_SECRET=whsec_1234567890abcdef1234567890abcdef
```

**How to Obtain:**
1. Log into [LemonSqueezy Dashboard](https://app.lemonsqueezy.com/)
2. Navigate to **Settings** → **Webhooks**
3. Click **Add Webhook Endpoint**
4. Set URL: `https://yourdomain.com/api/v1/subscriptions/webhooks/lemonsqueezy`
5. Select events:
   - `subscription_created`
   - `subscription_updated`
   - `subscription_cancelled`
   - `subscription_resumed`
   - `subscription_expired`
   - `subscription_paused`
   - `subscription_unpaused`
   - `subscription_payment_success`
   - `subscription_payment_failed`
   - `subscription_payment_recovered`
   - `order_created`
   - `license_key_created`
6. Save and copy the **Signing Secret**

**Validation:**
- Must not be empty when using LemonSqueezy webhooks
- Must be validated on every webhook request (timing-safe comparison)
- Invalid signature → reject webhook

**Used By:**
- `src/routes/lemonsqueezy_webhook_routes.py`
- `src/services/lemonsqueezy_webhook_service.py`
- Webhook signature verification

---

### Payment Provider Configuration

#### 4. PAYMENT_PROVIDER (Optional - Future Enhancement)

**Purpose:** Select which payment provider to use

**Required:** No (defaults to LemonSqueezy in production, mock in development)

**Security:** 🟢 **PUBLIC** - Safe to commit

**Format:** String enum

**Options:**
- `mock` - Mock provider for development/testing
- `lemonsqueezy` - LemonSqueezy production provider
- `stripe` - Stripe (future support)
- `paddle` - Paddle (future support)

**Example:**
```bash
# Development
PAYMENT_PROVIDER=mock

# Production
PAYMENT_PROVIDER=lemonsqueezy
```

**Validation:**
- Must be one of the supported providers
- If not set, defaults based on ENVIRONMENT variable
- When set to `lemonsqueezy`, requires API_KEY and STORE_ID

**Used By:**
- `src/providers/payment/factory.py` (if implementing factory pattern)
- Service initialization

**Current Status:** Not implemented yet (hardcoded provider selection)

**Future Enhancement:** Implement provider factory for easy switching

---

### Complete Backend .env.example Updates

**Add to `wrext-backend/.env.example`:**

```bash
# ----------------------------------------------------------------------------
# Payment Provider - LemonSqueezy
# ----------------------------------------------------------------------------
# LemonSqueezy API Configuration
# Get keys from: https://app.lemonsqueezy.com/settings/api
#
# REQUIRED for production when using LemonSqueezy provider
# OPTIONAL for development (can use mock provider)
#
# Steps to set up:
# 1. Create/login to LemonSqueezy account: https://app.lemonsqueezy.com
# 2. Go to Settings → API → Create API Key
# 3. Copy API key and store ID
# 4. Set up webhook endpoint (see below)
# 5. Test with sandbox mode first (use test API key)
#
LEMONSQUEEZY_API_KEY=your_lemonsqueezy_api_key_here
LEMONSQUEEZY_STORE_ID=your_store_id_here

# LemonSqueezy Webhook Configuration
# CRITICAL: Required for production to verify webhook signatures
# SECURITY: Prevents unauthorized webhook requests to your server
#
# Setup Instructions:
# 1. Go to Settings → Webhooks in LemonSqueezy Dashboard
# 2. Add endpoint: https://yourdomain.com/api/v1/subscriptions/webhooks/lemonsqueezy
# 3. Select all subscription_* events + order_created + license_key_created
# 4. Copy the Signing Secret
# 5. Paste below
#
# For local development:
# - Use ngrok or similar to expose localhost
# - Example: ngrok http 8000
# - Set webhook URL to: https://your-ngrok-url.ngrok.io/api/v1/subscriptions/webhooks/lemonsqueezy
#
LEMONSQUEEZY_WEBHOOK_SECRET=your_lemonsqueezy_webhook_signing_secret_here

# LemonSqueezy Environment (Sandbox vs Production)
# - Use sandbox/test mode during development
# - Switch to production mode only after thorough testing
# - Sandbox transactions don't charge real money
#
# LEMONSQUEEZY_SANDBOX_MODE=true  # Development
# LEMONSQUEEZY_SANDBOX_MODE=false # Production
```

**Note:** The existing payment provider section (lines 148-178) already has placeholders for LemonSqueezy, so only uncomment and update the documentation.

---

## Frontend Variables (wrext-admin)

### Public API Configuration

#### 5. NEXT_PUBLIC_BACKEND_API_URL

**Purpose:** Backend API URL accessible from the browser

**Required:** Yes

**Security:** 🟢 **PUBLIC** - Exposed to client-side code

**Format:** URL string

**Example:**
```bash
# Development
NEXT_PUBLIC_BACKEND_API_URL=http://127.0.0.1:2024

# Production
NEXT_PUBLIC_BACKEND_API_URL=https://api.wrext.com
```

**Validation:**
- Must be a valid URL
- Must be accessible from the user's browser
- Must include protocol (http:// or https://)
- Production must use HTTPS

**Used By:**
- `lib/api-client/core.ts` - API client base URL
- `lib/api-client/subscriptions.ts` - Subscription endpoints
- All frontend API requests

**Current Status:** Already configured in `.env.example` as `NEXT_PUBLIC_API_BASE_URL`

**Note:** The variable is already present. No new variables needed for frontend.

---

### Complete Frontend .env.example Updates

**No changes needed to `.env.example`** - Already has `NEXT_PUBLIC_API_BASE_URL`

**Verify in `.env.local.example`:**

```bash
# Backend API URL (adjust for your environment)
BACKEND_API_URL=http://127.0.0.1:2024

# API Base URL for client-side requests (accessible in browser)
# This MUST have NEXT_PUBLIC_ prefix to be accessible in client-side code
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:2024
```

**No changes required** - Frontend is already configured correctly.

---

## Testing & Development Variables

### Sandbox/Test Mode Configuration

#### 6. LEMONSQUEEZY_SANDBOX_MODE

**Purpose:** Toggle between sandbox (test) and production modes

**Required:** No (defaults to true in development, false in production)

**Security:** 🟢 **PUBLIC** - Safe to commit

**Format:** Boolean string

**Example:**
```bash
# Development - Use sandbox mode (no real charges)
LEMONSQUEEZY_SANDBOX_MODE=true

# Production - Use live mode (real charges)
LEMONSQUEEZY_SANDBOX_MODE=false
```

**Validation:**
- Must be `true` or `false`
- Should be `true` for all non-production environments
- Should default to `true` if not set in development

**Used By:**
- `src/providers/payment/lemonsqueezy_provider.py`
- API endpoint selection (sandbox vs production API)

**Current Status:** Not implemented yet

**Future Enhancement:** Add sandbox mode support to provider

---

#### 7. LEMONSQUEEZY_TEST_API_KEY

**Purpose:** Separate API key for sandbox/test environment

**Required:** No (can use same key for sandbox and production)

**Security:** 🟡 **INTERNAL** - Less sensitive than production key

**Format:** String (JWT format)

**Example:**
```bash
LEMONSQUEEZY_TEST_API_KEY=eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...
```

**How to Obtain:**
1. Create separate LemonSqueezy store for testing (recommended)
2. Generate API key for test store
3. Use test API key during development

**Validation:**
- Same validation as `LEMONSQUEEZY_API_KEY`
- Used when `LEMONSQUEEZY_SANDBOX_MODE=true`

**Used By:**
- `src/providers/payment/lemonsqueezy_provider.py` (when in sandbox mode)

**Current Status:** Not implemented yet

**Future Enhancement:** Support separate test/production keys

---

#### 8. LEMONSQUEEZY_TEST_WEBHOOK_SECRET

**Purpose:** Webhook secret for sandbox/test environment

**Required:** No (can use same secret for sandbox and production)

**Security:** 🟡 **INTERNAL** - Less sensitive than production secret

**Format:** String (starts with `whsec_`)

**Example:**
```bash
LEMONSQUEEZY_TEST_WEBHOOK_SECRET=whsec_test1234567890abcdef1234567890
```

**How to Obtain:**
1. Set up webhook endpoint for test store
2. Use ngrok or similar for local testing
3. Copy signing secret

**Validation:**
- Same validation as `LEMONSQUEEZY_WEBHOOK_SECRET`
- Used when `LEMONSQUEEZY_SANDBOX_MODE=true`

**Used By:**
- `src/routes/lemonsqueezy_webhook_routes.py` (when in sandbox mode)

**Current Status:** Not implemented yet

**Future Enhancement:** Support separate test/production webhook secrets

---

## Environment-Specific Configuration

### Development Environment

**File:** `.env` (local development)

**Required Variables:**
```bash
# Core Configuration
NODE_ENV=development
ENVIRONMENT=development

# Database (local PostgreSQL)
POSTGRES_URI_CUSTOM=postgresql://user:pass@localhost:5432/wrext_dev

# Backend API
HOST=0.0.0.0
PORT=8000

# LemonSqueezy (Sandbox Mode - RECOMMENDED)
LEMONSQUEEZY_SANDBOX_MODE=true
LEMONSQUEEZY_API_KEY=your_test_api_key_here
LEMONSQUEEZY_STORE_ID=your_test_store_id_here
LEMONSQUEEZY_WEBHOOK_SECRET=your_test_webhook_secret_here

# OR use mock provider (no LemonSqueezy keys needed)
# PAYMENT_PROVIDER=mock
```

**Frontend (.env.local):**
```bash
NODE_ENV=development
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:2024
```

**Notes:**
- Use sandbox mode to avoid real charges
- Can use mock provider if LemonSqueezy not available
- Webhook testing requires ngrok or similar

---

### Staging Environment

**Deployment Platform:** (e.g., Railway, Render, Fly.io)

**Required Variables:**
```bash
# Core Configuration
NODE_ENV=staging
ENVIRONMENT=staging

# Database (hosted PostgreSQL)
POSTGRES_URI_CUSTOM=postgresql://user:pass@staging-db-host:5432/wrext_staging

# LemonSqueezy (Sandbox Mode - RECOMMENDED)
LEMONSQUEEZY_SANDBOX_MODE=true
LEMONSQUEEZY_API_KEY=your_test_api_key_here
LEMONSQUEEZY_STORE_ID=your_test_store_id_here
LEMONSQUEEZY_WEBHOOK_SECRET=your_test_webhook_secret_here

# Webhook URL should point to staging domain
# Example: https://staging.wrext.com/api/v1/subscriptions/webhooks/lemonsqueezy
```

**Frontend:**
```bash
NODE_ENV=production  # Next.js build optimization
NEXT_PUBLIC_API_BASE_URL=https://api-staging.wrext.com
```

**Notes:**
- Use staging database (separate from production)
- Use sandbox mode for testing
- All features should be tested here before production

---

### Production Environment

**Deployment Platform:** (e.g., Railway, Render, Fly.io, AWS)

**Required Variables:**
```bash
# Core Configuration
NODE_ENV=production
ENVIRONMENT=production

# Database (production PostgreSQL)
POSTGRES_URI_CUSTOM=postgresql://user:pass@prod-db-host:5432/wrext_prod

# LemonSqueezy (LIVE MODE - REAL CHARGES)
LEMONSQUEEZY_SANDBOX_MODE=false
LEMONSQUEEZY_API_KEY=your_production_api_key_here
LEMONSQUEEZY_STORE_ID=your_production_store_id_here
LEMONSQUEEZY_WEBHOOK_SECRET=your_production_webhook_secret_here

# Security (CRITICAL)
SECRET_KEY=your_64_char_production_secret_key
REFRESH_SECRET_KEY=your_64_char_production_refresh_key

# Monitoring
SENTRY_DSN=your_sentry_dsn_here
SENTRY_ENVIRONMENT=production
```

**Frontend:**
```bash
NODE_ENV=production
NEXT_PUBLIC_API_BASE_URL=https://api.wrext.com
```

**CRITICAL SECURITY CHECKLIST:**
- ✅ Use separate production API key (not test key)
- ✅ Set `LEMONSQUEEZY_SANDBOX_MODE=false`
- ✅ Verify webhook URL points to production domain
- ✅ Use HTTPS for all URLs
- ✅ Rotate secrets regularly
- ✅ Enable Sentry monitoring
- ✅ Set up database backups
- ✅ Test webhooks thoroughly before launch

---

## Security Guidelines

### Secret Management

#### 1. Never Commit Secrets

**❌ NEVER:**
- Commit `.env` files with real keys
- Commit `.env.local` files
- Hardcode secrets in source code
- Share secrets in Slack/email
- Store secrets in browser local storage

**✅ ALWAYS:**
- Use `.env.example` with placeholder values
- Store real secrets in `.env.local` (gitignored)
- Use environment variable injection on deployment platforms
- Rotate secrets regularly
- Use secret management services (AWS Secrets Manager, etc.)

---

#### 2. Variable Naming Conventions

**Frontend (Next.js):**

| Prefix | Visibility | Use For | Example |
|--------|-----------|---------|---------|
| `NEXT_PUBLIC_*` | 🌐 Public (browser) | API URLs, feature flags | `NEXT_PUBLIC_API_BASE_URL` |
| No prefix | 🔒 Server-only | API keys, secrets | `LEMONSQUEEZY_API_KEY` |

**Backend (FastAPI):**

| Type | Security | Use For | Example |
|------|----------|---------|---------|
| Secrets | 🔴 SECRET | API keys, webhook secrets | `LEMONSQUEEZY_API_KEY` |
| Internal | 🟡 INTERNAL | Store IDs, configuration | `LEMONSQUEEZY_STORE_ID` |
| Public | 🟢 PUBLIC | Feature flags, URLs | `LEMONSQUEEZY_SANDBOX_MODE` |

---

#### 3. Webhook Security

**Critical Requirements:**

1. **Signature Verification:**
   ```python
   # MUST verify every webhook request
   signature = request.headers.get("X-Signature")
   is_valid = verify_webhook_signature(
       payload=request.body,
       signature=signature,
       secret=LEMONSQUEEZY_WEBHOOK_SECRET
   )
   if not is_valid:
       raise HTTPException(status_code=401, detail="Invalid signature")
   ```

2. **Timing-Safe Comparison:**
   ```python
   import hmac
   # Use hmac.compare_digest (prevents timing attacks)
   is_valid = hmac.compare_digest(calculated_signature, provided_signature)
   ```

3. **HTTPS Only (Production):**
   - LemonSqueezy requires HTTPS for webhooks
   - Development: Use ngrok or similar
   - Production: Ensure SSL certificate is valid

4. **Rate Limiting:**
   ```python
   # Protect webhook endpoint from abuse
   @router.post("/webhooks/lemonsqueezy")
   @limiter.limit("100/minute")  # Adjust based on traffic
   async def handle_webhook(request: Request):
       ...
   ```

---

#### 4. Key Rotation Strategy

**Recommended Schedule:**

| Secret | Rotation Frequency | Priority |
|--------|-------------------|----------|
| `SECRET_KEY` | Every 90 days | HIGH |
| `REFRESH_SECRET_KEY` | Every 90 days | HIGH |
| `LEMONSQUEEZY_API_KEY` | Yearly or on breach | MEDIUM |
| `LEMONSQUEEZY_WEBHOOK_SECRET` | Yearly or on breach | HIGH |

**Rotation Process:**

1. **Pre-Rotation:**
   - Schedule maintenance window
   - Notify users if downtime expected
   - Backup database

2. **Rotation Steps:**
   - Generate new secret
   - Update environment variables
   - Deploy new version
   - Verify functionality
   - Revoke old secret

3. **Post-Rotation:**
   - Monitor error logs
   - Test critical flows
   - Update documentation

---

## Validation Requirements

### Startup Validation

**Backend should validate on startup:**

```python
# src/config.py or src/main.py
def validate_environment():
    """Validate required environment variables on startup"""

    required_vars = {
        "SECRET_KEY": {"min_length": 32},
        "REFRESH_SECRET_KEY": {"min_length": 32},
        "POSTGRES_URI_CUSTOM": {"required": True},
    }

    # LemonSqueezy variables (if not using mock provider)
    if not is_mock_provider():
        required_vars.update({
            "LEMONSQUEEZY_API_KEY": {"required": True},
            "LEMONSQUEEZY_STORE_ID": {"required": True},
        })

    # Webhook secret (production only)
    if ENVIRONMENT == "production":
        required_vars["LEMONSQUEEZY_WEBHOOK_SECRET"] = {"required": True}

    errors = []
    for var_name, rules in required_vars.items():
        value = os.getenv(var_name)

        if rules.get("required") and not value:
            errors.append(f"{var_name} is required but not set")

        if rules.get("min_length") and len(value or "") < rules["min_length"]:
            errors.append(f"{var_name} must be at least {rules['min_length']} characters")

    if errors:
        raise RuntimeError(f"Environment validation failed:\n" + "\n".join(errors))

# Call on startup
validate_environment()
```

---

### Runtime Validation

**Validate before API calls:**

```python
# src/providers/payment/lemonsqueezy_provider.py
class LemonSqueezyProvider:
    def __init__(self):
        self.api_key = os.getenv("LEMONSQUEEZY_API_KEY")
        self.store_id = os.getenv("LEMONSQUEEZY_STORE_ID")

        if not self.api_key:
            raise ValueError("LEMONSQUEEZY_API_KEY is required")

        if not self.store_id:
            raise ValueError("LEMONSQUEEZY_STORE_ID is required")

        # Test API connection on initialization
        self._validate_api_connection()

    def _validate_api_connection(self):
        """Test API connection and credentials"""
        try:
            # Make test API call
            response = requests.get(
                f"{LEMONSQUEEZY_API_URL}/v1/stores/{self.store_id}",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise ValueError("Invalid LEMONSQUEEZY_API_KEY")
            elif e.response.status_code == 404:
                raise ValueError("Invalid LEMONSQUEEZY_STORE_ID")
            raise
```

---

## Migration Guide

### Step 1: Current State (Mock Provider)

**Current Configuration:**
```bash
# wrext-backend/.env
# No LemonSqueezy variables needed
# Mock provider is used by default
```

**Current Behavior:**
- Mock provider handles all payment operations
- No real charges
- Instant subscription activation
- No webhook processing

---

### Step 2: Add LemonSqueezy Variables (Development)

**Update `.env`:**
```bash
# Add LemonSqueezy configuration
LEMONSQUEEZY_SANDBOX_MODE=true
LEMONSQUEEZY_API_KEY=your_test_api_key_here
LEMONSQUEEZY_STORE_ID=your_test_store_id_here
LEMONSQUEEZY_WEBHOOK_SECRET=your_test_webhook_secret_here
```

**Update Code:**
- Implement `src/providers/payment/lemonsqueezy_provider.py`
- Add webhook routes
- Update services to use new provider

**Test Thoroughly:**
- Create test subscription
- Process test webhooks
- Cancel test subscription
- Verify database updates

---

### Step 3: Deploy to Staging

**Set Environment Variables on Platform:**
```bash
# Railway/Render/Fly.io
railway variables set LEMONSQUEEZY_API_KEY="your_test_key"
railway variables set LEMONSQUEEZY_STORE_ID="12345"
railway variables set LEMONSQUEEZY_WEBHOOK_SECRET="whsec_test123"
railway variables set LEMONSQUEEZY_SANDBOX_MODE="true"
```

**Configure Webhook:**
1. Set webhook URL to staging domain
2. Test webhook delivery
3. Verify idempotency

**Testing Checklist:**
- [ ] Checkout flow works
- [ ] Webhooks processed correctly
- [ ] Subscriptions created in database
- [ ] Emails sent correctly
- [ ] Customer portal access works
- [ ] Cancellations work
- [ ] Upgrades work
- [ ] Error handling works

---

### Step 4: Deploy to Production

**CRITICAL: Use Production Keys**
```bash
# Production environment variables
railway variables set LEMONSQUEEZY_API_KEY="your_prod_key"
railway variables set LEMONSQUEEZY_STORE_ID="67890"
railway variables set LEMONSQUEEZY_WEBHOOK_SECRET="whsec_prod123"
railway variables set LEMONSQUEEZY_SANDBOX_MODE="false"
```

**Pre-Launch Checklist:**
- [ ] Production API key generated
- [ ] Production webhook configured
- [ ] HTTPS enabled on all URLs
- [ ] SSL certificate valid
- [ ] Database backups configured
- [ ] Monitoring (Sentry) enabled
- [ ] Rate limiting configured
- [ ] All tests passing
- [ ] Staging tested successfully
- [ ] Rollback plan documented

**Launch:**
1. Deploy backend with LemonSqueezy provider
2. Deploy frontend
3. Verify health checks
4. Test one real subscription (small amount)
5. Monitor logs closely for 24 hours
6. Announce to users

---

### Step 5: Remove Mock Provider (Optional)

**After 30 days of stable production:**
- Archive mock provider code
- Remove mock provider tests
- Update documentation

**Keep Mock Provider If:**
- Need local development without LemonSqueezy
- Running automated tests in CI/CD
- Supporting multiple payment providers

---

## Troubleshooting

### Common Issues

#### Issue 1: "LEMONSQUEEZY_API_KEY is required"

**Cause:** Environment variable not set

**Solution:**
```bash
# Check if variable is set
echo $LEMONSQUEEZY_API_KEY

# If empty, add to .env
echo 'LEMONSQUEEZY_API_KEY=your_key_here' >> .env

# Restart application
```

---

#### Issue 2: "Invalid webhook signature"

**Cause:** Webhook secret mismatch or incorrect signature verification

**Solution:**
1. Verify webhook secret in LemonSqueezy dashboard
2. Ensure secret matches exactly (no extra spaces)
3. Check signature verification algorithm
4. Use timing-safe comparison

**Debug:**
```python
# Log signature details (remove in production)
logger.debug(f"Expected signature: {calculated_signature}")
logger.debug(f"Provided signature: {provided_signature}")
logger.debug(f"Webhook secret: {LEMONSQUEEZY_WEBHOOK_SECRET[:10]}...")
```

---

#### Issue 3: "401 Unauthorized" from LemonSqueezy API

**Cause:** Invalid API key or expired key

**Solution:**
1. Regenerate API key in LemonSqueezy dashboard
2. Update environment variable
3. Restart application
4. Test API connection

---

#### Issue 4: "Webhook endpoint not receiving events"

**Cause:** Incorrect webhook URL or firewall blocking

**Solution:**
1. Verify webhook URL in LemonSqueezy dashboard
2. Check URL is publicly accessible
3. Ensure HTTPS (production)
4. Test with ngrok (development)
5. Check firewall/security group settings

**Test Webhook Delivery:**
```bash
# Use LemonSqueezy webhook test feature
# Or manually trigger with curl
curl -X POST https://yourdomain.com/api/v1/subscriptions/webhooks/lemonsqueezy \
  -H "Content-Type: application/json" \
  -H "X-Signature: test_signature" \
  -d '{"test": true}'
```

---

#### Issue 5: "Store ID not found"

**Cause:** Incorrect store ID or API key for different store

**Solution:**
1. Verify store ID in LemonSqueezy dashboard (Settings → General)
2. Ensure API key belongs to correct store
3. Update environment variable
4. Restart application

---

#### Issue 6: Frontend can't connect to backend

**Cause:** NEXT_PUBLIC_API_BASE_URL pointing to wrong URL

**Solution:**
```bash
# Check current value
echo $NEXT_PUBLIC_API_BASE_URL

# Update for your environment
# Development
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:2024

# Production
NEXT_PUBLIC_API_BASE_URL=https://api.wrext.com

# Restart frontend (Next.js)
npm run dev  # or npm run build && npm start
```

---

### Debugging Tips

**1. Enable Debug Logging:**
```bash
# Backend
LOG_LEVEL=DEBUG
DEBUG=true

# Check logs
tail -f logs/app.log
```

**2. Test LemonSqueezy API Connection:**
```bash
# Test API key
curl https://api.lemonsqueezy.com/v1/stores/YOUR_STORE_ID \
  -H "Authorization: Bearer YOUR_API_KEY"

# Should return store details if valid
```

**3. Test Webhook Secret:**
```python
# Quick test script
import hmac
import hashlib

payload = b'{"test": true}'
secret = "your_webhook_secret"
signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
print(f"Signature: {signature}")
```

**4. Verify Environment Variables Loaded:**
```python
# Add to startup
import os
print("LEMONSQUEEZY_API_KEY:", os.getenv("LEMONSQUEEZY_API_KEY")[:10] + "...")
print("LEMONSQUEEZY_STORE_ID:", os.getenv("LEMONSQUEEZY_STORE_ID"))
print("LEMONSQUEEZY_WEBHOOK_SECRET:", "SET" if os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET") else "NOT SET")
```

---

## Summary Checklist

### Development Setup

- [ ] Copy `.env.example` to `.env`
- [ ] Create LemonSqueezy test account
- [ ] Generate test API key
- [ ] Get test store ID
- [ ] Set up test webhook with ngrok
- [ ] Add all 3 LemonSqueezy variables to `.env`
- [ ] Test API connection
- [ ] Test webhook delivery
- [ ] Verify database updates

### Staging Deployment

- [ ] Set all environment variables on platform
- [ ] Use test/sandbox mode
- [ ] Configure webhook URL (staging domain)
- [ ] Test full checkout flow
- [ ] Verify webhook processing
- [ ] Test error scenarios
- [ ] Monitor logs for 24 hours

### Production Deployment

- [ ] Generate production API key (separate from test)
- [ ] Get production store ID
- [ ] Set `LEMONSQUEEZY_SANDBOX_MODE=false`
- [ ] Configure production webhook URL (HTTPS)
- [ ] Verify SSL certificate
- [ ] Set all production environment variables
- [ ] Test with real (small) transaction
- [ ] Enable monitoring (Sentry)
- [ ] Monitor logs for 48 hours
- [ ] Document rollback procedure

---

## Conclusion

This environment variables checklist provides a comprehensive guide for configuring the LemonSqueezy integration across all environments. Key points:

- **7 total variables** (3 required, 4 optional for testing)
- **Security first** - Never commit secrets
- **Environment-specific** - Different keys for dev/staging/prod
- **Validation** - Check variables on startup
- **Migration path** - Clear steps from mock to LemonSqueezy
- **Troubleshooting** - Common issues and solutions

All variables are documented with purpose, security classification, examples, and usage context. This document should be referenced during implementation and deployment.

---

**Document Status:** ✅ Complete
**Next Task:** 0.3.3 - LemonSqueezy account setup
**Related Documents:**
- File Change Inventory: `wrext-backend/docs/lemonsqueezy-file-change-inventory.md`
- All Phase 0 Audits: `wrext-backend/docs/audits/phase0-task-*.md`
