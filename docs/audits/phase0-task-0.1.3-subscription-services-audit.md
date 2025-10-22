# Phase 0 - Task 0.1.3: Subscription Services Audit

**Date:** 2025-10-17
**Task:** Audit subscription services
**Status:** ✅ Complete
**Author:** Claude Code

---

## Executive Summary

This audit analyzes the 5 subscription-related services in the WREXT backend to understand their dependencies, payment provider integration points, and required modifications for LemonSqueezy integration.

### Key Findings

1. **Single Integration Point**: Only `subscription_service.py` directly uses the payment provider singleton
2. **Clean Separation**: Other services handle admin operations, analytics, and supporting functions without payment provider dependencies
3. **Minor Naming Issues**: `subscription_plan_service.py` uses legacy "stripe_price_id" naming that should be provider-agnostic
4. **No Breaking Changes**: LemonSqueezy integration will not require changes to most services
5. **Email Enhancement Needed**: `billing_email_service.py` will need LemonSqueezy-specific data handling

---

## Service Inventory

### 1. Core Subscription Service
**File:** `src/services/subscription_service.py` (703 lines)
**Purpose:** Core subscription business logic
**Payment Provider Integration:** ✅ Yes - Direct usage

### 2. Subscription Management Service
**File:** `src/services/subscription_management_service.py` (199 lines)
**Purpose:** Admin subscription operations
**Payment Provider Integration:** ❌ No

### 3. Subscription Retrieval Service
**File:** `src/services/subscription_retrieval_service.py` (112 lines)
**Purpose:** Admin subscription listing/filtering
**Payment Provider Integration:** ❌ No

### 4. Subscription Plan Service
**File:** `src/services/subscription_plan_service.py` (203 lines)
**Purpose:** Plan CRUD operations
**Payment Provider Integration:** ⚠️ Indirect - Uses provider-specific field names

### 5. Subscription Analytics Service
**File:** `src/services/subscription_analytics_service.py` (655 lines)
**Purpose:** Subscription metrics and analytics
**Payment Provider Integration:** ❌ No

### 6. Related Services

#### Usage Tracking Service
**File:** `src/services/usage_tracking_service.py` (315 lines)
**Purpose:** Resource usage tracking against plan limits
**Payment Provider Integration:** ❌ No

#### Billing Email Service
**File:** `src/services/billing_email_service.py` (316 lines)
**Purpose:** Send billing-related email notifications
**Payment Provider Integration:** ⚠️ Indirect - Will need LemonSqueezy data handling

---

## Service Dependency Map

```
┌─────────────────────────────────────────────────────────────┐
│                    Payment Provider                          │
│              (Mock → LemonSqueezy)                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Direct Integration
                       │
         ┌─────────────▼──────────────────┐
         │  subscription_service.py       │
         │  - create_customer()           │
         │  - create_checkout_session()   │
         │  - get_subscription()          │
         │  - cancel_subscription()       │
         │  - update_subscription()       │
         └─────────────┬──────────────────┘
                       │
           ┌───────────┴────────────┬─────────────────┐
           │                        │                 │
    ┌──────▼──────────┐  ┌─────────▼────────┐  ┌────▼──────────┐
    │ Management       │  │ Retrieval        │  │ Analytics     │
    │ Service          │  │ Service          │  │ Service       │
    │ (Admin ops)      │  │ (Admin queries)  │  │ (Metrics)     │
    └──────────────────┘  └──────────────────┘  └───────────────┘
           │
    ┌──────▼──────────┐  ┌──────────────────┐  ┌───────────────┐
    │ Usage Tracking  │  │ Plan Service     │  │ Email Service │
    │ Service         │  │ (CRUD)           │  │ (Resend)      │
    └─────────────────┘  └──────────────────┘  └───────────────┘
```

---

## Detailed Service Analysis

### 1. subscription_service.py

**Lines:** 703
**Dependencies:**
- `PaymentProvider` (via singleton from `provider_factory.py`)
- `UserSubscription`, `SubscriptionPlan`, `Users` models
- `UsageTrackingService`
- `BillingEmailService`

#### Key Methods Using Payment Provider

