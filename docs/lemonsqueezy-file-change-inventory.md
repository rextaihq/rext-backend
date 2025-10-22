# LemonSqueezy Integration - File Change Inventory

**Created:** 2025-10-17
**Phase:** 0 - Discovery & Analysis
**Task:** 0.3.1 - Comprehensive File Change Inventory
**Status:** ✅ Complete

---

## Executive Summary

This document provides a comprehensive inventory of all files that will be created, modified, or deleted during the LemonSqueezy payment integration. It consolidates findings from 11 audit documents covering backend services, frontend components, database schema, API routes, email templates, and testing infrastructure.

### Overview Statistics

| Category | Files to Create | Files to Modify | Total Effort (hours) |
|----------|----------------|-----------------|---------------------|
| **Database** | 2 | 2 | 4-6 |
| **Backend Services** | 1 | 5 | 12-16 |
| **Backend API** | 2 | 1 | 8-10 |
| **Backend Tests** | 6 | 4 | 28-41 |
| **Email Templates** | 0 | 3 | 1 |
| **Frontend Types** | 0 | 2 | 2.5-3 |
| **Frontend API Client** | 0 | 2 | 1.75-2 |
| **Frontend Components** | 4 | 4 | 9-10 |
| **Frontend Routes** | 2 | 1 | 2.5-3 |
| **Frontend State** | 0 | 1 | 2-3 |
| **Configuration** | 0 | 2 | 0.5 |
| **Documentation** | 1 | 0 | 2 |
| **TOTAL** | **18** | **29** | **73-97** |

### Critical Path Summary

1. **Database Schema** (6-8 hours) - Foundation for all backend work
2. **LemonSqueezy Provider** (8-12 hours) - Core payment integration
3. **Webhook Handler** (6-8 hours) - Process LemonSqueezy events
4. **API Routes** (8-10 hours) - Checkout and portal endpoints
5. **Frontend Types & API** (4-5 hours) - Type safety and API methods
6. **Frontend Components** (9-10 hours) - UI for checkout and billing
7. **Testing** (28-41 hours) - Comprehensive test coverage

---

## Table of Contents

