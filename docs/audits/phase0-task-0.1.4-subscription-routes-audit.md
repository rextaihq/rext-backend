# Phase 0 - Task 0.1.4: Subscription Routes Audit

**Date:** 2025-10-17
**Task:** Audit subscription routes/endpoints
**Status:** ✅ Complete
**Author:** Claude Code

---

## Executive Summary

This audit analyzes all subscription-related API endpoints in the WREXT backend to understand their integration with payment providers, identify required modifications for LemonSqueezy, and plan new endpoint creation.

### Key Findings

1. **Well-Structured Routes**: 3 route files with clear separation of concerns (user subscriptions, admin plans, webhooks)
2. **13 Existing Endpoints**: All endpoints documented with clear request/response models
3. **1 Mock Webhook Endpoint**: Placeholder webhook handler that needs replacement with LemonSqueezy webhook handler
4. **Schema Issues**: Pydantic schemas still use "stripe_price_id" naming (same issue identified in service audit)
5. **New Endpoints Needed**: 2 new endpoints required (LemonSqueezy webhook handler, license validation)
6. **No Breaking Changes**: Existing endpoints can remain as-is with minor Pydantic model updates

---

## Route File Inventory

### 1. User Subscription Routes
**File:** `src/api/routes/subscriptions/subscription_routes.py` (345 lines)
**Prefix:** `/subscriptions`
**Tag:** `subscriptions`
**Purpose:** End-user subscription management
**Endpoints:** 7 user-facing endpoints

### 2. Subscription Plan Routes (Admin)
**File:** `src/api/routes/subscriptions/plan_routes.py` (161 lines)
**Prefix:** `/subscriptions/plans`
**Tag:** `subscription-plans`
**Purpose:** Admin plan CRUD operations
**Endpoints:** 5 admin endpoints + 1 public endpoint

### 3. Webhook Routes
**File:** `src/api/routes/subscriptions/webhook_routes.py` (191 lines)
**Prefix:** `/subscriptions/webhooks`
**Tag:** `subscriptions`, `webhooks`
**Purpose:** Payment provider webhook handlers
**Endpoints:** 1 mock webhook endpoint

---

## Complete Endpoint Inventory

### User Subscription Endpoints (subscription_routes.py)

#### 1. POST /subscriptions/subscribe
**Line:** 29-74
**Purpose:** Subscribe to a plan
**Authentication:** Required (JWT)
**Authorization:** `subscription.manage` permission (user-scoped)
**Request Model:** `SubscriptionCreateRequest`
**Response Model:** dict

**Request Body:**
```python
{
  "plan_id": "UUID",
  "billing_period": "monthly" | "yearly" | "lifetime"
}
```

**Response Data:**
```python
{
  "id": "UUID",
  "user_id": "UUID",
  "plan_id": "UUID",
  "plan_name": "string",
  "plan_display_name": "string",
  "status": "trial" | "active" | "cancelled" | "expired" | "suspended",
  "billing_period": "monthly" | "yearly" | "lifetime",
  "start_date": "ISO datetime",
  "end_date": "ISO datetime | null",
  "trial_end_date": "ISO datetime | null",
  "cancelled_at": "ISO datetime | null",
  "current_api_calls": int,
  "created_at": "ISO datetime"
}
```

**Service Call:** `SubscriptionService.subscribe(user_id, plan_id, billing_period)`

**Payment Provider Integration:** ✅ Yes (via service layer)
- Creates customer at payment provider
- Creates checkout session
- Returns checkout URL

**LemonSqueezy Changes Needed:** ❌ None
- Service layer handles provider abstraction
- Endpoint remains unchanged

---

#### 2. GET /subscriptions/my-subscription
**Line:** 77-123
**Purpose:** Get current user's active subscription
**Authentication:** Required (JWT)
**Authorization:** None (user can view own subscription)
**Request Model:** None (query params only)
**Response Model:** dict

**Response Data:**
```python
{
  "id": "UUID",
  "user_id": "UUID",
  "plan_id": "UUID",
  "plan_name": "string",
  "plan_display_name": "string",
  "plan_features": {...},
  "plan_limits": {
    "max_workspaces": int,
    "max_members_per_workspace": int,
    "max_topics": int,
    "max_knowledge_items": int,
    "max_api_calls_per_month": int
  },
  "status": "string",
  "billing_period": "string",
  "start_date": "ISO datetime",
  "end_date": "ISO datetime | null",
  "trial_end_date": "ISO datetime | null",
  "cancelled_at": "ISO datetime | null",
  "current_api_calls": int
}
```

**Service Call:** `SubscriptionService.get_subscription_by_user(user_id)`

**Payment Provider Integration:** ❌ No (read-only from database)

**LemonSqueezy Changes Needed:** ⚠️ Minor enhancement
- Add LemonSqueezy-specific fields to response:
  - `urls` (customer portal, invoice URLs)
  - `card_brand`
  - `card_last_four`
  - `renews_at`
  - `cancel_at_period_end`

**Estimated Effort:** 30 minutes

---

#### 3. GET /subscriptions/history
**Line:** 126-156
**Purpose:** Get subscription history for current user
**Authentication:** Required (JWT)
**Authorization:** None (user can view own history)
**Query Parameters:**
- `limit: int = 10` (1-100)

**Response Data:**
```python
{
  "subscriptions": [
    {
      // Same structure as my-subscription
    }
  ],
  "count": int
}
```