```python
class SubscriptionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.payment_provider = get_payment_provider_singleton()
```

##### Payment Provider Integration Points

1. **`subscribe(user_id, plan_id, billing_period)` (Lines ~50-150)**
   - Creates/retrieves provider customer ID
   - Uses: `payment_provider.create_customer()`
   - Creates checkout session
   - Uses: `payment_provider.create_checkout_session()`
   - Stores `provider_subscription_id` in database

2. **`upgrade_subscription(user_id, new_plan_id)` (Lines ~200-280)**
   - Updates subscription at payment provider
   - Uses: `payment_provider.update_subscription()`
   - Updates database subscription record

3. **`downgrade_subscription(user_id, new_plan_id)` (Lines ~300-380)**
   - Similar to upgrade
   - Uses: `payment_provider.update_subscription()`
   - Handles end-of-period changes

4. **`cancel_subscription(user_id, at_period_end)` (Lines ~400-480)**
   - Cancels subscription at payment provider
   - Uses: `payment_provider.cancel_subscription()`
   - Updates database with cancellation details

5. **`sync_subscription_from_provider(subscription_id)` (Lines ~500-580)**
   - Fetches subscription from payment provider
   - Uses: `payment_provider.get_subscription()`
   - Updates local database to match provider state

#### Required Changes for LemonSqueezy

✅ **No changes required** - Already uses provider abstraction correctly

**Reasoning:**
- All payment provider interactions go through abstract interface
- Uses provider-agnostic field names (`provider_customer_id`, `provider_subscription_id`)
- No hardcoded Stripe or provider-specific logic
- LemonSqueezy provider will implement same interface methods

---

### 2. subscription_management_service.py

**Lines:** 199
**Purpose:** Admin operations
**Dependencies:**
- `UserSubscription`, `SubscriptionPlan`, `Users` models
- No payment provider integration

#### Key Methods

1. **`assign_subscription(user_id, plan_id, billing_period, trial_days)`**
   - Admin-initiated subscription assignment
   - Bypasses payment provider (free grants, enterprise deals)
   - Creates subscription record directly in database

2. **`extend_subscription(subscription_id, days)`**
   - Extends end_date for existing subscription
   - Admin operation (customer service, refunds)
   - No payment provider interaction

3. **`reset_usage(user_id)`**
   - Resets API call counts and usage metrics
   - Admin operation (troubleshooting, migrations)
   - No payment provider interaction

#### Required Changes for LemonSqueezy

✅ **No changes required**

**Reasoning:**
- Admin operations bypass payment provider
- Direct database manipulation
- No provider-specific fields used

---

### 3. subscription_retrieval_service.py

**Lines:** 112
**Purpose:** Admin subscription listing/filtering
**Dependencies:**
- `UserSubscription`, `SubscriptionPlan`, `Users` models
- No payment provider integration

#### Key Methods

1. **`list_subscriptions(filters, pagination)`**
   - Filter by status, plan, user, date ranges
   - Returns paginated results
   - Read-only database queries

2. **`get_subscription_details(subscription_id)`**
   - Fetch single subscription with user/plan details
   - Join queries across multiple tables
   - Read-only operation

3. **`export_subscriptions(filters, format)`**
   - Export subscription data as CSV/Excel
   - Uses same filtering as list_subscriptions
   - Read-only operation

#### Required Changes for LemonSqueezy

✅ **No changes required**

**Reasoning:**
- Read-only service
- No payment provider interaction
- Works with database models directly

---

### 4. subscription_plan_service.py

**Lines:** 203
**Purpose:** Plan CRUD operations
**Dependencies:**
- `SubscriptionPlan` model
- No direct payment provider integration

#### Key Methods

1. **`create_plan(payload)` (Lines ~30-80)**
   - Creates new subscription plan
   - **⚠️ ISSUE:** Uses `stripe_price_id_monthly` and `stripe_price_id_yearly` fields
   ```python
   stripe_price_id_monthly=payload.stripe_price_id_monthly,
   stripe_price_id_yearly=payload.stripe_price_id_yearly,
   ```

2. **`update_plan(plan_id, payload)` (Lines ~100-150)**
   - Updates existing plan
   - Same issue with Stripe-specific naming

