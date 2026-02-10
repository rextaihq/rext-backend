# Task 140: Remove Stripe Remnants from Frontend Types and Backend Service

## Metadata
- **Task ID:** TASK-140
- **Source:** Subscription & Billing (Finding #19 under P2 Medium)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The Rext AI codebase contains leftover Stripe payment processor references despite exclusively using LemonSqueezy for payment processing. These remnants exist in two layers:

1. **Frontend types** (`rext-admin/types/subscription.ts`, lines 60-61 and 77-78): The `SubscriptionPlanCreate` and `SubscriptionPlanUpdate` TypeScript interfaces include `stripe_price_id_monthly` and `stripe_price_id_yearly` optional fields. These fields serve no purpose since no Stripe integration exists — no Stripe SDK is installed, no Stripe provider is implemented, and no Stripe webhooks are configured.

2. **Backend service** (`rext-backend/src/services/subscription_plan_service.py`, lines 65-66): The `create_plan()` method attempts to pass `stripe_price_id_monthly` and `stripe_price_id_yearly` from the Pydantic schema payload to the SQLAlchemy model constructor. However, the database model (`plans.py`) was already migrated via Alembic migration `2f08b3178c5d` to use `provider_price_id_monthly` and `provider_price_id_yearly` instead. The model no longer has `stripe_price_id_*` attributes. This means if a frontend admin form ever sends these fields, the service will raise an `AttributeError` at runtime because `SubscriptionPlan` has no `stripe_price_id_monthly` attribute.

Critically, the backend Pydantic schema (`plan_schemas.py`) was already correctly updated to use `lemonsqueezy_*` fields — it has no Stripe fields. This creates a layer mismatch: the frontend types define Stripe fields, but the backend schema rejects them. And the service references Stripe attributes that no longer exist on the model. The migration from Stripe to LemonSqueezy was partially completed, with the model and schema layers done but the service and frontend types left behind.

---

## Current Code

```typescript
// File: rext-admin/types/subscription.ts
// Lines: 46-62
export interface SubscriptionPlanCreate {
  name: string;
  display_name: string;
  description?: string;
  price_monthly: number;
  price_yearly: number;
  features?: Record<string, unknown>;
  max_workspaces?: number;
  max_members_per_workspace?: number;
  max_topics?: number;
  max_knowledge_items?: number;
  max_api_calls_per_month?: number;
  is_active?: boolean;
  is_public?: boolean;
  stripe_price_id_monthly?: string;   // <-- Stripe remnant
  stripe_price_id_yearly?: string;    // <-- Stripe remnant
}
```

```typescript
// File: rext-admin/types/subscription.ts
// Lines: 64-79
export interface SubscriptionPlanUpdate {
  display_name?: string;
  description?: string;
  price_monthly?: number;
  price_yearly?: number;
  features?: Record<string, unknown>;
  max_workspaces?: number;
  max_members_per_workspace?: number;
  max_topics?: number;
  max_knowledge_items?: number;
  max_api_calls_per_month?: number;
  is_active?: boolean;
  is_public?: boolean;
  stripe_price_id_monthly?: string;   // <-- Stripe remnant
  stripe_price_id_yearly?: string;    // <-- Stripe remnant
}
```

```python
# File: rext-backend/src/services/subscription_plan_service.py
# Lines: 48-69
async def create_plan(self, payload: SubscriptionPlanCreate) -> Dict[str, object]:
    await self._ensure_unique_name(payload.name)

    plan = SubscriptionPlan(
        name=payload.name.lower(),
        display_name=payload.display_name,
        description=payload.description,
        price_monthly=payload.price_monthly,
        price_yearly=payload.price_yearly,
        features=payload.features or {},
        max_workspaces=payload.max_workspaces,
        max_members_per_workspace=payload.max_members_per_workspace,
        max_topics=payload.max_topics,
        max_knowledge_items=payload.max_knowledge_items,
        max_api_calls_per_month=payload.max_api_calls_per_month,
        is_active=payload.is_active,
        is_public=payload.is_public,
        stripe_price_id_monthly=payload.stripe_price_id_monthly,  # <-- AttributeError at runtime
        stripe_price_id_yearly=payload.stripe_price_id_yearly,    # <-- AttributeError at runtime
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
```

---

## Why This Matters (Context & Reasoning)

The subscription plan system is the foundation of the billing architecture. Admin users create and manage plans through admin pages that submit `SubscriptionPlanCreate` payloads. The plan creation service is the write path for this critical data. If the admin plan form ever includes Stripe fields (which the frontend types suggest it might), the backend service will crash because the SQLAlchemy model was already renamed to `provider_price_id_*`. Even if Stripe fields are never sent, their presence in the codebase misleads developers into thinking Stripe integration is planned or partially complete, wasting investigation time and creating confusion during onboarding.

---

## Impact

- **Severity:** If an admin attempts to create a plan with Stripe price IDs populated, the service raises an `AttributeError` at runtime, blocking plan creation. Even without triggering the error, the dead code creates confusion and maintenance burden.
- **Affected Users/Flows:** Admin plan creation flow, admin plan update flow, any developer working on billing features.
- **Blast Radius:** Isolated to the plan management feature. Does not affect existing subscriptions or end users.

---

## Recommended Solution

### Step 1: Remove Stripe fields from frontend TypeScript types

```typescript
// File: rext-admin/types/subscription.ts
// Remove lines 60-61 from SubscriptionPlanCreate interface
// Remove lines 77-78 from SubscriptionPlanUpdate interface

// Updated SubscriptionPlanCreate (lines 46-60):
export interface SubscriptionPlanCreate {
  name: string;
  display_name: string;
  description?: string;
  price_monthly: number;
  price_yearly: number;
  features?: Record<string, unknown>;
  max_workspaces?: number;
  max_members_per_workspace?: number;
  max_topics?: number;
  max_knowledge_items?: number;
  max_api_calls_per_month?: number;
  is_active?: boolean;
  is_public?: boolean;
}

// Updated SubscriptionPlanUpdate (lines 62-75):
export interface SubscriptionPlanUpdate {
  display_name?: string;
  description?: string;
  price_monthly?: number;
  price_yearly?: number;
  features?: Record<string, unknown>;
  max_workspaces?: number;
  max_members_per_workspace?: number;
  max_topics?: number;
  max_knowledge_items?: number;
  max_api_calls_per_month?: number;
  is_active?: boolean;
  is_public?: boolean;
}
```

### Step 2: Remove Stripe attribute assignments from backend service

```python
# File: rext-backend/src/services/subscription_plan_service.py
# Replace lines 51-69 (the SubscriptionPlan constructor call) with:

    plan = SubscriptionPlan(
        name=payload.name.lower(),
        display_name=payload.display_name,
        description=payload.description,
        price_monthly=payload.price_monthly,
        price_yearly=payload.price_yearly,
        features=payload.features or {},
        max_workspaces=payload.max_workspaces,
        max_members_per_workspace=payload.max_members_per_workspace,
        max_topics=payload.max_topics,
        max_knowledge_items=payload.max_knowledge_items,
        max_api_calls_per_month=payload.max_api_calls_per_month,
        is_active=payload.is_active,
        is_public=payload.is_public,
        lemonsqueezy_product_id=payload.lemonsqueezy_product_id,
        lemonsqueezy_variant_id_monthly=payload.lemonsqueezy_variant_id_monthly,
        lemonsqueezy_variant_id_yearly=payload.lemonsqueezy_variant_id_yearly,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
```

### Step 3: Verify no other references to Stripe fields exist

Search the entire codebase for any remaining references to `stripe_price_id` and remove them. Known locations:
- `rext-admin/lib/csp.ts` line 34: Remove commented-out Stripe CSP reference.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/lib/csp.ts` | `34` | Commented-out Stripe CSP entry (`// stripe: "https://js.stripe.com"`) |
| `rext-backend/alembic/versions/f9e8d7c6b5a4_seed_subscription_plans.py` | `44-45, 88-89, 115-116, 145-146` | Seed migration references `stripe_price_id_*` columns with NULL values — historical migration, no change needed |
| `rext-backend/alembic/versions/2f08b3178c5d_rename_stripe_fields_to_provider_.py` | `24-33` | Migration that renamed Stripe columns to provider-agnostic names — historical, no change needed |
| `rext-backend/scripts/verify_route_protection.py` | `44` | References `/stripe` as a potential webhook endpoint in route verification — remove reference |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Confirm Stripe fields exist in frontend types: `grep -n "stripe_price_id" rext-admin/types/subscription.ts`
2. Confirm Stripe attribute assignment exists in service: `grep -n "stripe_price_id" rext-backend/src/services/subscription_plan_service.py`
3. Confirm the model does NOT have Stripe fields: `grep -n "stripe_price_id" rext-backend/src/api/models/subscription_models/plans.py` — should return nothing (model already uses `provider_price_id_*`)

### After Fix (Verify the Solution):
1. Search for `stripe_price_id` across both codebases — should return no results in non-migration files
2. Verify TypeScript compiles: `cd rext-admin && npx tsc --noEmit`
3. Verify no import errors in Python service: `cd rext-backend && python -c "from src.services.subscription_plan_service import SubscriptionPlanService"`

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "subscription_plan" -v
cd rext-admin && npm test -- --testPathPattern="subscription"
```

---

## Acceptance Criteria

- [ ] `stripe_price_id_monthly` and `stripe_price_id_yearly` removed from `SubscriptionPlanCreate` interface in `types/subscription.ts`
- [ ] `stripe_price_id_monthly` and `stripe_price_id_yearly` removed from `SubscriptionPlanUpdate` interface in `types/subscription.ts`
- [ ] `stripe_price_id_monthly` and `stripe_price_id_yearly` attribute assignments removed from `subscription_plan_service.py` `create_plan()` method
- [ ] LemonSqueezy fields (`lemonsqueezy_product_id`, `lemonsqueezy_variant_id_monthly`, `lemonsqueezy_variant_id_yearly`) are passed through in `create_plan()` instead
- [ ] No remaining `stripe_price_id` references in non-migration source files
- [ ] TypeScript compilation succeeds without errors
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Alembic Operation Reference - drop_column](https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.drop_column) — for reference on the migration that renamed Stripe columns
- **Security Advisory:** N/A
- **Migration Guide:** N/A — the Stripe-to-LemonSqueezy migration was a custom project decision, not a library migration
- **Best Practice Reference:** [SQLAlchemy 2.0 Migration Guide](https://docs.sqlalchemy.org/en/20/changelog/migration_20.html) — ensuring model attributes match actual column names
- **Related Issues/PRs:** None identified

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-129 (SubscriptionStatus Enum Mismatch Across Three Layers — another cross-layer type mismatch in the same billing system)