1. [Database Changes](#database-changes)
2. [Backend Services](#backend-services)
3. [Backend API Routes](#backend-api-routes)
4. [Backend Tests](#backend-tests)
5. [Email Templates](#email-templates)
6. [Frontend Types](#frontend-types)
7. [Frontend API Client](#frontend-api-client)
8. [Frontend Components](#frontend-components)
9. [Frontend Routes](#frontend-routes)
10. [Frontend State Management](#frontend-state-management)
11. [Configuration & Environment](#configuration--environment)
12. [Documentation](#documentation)
13. [Implementation Order](#implementation-order)
14. [Dependency Matrix](#dependency-matrix)

---

## Database Changes

### New Tables

#### 1. `webhook_events` (CREATE)

**File:** `wrext-backend/alembic/versions/XXX_create_webhook_events_table.py`
**Purpose:** Track LemonSqueezy webhook events for idempotency
**Priority:** CRITICAL
**Effort:** 2 hours

**Schema:**
```sql
CREATE TABLE webhook_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id VARCHAR(255) UNIQUE NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_webhook_events_event_id (event_id),
    INDEX idx_webhook_events_event_type (event_type),
    INDEX idx_webhook_events_created_at (created_at)
);
```

**Dependencies:** None

---

#### 2. `licenses` (CREATE)

**File:** `wrext-backend/alembic/versions/XXX_create_licenses_table.py`
**Purpose:** Store LemonSqueezy license keys (optional feature)
**Priority:** LOW (optional)
**Effort:** 2 hours

**Schema:**
```sql
CREATE TABLE licenses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    license_key VARCHAR(255) UNIQUE NOT NULL,
    subscription_id UUID REFERENCES user_subscriptions(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'active',
    activation_limit INTEGER DEFAULT 1,
    activation_count INTEGER DEFAULT 0,
    expires_at TIMESTAMP,
    instance_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_licenses_license_key (license_key),
    INDEX idx_licenses_subscription_id (subscription_id),
    INDEX idx_licenses_status (status)
);
```

**Dependencies:** `user_subscriptions` table must exist

---

### Modified Tables

#### 3. `subscription_plans` (MODIFY)

**File:** `wrext-backend/alembic/versions/XXX_add_lemonsqueezy_fields_to_plans.py`
**Purpose:** Add LemonSqueezy product and variant IDs
**Priority:** CRITICAL
**Effort:** 1 hour

**Changes:**
```sql
ALTER TABLE subscription_plans
ADD COLUMN lemonsqueezy_product_id VARCHAR(255),
ADD COLUMN lemonsqueezy_variant_id_monthly VARCHAR(255),
ADD COLUMN lemonsqueezy_variant_id_yearly VARCHAR(255),
ADD COLUMN lemonsqueezy_store_id VARCHAR(255);

CREATE INDEX idx_plans_lemonsqueezy_product ON subscription_plans(lemonsqueezy_product_id);
```

**Dependencies:** None

---

#### 4. `user_subscriptions` (MODIFY)

**File:** `wrext-backend/alembic/versions/XXX_add_lemonsqueezy_fields_to_subscriptions.py`
**Purpose:** Add LemonSqueezy subscription metadata
**Priority:** CRITICAL
**Effort:** 1 hour

**Changes:**
```sql
ALTER TABLE user_subscriptions
ADD COLUMN provider_order_id VARCHAR(255),
ADD COLUMN provider_subscription_id VARCHAR(255),
ADD COLUMN provider_customer_id VARCHAR(255),
ADD COLUMN provider_variant_id VARCHAR(255),
ADD COLUMN card_brand VARCHAR(50),
ADD COLUMN card_last_four VARCHAR(4),
ADD COLUMN cancel_at_period_end BOOLEAN DEFAULT FALSE,
ADD COLUMN paused_at TIMESTAMP,
ADD COLUMN urls JSONB,
ADD COLUMN metadata JSONB;

CREATE INDEX idx_subs_provider_subscription_id ON user_subscriptions(provider_subscription_id);
CREATE INDEX idx_subs_provider_customer_id ON user_subscriptions(provider_customer_id);
```

**Enum Update:**
```sql
ALTER TYPE subscription_status ADD VALUE 'paused';
ALTER TYPE subscription_status ADD VALUE 'past_due';
```

**Dependencies:** None

---

## Backend Services

### New Services

#### 5. `src/providers/payment/lemonsqueezy_provider.py` (CREATE)

**Purpose:** LemonSqueezy payment provider implementation
**Priority:** CRITICAL
**Effort:** 8-12 hours

**Methods to Implement:**
- `__init__(api_key, store_id)` - Initialize provider
- `create_customer(email, name, metadata)` - Create LemonSqueezy customer
- `create_checkout_session(...)` - Create checkout session
- `get_subscription(subscription_id)` - Get subscription details
- `cancel_subscription(subscription_id, immediately)` - Cancel subscription
- `update_subscription(subscription_id, variant_id)` - Change plan
- `pause_subscription(subscription_id)` - Pause subscription
- `resume_subscription(subscription_id)` - Resume subscription
- `create_customer_portal_session(customer_id, return_url)` - Portal URL
- `get_payment_method(subscription_id)` - Get payment details
- `get_invoices(customer_id, limit)` - Get invoice history
- `get_upcoming_invoice(subscription_id)` - Get upcoming invoice
- `validate_license(license_key)` - Validate license key
- `activate_license(license_key, instance_id)` - Activate license
- `deactivate_license(license_key, instance_id)` - Deactivate license
- `verify_webhook_signature(payload, signature, secret)` - Verify webhook
- `handle_webhook_event(event_type, data)` - Process webhook event

**Dependencies:**
- ~~LemonSqueezy SDK~~ **Using direct HTTP API via httpx** (already installed)
- Environment variables: `LEMONSQUEEZY_API_KEY`, `LEMONSQUEEZY_STORE_ID`, `LEMONSQUEEZY_WEBHOOK_SECRET`

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.1-mock-provider-audit.md`
- Reference: `src/providers/payment/mock_provider.py`

---

### Modified Services

#### 6. `src/services/subscription_service.py` (MODIFY)

**Purpose:** Update to use LemonSqueezy provider
**Priority:** CRITICAL
**Effort:** 4-6 hours

**Changes:**
- Replace `mock_provider` with `lemonsqueezy_provider`
- Update subscription field mapping
- Add provider metadata storage
- Update webhook integration
- Add license validation logic (if using licenses)

**Files Modified:** 1 file (703 lines)
**Dependencies:** LemonSqueezy provider must be complete

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.3-subscription-services-audit.md`

---

#### 7. `src/services/subscription_plan_service.py` (MODIFY)

**Purpose:** Add LemonSqueezy product/variant management
**Priority:** HIGH
**Effort:** 2 hours

**Changes:**
- Add `lemonsqueezy_product_id` field handling
- Add `lemonsqueezy_variant_id_monthly` field handling
- Add `lemonsqueezy_variant_id_yearly` field handling
- Add `lemonsqueezy_store_id` field handling
- Update Pydantic schemas

**Files Modified:** 1 file (~200 lines)
**Dependencies:** Database migrations for `subscription_plans`

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.3-subscription-services-audit.md`

---

#### 8. `src/services/subscription_management_service.py` (MODIFY)

**Purpose:** Add pause/resume support
**Priority:** MEDIUM
**Effort:** 2 hours

**Changes:**
- Add `pause_subscription(subscription_id)` method
- Add `resume_subscription(subscription_id)` method
- Update cancellation logic for `cancel_at_period_end`

**Files Modified:** 1 file (~150 lines)
**Dependencies:** LemonSqueezy provider pause/resume methods

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.3-subscription-services-audit.md`

---

#### 9. `src/services/subscription_retrieval_service.py` (MODIFY)

**Purpose:** Add payment method and invoice retrieval
**Priority:** MEDIUM
**Effort:** 1-2 hours

**Changes:**
- Add `get_payment_method(subscription_id)` method
- Add `get_invoices(subscription_id)` method
- Add `get_customer_portal_url(customer_id, return_url)` method

**Files Modified:** 1 file (~100 lines)
**Dependencies:** LemonSqueezy provider retrieval methods

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.3-subscription-services-audit.md`

---

#### 10. `src/services/subscription_analytics_service.py` (MODIFY)

**Purpose:** Update analytics for LemonSqueezy data
**Priority:** LOW
**Effort:** 1 hour

**Changes:**
- Update MRR calculation to use LemonSqueezy pricing
- Add pause status to churn calculation
- Update cohort analysis for new statuses

**Files Modified:** 1 file (~150 lines)
**Dependencies:** None (minor updates)

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.3-subscription-services-audit.md`

---

## Backend API Routes

### New Routes

#### 11. `src/routes/lemonsqueezy_webhook_routes.py` (CREATE)

**Purpose:** Handle LemonSqueezy webhooks
**Priority:** CRITICAL
**Effort:** 6-8 hours

**Endpoints:**
- `POST /api/v1/subscriptions/webhooks/lemonsqueezy` - Webhook receiver

**Features:**
- Signature verification
- Idempotency check (webhook_events table)
- Event routing (12 event types)
- Database transaction management
- Email notification triggering
- Error handling and logging

**Event Types to Handle:**
- `subscription_created` → Create subscription
- `subscription_updated` → Update subscription
- `subscription_cancelled` → Mark as cancelled
- `subscription_resumed` → Reactivate subscription
- `subscription_expired` → Mark as expired
- `subscription_paused` → Set paused status
- `subscription_unpaused` → Remove paused status
- `subscription_payment_success` → Update payment info
- `subscription_payment_failed` → Send failure email
- `subscription_payment_recovered` → Update status
- `order_created` → Record one-time purchase
- `license_key_created` → Create license record

**Dependencies:**
- LemonSqueezy provider (signature verification)
- Database models (`webhook_events`, `user_subscriptions`)
- Email service

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.4-subscription-routes-audit.md`

---

#### 12. `src/routes/license_routes.py` (CREATE)

**Purpose:** License validation endpoints (optional)
**Priority:** LOW (optional)
**Effort:** 2-3 hours

**Endpoints:**
- `POST /api/v1/subscriptions/validate-license` - Validate license key
- `POST /api/v1/subscriptions/activate-license` - Activate license
- `POST /api/v1/subscriptions/deactivate-license` - Deactivate license

**Dependencies:**
- LemonSqueezy provider license methods
- `licenses` database table

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.4-subscription-routes-audit.md`

---

### Modified Routes

#### 13. `src/routes/subscription_routes.py` (MODIFY)

**Purpose:** Update existing routes for LemonSqueezy
**Priority:** CRITICAL
**Effort:** 4-6 hours

**Changes:**
- Update `POST /api/v1/subscriptions/checkout` → `POST /api/v1/subscriptions/checkout-session`
  - Return LemonSqueezy checkout URL
  - Add success_url and cancel_url parameters
- Add `GET /api/v1/subscriptions/customer-portal` - Get portal URL
- Update Pydantic schemas:
  - `SubscriptionPlanCreate`: Add LemonSqueezy fields
  - `SubscriptionPlanUpdate`: Add LemonSqueezy fields
  - `UserSubscriptionResponse`: Add provider metadata

**Affected Endpoints:** 13 existing + 2 new
**Dependencies:** Database migrations, LemonSqueezy provider

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.4-subscription-routes-audit.md`

---

## Backend Tests

### New Test Files

#### 14. `tests/unit/providers/payment/test_lemonsqueezy_provider.py` (CREATE)

**Purpose:** Unit tests for LemonSqueezy provider
**Priority:** HIGH
**Effort:** 8-12 hours

**Test Classes:**
- `TestLemonSqueezyProviderBasics` (3-4 tests)
- `TestLemonSqueezyProviderCustomers` (3-4 tests)
- `TestLemonSqueezyProviderCheckout` (3-4 tests)
- `TestLemonSqueezyProviderSubscriptions` (6-8 tests)
- `TestLemonSqueezyProviderWebhooks` (4-5 tests)
- `TestLemonSqueezyProviderPortal` (1-2 tests)

**Total Tests:** 20-27 tests
**Testing Approach:** Mock HTTP requests with `responses` library

**Dependencies:**
- `responses>=0.23.0` (HTTP mocking)
- LemonSqueezy provider implementation

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.6-tests-audit.md`

---

#### 15. `tests/integration/test_lemonsqueezy_webhooks.py` (CREATE)

**Purpose:** Integration tests for webhook handling
**Priority:** CRITICAL
**Effort:** 8-12 hours

**Test Classes:**
- `TestWebhookAuthentication` (3-4 tests)
- `TestWebhookIdempotency` (3-4 tests)
- `TestSubscriptionWebhooks` (12+ tests - one per event type)
- `TestWebhookErrorHandling` (4-5 tests)
- `TestWebhookSideEffects` (4-5 tests)

**Total Tests:** 26-30 tests

**Dependencies:**
- Webhook routes implementation
- Database test fixtures
- Email service mocks

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.6-tests-audit.md`

---

#### 16. `tests/integration/test_subscription_routes.py` (CREATE)

**Purpose:** Integration tests for API routes
**Priority:** HIGH
**Effort:** 6-8 hours

**Test Classes:**
- `TestSubscriptionRoutes` (7 tests)
- `TestPlanRoutes` (6 tests)
- `TestWebhookRoutes` (2 tests)
- `TestRouteAuthentication` (3-4 tests)
- `TestRouteValidation` (4-5 tests)

**Total Tests:** 22-24 tests

**Dependencies:**
- All subscription routes
- FastAPI test client
- Database test fixtures

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.6-tests-audit.md`

---

#### 17. `tests/unit/emails/test_billing_templates.py` (CREATE)

**Purpose:** Unit tests for email templates
**Priority:** MEDIUM
**Effort:** 2-3 hours

**Test Classes:**
- `TestSubscriptionEmails` (4 tests)
- `TestPaymentEmails` (2 tests)
- `TestPlanChangeEmails` (2 tests)
- `TestUsageEmails` (2 tests)
- `TestEmailComponents` (3 tests)

**Total Tests:** 13 tests

**Dependencies:**
- Email template files
- Resend mock

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.6-tests-audit.md`

---

#### 18. `tests/performance/test_subscription_performance.py` (CREATE)

**Purpose:** Performance tests (optional)
**Priority:** LOW (optional)
**Effort:** 4-6 hours

**Test Scenarios:**
- Concurrent subscriptions (100 simultaneous)
- Webhook processing (1000 webhooks in 60s)
- Analytics queries (10,000 subscriptions)
- Usage limit checks (1000 concurrent)

**Total Tests:** 6-8 tests

**Dependencies:**
- Complete implementation
- Performance testing framework

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.6-tests-audit.md`

---

### Modified Test Files

#### 19. `tests/unit/providers/payment/test_mock_provider.py` (MODIFY)

**Purpose:** Update or archive mock provider tests
**Priority:** MEDIUM
**Effort:** 2 hours

**Changes:**
- Option A: Archive tests (mock provider deprecated)
- Option B: Keep as reference for provider interface

**Files Modified:** 1 file (324 lines, 17 tests)
**Dependencies:** None

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.6-tests-audit.md`

---

#### 20. `tests/unit/services/test_subscription_service.py` (MODIFY)

**Purpose:** Update tests for LemonSqueezy provider
**Priority:** HIGH
**Effort:** 4-6 hours

**Changes:**
- Update provider mocks to use LemonSqueezy
- Add tests for new fields (provider_order_id, etc.)
- Add tests for pause/resume functionality
- Update field naming (stripe → lemonsqueezy)

**Files Modified:** 1 file (~800 lines, 25 tests)
**Dependencies:** LemonSqueezy provider

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.6-tests-audit.md`

---

#### 21. `tests/unit/services/test_subscription_plan_service.py` (MODIFY)

**Purpose:** Update tests for LemonSqueezy plan fields
**Priority:** MEDIUM
**Effort:** 1 hour

**Changes:**
- Add tests for `lemonsqueezy_product_id`
- Add tests for `lemonsqueezy_variant_id_monthly/yearly`
- Update test fixtures

**Files Modified:** 1 file (~200 lines, 8 tests)
**Dependencies:** Plan service updates

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.6-tests-audit.md`

---

#### 22. `tests/integration/test_subscription_flows.py` (MODIFY)

**Purpose:** Update integration tests for LemonSqueezy
**Priority:** MEDIUM
**Effort:** 2-3 hours

**Changes:**
- Update checkout flow tests
- Add webhook flow tests
- Update provider mocks

**Files Modified:** 1 file (298 lines, ~8 tests)
**Dependencies:** LemonSqueezy provider, webhook routes

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.6-tests-audit.md`

---

## Email Templates

### Modified Templates

#### 23. `src/emails/billing/payment_succeeded.py` (MODIFY)

**Purpose:** Add card info to payment success emails
**Priority:** MEDIUM
**Effort:** 30 minutes

**Changes:**
```python
# Add optional parameters
card_brand: str = None,
card_last_four: str = None,

# Add to template
if card_brand and card_last_four:
    html += f"<p>Payment method: {card_brand} ending in {card_last_four}</p>"
```

**Files Modified:** 1 file (part of 1,180 lines across 11 templates)
**Dependencies:** None

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.5-email-templates-audit.md`

---

#### 24. `src/emails/billing/payment_failed.py` (MODIFY)

**Purpose:** Add customer portal URL to failure emails
**Priority:** MEDIUM
**Effort:** 15 minutes

**Changes:**
```python
# Add optional parameter
customer_portal_url: str = None,

# Add to template
if customer_portal_url:
    html += render_primary_button("Update Payment Method", customer_portal_url)
```

**Files Modified:** 1 file
**Dependencies:** Customer portal URL generation

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.5-email-templates-audit.md`

---

#### 25. `src/emails/billing/subscription_renewed.py` (MODIFY)

**Purpose:** Add invoice URL to renewal emails
**Priority:** MEDIUM
**Effort:** 20 minutes

**Changes:**
```python
# Add optional parameter
invoice_url: str = None,

# Add to template
if invoice_url:
    html += render_secondary_button("View Invoice", invoice_url)
```

**Files Modified:** 1 file
**Dependencies:** Invoice URL from LemonSqueezy

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.5-email-templates-audit.md`

---

## Frontend Types

### Modified Type Files

#### 26. `wrext-admin/types/subscription.ts` (MODIFY)

**Purpose:** Update subscription types for LemonSqueezy
**Priority:** CRITICAL
**Effort:** 2 hours

**Changes:**

1. **Fix Stripe Naming (BREAKING)**:
```typescript
// BEFORE
export interface SubscriptionPlanCreate {
  stripe_price_id_monthly?: string;
  stripe_price_id_yearly?: string;
}

// AFTER
export interface SubscriptionPlanCreate {
  lemonsqueezy_variant_id_monthly?: string;
  lemonsqueezy_variant_id_yearly?: string;
  lemonsqueezy_product_id?: string;
  lemonsqueezy_store_id?: string;
}
```

2. **Enhance UserSubscription Interface**:
```typescript
export interface UserSubscription {
  // ... existing fields ...

  // NEW: Provider integration fields
  provider_order_id: string | null;
  provider_subscription_id: string | null;
  provider_variant_id: string | null;
  provider_customer_id: string | null;

  // NEW: Subscription management
  cancel_at_period_end: boolean;
  renews_at: string | null;
  paused_at: string | null;

  // NEW: Payment method info
  card_brand: string | null;
  card_last_four: string | null;

  // NEW: LemonSqueezy URLs
  urls: {
    customer_portal?: string;
    update_payment_method?: string;
    invoice_url?: string;
  } | null;

  // NEW: Metadata
  metadata: Record<string, unknown> | null;
}
```

3. **Add New Interfaces**:
```typescript
export interface CheckoutSession { ... }
export interface CreateCheckoutSessionRequest { ... }
export interface CreateCheckoutSessionResponse { ... }
export interface PaymentMethod { ... }
export type WebhookEventType = "subscription_created" | ...;
export interface WebhookEvent { ... }
export interface SubscriptionEvent { ... }
```

4. **Add License Types (Optional)**:
```typescript
export enum LicenseStatus { ... }
export interface LicenseKey { ... }
export interface ValidateLicenseRequest { ... }
export interface ValidateLicenseResponse { ... }
```

**Files Modified:** 1 file (232 lines → ~350 lines)
**Breaking Changes:** YES (field naming)
**Dependencies:** Backend schema must match

**Source Files:**
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.1-subscription-types-audit.md`

---

#### 27. `wrext-admin/types/index.ts` (MODIFY)

**Purpose:** Export new subscription types
**Priority:** CRITICAL
**Effort:** 10 minutes

**Changes:**
```typescript
export type {
  CheckoutSession,
  CreateCheckoutSessionRequest,
  CreateCheckoutSessionResponse,
  PaymentMethod,
  WebhookEvent,
  WebhookEventType,
  // ... all other subscription types
} from "./subscription";
```

**Files Modified:** 1 file (277 lines)
**Dependencies:** `types/subscription.ts` updates

**Source Files:**
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.1-subscription-types-audit.md`

---

## Frontend API Client

### Modified API Client Files

#### 28. `wrext-admin/lib/api-client/core.ts` (MODIFY)

**Purpose:** Add retry logic and timeout support
**Priority:** HIGH
**Effort:** 1 hour

**Changes:**

1. **Add Retry Logic**:
```typescript
async request<T>(
  endpoint: string,
  options: RequestInit & {
    timeout?: number;
    retryConfig?: Partial<RetryConfig>;
  } = {}
): Promise<T> {
  const { timeout = 30000, retryConfig, ...fetchOptions } = options;
  const config = { ...DEFAULT_RETRY_CONFIG, ...retryConfig };

  let attempt = 0;
  while (attempt < config.maxAttempts) {
    attempt++;
    try {
      // ... existing fetch logic ...
      return result as T;
    } catch (error) {
      const classifiedError = classifyError(error, requestId, attempt);
      if (!shouldRetry(classifiedError, attempt, config)) {
        throw error;
      }
      const delay = calculateRetryDelay(attempt, config);
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
}
```

2. **Add Timeout Support**:
```typescript
// Create AbortController
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), timeout);

// Add signal to fetch
const response = await authenticatedFetch(url, {
  ...fetchOptions,
  signal: controller.signal,
});

clearTimeout(timeoutId);
```

**Files Modified:** 1 file (129 lines)
**Dependencies:** `error-utils.ts` (already exists)

**Source Files:**
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.2-api-client-audit.md`

---

#### 29. `wrext-admin/lib/api-client/subscriptions.ts` (MODIFY)

**Purpose:** Add LemonSqueezy API methods
**Priority:** CRITICAL
**Effort:** 45 minutes

**Changes:**

1. **Add Checkout Session Method**:
```typescript
createCheckoutSession: async (data: CreateCheckoutSessionRequest) => {
  return client.request<CreateCheckoutSessionResponse>(
    "/api/v1/subscriptions/checkout-session",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }
  );
},
```

2. **Add Customer Portal Method**:
```typescript
getCustomerPortalUrl: async (return_url?: string) => {
  const params = return_url ? new URLSearchParams({ return_url }) : undefined;
  return client.request<{ url: string }>(
    `/api/v1/subscriptions/customer-portal${params ? `?${params}` : ""}`,
    { method: "GET" }
  );
},
```

3. **Add License Methods (Optional)**:
```typescript
validateLicense: async (data: ValidateLicenseRequest) => { ... },
activateLicense: async (data) => { ... },
deactivateLicense: async (data) => { ... },
```

**Files Modified:** 1 file (139 lines → ~180 lines)
**Dependencies:** Type definitions from `types/subscription.ts`

**Source Files:**
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.2-api-client-audit.md`

---

## Frontend Components

### New Components

#### 30. `wrext-admin/app/checkout/success/page.tsx` (CREATE)

**Purpose:** Checkout success page with webhook polling
**Priority:** CRITICAL
**Effort:** 2 hours

**Features:**
- Display "Processing..." message
- Poll subscription status every 1-2 seconds
- Show success when subscription is active
- Auto-redirect to `/settings/subscription`
- Timeout handling (30 seconds)

**Component Type:** Page (Next.js 15 App Router)
**Dependencies:**
- `apiClient.subscriptions.getCurrentPlan()`
- Subscription types

**Source Files:**
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.3-ui-components-audit.md`
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.4-routing-audit.md`

---

#### 31. `wrext-admin/app/checkout/cancel/page.tsx` (CREATE)

**Purpose:** Checkout cancel page
**Priority:** MEDIUM
**Effort:** 30 minutes

**Features:**
- Display "Checkout cancelled" message
- Link back to `/pricing`
- No charges confirmation

**Component Type:** Page (Next.js 15 App Router)
**Dependencies:** None (static page)

**Source Files:**
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.4-routing-audit.md`

---

#### 32. `wrext-admin/components/subscriptions/customer-portal-button.tsx` (CREATE)

**Purpose:** Button to open LemonSqueezy customer portal
**Priority:** CRITICAL
**Effort:** 1 hour

**Features:**
- Loading state while fetching portal URL
- Error handling with toast
- Redirect to LemonSqueezy portal
- Customizable button props

**Component Type:** Client Component
**Dependencies:**
- `apiClient.subscriptions.getCustomerPortalUrl()`
- Button component from shadcn/ui

**Source Files:**
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.3-ui-components-audit.md`

---

#### 33. `wrext-admin/components/subscriptions/payment-method-card.tsx` (CREATE)

**Purpose:** Display payment method information
**Priority:** HIGH
**Effort:** 30 minutes

**Features:**
- Show card brand and last 4 digits
- "Update" button → customer portal
- Handle missing payment method

**Component Type:** Client Component
**Dependencies:**
- `UserSubscription` type
- CustomerPortalButton component

**Source Files:**
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.3-ui-components-audit.md`

---

#### 34. `wrext-admin/components/subscriptions/invoice-list.tsx` (CREATE)

**Purpose:** List and download invoices
**Priority:** HIGH
**Effort:** 1.5 hours

**Features:**
- Fetch invoices via React Query
- Display invoice date, amount, status
- Download button for each invoice
- Loading skeleton
- Empty state

**Component Type:** Client Component
**Dependencies:**
- `apiClient.subscriptions.getInvoices()` (NEW API method needed)
- Invoice type definition

**Source Files:**
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.3-ui-components-audit.md`

---

### Modified Components

#### 35. `wrext-admin/app/pricing/page.tsx` (MODIFY)

**Purpose:** Replace raw fetch with apiClient
**Priority:** CRITICAL
**Effort:** 30 minutes

**Changes:**
```typescript
// BEFORE
const response = await fetch(`${apiUrl}/api/v1/subscriptions/checkout`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${session.user.accessToken}`,
  },
  body: JSON.stringify({ plan_id, billing_period }),
});

// AFTER
const response = await apiClient.subscriptions.createCheckoutSession({
  plan_id: planId,
  billing_period: billingPeriod,
  success_url: `${window.location.origin}/checkout/success`,
  cancel_url: `${window.location.origin}/checkout/cancel`,
});
```

**Files Modified:** 1 file
**Dependencies:** API client checkout method

**Source Files:**
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.3-ui-components-audit.md`

---

#### 36. `wrext-admin/app/settings/subscription/page.tsx` (MODIFY)

**Purpose:** Add portal button, payment display, invoices
**Priority:** HIGH
**Effort:** 2 hours

**Changes:**
1. Import and use `CustomerPortalButton`
2. Import and use `PaymentMethodCard`
3. Import and use `InvoiceList` (optional)
4. Update subscription display to show new fields

**Files Modified:** 1 file
**Dependencies:** New components (30-33)

**Source Files:**
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.3-ui-components-audit.md`

---

#### 37. `wrext-admin/app/settings/billing/page.tsx` (MODIFY)

**Purpose:** Replace raw fetch with apiClient
**Priority:** MEDIUM
**Effort:** 1 hour

**Changes:**
- Replace raw fetch with `apiClient.subscriptions.*`
- Add customer portal button
- Display next billing date
- Show upcoming invoice amount (if available)

**Files Modified:** 1 file
**Dependencies:** API client

**Source Files:**
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.3-ui-components-audit.md`

---

#### 38. `wrext-admin/components/admin/subscription-plans/subscription-plan-form.tsx` (MODIFY)

**Purpose:** Add LemonSqueezy ID fields
**Priority:** LOW
**Effort:** 1 hour

**Changes:**
- Add input field: `lemonsqueezy_product_id`
- Add input field: `lemonsqueezy_variant_id_monthly`
- Add input field: `lemonsqueezy_variant_id_yearly`
- Add input field: `lemonsqueezy_store_id`
- Update form validation schema

**Files Modified:** 1 file
**Dependencies:** Type definitions

**Source Files:**
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.3-ui-components-audit.md`

---

## Frontend Routes

### New Routes

#### 39. `/checkout/success` - Checkout Success Route

**File:** `wrext-admin/app/checkout/success/page.tsx` (see Component #30)
**Access:** Public (for LemonSqueezy redirect)
**Priority:** CRITICAL
**Effort:** Included in component effort (2 hours)

**Source Files:**
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.4-routing-audit.md`

---

#### 40. `/checkout/cancel` - Checkout Cancel Route

**File:** `wrext-admin/app/checkout/cancel/page.tsx` (see Component #31)
**Access:** Public (for LemonSqueezy redirect)
**Priority:** MEDIUM
**Effort:** Included in component effort (30 minutes)

**Source Files:**
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.4-routing-audit.md`

---

### Modified Routes

#### 41. `wrext-admin/middleware.ts` (MODIFY)

**Purpose:** Add new routes to public routes array
**Priority:** CRITICAL
**Effort:** 5 minutes

**Changes:**
```typescript
const publicRoutes = [
  // ... existing ...
  "/pricing",           // ADD: Public pricing page
  "/mock-checkout",     // ADD: Mock checkout for dev
  "/checkout/success",  // ADD: Checkout success
  "/checkout/cancel",   // ADD: Checkout cancel
];
```

**Files Modified:** 1 file
**Dependencies:** None

**Source Files:**
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.4-routing-audit.md`

---

## Frontend State Management

### Modified State Files

#### 42. `wrext-admin/lib/query-client.ts` (MODIFY)

**Purpose:** Add retry logic and optimize subscription queries
**Priority:** HIGH
**Effort:** 2-3 hours

**Changes:**

1. **Add Smart Retry Strategy**:
```typescript
retry: (failureCount, error) => {
  // Don't retry on 4xx errors
  if (error instanceof ApiError && error.statusCode >= 400 && error.statusCode < 500) {
    return false;
  }
  return failureCount < 3;
},
retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
```

2. **Create Hierarchical Query Keys**:
```typescript
export const queryKeys = {
  subscriptions: {
    all: ["subscriptions"] as const,
    detail: () => [...queryKeys.subscriptions.all, "detail"] as const,
    current: () => [...queryKeys.subscriptions.detail(), "current"] as const,
    usage: (subscriptionId?: string) =>
      [...queryKeys.subscriptions.all, "usage", subscriptionId] as const,
    // ... more keys
  },
};
```

3. **Add Centralized Invalidation**:
```typescript
export const subscriptionInvalidation = {
  afterUpgrade: (queryClient: QueryClient) => {
    queryClient.invalidateQueries({ queryKey: queryKeys.subscriptions.detail() });
    queryClient.invalidateQueries({ queryKey: queryKeys.subscriptions.usage() });
  },
  // ... more helpers
};
```

**Files Modified:** 1 file
**Dependencies:** None

**Source Files:**
- Audit: `wrext-admin/docs/audits/phase0-task-0.2.5-state-management-audit.md`

---

## Configuration & Environment

### Modified Configuration Files

#### 43. `wrext-backend/.env.example` (MODIFY)

**Purpose:** Add LemonSqueezy environment variables
**Priority:** HIGH
**Effort:** 10 minutes

**Changes:**
```bash
# LemonSqueezy Configuration
LEMONSQUEEZY_API_KEY=your_api_key_here
LEMONSQUEEZY_STORE_ID=your_store_id_here
LEMONSQUEEZY_WEBHOOK_SECRET=your_webhook_secret_here

# LemonSqueezy URLs
LEMONSQUEEZY_API_URL=https://api.lemonsqueezy.com/v1
```

**Files Modified:** 1 file
**Dependencies:** None

**Source Files:**
- Cross-cutting requirements

---

#### 44. `wrext-backend/requirements.txt` (MODIFY)

**Purpose:** ~~Add LemonSqueezy SDK~~ Verify httpx for direct API integration
**Priority:** HIGH
**Effort:** 5 minutes

**Changes:**
```
# Payment Processing
lemonsqueezy>=1.0.0

# Testing (move to requirements-dev.txt)
responses>=0.23.0
pytest-cov>=4.1.0
freezegun>=1.2.0
```

**Files Modified:** 1 file
**Dependencies:** None

**Source Files:**
- Audit: `wrext-backend/docs/audits/phase0-task-0.1.6-tests-audit.md`

---

## Documentation

### New Documentation Files

#### 45. `wrext-backend/docs/lemonsqueezy-webhook-events.md` (CREATE)

**Purpose:** Document all webhook events and their handling
**Priority:** MEDIUM
**Effort:** 2 hours

**Content:**
- Overview of LemonSqueezy webhook system
- List of all 12 event types
- Event payload structure for each type
- Database side effects for each event
- Email notifications triggered
- Troubleshooting guide

**Files Created:** 1 file
**Dependencies:** Webhook implementation

**Source Files:**
- Implementation experience

---

## Implementation Order

### Phase-by-Phase Breakdown

#### **Phase 1: Database Foundation** (6-8 hours)
**Priority:** CRITICAL
**Dependencies:** None

1. Create `webhook_events` table migration
2. Create `licenses` table migration (optional)
3. Modify `subscription_plans` table
4. Modify `user_subscriptions` table
5. Run migrations in dev environment
6. Verify schema changes

**Deliverable:** Database schema ready for LemonSqueezy data

---

#### **Phase 2: Backend Core Services** (12-16 hours)
**Priority:** CRITICAL
**Dependencies:** Phase 1 complete

1. Implement `lemonsqueezy_provider.py` (17 methods)
2. Update `subscription_service.py`
3. Update `subscription_plan_service.py`
4. Update `subscription_management_service.py`
5. Update `subscription_retrieval_service.py`
6. Manual testing with LemonSqueezy sandbox

**Deliverable:** Backend services integrated with LemonSqueezy

---

#### **Phase 3: Backend API Routes** (10-14 hours)
**Priority:** CRITICAL
**Dependencies:** Phase 2 complete

1. Create `lemonsqueezy_webhook_routes.py` (12 event handlers)
2. Create `license_routes.py` (optional)
3. Update `subscription_routes.py` (checkout, portal endpoints)
4. Update Pydantic schemas
5. Test webhook signature verification
6. Test checkout session creation

**Deliverable:** API ready for frontend integration

---

#### **Phase 4: Frontend Types & API** (4-5 hours)
**Priority:** CRITICAL
**Dependencies:** Phase 3 complete

1. Update `types/subscription.ts` (fix naming, add fields)
2. Update `types/index.ts` (export new types)
3. Update `lib/api-client/core.ts` (retry, timeout)
4. Update `lib/api-client/subscriptions.ts` (checkout, portal methods)
5. Run type checks (`npm run type-check`)

**Deliverable:** Type-safe frontend-backend communication

---

#### **Phase 5: Frontend Components** (9-10 hours)
**Priority:** HIGH
**Dependencies:** Phase 4 complete

1. Create `checkout/success/page.tsx` (webhook polling)
2. Create `checkout/cancel/page.tsx`
3. Create `customer-portal-button.tsx`
4. Create `payment-method-card.tsx`
5. Create `invoice-list.tsx`
6. Update `app/pricing/page.tsx` (use apiClient)
7. Update `app/settings/subscription/page.tsx` (add portal, payment)
8. Update `app/settings/billing/page.tsx` (use apiClient)
9. Update admin plan form (LemonSqueezy IDs)

**Deliverable:** Complete UI for LemonSqueezy integration

---

#### **Phase 6: Frontend State & Config** (2-3 hours)
**Priority:** HIGH
**Dependencies:** Phase 5 complete

1. Update `lib/query-client.ts` (retry, query keys, invalidation)
2. Update `middleware.ts` (public routes)
3. Test state management changes

**Deliverable:** Optimized state management

---

#### **Phase 7: Email Templates** (1 hour)
**Priority:** MEDIUM
**Dependencies:** Phase 2 complete

1. Update `payment_succeeded.py` (card info)
2. Update `payment_failed.py` (portal URL)
3. Update `subscription_renewed.py` (invoice URL)
4. Test email rendering

**Deliverable:** Enhanced email notifications

---

#### **Phase 8: Testing** (28-41 hours)
**Priority:** HIGH
**Dependencies:** Phases 1-7 complete

1. Create `test_lemonsqueezy_provider.py` (8-12h)
2. Create `test_lemonsqueezy_webhooks.py` (8-12h)
3. Create `test_subscription_routes.py` (6-8h)
4. Create `test_billing_templates.py` (2-3h)
5. Update `test_subscription_service.py` (4-6h)
6. Update other existing tests (2-3h)
7. Run full test suite, achieve 80%+ coverage

**Deliverable:** Comprehensive test coverage

---

#### **Phase 9: Documentation & Polish** (2 hours)
**Priority:** LOW
**Dependencies:** Phase 8 complete

1. Create `lemonsqueezy-webhook-events.md`
2. Update README with setup instructions
3. Create deployment checklist
4. Document environment variables

**Deliverable:** Complete documentation

---

## Dependency Matrix

### File Dependencies

| File | Depends On | Blocks |
|------|-----------|--------|
| **Database Migrations** | None | All backend work |
| `lemonsqueezy_provider.py` | Database, httpx (direct API) | All services |
| `subscription_service.py` | LemonSqueezy provider | API routes |
| `lemonsqueezy_webhook_routes.py` | Provider, services | None |
| `subscription_routes.py` | Services | Frontend API calls |
| `types/subscription.ts` | Backend schema | Frontend components |
| `lib/api-client/subscriptions.ts` | Types, backend routes | Components |
| `checkout/success/page.tsx` | API client | None |
| `customer-portal-button.tsx` | API client | Subscription pages |
| `lib/query-client.ts` | None | None (optimization) |
| **Tests** | Complete implementation | Deployment |

### Critical Path

```
Database Migrations (6-8h)
    ↓
LemonSqueezy Provider (8-12h)
    ↓
Subscription Services (6-10h)
    ↓
API Routes (10-14h)
    ↓
Frontend Types (2.5-3h)
    ↓
Frontend API Client (1.75-2h)
    ↓
Frontend Components (9-10h)
    ↓
Testing (28-41h)
    ↓
TOTAL: 72-100 hours
```

---

## Risk Assessment

### High-Risk Changes

| Change | Risk | Mitigation |
|--------|------|------------|
| Database schema changes | Data loss if migrations fail | Test migrations in dev, backup prod DB |
| Provider swap (mock → LemonSqueezy) | Service disruption | Deploy with feature flag, keep mock as fallback |
| Type naming changes (stripe → lemonsqueezy) | Frontend-backend mismatch | Coordinate deployment, use backward-compatible API |
| Webhook signature verification | Security vulnerability | Thorough testing, rate limiting, monitoring |

### Medium-Risk Changes

| Change | Risk | Mitigation |
|--------|------|------------|
| API client retry logic | Infinite retries | Max retry limit (3), exponential backoff |
| Checkout success polling | Resource waste | Exponential backoff, 30s timeout |
| Query key refactoring | Cache misses | Gradual rollout, invalidate all on deploy |

### Low-Risk Changes

| Change | Risk | Mitigation |
|--------|------|------------|
| Email template enhancements | Broken emails | Template testing, fallback to existing |
| Admin plan form fields | Admin confusion | Documentation, tooltips |
| Invoice display | API errors | Graceful error handling, empty state |

---

## Testing Strategy

### Test Coverage Goals

| Component | Target Coverage | Priority |
|-----------|----------------|----------|
| LemonSqueezy Provider | 90% | CRITICAL |
| Webhook Handlers | 95% | CRITICAL |
| Subscription Service | 85% | CRITICAL |
| API Routes | 80% | HIGH |
| Email Templates | 70% | MEDIUM |
| Frontend Components | 60% | MEDIUM |

### Testing Phases

1. **Unit Tests** (20-30h)
   - Provider methods
   - Service logic
   - Email templates
   - Type utilities

2. **Integration Tests** (14-18h)
   - API routes
   - Webhook flows
   - Service interactions

3. **End-to-End Tests** (4-6h)
   - Checkout flow
   - Webhook processing
   - Portal access

---

## Rollout Plan

### Pre-Deployment Checklist

- [ ] All migrations tested in staging
- [ ] LemonSqueezy sandbox configured
- [ ] Environment variables set
- [ ] Webhook endpoint registered with LemonSqueezy
- [ ] Test subscription created in sandbox
- [ ] All tests passing (80%+ coverage)
- [ ] Documentation complete
- [ ] Rollback plan documented

### Deployment Phases

#### Phase 1: Staging Deployment (Week 1)
- Deploy backend with feature flag
- Deploy frontend
- Test with LemonSqueezy sandbox
- Monitor webhook processing

#### Phase 2: Limited Production (Week 2)
- Enable for internal users only
- Monitor for issues
- Collect feedback

#### Phase 3: Full Production (Week 3)
- Enable for all users
- Migrate existing subscriptions (if any)
- Monitor closely for 48 hours

---

## Success Criteria

### MVP Launch Criteria

- [ ] Users can view pricing page without login
- [ ] Users can create new subscriptions
- [ ] LemonSqueezy checkout flow works end-to-end
- [ ] Webhooks process successfully (all 12 event types)
- [ ] Customer portal access works
- [ ] Payment methods display correctly
- [ ] Email notifications sent correctly
- [ ] Admin can manage plans with LemonSqueezy IDs
- [ ] All tests passing (80%+ coverage)
- [ ] Zero critical bugs in production

### Post-Launch Metrics

- Checkout conversion rate > 70%
- Webhook processing latency < 2 seconds
- API response time < 500ms (p95)
- Zero payment failures due to integration issues
- User satisfaction > 4/5 stars

---

## Conclusion

This comprehensive file change inventory provides a complete roadmap for the LemonSqueezy integration. The project involves:

- **47 total files** (18 new, 29 modified)
- **73-97 hours** of estimated effort
- **9 implementation phases** over 3-4 weeks
- **Critical path: Database → Provider → Services → API → Frontend → Tests**

All changes are well-documented, with clear dependencies, effort estimates, and risk assessments. The integration is fully audited and ready for implementation.

---

**Document Status:** ✅ Complete
**Next Step:** Mark Task 0.3.1 complete in LEMONSQUEEZY_INTEGRATION_PROMPT.md
**Ready for:** Phase 1 implementation (Database migrations)