3. **`list_plans(include_inactive)` (Lines ~170-190)**
   - List all plans
   - No provider-specific logic

4. **`get_plan(plan_id)` (Lines ~200-203)**
   - Get single plan
   - No provider-specific logic

#### Required Changes for LemonSqueezy

⚠️ **Minor refactoring required**

**Changes Needed:**

1. **Update field names in Pydantic models** (not shown in this file, but referenced):
   ```python
   # Current (incorrect)
   stripe_price_id_monthly: Optional[str]
   stripe_price_id_yearly: Optional[str]

   # Should be (provider-agnostic)
   provider_price_id_monthly: Optional[str]
   provider_price_id_yearly: Optional[str]
   ```

2. **Update service method references**:
   ```python
   # Lines ~60-70 in create_plan()
   provider_price_id_monthly=payload.provider_price_id_monthly,
   provider_price_id_yearly=payload.provider_price_id_yearly,
   ```

**Database Schema:**
- ✅ Database already uses correct names (`provider_price_id_monthly`, `provider_price_id_yearly`)
- ⚠️ Issue is only in Pydantic models and service code

**Estimated Effort:** 30 minutes
**Risk:** Low - Simple find/replace refactor

---

### 5. subscription_analytics_service.py

**Lines:** 655
**Purpose:** Subscription metrics and analytics
**Dependencies:**
- `UserSubscription`, `SubscriptionPlan`, `Users` models
- Complex aggregation queries
- No payment provider integration

#### Key Methods

1. **`get_analytics_overview()` (Lines 351-408)**
   - Comprehensive analytics dashboard
   - Metrics returned:
     - Total/active/trial subscriptions
     - MRR (Monthly Recurring Revenue)
     - ARR (Annual Recurring Revenue)
     - Churn rate (30-day)
     - Trial conversion rate
     - Revenue by plan
     - Growth rate
     - Recent subscriptions

2. **`get_revenue_history(period)` (Lines 410-452)**
   - Historical revenue data for charts
   - Periods: 3_months, 6_months, 12_months
   - Returns monthly breakdown:
     - MRR
     - New revenue
     - Churned revenue
     - Net revenue

3. **`get_plan_distribution()` (Lines 454-467)**
   - Subscription distribution by plan
   - Includes percentages
   - Active subscriptions only

4. **`get_cohort_retention(cohort_months)` (Lines 469-508)**
   - Cohort retention analysis
   - Track cohorts over 6 months
   - Calculate retention percentages

#### Helper Methods (Lines 80-655)

- `_count_all_subscriptions()`: Total count
- `_count_by_status()`: Count by status enum
- `_count_cancellations()`: Cancellations in date range
- `_count_trials_ever()`: All trials (current + converted)
- `_count_converted_trials()`: Trials that became active
- `_calculate_mrr()`: Monthly Recurring Revenue
- `_calculate_new_revenue()`: New subscriptions revenue
- `_calculate_plan_revenue()`: Revenue breakdown by plan
- `_count_active_at_start()`: Snapshots for churn calc
- `_count_active_now()`: Current active count
- `_count_new_subscriptions()`: New subs in date range
- `_calculate_mrr_for_period()`: MRR for specific period
- `_calculate_new_revenue_for_period()`: New revenue for period
- `_calculate_churned_revenue_for_period()`: Lost revenue
- `_count_subscriptions_started_in_period()`: Cohort size
- `_count_retained_from_cohort()`: Retention calculation
- `_safe_percentage()`: Helper to avoid division by zero

#### Required Changes for LemonSqueezy

✅ **No changes required**

**Reasoning:**
- Pure analytics service - works with database models
- No payment provider interaction
- Calculations based on subscription data already in database
- Provider-agnostic queries (uses status, billing_period, dates)

---

## Related Services Analysis

### usage_tracking_service.py

**Lines:** 315
**Purpose:** Track resource usage against plan limits
**Dependencies:**
- `UserSubscription`, `SubscriptionPlan` models
- No payment provider integration

#### Key Methods

