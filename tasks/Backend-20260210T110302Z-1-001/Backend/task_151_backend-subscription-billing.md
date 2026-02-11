# Task 151: Decorator Ordering Issues in Subscription Routes

## Metadata
- **Task ID:** TASK-151
- **Source:** B5 - Subscription & Billing (Finding #33 under P3 Low)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `@require_permissions` and `@db_transaction_handler` decorators are applied in inconsistent order across the subscription route files. Python decorators execute from the outermost (topmost) to the innermost (bottommost) at call time — so the decorator listed first (top) wraps everything below it. The correct convention is `@db_transaction_handler` (outermost) wrapping `@require_permissions` (innermost), so that the database transaction context encompasses the entire request lifecycle including permission checks.

Looking at the actual codebase, the subscription route files exhibit both orderings:

**Pattern A (correct — `@db_transaction_handler` outermost):**
- `trial_routes.py` lines 90–91: `@db_transaction_handler` → `@require_permissions`
- `trial_routes.py` lines 152–153: Same correct order
- `trial_routes.py` lines 218–219: Same correct order
- `license_routes.py` lines 149–150, 236–237, 288–289, 336–337: Same correct order

**Pattern B (incorrect — `@require_permissions` outermost):**
- `subscription_routes.py` lines 49–50, 98–99, 150–151, 423–424: `@require_permissions` → `@db_transaction_handler`
- `admin_subscription_management.py` lines 33–34, 61–62, 88–89: `@require_permissions` → `@db_transaction_handler`
- `admin_subscription_analytics.py` lines 28–29, 54–55: `@require_permissions` → `@db_transaction_handler`
- `webhook_monitoring_routes.py` lines 32–33, 146–147, 255–256: `@require_permissions` → `@db_transaction_handler`
- `license_routes.py` lines 38–39: `@require_permissions` → `@db_transaction_handler` (inconsistent even within the same file)

When `@require_permissions` is the outermost decorator, a permission check failure happens outside the transaction context. If any database state was read during the permission check (e.g., looking up user roles), that state is not part of a managed transaction — meaning any partial database operations won't be rolled back if the permission check raises an exception after a flush.

While this is a minor issue in practice (permission checks rarely cause side effects), the inconsistency makes the codebase harder to reason about and maintain. A developer looking at `trial_routes.py` would assume one convention, then see the opposite in `subscription_routes.py`.

---

## Current Code

```python
# File: src/api/routes/subscriptions/subscription_routes.py
# Lines: 423-426 (Pattern B — incorrect order)
@router.post("/cancel", response_model=dict)
@require_permissions("subscription.manage")
@db_transaction_handler("cancel subscription")
async def cancel_subscription(
```

```python
# File: src/api/routes/subscriptions/trial_routes.py
# Lines: 89-92 (Pattern A — correct order)
@router.post("/{subscription_id}/extend", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("extend trial")
@require_permissions("subscription.manage", workspace_scoped=False)
async def extend_trial_endpoint(
```

```python
# File: src/api/routes/subscriptions/admin/admin_subscription_management.py
# Lines: 32-35 (Pattern B — incorrect order)
@router.post("/assign", response_model=dict, status_code=status.HTTP_201_CREATED)
@require_permissions("subscription.manage")
@db_transaction_handler("assign subscription", auto_commit=True)
async def assign_subscription(
```

---

## Why This Matters (Context & Reasoning)

The subscription and billing routes handle financial operations — subscriptions, cancellations, plan changes, and license management. These are among the most sensitive operations in the application. Having a consistent, predictable decorator ordering ensures that:

1. Every request is wrapped in a transaction context before any business logic (including permission checks) executes.
2. If a permission check fails after any database reads, the transaction is properly rolled back.
3. Developers can reason about the execution order without checking each endpoint individually.

The risk of NOT fixing this is primarily maintenance burden and cognitive overhead. A new developer might copy the wrong pattern when creating new endpoints, propagating the inconsistency further.

---

## Impact

- **Severity:** Minor — may cause permission check failures to not properly roll back transactions in edge cases where permission checking involves database reads.
- **Affected Users/Flows:** All subscription management endpoints (subscribe, cancel, upgrade, checkout, admin operations, license management).
- **Blast Radius:** Subscription routes only. No user-visible behavior change expected in normal operation.

---

## Recommended Solution

Standardize all subscription route files to use the correct decorator order: `@router.method(...)` → `@db_transaction_handler(...)` → `@require_permissions(...)` → `async def handler(...)`.

### Step 1: Fix `subscription_routes.py`

```python
# File: src/api/routes/subscriptions/subscription_routes.py
# For each endpoint that has @require_permissions ABOVE @db_transaction_handler,
# swap the order so @db_transaction_handler is above @require_permissions.

# Example fix for the cancel endpoint (lines 423-426):
@router.post("/cancel", response_model=dict)
@db_transaction_handler("cancel subscription")
@require_permissions("subscription.manage")
async def cancel_subscription(
```

Apply the same swap to all endpoints in this file where `@require_permissions` appears above `@db_transaction_handler`:
- `subscribe` endpoint (~line 49-50)
- `create_checkout_session` endpoint (~line 98-99)
- `get_my_subscription` endpoint (~line 150-151)
- `cancel_subscription` endpoint (~line 423-424)

### Step 2: Fix `admin_subscription_management.py`

```python
# File: src/api/routes/subscriptions/admin/admin_subscription_management.py
# Swap decorator order for all 3 endpoints:

# assign_subscription (lines 32-34):
@router.post("/assign", response_model=dict, status_code=status.HTTP_201_CREATED)
@db_transaction_handler("assign subscription", auto_commit=True)
@require_permissions("subscription.manage")
async def assign_subscription(

# extend_subscription (lines 60-62):
@router.post("/{subscription_id}/extend", response_model=dict)
@db_transaction_handler("extend subscription", auto_commit=True)
@require_permissions("subscription.manage")
async def extend_subscription(

# reset_usage (lines 87-89):
@router.post("/{subscription_id}/reset-usage", response_model=dict)
@db_transaction_handler("reset usage", auto_commit=True)
@require_permissions("subscription.manage")
async def reset_usage(
```

### Step 3: Fix `admin_subscription_analytics.py`

```python
# File: src/api/routes/subscriptions/admin/admin_subscription_analytics.py
# Swap decorator order for endpoints where @require_permissions is above @db_transaction_handler
```

### Step 4: Fix `webhook_monitoring_routes.py`

```python
# File: src/api/routes/subscriptions/admin/webhook_monitoring_routes.py
# Swap decorator order for all endpoints where @require_permissions is above @db_transaction_handler
```

### Step 5: Fix `license_routes.py` inconsistency

```python
# File: src/api/routes/subscriptions/license_routes.py
# Line 38-39: The validate endpoint has @require_permissions above @db_transaction_handler
# Swap to match the rest of the file:
@router.post("/validate", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("validate license", auto_commit=False)
@require_permissions("license.validate", workspace_scoped=False)
async def validate_license_endpoint(
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/subscriptions/subscription_routes.py` | `49-50, 98-99, 150-151, 423-424` | 4 endpoints with reversed decorator order |
| `src/api/routes/subscriptions/admin/admin_subscription_management.py` | `33-34, 61-62, 88-89` | 3 endpoints with reversed decorator order |
| `src/api/routes/subscriptions/admin/admin_subscription_analytics.py` | `28-29, 54-55` | 2 endpoints with reversed decorator order |
| `src/api/routes/subscriptions/admin/webhook_monitoring_routes.py` | `32-33, 146-147, 255-256` | 3 endpoints with reversed decorator order |
| `src/api/routes/subscriptions/license_routes.py` | `38-39` | 1 endpoint with reversed decorator order |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open `subscription_routes.py` and `trial_routes.py` side by side.
2. Observe that the decorator order differs between the two files for equivalent endpoint patterns.
3. Verify by reading each file's decorator stacking.

### After Fix (Verify the Solution):
1. Search all subscription route files for `@require_permissions` and `@db_transaction_handler`.
2. Verify that every endpoint where both decorators are present has `@db_transaction_handler` listed ABOVE `@require_permissions`.
3. Test each endpoint to ensure it still responds correctly:
   - `POST /api/v1/subscriptions/subscribe` — should require authentication
   - `POST /api/v1/subscriptions/cancel` — should require authentication
   - `POST /api/v1/trials/{id}/extend` — should require admin permissions

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "subscription or trial or license" -v
```

---

## Acceptance Criteria

- [ ] All subscription route files use consistent decorator order: `@db_transaction_handler` above `@require_permissions`
- [ ] No endpoint has `@require_permissions` listed above `@db_transaction_handler`
- [ ] All endpoints still function correctly (authentication and permission checks work)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python Decorators — Real Python (Decorator Chaining)](https://realpython.com/primer-on-python-decorators/)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Python by Structure: Decorator Chains and Execution Order](https://dev.to/aaron_rose_0787cc8b4775a0/python-by-structure-decorator-chains-and-execution-order-13p0)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-134 (Cancel Endpoint Returns HTTP 200 for Errors — also in subscription_routes.py cancel endpoint)