**Service Call:** `SubscriptionService.get_subscription_history(user_id, limit)`

**Payment Provider Integration:** ❌ No (read-only from database)

**LemonSqueezy Changes Needed:** ❌ None

---

#### 4. POST /subscriptions/upgrade
**Line:** 159-202
**Purpose:** Upgrade or downgrade subscription plan
**Authentication:** Required (JWT)
**Authorization:** `subscription.manage` permission (user-scoped)
**Request Model:** `SubscriptionUpgradeRequest`
**Response Model:** dict

**Request Body:**
```python
{
  "new_plan_id": "UUID",
  "billing_period": "monthly" | "yearly" | null  // Optional
}
```

**Response Data:**
```python
{
  // Same structure as subscribe endpoint
}
```

**Service Call:** `SubscriptionService.upgrade(user_id, new_plan_id, billing_period)`

**Payment Provider Integration:** ✅ Yes (via service layer)
- Updates subscription at payment provider
- Changes plan/variant

**LemonSqueezy Changes Needed:** ❌ None
- Service layer handles provider abstraction

---

#### 5. POST /subscriptions/cancel
**Line:** 205-244
**Purpose:** Cancel current subscription
**Authentication:** Required (JWT)
**Authorization:** `subscription.manage` permission (user-scoped)
**Request Model:** `SubscriptionCancelRequest`
**Response Model:** dict

**Request Body:**
```python
{
  "reason": "string (max 500 chars) | null",
  "cancel_immediately": bool  // Default: false
}
```

**Response Data:**
```python
{
  // Same structure as my-subscription
}
```

**Service Call:** `SubscriptionService.cancel(user_id, reason, cancel_immediately)`

**Payment Provider Integration:** ✅ Yes (via service layer)
- Cancels subscription at payment provider
- Sets cancellation date

**LemonSqueezy Changes Needed:** ❌ None
- Service layer handles provider abstraction

---

#### 6. GET /subscriptions/usage
**Line:** 247-312
**Purpose:** Get current usage statistics vs plan limits
**Authentication:** Required (JWT)
**Authorization:** None (user can view own usage)
**Request Model:** None
**Response Model:** dict

**Response Data:**
```python
{
  "subscription_id": "UUID",
  "plan_name": "string",
  "billing_period": "string",
  "current_workspaces": int,
  "current_topics": int,
  "current_knowledge_items": int,
  "current_api_calls": int,
  "max_workspaces": int,
  "max_topics": int,
  "max_knowledge_items": int,
  "max_api_calls_per_month": int,
  "workspaces_usage_percent": float,
  "topics_usage_percent": float,
  "knowledge_items_usage_percent": float,
  "api_calls_usage_percent": float,
  "usage_reset_date": "ISO datetime"
}
```

**Service Call:** `SubscriptionService.calculate_usage(user_id)`

**Payment Provider Integration:** ❌ No (calculated from database)

**LemonSqueezy Changes Needed:** ❌ None

---

#### 7. GET /subscriptions/trial-status
**Line:** 315-344
**Purpose:** Get trial status for current subscription
**Authentication:** Required (JWT)
**Authorization:** None (user can view own trial status)
**Request Model:** None
**Response Model:** dict

**Response Data:**
```python
{
  "is_trial": bool,
  "trial_end_date": "ISO datetime | null",
  "days_remaining": int,
  "trial_expired": bool
}
```

**Service Call:** `SubscriptionService.check_trial_status(user_id)`

**Payment Provider Integration:** ❌ No (calculated from database)

**LemonSqueezy Changes Needed:** ❌ None

---

### Admin Plan Endpoints (plan_routes.py)

#### 8. GET /subscriptions/plans/public
**Line:** 28-48
**Purpose:** List public subscription plans (no auth required)
**Authentication:** ❌ Not required
**Authorization:** None (public endpoint)
**Query Parameters:** None
**Response Model:** dict

**Response Data:**
```python
{
  "plans": [
    {
      "id": "UUID",
      "name": "string",
      "display_name": "string",
      "description": "string",
      "price_monthly": float,
      "price_yearly": float,
      "features": {...},
      "max_workspaces": int,
      "max_members_per_workspace": int,
      "max_topics": int,
      "max_knowledge_items": int,
      "max_api_calls_per_month": int,
      "is_active": bool,
      "is_public": bool,
      "created_at": "ISO datetime"
    }
  ],
  "count": int
}
```

**Service Call:** `SubscriptionPlanService.list_plans(include_inactive=False, include_private=False, is_admin=False)`

**Payment Provider Integration:** ❌ No (read-only from database)

**LemonSqueezy Changes Needed:** ⚠️ Add LemonSqueezy variant IDs to response
- Add `lemonsqueezy_variant_id_monthly`
- Add `lemonsqueezy_variant_id_yearly`
- Frontend needs these for checkout creation

**Estimated Effort:** 15 minutes

---

#### 9. POST /subscriptions/plans
**Line:** 51-69
**Purpose:** Create a new subscription plan
**Authentication:** Required (JWT)
**Authorization:** Admin only (checked via `service.require_admin()`)
**Request Model:** `SubscriptionPlanCreate`
**Response Model:** dict