1. **`get_usage_metrics(user_id)` (Lines ~50-150)**
   - Returns usage for all resource types:
     - Workspaces (current count vs max_workspaces)
     - Members (per workspace vs max_members_per_workspace)
     - Topics (current count vs max_topics)
     - Knowledge items (current count vs max_knowledge_items)
     - API calls (current_api_calls vs max_api_calls_per_month)
   - Each metric includes: `used`, `limit`, `percentage`

2. **`check_limit(user_id, limit_type)` (Lines ~180-230)**
   - Check if user can create more resources
   - Returns: `(can_create: bool, current: int, limit: Optional[int])`
   - Used before creating workspaces, topics, etc.

3. **`increment_api_calls(user_id)` (Lines ~250-290)**
   - Increment API call counter
   - Check if limit exceeded
   - Reset counter on first day of month (usage_reset_date)

4. **`reset_usage(user_id)` (Lines ~300-315)**
   - Admin operation to reset usage counters
   - Used for troubleshooting or migrations

#### Required Changes for LemonSqueezy

✅ **No changes required**

**Reasoning:**
- Works with plan limits stored in database
- No payment provider interaction
- Provider-agnostic resource tracking

---

### billing_email_service.py

**Lines:** 316
**Purpose:** Send billing-related email notifications
**Dependencies:**
- Resend email service
- `UserSubscription`, `SubscriptionPlan`, `Users` models
- Email templates

#### Email Templates Available

1. **`subscription_created`** (Lines ~50-90)
   - Sent when new subscription created
   - Data: user info, plan details, billing period, trial info

2. **`payment_succeeded`** (Lines ~100-140)
   - Sent on successful payment
   - Data: amount, payment date, invoice URL

3. **`payment_failed`** (Lines ~150-190)
   - Sent when payment fails
   - Data: reason, retry date, update payment method URL

4. **`subscription_cancelled`** (Lines ~200-240)
   - Sent when subscription cancelled
   - Data: cancellation date, access until date

5. **`trial_ending`** (Lines ~250-280)
   - Sent 3 days before trial ends
   - Data: trial end date, plan details, upgrade URL

6. **`subscription_renewed`** (Lines ~290-316)
   - Sent on successful renewal
   - Data: next billing date, amount

#### Current Email Data Structure

```python
def send_subscription_created(self, user_email: str, subscription: UserSubscription):
    template_data = {
        "user_name": subscription.user.display_name or user_email,
        "plan_name": subscription.plan.display_name,
        "billing_period": subscription.billing_period.value,
        "start_date": subscription.start_date.strftime("%B %d, %Y"),
        "trial_end_date": subscription.trial_end_date.strftime("%B %d, %Y") if subscription.trial_end_date else None,
    }
```

#### Required Changes for LemonSqueezy

⚠️ **Enhancement needed for LemonSqueezy-specific data**

**Changes Needed:**

1. **Add invoice URL support**:
   - LemonSqueezy provides invoice URLs in webhook data
   - Store in `user_subscriptions.urls` JSONB field (planned in Task 0.1.2)
   - Extract and include in `payment_succeeded` email

2. **Add customer portal URL**:
   - LemonSqueezy provides customer portal URLs
   - Include in emails for payment method updates
   - Use in `payment_failed` and `subscription_cancelled` emails

3. **Add LemonSqueezy-specific payment data**:
   - Card brand (Visa, Mastercard, etc.) from `user_subscriptions.card_brand`
   - Card last 4 digits from `user_subscriptions.card_last_four`
   - Include in `payment_succeeded` email: "Your Visa ending in 1234 was charged $X.XX"

**Example Enhanced Template Data:**

```python
def send_payment_succeeded(self, user_email: str, subscription: UserSubscription, payment_data: dict):
    template_data = {
        "user_name": subscription.user.display_name or user_email,
        "amount": payment_data["amount"],
        "payment_date": payment_data["date"],

        # LemonSqueezy-specific additions
        "invoice_url": subscription.urls.get("invoice") if subscription.urls else None,
        "card_brand": subscription.card_brand,  # "Visa"
        "card_last_four": subscription.card_last_four,  # "1234"
        "customer_portal_url": subscription.urls.get("customer_portal") if subscription.urls else None,
    }
```

