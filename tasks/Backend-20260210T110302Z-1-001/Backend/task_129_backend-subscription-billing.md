# Task 129: SubscriptionStatus Enum Mismatch Across Three Layers — PAST_DUE and PAUSED Missing

## Metadata
- **Task ID:** TASK-129
- **Source:** B5 - Subscription & Billing (Finding #12 under P1 High)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P1 High
- **Category:** data-integrity
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `SubscriptionStatus` enum is defined in three separate locations across the stack, and the definitions do not match:

1. **SQLAlchemy Model** (`rext-backend/src/api/models/subscription_models/subscriptions.py`, line 12-20) — Defines **7 values**: `ACTIVE`, `CANCELLED`, `EXPIRED`, `TRIAL`, `SUSPENDED`, `PAST_DUE`, `PAUSED`

2. **Pydantic Schema** (`rext-backend/src/api/schema/subscription/enums.py`, line 10-16) — Defines only **5 values**: `ACTIVE`, `CANCELLED`, `EXPIRED`, `TRIAL`, `SUSPENDED` — **missing `PAST_DUE` and `PAUSED`**

3. **Frontend TypeScript** (`rext-admin/types/subscription.ts`, line 10-16) — Defines only **5 values**: `ACTIVE`, `CANCELLED`, `EXPIRED`, `TRIAL`, `SUSPENDED` — **same gap as Pydantic**

The `PAST_DUE` status is actively used in the codebase. When a subscription payment fails, the webhook handler in `subscription_handlers.py` sets the subscription status to `PAST_DUE`. The dunning service then sends payment reminder emails based on this status. However, when the API serializes this subscription through Pydantic schemas, one of two things happens:

- If Pydantic strict validation is enabled, it raises a `ValidationError` because `"past_due"` is not a valid member of the schema enum — the API returns a 500 error instead of subscription data.
- If the `to_dict()` method is used for serialization (bypassing Pydantic validation), the raw string `"past_due"` passes through, but the frontend TypeScript enum doesn't include it, so TypeScript type guards and switch statements that handle subscription status won't match this value.

The `PAUSED` status has the same issue. The LemonSqueezy provider's `pause_subscription()` method sets subscriptions to `PAUSED`, but this status cannot be correctly serialized or displayed.

The root cause is that the Pydantic schema and TypeScript types were defined based on an earlier version of the model that only had 5 statuses. When `PAST_DUE` and `PAUSED` were added to the model (likely during payment failure handling implementation), the schema and frontend types were not updated.

---

## Current Code

```python
# File: rext-backend/src/api/models/subscription_models/subscriptions.py
# Lines: 12-20
class SubscriptionStatus(str, enum.Enum):
    """Subscription status enum."""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"
    SUSPENDED = "suspended"
    PAST_DUE = "past_due"  # Payment failed, retrying
    PAUSED = "paused"  # Subscription temporarily paused
```

```python
# File: rext-backend/src/api/schema/subscription/enums.py
# Lines: 10-16
class SubscriptionStatus(str, Enum):
    """Subscription status enum."""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"
    SUSPENDED = "suspended"
    # MISSING: PAST_DUE = "past_due"
    # MISSING: PAUSED = "paused"
```

```typescript
// File: rext-admin/types/subscription.ts
// Lines: 10-16
export enum SubscriptionStatus {
  ACTIVE = "active",
  CANCELLED = "cancelled",
  EXPIRED = "expired",
  TRIAL = "trial",
  SUSPENDED = "suspended",
  // MISSING: PAST_DUE = "past_due"
  // MISSING: PAUSED = "paused"
}
```

---

## Why This Matters (Context & Reasoning)

The subscription status is a critical piece of data that flows through the entire stack: database → model → service → schema → API response → frontend. When the enum definitions don't match across layers, it creates a "schema gap" where certain valid database states cannot be correctly communicated to the user.

The `PAST_DUE` status is particularly important because it represents a payment failure state. Users with past-due subscriptions need to see a clear status in the UI so they can update their payment method. If the frontend receives `"past_due"` but doesn't have it in its enum, the subscription status might display as `undefined`, "Unknown", or trigger a JavaScript error depending on how the frontend handles unknown enum values.

The `PAUSED` status is used when a user explicitly pauses their subscription through LemonSqueezy. This is a legitimate billing feature that users should be able to see and understand.

In a properly typed system, all three layers (model, schema, frontend) should define exactly the same set of enum values. The model defines what the database can store, the schema defines what the API can serialize, and the frontend defines what the UI can display. Any mismatch is a bug.

---

## Impact

- **Severity:** Subscriptions in `PAST_DUE` or `PAUSED` state may cause API serialization errors (500 responses) or display incorrectly in the frontend. Users with failed payments may not see their subscription status correctly, preventing them from taking corrective action.
- **Affected Users/Flows:** Any user whose subscription enters `PAST_DUE` (payment failure) or `PAUSED` (manual pause) state. This affects the subscription status display, billing page, admin subscription management, and any frontend logic that switches on subscription status.
- **Blast Radius:** Moderate — affects subscription status display across multiple frontend pages and any Pydantic-validated API responses that include subscription status.

---

## Recommended Solution

Add the missing enum values to both the Pydantic schema and the TypeScript types. Also update any frontend components that switch on subscription status to handle the new values.

### Step 1: Add missing values to Pydantic schema enum

```python
# File: rext-backend/src/api/schema/subscription/enums.py
# Replace the SubscriptionStatus class (lines 10-16):
class SubscriptionStatus(str, Enum):
    """Subscription status enum."""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"
    SUSPENDED = "suspended"
    PAST_DUE = "past_due"
    PAUSED = "paused"
```

### Step 2: Add missing values to TypeScript enum

```typescript
// File: rext-admin/types/subscription.ts
// Replace the SubscriptionStatus enum (lines 10-16):
export enum SubscriptionStatus {
  ACTIVE = "active",
  CANCELLED = "cancelled",
  EXPIRED = "expired",
  TRIAL = "trial",
  SUSPENDED = "suspended",
  PAST_DUE = "past_due",
  PAUSED = "paused",
}
```

### Step 3: Update frontend subscription status display components

Search for any switch statements or conditional rendering based on `SubscriptionStatus` and add cases for the new values.

```typescript
// File: rext-admin/components/subscription/subscription-status-card.tsx
// Add to the status display logic (look for switch/if statements on subscription status):

// Add these status display configurations:
// For PAST_DUE:
//   - Label: "Past Due"
//   - Color: warning/orange
//   - Description: "Payment failed. Please update your payment method."
//   - Action: Link to billing portal

// For PAUSED:
//   - Label: "Paused"
//   - Color: neutral/gray
//   - Description: "Your subscription is paused. Resume anytime."
//   - Action: Resume subscription button
```

Search for specific patterns to update:

```bash
# Find all files that reference SubscriptionStatus in the frontend
grep -rn "SubscriptionStatus\." rext-admin/
```

### Step 4: Update any Pydantic response schemas that use the enum

```bash
# Search for schemas that reference the enum
grep -rn "SubscriptionStatus" rext-backend/src/api/schema/
```

Verify that all response schemas that include a `status` field typed as `SubscriptionStatus` will now accept the full 7-value set.

### Step 5: Verify the Zod schema (if used for frontend validation)

```bash
# Check if rext-admin uses Zod or similar for runtime validation
grep -rn "subscriptionStatus\|SubscriptionStatus" rext-admin/schemas/
```

```typescript
// File: rext-admin/schemas/subscription-schemas.ts
// If there's a Zod schema for subscription status, update it:
// Add "past_due" and "paused" to the z.enum() or z.nativeEnum() definition
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/components/subscription/subscription-status-card.tsx` | Various | Status display — needs cases for `PAST_DUE` and `PAUSED` |
| `rext-admin/app/settings/billing/page.tsx` | Various | Billing page — may display subscription status |
| `rext-admin/app/subscription/page.tsx` | Various | Subscription page — may display subscription status |
| `rext-admin/app/admin/subscriptions/page.tsx` | Various | Admin subscription list — needs to display all statuses |
| `rext-admin/stores/subscription-store.ts` | Various | Subscription store — may filter or compare by status |
| `rext-admin/schemas/subscription-schemas.ts` | Various | Zod schemas — may validate status values |
| `rext-backend/src/services/webhook_handlers/subscription_handlers.py` | Various | Sets `PAST_DUE` status — already compatible with model enum |
| `rext-backend/src/services/dunning_service.py` | Various | Queries by `PAST_DUE` status — already compatible |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Manually set a subscription status to `PAST_DUE` in the database:
   ```sql
   UPDATE user_subscriptions SET status = 'past_due' WHERE id = '<subscription-id>';
   ```
2. Call the subscription status endpoint:
   ```bash
   curl http://localhost:2024/api/v1/subscriptions/my-subscription \
     -H "Authorization: Bearer <token>"
   ```
3. Observe the behavior — either a 500 error (if Pydantic validates the response) or `"past_due"` raw string in the response
4. Check the frontend — the subscription status display likely shows "Unknown" or is blank

### After Fix (Verify the Solution):
1. With the same `PAST_DUE` subscription, call the API
2. Verify the response includes `"status": "past_due"` without errors
3. Check the frontend — should display "Past Due" with appropriate styling
4. Repeat for `PAUSED` status

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "subscription" -v
cd rext-admin && npm test -- --watchAll=false
```

---

## Acceptance Criteria

- [ ] Pydantic `SubscriptionStatus` enum has all 7 values matching the SQLAlchemy model
- [ ] TypeScript `SubscriptionStatus` enum has all 7 values matching the backend
- [ ] Frontend components handle `PAST_DUE` status with appropriate display (warning color, "Past Due" label)
- [ ] Frontend components handle `PAUSED` status with appropriate display (neutral color, "Paused" label)
- [ ] Zod/validation schemas (if any) accept the new values
- [ ] API can serialize subscriptions in `PAST_DUE` or `PAUSED` state without errors
- [ ] Admin subscription list correctly displays all 7 statuses
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Pydantic Enum Types](https://docs.pydantic.dev/latest/concepts/types/#enum-types) — Pydantic's handling of enum validation in models
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Response Model Validation](https://fastapi.tiangolo.com/tutorial/response-model/) — FastAPI validates response models against the schema, so enum mismatches cause 500 errors
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-068 (Frontend-Backend User Type Mismatch from B3 — similar cross-layer type mismatch pattern)