**Request Body:**
```python
{
  "name": "string (2-100 chars, lowercase, a-z0-9_)",
  "display_name": "string (2-150 chars)",
  "description": "string | null",
  "price_monthly": decimal (0.00-99999.99),
  "price_yearly": decimal (0.00-99999.99),
  "features": {...},
  "max_workspaces": int (-1 = unlimited),
  "max_members_per_workspace": int (-1 = unlimited),
  "max_topics": int (-1 = unlimited),
  "max_knowledge_items": int (-1 = unlimited),
  "max_api_calls_per_month": int (-1 = unlimited),
  "is_active": bool,
  "is_public": bool,
  "stripe_price_id_monthly": "string | null",  // ⚠️ Legacy naming
  "stripe_price_id_yearly": "string | null"     // ⚠️ Legacy naming
}
```

**Service Call:** `SubscriptionPlanService.create_plan(plan_data)`

**Payment Provider Integration:** ❌ No (admin creates plan in database)
- Admin must manually create product/variant in LemonSqueezy dashboard
- Then populate LemonSqueezy IDs in this endpoint

**LemonSqueezy Changes Needed:** ⚠️ Update Pydantic schema
- Rename `stripe_price_id_monthly` → `lemonsqueezy_variant_id_monthly`
- Rename `stripe_price_id_yearly` → `lemonsqueezy_variant_id_yearly`
- Add `lemonsqueezy_product_id` (optional)
- Add `lemonsqueezy_store_id` (optional)

**Estimated Effort:** 30 minutes

---

#### 10. GET /subscriptions/plans
**Line:** 72-95
**Purpose:** List all subscription plans (with admin filters)
**Authentication:** Required (JWT)
**Authorization:** None (filters applied based on admin status)
**Query Parameters:**
- `include_inactive: bool = False` (admin only)
- `include_private: bool = False` (admin only)

**Response Data:**
```python
{
  "plans": [...],  // Same structure as GET /plans/public
  "count": int
}
```

**Service Call:** `SubscriptionPlanService.list_plans(include_inactive, include_private, is_admin)`

**Payment Provider Integration:** ❌ No (read-only from database)

**LemonSqueezy Changes Needed:** ⚠️ Add LemonSqueezy IDs to response
- Same as GET /plans/public

**Estimated Effort:** Included in endpoint 8 changes

---

#### 11. GET /subscriptions/plans/{plan_id}
**Line:** 98-116
**Purpose:** Retrieve subscription plan details
**Authentication:** Required (JWT)
**Authorization:** None (filters applied based on admin status)
**Path Parameters:**
- `plan_id: UUID`

**Response Data:**
```python
{
  // Same structure as plan in list response
}
```

**Service Call:** `SubscriptionPlanService.get_plan(plan_id, is_admin)`

**Payment Provider Integration:** ❌ No (read-only from database)

**LemonSqueezy Changes Needed:** ⚠️ Add LemonSqueezy IDs to response
- Same as GET /plans/public

**Estimated Effort:** Included in endpoint 8 changes

---

#### 12. PATCH /subscriptions/plans/{plan_id}
**Line:** 119-138
**Purpose:** Update subscription plan metadata
**Authentication:** Required (JWT)
**Authorization:** Admin only
**Path Parameters:**
- `plan_id: UUID`
**Request Model:** `SubscriptionPlanUpdate`
**Response Model:** dict

**Request Body:**
```python
{
  // All fields from SubscriptionPlanCreate, but optional
  // Same ⚠️ legacy naming issues
}
```

**Service Call:** `SubscriptionPlanService.update_plan(plan_id, plan_data)`

**Payment Provider Integration:** ❌ No (admin updates plan in database only)

**LemonSqueezy Changes Needed:** ⚠️ Update Pydantic schema
- Same as POST /plans

**Estimated Effort:** Included in endpoint 9 changes

---

#### 13. DELETE /subscriptions/plans/{plan_id}
**Line:** 141-160
**Purpose:** Delete a subscription plan
**Authentication:** Required (JWT)
**Authorization:** Admin only
**Path Parameters:**
- `plan_id: UUID`
**Query Parameters:**
- `force: bool = False` (force delete even if subscriptions exist)

**Response Data:**
```python
{
  "plan_id": "UUID",
  "plan_name": "string",
  "deleted": bool
}
```

**Service Call:** `SubscriptionPlanService.delete_plan(plan_id, force)`

**Payment Provider Integration:** ❌ No (database operation only)

**LemonSqueezy Changes Needed:** ❌ None

---

### Webhook Endpoints (webhook_routes.py)

#### 14. POST /subscriptions/webhooks/mock/checkout-complete
**Line:** 45-190
**Purpose:** Handle mock checkout completion webhook (development only)
**Authentication:** ❌ Not required (webhook endpoint)
**Authorization:** None (should verify webhook signature in production)
**Request Model:** `MockCheckoutCompleteRequest`
**Response Model:** dict

**Request Body:**
```python
{
  "session_id": "string",
  "success": bool  // Default: true
}
```

**Current Implementation:**
- Retrieves checkout session from mock provider's in-memory storage
- Extracts metadata (user_id, plan_id, billing_period)
- Creates subscription via `SubscriptionService.subscribe()`
- Creates provider subscription
- Sends subscription_created email
- Returns subscription details

**Issues with Current Implementation:**
1. ❌ No webhook signature verification
2. ❌ No idempotency (no event ID tracking)
3. ❌ In-memory session storage (lost on restart)
4. ❌ Hardcoded to mock provider flow
5. ❌ No error recovery or retry logic

**Payment Provider Integration:** ✅ Yes (mock provider only)