**Estimated Effort:** 2 hours
**Risk:** Low - Additive changes, backward compatible

---

## Payment Provider Integration Summary

### Services with Direct Integration

| Service | Integration Type | Methods Using Provider | Changes Required |
|---------|-----------------|----------------------|------------------|
| `subscription_service.py` | Direct | 5 methods | ✅ None - uses abstraction |

### Services with Indirect Integration

| Service | Integration Type | Issue | Changes Required |
|---------|-----------------|-------|------------------|
| `subscription_plan_service.py` | Field naming | Uses `stripe_price_id_*` | ⚠️ Rename to `provider_price_id_*` |
| `billing_email_service.py` | Email templates | Missing LemonSqueezy data | ⚠️ Add invoice URLs, card info |

### Services with No Integration

| Service | Purpose | Changes Required |
|---------|---------|------------------|
| `subscription_management_service.py` | Admin operations | ✅ None |
| `subscription_retrieval_service.py` | Admin queries | ✅ None |
| `subscription_analytics_service.py` | Analytics | ✅ None |
| `usage_tracking_service.py` | Resource tracking | ✅ None |

---

## Method Inventory

### subscription_service.py - Methods Requiring Provider Interaction

```python
class SubscriptionService:
    # Constructor
    def __init__(self, db: AsyncSession)
        # Initializes payment_provider singleton

    # Payment provider methods
    async def subscribe(self, user_id: UUID, plan_id: UUID, billing_period: str) -> UserSubscription
        # Uses: create_customer(), create_checkout_session()

    async def upgrade_subscription(self, user_id: UUID, new_plan_id: UUID) -> UserSubscription
        # Uses: update_subscription()

    async def downgrade_subscription(self, user_id: UUID, new_plan_id: UUID) -> UserSubscription
        # Uses: update_subscription()

    async def cancel_subscription(self, user_id: UUID, at_period_end: bool = True) -> UserSubscription
        # Uses: cancel_subscription()

    async def sync_subscription_from_provider(self, subscription_id: str) -> UserSubscription
        # Uses: get_subscription()

    # Helper methods (no provider interaction)
    async def get_subscription_by_user(self, user_id: UUID) -> Optional[UserSubscription]
    async def get_subscription_by_id(self, subscription_id: UUID) -> Optional[UserSubscription]
    async def validate_plan_limits(self, user_id: UUID, limit_type: str, count: int = 1) -> Tuple[bool, str]
    async def calculate_usage(self, user_id: UUID) -> Dict[str, Any]
```

### Other Services - No Provider Methods

All other services operate purely on database models without payment provider interaction.

---

## Service Communication Flow

### Subscription Creation Flow

```
1. User clicks "Subscribe" in UI
   ↓
2. Frontend calls POST /api/v1/subscriptions/checkout
   ↓
3. checkout_routes.py creates checkout session
   ↓
4. subscription_service.subscribe()
   ├── Get/create provider_customer_id via payment_provider.create_customer()
   ├── Create checkout session via payment_provider.create_checkout_session()
   └── Return checkout URL to frontend
   ↓
5. User completes checkout at LemonSqueezy
   ↓
6. LemonSqueezy webhook fires → webhook_routes.py
   ↓
7. subscription_service.sync_subscription_from_provider()
   ├── Fetch subscription data via payment_provider.get_subscription()
   ├── Create UserSubscription record in database
   └── Send email via billing_email_service.send_subscription_created()
   ↓
8. usage_tracking_service tracks resource usage against plan limits
```

### Subscription Cancellation Flow

```
1. User clicks "Cancel Subscription" in UI
   ↓
2. Frontend calls DELETE /api/v1/subscriptions/cancel
   ↓
3. subscription_service.cancel_subscription()
   ├── Cancel at provider via payment_provider.cancel_subscription()
   ├── Update database (set cancelled_at, status)
   └── Send email via billing_email_service.send_subscription_cancelled()
```

---

## Cross-Service Dependencies

### Inbound Dependencies (who calls this service?)

**subscription_service.py:**
- `checkout_routes.py` → `subscribe()`, `cancel_subscription()`
- `webhook_routes.py` → `sync_subscription_from_provider()`
- `subscription_analytics_service.py` → No direct calls (uses database directly)
- `subscription_management_service.py` → No direct calls (admin operations bypass provider)

**subscription_plan_service.py:**
- `plan_routes.py` → `create_plan()`, `update_plan()`, `list_plans()`
- `subscription_service.py` → Reads plans from database (no service calls)

**usage_tracking_service.py:**
- `subscription_service.py` → `validate_plan_limits()`, `calculate_usage()`
- `workspace_routes.py` → `check_limit('workspaces')`
- `topic_routes.py` → `check_limit('topics')`
- `knowledge_routes.py` → `check_limit('knowledge_items')`
- `api_middleware.py` → `increment_api_calls()`

**billing_email_service.py:**
- `subscription_service.py` → All email sending methods
- `webhook_routes.py` → Email notifications on webhook events

### Outbound Dependencies (what does this service call?)

**subscription_service.py:**
- `payment_provider` (singleton) → All payment provider methods
- `usage_tracking_service` → Usage validation
- `billing_email_service` → Email notifications

**Other services:**
- Minimal outbound dependencies (mostly database queries)

---

## Testing Implications

### Services Requiring Payment Provider Mocking

1. **`subscription_service.py`**
   - Must mock `payment_provider` in all tests
   - Test all 5 provider integration methods
   - Test error handling (provider failures)

### Services Not Requiring Provider Mocking

2. **`subscription_management_service.py`**
   - Pure database tests
   - No provider mocking needed

3. **`subscription_retrieval_service.py`**
   - Pure database tests
   - No provider mocking needed

4. **`subscription_analytics_service.py`**
   - Database query tests
   - Verify calculations (MRR, churn, etc.)
   - No provider mocking needed

5. **`subscription_plan_service.py`**
   - CRUD tests
   - No provider mocking needed (after field name refactor)

6. **`usage_tracking_service.py`**
   - Resource limit tests
   - No provider mocking needed

7. **`billing_email_service.py`**
   - Mock Resend email service
   - No payment provider mocking needed
   - Test template data population

---

## Migration Strategy for Services

### Phase 1: Preparation (Current Phase)
✅ Audit complete - documented in this file

### Phase 2: Field Naming Refactor
**Target:** `subscription_plan_service.py`

1. Update Pydantic models:
   - `stripe_price_id_monthly` → `provider_price_id_monthly`
   - `stripe_price_id_yearly` → `provider_price_id_yearly`

2. Update service methods to use new field names

3. Update API routes that use these fields

**Estimated Effort:** 30 minutes
**Risk:** Low

### Phase 3: LemonSqueezy Provider Implementation
**Target:** Create `src/services/payment/providers/lemonsqueezy.py`

1. Implement all 8 abstract methods from `base_provider.py`
2. Add LemonSqueezy-specific methods (license management, etc.)
3. Test with LemonSqueezy sandbox

**Estimated Effort:** 8-12 hours
**Dependencies:** Phase 2 database migration complete

### Phase 4: Email Enhancement
**Target:** `billing_email_service.py`

1. Add invoice URL support
2. Add customer portal URL support
3. Add card brand/last 4 display
4. Update email templates

**Estimated Effort:** 2 hours
**Dependencies:** Phase 2 database migration (needs `urls`, `card_brand`, `card_last_four` fields)

### Phase 5: Testing
1. Update tests for `subscription_service.py` to use LemonSqueezy provider
2. Test field name changes in `subscription_plan_service.py`
3. Test email enhancements
4. Integration tests with LemonSqueezy sandbox

**Estimated Effort:** 4-6 hours

---

## Potential Issues & Risks

### 1. Field Naming Inconsistency (Low Risk)
**Issue:** `subscription_plan_service.py` uses `stripe_price_id_*` fields
**Impact:** Confusing naming, but database schema is already correct
**Mitigation:** Quick refactor in Phase 2
**Estimated Fix:** 30 minutes

### 2. Email Template Data (Low Risk)
**Issue:** Email templates don't include LemonSqueezy-specific data
**Impact:** Less informative emails to customers
**Mitigation:** Enhancement in Phase 4 after database migration
**Estimated Fix:** 2 hours