**LemonSqueezy Changes Needed:** ⚠️ Complete replacement required
- Create new endpoint: `POST /subscriptions/webhooks/lemonsqueezy`
- Implement signature verification using `X-Signature` header
- Add idempotency using `webhook_events` table
- Handle multiple event types:
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
  - `order_created` (for one-time purchases/licenses)
  - `license_key_created`

**Estimated Effort:** 8-12 hours (new endpoint creation + testing)

---

## Pydantic Schema Analysis

### Request/Response Models

#### User Subscription Schemas (user_subscription_schemas.py)

**SubscriptionCreateRequest** (Lines 12-29)
```python
class SubscriptionCreateRequest(BaseModel):
    plan_id: str  # UUID
    billing_period: BillingPeriod  # Enum
```
**LemonSqueezy Changes:** ❌ None needed

---

**SubscriptionUpgradeRequest** (Lines 32-49)
```python
class SubscriptionUpgradeRequest(BaseModel):
    new_plan_id: str  # UUID
    billing_period: Optional[BillingPeriod]  # Optional change
```
**LemonSqueezy Changes:** ❌ None needed

---

**SubscriptionCancelRequest** (Lines 52-70)
```python
class SubscriptionCancelRequest(BaseModel):
    reason: Optional[str]  # Max 500 chars
    cancel_immediately: bool  # Default: False
```
**LemonSqueezy Changes:** ❌ None needed

---

**UserSubscriptionResponse** (Lines 73-106)
```python
class UserSubscriptionResponse(BaseModel):
    id: str
    user_id: str
    plan_id: str
    plan_name: Optional[str]
    plan_display_name: Optional[str]
    status: str
    billing_period: str
    start_date: str
    end_date: Optional[str]
    trial_end_date: Optional[str]
    cancelled_at: Optional[str]
    current_api_calls: int
    created_at: str
```

**LemonSqueezy Changes:** ⚠️ Add new fields
```python
# Add these fields:
provider_order_id: Optional[str] = None
provider_variant_id: Optional[str] = None
cancel_at_period_end: bool = False
renews_at: Optional[str] = None
paused_at: Optional[str] = None
card_brand: Optional[str] = None
card_last_four: Optional[str] = None
urls: Optional[Dict[str, str]] = None  # customer_portal, invoice
```

**Estimated Effort:** 1 hour

---

#### Plan Schemas (plan_schemas.py)

**SubscriptionPlanCreate** (Lines 12-112)
```python
class SubscriptionPlanCreate(BaseModel):
    name: str  # lowercase, a-z0-9_
    display_name: str
    description: Optional[str]
    price_monthly: Decimal
    price_yearly: Decimal
    features: Optional[Dict[str, Any]]
    max_workspaces: int
    max_members_per_workspace: int
    max_topics: int
    max_knowledge_items: int
    max_api_calls_per_month: int
    is_active: bool
    is_public: bool

    # ⚠️ Legacy Stripe naming
    stripe_price_id_monthly: Optional[str]
    stripe_price_id_yearly: Optional[str]
```

**LemonSqueezy Changes:** ⚠️ Rename + add fields
```python
# Rename:
stripe_price_id_monthly → lemonsqueezy_variant_id_monthly
stripe_price_id_yearly → lemonsqueezy_variant_id_yearly

# Add:
lemonsqueezy_product_id: Optional[str] = None
lemonsqueezy_store_id: Optional[str] = None
```

**Estimated Effort:** 30 minutes

---

**SubscriptionPlanUpdate** (Lines 115-185)
- Same fields as `SubscriptionPlanCreate` but all optional
- Same LemonSqueezy changes needed

**Estimated Effort:** Included in SubscriptionPlanCreate changes

---

**SubscriptionPlanResponse** (Lines 188-228)
```python
class SubscriptionPlanResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str]
    price_monthly: float
    price_yearly: float
    features: Dict[str, Any]
    max_workspaces: int
    max_members_per_workspace: int
    max_topics: int
    max_knowledge_items: int
    max_api_calls_per_month: int
    is_active: bool
    is_public: bool
    created_at: str
```

**LemonSqueezy Changes:** ⚠️ Add LemonSqueezy IDs
```python
# Add these fields:
lemonsqueezy_product_id: Optional[str] = None
lemonsqueezy_variant_id_monthly: Optional[str] = None
lemonsqueezy_variant_id_yearly: Optional[str] = None
lemonsqueezy_store_id: Optional[str] = None
```

**Estimated Effort:** 15 minutes

---

## New Endpoints Required

### 1. LemonSqueezy Webhook Handler

**Endpoint:** `POST /subscriptions/webhooks/lemonsqueezy`
**Purpose:** Handle all LemonSqueezy webhook events
**Authentication:** ❌ Not required (webhook signature verification)
**Authorization:** Signature verification using `X-Signature` header

**Implementation Requirements:**

1. **Signature Verification**:
   ```python
   async def verify_lemonsqueezy_signature(
       payload: bytes,
       signature: str,
       secret: str
   ) -> bool:
       # Use HMAC SHA-256 to verify signature
       # LemonSqueezy sends signature in X-Signature header
   ```

2. **Idempotency Check**:
   ```python
   # Check if event already processed
   event_id = webhook_data["meta"]["event_name"] + "_" + webhook_data["data"]["id"]

   # Query webhook_events table
   existing_event = await db.execute(
       select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
   )

   if existing_event:
       return {"status": "already_processed"}
   ```