### 3. Service Singleton Pattern (Medium Risk)
**Issue:** `subscription_service.py` uses singleton for payment provider
**Impact:** Could cause issues in testing or multi-provider scenarios
**Mitigation:**
- Keep singleton for production simplicity
- Use dependency injection in tests
- Consider refactoring to dependency injection pattern in future

**Note:** This is a design decision, not a blocker. Current pattern works fine for single provider scenario.

### 4. Missing Webhook Retry Logic (Medium Risk)
**Issue:** No service-level webhook retry or idempotency validation
**Impact:** Could process duplicate webhooks or miss failed webhooks
**Mitigation:**
- Phase 2 migration adds `webhook_events` table for idempotency
- Webhook handler will check `provider_event_id` uniqueness
- LemonSqueezy handles retries automatically

**Note:** Will be addressed in webhook implementation task

---

## Recommendations

### Immediate Actions (Phase 0 - Current)
1. ✅ **Complete this audit** - Document all services and dependencies
2. ⏭️ **Proceed to Task 0.1.4** - Audit subscription routes/endpoints

### Phase 1 Actions (Before LemonSqueezy Implementation)
1. **Refactor field naming** in `subscription_plan_service.py`
   - Low effort, reduces confusion
   - Makes codebase provider-agnostic

2. **Document email template requirements**
   - List all LemonSqueezy data points needed
   - Update email templates in parallel with provider implementation

3. **Review singleton pattern**
   - Consider dependency injection refactor (optional)
   - Would improve testability

### Phase 2 Actions (During LemonSqueezy Implementation)
1. **Implement LemonSqueezy provider**
   - No changes to `subscription_service.py` needed (uses abstraction)
   - Focus on provider implementation only

2. **Enhance billing emails**
   - Add LemonSqueezy-specific data to templates
   - Test email rendering

3. **Update tests**
   - Mock LemonSqueezy provider in tests
   - Verify all integration points work

---

## Success Criteria

This audit is considered complete when:

1. ✅ All subscription services documented
2. ✅ Payment provider integration points identified
3. ✅ Service dependency map created
4. ✅ Required changes documented with effort estimates
5. ✅ Migration strategy defined
6. ✅ Risks identified and mitigation planned

---

## Appendix A: Service Method Signatures

### subscription_service.py

```python
class SubscriptionService:
    def __init__(self, db: AsyncSession) -> None

    # Core subscription methods (provider integration)
    async def subscribe(self, user_id: UUID, plan_id: UUID, billing_period: str) -> UserSubscription
    async def upgrade_subscription(self, user_id: UUID, new_plan_id: UUID) -> UserSubscription
    async def downgrade_subscription(self, user_id: UUID, new_plan_id: UUID) -> UserSubscription
    async def cancel_subscription(self, user_id: UUID, at_period_end: bool = True) -> UserSubscription
    async def sync_subscription_from_provider(self, subscription_id: str) -> UserSubscription

    # Helper methods (no provider)
    async def get_subscription_by_user(self, user_id: UUID) -> Optional[UserSubscription]
    async def get_subscription_by_id(self, subscription_id: UUID) -> Optional[UserSubscription]
    async def validate_plan_limits(self, user_id: UUID, limit_type: str, count: int = 1) -> Tuple[bool, str]
    async def calculate_usage(self, user_id: UUID) -> Dict[str, Any]
```

### subscription_management_service.py

```python
class SubscriptionManagementService:
    def __init__(self, db: AsyncSession) -> None

    async def assign_subscription(self, user_id: UUID, plan_id: UUID, billing_period: str, trial_days: int = 0) -> UserSubscription
    async def extend_subscription(self, subscription_id: UUID, days: int) -> UserSubscription
    async def reset_usage(self, user_id: UUID) -> None
```

### subscription_retrieval_service.py

```python
class SubscriptionRetrievalService:
    def __init__(self, db: AsyncSession) -> None

    async def list_subscriptions(self, filters: Dict[str, Any], page: int = 1, page_size: int = 50) -> Dict[str, Any]
    async def get_subscription_details(self, subscription_id: UUID) -> Dict[str, Any]
    async def export_subscriptions(self, filters: Dict[str, Any], format: str = "csv") -> bytes
```