3. **Event Routing**:
   ```python
   event_name = webhook_data["meta"]["event_name"]

   handlers = {
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
       "order_created": handle_order_created,
       "license_key_created": handle_license_created,
   }

   handler = handlers.get(event_name)
   if handler:
       await handler(webhook_data, db)
   ```

4. **Event Storage**:
   ```python
   # Store webhook event for idempotency
   webhook_event = WebhookEvent(
       provider="lemonsqueezy",
       provider_event_id=event_id,
       event_type=event_name,
       payload=webhook_data,
       processed_at=datetime.utcnow()
   )
   db.add(webhook_event)
   await db.commit()
   ```

**Request Headers:**
- `X-Signature`: HMAC SHA-256 signature of payload

**Request Body:**
```python
{
  "meta": {
    "event_name": "subscription_created",
    "custom_data": {...}
  },
  "data": {
    "type": "subscriptions",
    "id": "12345",
    "attributes": {
      "store_id": 67890,
      "customer_id": 123,
      "order_id": 456,
      "product_id": 789,
      "variant_id": 101,
      "product_name": "Pro Plan",
      "variant_name": "Monthly",
      "user_name": "John Doe",
      "user_email": "john@example.com",
      "status": "active",
      "status_formatted": "Active",
      "card_brand": "visa",
      "card_last_four": "4242",
      "pause": null,
      "cancelled": false,
      "trial_ends_at": null,
      "billing_anchor": 1,
      "urls": {
        "update_payment_method": "https://...",
        "customer_portal": "https://..."
      },
      "renews_at": "2025-11-17T00:00:00.000000Z",
      "ends_at": null,
      "created_at": "2025-10-17T00:00:00.000000Z",
      "updated_at": "2025-10-17T00:00:00.000000Z"
    }
  }
}
```

**Response:**
```python
{
  "status": "success",
  "message": "Webhook processed successfully"
}
```

**File Location:** `src/api/routes/subscriptions/webhook_routes.py` (replace mock handler)

**Estimated Effort:** 8-12 hours

**Dependencies:**
- `webhook_events` table created (Phase 1 migration)
- LemonSqueezy webhook secret configured in environment

---

### 2. License Validation Endpoint

**Endpoint:** `POST /subscriptions/licenses/validate`
**Purpose:** Validate license keys for one-time purchases
**Authentication:** ❌ Not required (license key is the authentication)
**Authorization:** Valid license key required

**Implementation Requirements:**

```python
class LicenseValidateRequest(BaseModel):
    license_key: str
    instance_id: Optional[str] = None  # For activation tracking

class LicenseValidateResponse(BaseModel):
    valid: bool
    license_id: str
    status: str  # "active", "inactive", "expired", "disabled"
    activation_limit: Optional[int]
    activation_usage: int
    expires_at: Optional[str]
    customer_email: str
    customer_name: str
```

**Request Body:**
```python
{
  "license_key": "XXXX-XXXX-XXXX-XXXX",
  "instance_id": "machine-identifier-123"  // Optional
}
```

**Response:**
```python
{
  "valid": true,
  "license_id": "UUID",
  "status": "active",
  "activation_limit": 5,
  "activation_usage": 2,
  "expires_at": "2026-10-17T00:00:00Z",
  "customer_email": "john@example.com",
  "customer_name": "John Doe"
}
```

**Validation Logic:**
1. Query `licenses` table by license_key
2. Check status == "active"
3. Check expires_at > now (if set)
4. Check activation_usage < activation_limit (if set)
5. If instance_id provided, track activation

**File Location:** `src/api/routes/subscriptions/license_routes.py` (new file)

**Estimated Effort:** 4-6 hours

**Dependencies:**
- `licenses` table created (Phase 1 migration)

---

## Route Security Analysis

### Authentication Methods

1. **JWT Bearer Token** (Most endpoints)
   - Validated by `get_current_user` dependency
   - Extracts user identity from token

2. **No Authentication** (Webhook endpoints, public endpoints)
   - `/subscriptions/plans/public` - Public pricing page data
   - `/subscriptions/webhooks/lemonsqueezy` - Signature verification instead

### Authorization Patterns

1. **Permission-Based** (User operations)
   - `@require_permissions("subscription.manage", workspace_scoped=False)`
   - Used for: subscribe, upgrade, cancel

2. **Admin-Only** (Plan management)
   - `await service.require_admin(user_id)`
   - Used for: create/update/delete plans

3. **User-Scoped** (View own data)
   - No explicit permission check
   - User can only view their own subscription/usage/trial status

### Webhook Security

**Current Implementation:**
- ❌ No signature verification
- ❌ No rate limiting
- ❌ No IP allowlist

**LemonSqueezy Requirements:**
- ✅ Signature verification using `X-Signature` header
- ✅ Idempotency using `webhook_events` table
- ⚠️ Consider rate limiting (optional)
- ⚠️ Consider IP allowlist (optional)

---

## Error Handling Patterns

### Decorator-Based Error Handling

All routes use `@db_transaction_handler` decorator:

```python
@db_transaction_handler("operation name", "success message", auto_commit=True|False)
```

**Features:**
- Automatic database transaction management
- Automatic error catching and formatting
- Consistent response structure
- Automatic rollback on errors

### Custom Exceptions

Routes raise custom exceptions:
- `ResourceNotFoundException` - 404 errors
- `ValidationException` - 400 errors
- `UnauthorizedException` - 401 errors
- `ForbiddenException` - 403 errors

### HTTP Status Codes

- `200 OK` - Successful GET requests
- `201 Created` - Successful POST create requests
- `400 Bad Request` - Validation errors
- `401 Unauthorized` - Missing/invalid authentication
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Unexpected errors

---

## Database Transaction Patterns

### Auto-Commit Enabled

Routes that modify data:
```python
@db_transaction_handler("create plan", auto_commit=True)
```

Used for:
- POST /subscriptions/subscribe
- POST /subscriptions/upgrade
- POST /subscriptions/cancel
- POST /subscriptions/plans
- PATCH /subscriptions/plans/{plan_id}
- DELETE /subscriptions/plans/{plan_id}
- POST /subscriptions/webhooks/mock/checkout-complete

### Auto-Commit Disabled (Read-Only)

Routes that only read data:
```python
@db_transaction_handler("get subscription", auto_commit=False)
```

Used for:
- GET /subscriptions/my-subscription
- GET /subscriptions/history
- GET /subscriptions/usage
- GET /subscriptions/trial-status
- GET /subscriptions/plans/public
- GET /subscriptions/plans
- GET /subscriptions/plans/{plan_id}

---

## Response Structure Standards

All routes use standardized response helpers:

### Success Response

```python
from src.utils.response_utils import success

return success(
    data={...},
    request=request,
    message="Operation successful"
)
```

Output:
```json
{
  "status": "success",
  "message": "Operation successful",
  "data": {...}
}
```

### Created Response

```python
from src.utils.response_utils import created

return created(
    data={...},
    request=request,
    message="Resource created"
)
```

Output (201 status):
```json
{
  "status": "success",
  "message": "Resource created",
  "data": {...}
}
```

---

## Integration Points Summary

### Endpoints with Payment Provider Integration

| Endpoint | Integration Type | Provider Method | Changes Needed |
|----------|-----------------|----------------|----------------|
| POST /subscriptions/subscribe | Direct | create_customer, create_checkout_session | ✅ None (via abstraction) |
| POST /subscriptions/upgrade | Direct | update_subscription | ✅ None (via abstraction) |
| POST /subscriptions/cancel | Direct | cancel_subscription | ✅ None (via abstraction) |
| POST /webhooks/mock/checkout-complete | Direct | Mock only | ⚠️ Complete replacement |

### Endpoints Requiring Response Enhancement

| Endpoint | Enhancement | Effort |
|----------|------------|--------|
| GET /subscriptions/my-subscription | Add LemonSqueezy fields | 30 min |
| GET /subscriptions/plans/public | Add variant IDs | 15 min |
| GET /subscriptions/plans | Add variant IDs | Included |
| GET /subscriptions/plans/{plan_id} | Add variant IDs | Included |

### Endpoints Requiring Schema Updates

| Endpoint | Schema | Changes | Effort |
|----------|--------|---------|--------|
| POST /subscriptions/plans | SubscriptionPlanCreate | Rename stripe → lemonsqueezy | 30 min |
| PATCH /subscriptions/plans/{plan_id} | SubscriptionPlanUpdate | Rename stripe → lemonsqueezy | Included |

---

## New Endpoints Summary

| Endpoint | Purpose | Effort | Dependencies |
|----------|---------|--------|--------------|
| POST /webhooks/lemonsqueezy | Handle LemonSqueezy webhooks | 8-12 hours | webhook_events table |
| POST /licenses/validate | Validate license keys | 4-6 hours | licenses table |

**Total New Endpoint Effort:** 12-18 hours

---

## Migration Checklist

### Phase 1: Pydantic Schema Updates

**File:** `src/api/schema/subscription/plan_schemas.py`

- [ ] Rename `stripe_price_id_monthly` → `lemonsqueezy_variant_id_monthly`
- [ ] Rename `stripe_price_id_yearly` → `lemonsqueezy_variant_id_yearly`
- [ ] Add `lemonsqueezy_product_id: Optional[str]`
- [ ] Add `lemonsqueezy_store_id: Optional[str]`
- [ ] Update `SubscriptionPlanCreate`
- [ ] Update `SubscriptionPlanUpdate`
- [ ] Update `SubscriptionPlanResponse`

**Estimated Effort:** 1 hour

---

**File:** `src/api/schema/subscription/user_subscription_schemas.py`

- [ ] Add `provider_order_id: Optional[str]` to `UserSubscriptionResponse`
- [ ] Add `provider_variant_id: Optional[str]` to `UserSubscriptionResponse`
- [ ] Add `cancel_at_period_end: bool` to `UserSubscriptionResponse`
- [ ] Add `renews_at: Optional[str]` to `UserSubscriptionResponse`
- [ ] Add `paused_at: Optional[str]` to `UserSubscriptionResponse`
- [ ] Add `card_brand: Optional[str]` to `UserSubscriptionResponse`
- [ ] Add `card_last_four: Optional[str]` to `UserSubscriptionResponse`
- [ ] Add `urls: Optional[Dict[str, str]]` to `UserSubscriptionResponse`

**Estimated Effort:** 1 hour

---

### Phase 2: Route Response Enhancements

**File:** `src/api/routes/subscriptions/subscription_routes.py`

- [ ] Update `get_my_subscription()` to include LemonSqueezy fields
- [ ] Update response serialization to include new fields

**Estimated Effort:** 30 minutes

---

**File:** `src/api/routes/subscriptions/plan_routes.py`

- [ ] Update `list_public_plans()` to include LemonSqueezy IDs
- [ ] Update `list_plans()` to include LemonSqueezy IDs
- [ ] Update `get_plan()` to include LemonSqueezy IDs