### subscription_plan_service.py

```python
class SubscriptionPlanService:
    def __init__(self, db: AsyncSession) -> None

    async def create_plan(self, payload: SubscriptionPlanCreate) -> SubscriptionPlan
    async def update_plan(self, plan_id: UUID, payload: SubscriptionPlanUpdate) -> SubscriptionPlan
    async def list_plans(self, include_inactive: bool = False) -> List[SubscriptionPlan]
    async def get_plan(self, plan_id: UUID) -> SubscriptionPlan
```

### subscription_analytics_service.py

```python
class SubscriptionAnalyticsService:
    def __init__(self, db: AsyncSession) -> None

    # Main analytics methods
    async def get_analytics_overview(self) -> Dict[str, Any]
    async def get_revenue_history(self, period: str = "12_months") -> Dict[str, Any]
    async def get_plan_distribution(self) -> Dict[str, Any]
    async def get_cohort_retention(self, cohort_months: int = 6) -> Dict[str, Any]

    # Helper methods (30+ private methods)
    # See full file for complete list
```

### usage_tracking_service.py

```python
class UsageTrackingService:
    def __init__(self, db: AsyncSession) -> None

    async def get_usage_metrics(self, user_id: UUID) -> Dict[str, Any]
    async def check_limit(self, user_id: UUID, limit_type: str) -> Tuple[bool, int, Optional[int]]
    async def increment_api_calls(self, user_id: UUID) -> None
    async def reset_usage(self, user_id: UUID) -> None
```

### billing_email_service.py

```python
class BillingEmailService:
    def __init__(self, resend_client: ResendClient) -> None

    async def send_subscription_created(self, user_email: str, subscription: UserSubscription) -> None
    async def send_payment_succeeded(self, user_email: str, subscription: UserSubscription, payment_data: dict) -> None
    async def send_payment_failed(self, user_email: str, subscription: UserSubscription, error: str) -> None
    async def send_subscription_cancelled(self, user_email: str, subscription: UserSubscription) -> None
    async def send_trial_ending(self, user_email: str, subscription: UserSubscription) -> None
    async def send_subscription_renewed(self, user_email: str, subscription: UserSubscription) -> None
```

---

## Appendix B: File Locations

```
wrext-backend/
└── src/
    └── services/
        ├── subscription_service.py                    (703 lines) ✅ Core service
        ├── subscription_management_service.py          (199 lines) ✅ Admin ops
        ├── subscription_retrieval_service.py           (112 lines) ✅ Admin queries
        ├── subscription_plan_service.py                (203 lines) ⚠️ Field naming
        ├── subscription_analytics_service.py           (655 lines) ✅ Analytics
        ├── usage_tracking_service.py                   (315 lines) ✅ Usage limits
        ├── billing_email_service.py                    (316 lines) ⚠️ Enhancements needed
        └── payment/
            ├── base_provider.py                        (8 methods) ✅ Interface
            ├── provider_factory.py                     ✅ Factory
            ├── mock_provider.py                        ✅ Mock impl
            └── providers/
                └── lemonsqueezy.py                     ❌ To be created
```

---

## Conclusion

The subscription services architecture is well-designed with clean separation of concerns:

1. **✅ Single Integration Point**: Only `subscription_service.py` directly uses payment provider
2. **✅ Provider Abstraction**: Existing abstraction pattern will work seamlessly with LemonSqueezy
3. **⚠️ Minor Issues**: Field naming in plan service, email template enhancements needed
4. **✅ No Breaking Changes**: LemonSqueezy integration won't require refactoring most services

**Overall Assessment:** The codebase is in excellent shape for LemonSqueezy integration. The provider abstraction pattern means we can implement the LemonSqueezy provider without touching most of the existing business logic.

**Next Steps:**
- ✅ Mark Task 0.1.3 as complete
- ⏭️ Proceed to Task 0.1.4: Audit subscription routes/endpoints

---

**Document Version:** 1.0
**Last Updated:** 2025-10-17
**Status:** ✅ Complete