**Estimated Effort:** 30 minutes

---

### Phase 3: New Route Creation

**File:** `src/api/routes/subscriptions/webhook_routes.py`

- [ ] Remove mock webhook handler
- [ ] Create `verify_lemonsqueezy_signature()` helper
- [ ] Create `check_webhook_idempotency()` helper
- [ ] Create event handler functions (12 handlers)
- [ ] Create `POST /webhooks/lemonsqueezy` endpoint
- [ ] Add comprehensive error handling
- [ ] Add logging for debugging

**Estimated Effort:** 8-12 hours

---

**File:** `src/api/routes/subscriptions/license_routes.py` (NEW FILE)

- [ ] Create `LicenseValidateRequest` schema
- [ ] Create `LicenseValidateResponse` schema
- [ ] Create `POST /licenses/validate` endpoint
- [ ] Implement license validation logic
- [ ] Implement activation tracking (optional)
- [ ] Add rate limiting (optional)

**Estimated Effort:** 4-6 hours

---

### Phase 4: Testing

- [ ] Update existing route tests for schema changes
- [ ] Create webhook handler tests (all event types)
- [ ] Create license validation tests
- [ ] Integration tests with LemonSqueezy sandbox
- [ ] Test idempotency (duplicate webhook events)
- [ ] Test signature verification (valid/invalid)
- [ ] Test error handling paths

**Estimated Effort:** 6-8 hours

---

## Potential Issues & Risks

### 1. Webhook Signature Verification (Medium Risk)

**Issue:** LemonSqueezy signature format may differ from documentation
**Impact:** Webhooks rejected if signature verification fails
**Mitigation:**
- Test thoroughly in sandbox environment
- Add detailed logging for signature verification failures
- Implement fallback for development environment

**Estimated Fix:** 2 hours debugging

---

### 2. Idempotency Race Conditions (Medium Risk)

**Issue:** Multiple identical webhooks could arrive simultaneously
**Impact:** Duplicate subscription records created
**Mitigation:**
- Use database UNIQUE constraint on `webhook_events.provider_event_id`
- Catch IntegrityError and return success (already processed)
- Add row-level locking if needed

**Estimated Fix:** 1 hour

---

### 3. Schema Migration Backward Compatibility (Low Risk)

**Issue:** Renaming Pydantic fields breaks existing API clients
**Impact:** Frontend or API consumers break
**Mitigation:**
- Database schema already uses provider-agnostic names
- Only Pydantic schemas need updates
- Update frontend in same deployment

**Estimated Fix:** N/A (preventable with coordinated deployment)

---

### 4. Webhook Event Ordering (Low Risk)

**Issue:** Webhooks may arrive out of order (created → updated → cancelled)
**Impact:** Database state inconsistency
**Mitigation:**
- Use LemonSqueezy's `updated_at` timestamp to determine freshness
- Don't overwrite newer data with older data
- Add version/timestamp comparison in handlers

**Estimated Fix:** 2 hours

---

## Recommendations

### Immediate Actions (Phase 0 - Current)

1. ✅ **Complete this audit** - Document all routes and required changes
2. ⏭️ **Proceed to Task 0.1.5** - Review email templates

### Phase 1 Actions (Before LemonSqueezy Implementation)

1. **Refactor Pydantic schemas**
   - Rename all "stripe" references to "lemonsqueezy" or provider-agnostic names
   - Add LemonSqueezy-specific fields
   - Update OpenAPI documentation

2. **Plan webhook handler architecture**
   - Design event handler pattern (strategy or factory)
   - Plan error recovery strategy
   - Design monitoring/alerting for webhook failures

3. **Review security requirements**
   - Confirm signature verification algorithm
   - Plan rate limiting strategy
   - Consider IP allowlisting

### Phase 2 Actions (During LemonSqueezy Implementation)

1. **Implement webhook handler**
   - Start with signature verification
   - Add idempotency checks
   - Implement event routing
   - Create individual event handlers
   - Add comprehensive logging

2. **Implement license validation**
   - Create license routes file
   - Implement validation logic
   - Add activation tracking
   - Test with LemonSqueezy license keys

3. **Update existing routes**
   - Add LemonSqueezy fields to responses
   - Update route tests
   - Update API documentation

---

## Testing Strategy

### Unit Tests

**Route Tests:**
- Test each endpoint with valid/invalid inputs
- Test authentication/authorization
- Test error handling
- Mock service layer

**Schema Tests:**
- Test Pydantic model validation
- Test serialization/deserialization
- Test field constraints

**Estimated Effort:** 4 hours

---

### Integration Tests

**Webhook Handler Tests:**
- Test signature verification (valid/invalid)
- Test idempotency (duplicate events)
- Test all 12 event types
- Test error recovery
- Test database state after each event

**License Validation Tests:**
- Test valid license
- Test expired license
- Test activation limits
- Test invalid license key

**Estimated Effort:** 6 hours

---

### End-to-End Tests

**Full Subscription Flow:**
1. User subscribes to plan
2. Redirect to LemonSqueezy checkout
3. Complete checkout in sandbox
4. Webhook fires → subscription created
5. Verify subscription in database
6. Verify email sent
7. User views subscription in UI

**Estimated Effort:** 4 hours

---

## Success Criteria

This audit is considered complete when:

1. ✅ All subscription route files documented
2. ✅ All endpoints analyzed for LemonSqueezy integration
3. ✅ Pydantic schema changes documented
4. ✅ New endpoint specifications created
5. ✅ Migration checklist created
6. ✅ Security requirements documented
7. ✅ Testing strategy defined

---

## Appendix A: Complete Route List

### User Subscription Routes (7 endpoints)

1. `POST /subscriptions/subscribe` - Subscribe to plan
2. `GET /subscriptions/my-subscription` - Get current subscription
3. `GET /subscriptions/history` - Get subscription history
4. `POST /subscriptions/upgrade` - Upgrade/downgrade plan
5. `POST /subscriptions/cancel` - Cancel subscription
6. `GET /subscriptions/usage` - Get usage statistics
7. `GET /subscriptions/trial-status` - Get trial status

### Admin Plan Routes (6 endpoints)

8. `GET /subscriptions/plans/public` - List public plans (no auth)
9. `POST /subscriptions/plans` - Create plan (admin)
10. `GET /subscriptions/plans` - List plans (admin filters)
11. `GET /subscriptions/plans/{plan_id}` - Get plan details
12. `PATCH /subscriptions/plans/{plan_id}` - Update plan (admin)
13. `DELETE /subscriptions/plans/{plan_id}` - Delete plan (admin)

### Webhook Routes (1 endpoint + 1 new)

14. `POST /subscriptions/webhooks/mock/checkout-complete` - Mock webhook (to be removed)
15. `POST /subscriptions/webhooks/lemonsqueezy` - LemonSqueezy webhook (NEW)

### License Routes (1 new)

16. `POST /subscriptions/licenses/validate` - Validate license key (NEW)

**Total:** 13 existing + 3 new = 16 endpoints

---

## Appendix B: File Locations

```
wrext-backend/
└── src/
    └── api/
        ├── routes/
        │   └── subscriptions/
        │       ├── __init__.py
        │       ├── subscription_routes.py         (345 lines) ✅ 7 endpoints
        │       ├── plan_routes.py                 (161 lines) ✅ 6 endpoints
        │       ├── webhook_routes.py              (191 lines) ⚠️ Replace mock handler
        │       └── license_routes.py              ❌ To be created
        └── schema/
            └── subscription/
                ├── __init__.py
                ├── user_subscription_schemas.py   (107 lines) ⚠️ Add LemonSqueezy fields
                ├── plan_schemas.py                (229 lines) ⚠️ Rename stripe → lemonsqueezy
                └── enums.py                       ✅ No changes needed
```

---

## Appendix C: LemonSqueezy Webhook Event Types

### Subscription Events

1. **subscription_created** - New subscription created
2. **subscription_updated** - Subscription details changed (plan, billing period, etc.)
3. **subscription_cancelled** - Subscription cancelled (will end at period end)
4. **subscription_resumed** - Cancelled subscription resumed
5. **subscription_expired** - Subscription ended (trial or billing period)
6. **subscription_paused** - Subscription paused (payment failed, user requested)
7. **subscription_unpaused** - Paused subscription resumed

### Payment Events

8. **subscription_payment_success** - Payment succeeded
9. **subscription_payment_failed** - Payment failed
10. **subscription_payment_recovered** - Failed payment recovered

### License Events

11. **order_created** - One-time purchase completed
12. **license_key_created** - License key generated for order

---

## Appendix D: Webhook Handler Pseudocode

```python
@router.post("/webhooks/lemonsqueezy")
async def handle_lemonsqueezy_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    # 1. Read raw body
    payload = await request.body()

    # 2. Verify signature
    signature = request.headers.get("X-Signature")
    if not await verify_signature(payload, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 3. Parse JSON
    webhook_data = json.loads(payload)

    # 4. Check idempotency
    event_id = f"{webhook_data['meta']['event_name']}_{webhook_data['data']['id']}"
    if await event_already_processed(event_id, db):
        return {"status": "already_processed"}

    # 5. Route to handler
    event_name = webhook_data["meta"]["event_name"]
    handler = get_handler(event_name)
    await handler(webhook_data, db)

    # 6. Store event
    await store_webhook_event(event_id, event_name, webhook_data, db)

    # 7. Return success
    return {"status": "success"}
```

---

## Conclusion

The subscription routes architecture is well-structured with clear separation of concerns:

1. **✅ Clean Route Organization**: User routes, admin routes, and webhooks separated
2. **✅ Consistent Patterns**: All routes use decorators, standard responses, and error handling
3. **⚠️ Minor Schema Issues**: Stripe naming in Pydantic schemas (easy fix)
4. **⚠️ Mock Webhook Handler**: Needs complete replacement with LemonSqueezy handler
5. **✅ No Breaking Changes**: Existing endpoints work as-is with schema updates

**Overall Assessment:** The route layer is production-ready and follows best practices. LemonSqueezy integration requires minimal changes to existing endpoints (mostly schema updates) plus creation of 2 new endpoints (webhook handler, license validation).

**Total Implementation Effort:**
- Schema updates: 2.5 hours
- Response enhancements: 1 hour
- New webhook handler: 8-12 hours
- New license endpoint: 4-6 hours
- Testing: 10-14 hours
- **Total: 25.5-35.5 hours**

**Next Steps:**
- ✅ Mark Task 0.1.4 as complete
- ⏭️ Proceed to Task 0.1.5: Review email templates

---

**Document Version:** 1.0
**Last Updated:** 2025-10-17
**Status:** ✅ Complete
