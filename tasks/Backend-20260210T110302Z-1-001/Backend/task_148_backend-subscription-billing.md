# Task 148: Extract DRY Violations in Subscription Webhook Handlers Into Shared Utilities

## Metadata
- **Task ID:** TASK-148
- **Source:** B5 - Subscription & Billing (Finding #26 under P2 Medium)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** large (4+ hours)

---

## Description

The `subscription_handlers.py` file (1,258 lines) contains 9 webhook handler functions that share extensive duplicated code patterns. The audit identified 6 DRY violations, and code analysis revealed an additional 9 previously undocumented duplications — totaling approximately **250-300 lines** of pure redundancy across the handlers.

The most repeated patterns are:
1. **`status_map` dict** — identical LemonSqueezy-to-internal status mapping copy-pasted 3 times (lines 189, 451, 531)
2. **Subscription lookup** — the `select(UserSubscription).where(lemonsqueezy_subscription_id == ...)` pattern repeated 9 times across all handlers
3. **User lookup** — UUID-then-email fallback pattern repeated 3 times across 2 files
4. **`datetime.fromisoformat(...).replace(tzinfo=None)`** — date parsing pattern repeated 12 times
5. **Plan lookup by variant ID** — repeated 4 times across 2 files
6. **User + plan fetch from subscription** — repeated 8 times across 4 files
7. **Amount cents-to-dollars formatting** — repeated 6 times across 3 files
8. **`user_name` resolution** — `user.full_name or user.display_name or user.email` repeated 6+ times

This duplication means any bug fix (e.g., fixing the status mapping, changing the date parsing logic, or adding a new fallback for user resolution) must be applied to every copy separately. Missing one creates inconsistent behavior between webhook events.

---

## Current Code

### DRY-1: `status_map` duplicated 3 times

```python
# File: rext-backend/src/services/webhook_handlers/subscription_handlers.py
# Lines: 189-198 (handle_subscription_created)
# Lines: 451-460 (handle_subscription_updated, fallback)
# Lines: 531-540 (handle_subscription_updated, main path)
status_map = {
    "on_trial": SubscriptionStatus.TRIAL,
    "active": SubscriptionStatus.ACTIVE,
    "paused": SubscriptionStatus.PAUSED,
    "past_due": SubscriptionStatus.PAST_DUE,
    "unpaid": SubscriptionStatus.PAST_DUE,
    "cancelled": SubscriptionStatus.CANCELLED,
    "expired": SubscriptionStatus.EXPIRED,
}
internal_status = status_map.get(status.lower(), SubscriptionStatus.ACTIVE)
```

### DRY-2: Subscription lookup duplicated 9 times

```python
# File: rext-backend/src/services/webhook_handlers/subscription_handlers.py
# Lines: 201, 398, 666, 721, 777, 861, 1029, 1175, 1234 (one per handler)
stmt = select(UserSubscription).where(
    UserSubscription.lemonsqueezy_subscription_id == lemonsqueezy_subscription_id
)
result = await db.execute(stmt)
subscription = result.scalar_one_or_none()
```

### DRY-3: User lookup repeated 3 times

```python
# File: rext-backend/src/services/webhook_handlers/subscription_handlers.py
# Lines: 125-161, 413-432
# File: rext-backend/src/services/webhook_handlers/order_handlers.py
# Lines: 105-132
user_identifier = get_user_identifier(webhook_data)
user = None
if user_identifier:
    try:
        user_id = UUID(user_identifier)
        stmt = select(Users).where(Users.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
    except (ValueError, TypeError):
        pass

if not user and user_email:
    stmt = select(Users).where(Users.email == user_email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

if not user:
    raise ValueError(f"User not found for subscription {lemonsqueezy_subscription_id}")
```

### EXTRA: Date parsing repeated 12 times

```python
# File: rext-backend/src/services/webhook_handlers/subscription_handlers.py
# Lines: 218, 257, 269, 491, 503, 616, 617, 618, 680, 798, 1061, 1247
datetime.fromisoformat(renews_at).replace(tzinfo=None) if renews_at else None
```

---

## Why This Matters (Context & Reasoning)

Webhook handlers are the entry point for all payment events from LemonSqueezy. They must be reliable, consistent, and maintainable because errors in webhook processing directly impact subscription state, billing accuracy, and user experience.

When duplicated logic diverges (e.g., one handler updates `status_map` but others don't), subscriptions processed by different webhook events may get mapped to different internal states for the same LemonSqueezy status. This creates data integrity issues that are extremely difficult to debug because they only manifest under specific event sequences.

The 1,258-line file is also difficult to review. Extracting shared patterns into well-named utility functions reduces the file size by ~250 lines and makes each handler's unique logic clearly visible.

---

## Impact

- **Severity:** Bug fixes applied to one copy but not all others cause inconsistent subscription state transitions. Maintenance cost is proportional to duplication count — currently ~15x for some patterns.
- **Affected Users/Flows:** All webhook-driven flows: subscription creation, updates, cancellation, expiration, payment success/failure/recovery, pause/resume.
- **Blast Radius:** Changes touch `subscription_handlers.py`, `order_handlers.py`, `dunning_service.py`, `grace_period_service.py`, and potentially a new shared utility module.

---

## Recommended Solution

Create a shared webhook utilities module and extract all duplicated patterns into it.

### Step 1: Create `rext-backend/src/services/webhook_handlers/webhook_utils.py`

```python
# File: rext-backend/src/services/webhook_handlers/webhook_utils.py
"""Shared utilities for webhook event handlers."""
from datetime import datetime, timezone
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus,
    BillingPeriod,
)
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.users import Users


# DRY-1: Module-level constant for LemonSqueezy status mapping
LEMONSQUEEZY_STATUS_MAP = {
    "on_trial": SubscriptionStatus.TRIAL,
    "active": SubscriptionStatus.ACTIVE,
    "paused": SubscriptionStatus.PAUSED,
    "past_due": SubscriptionStatus.PAST_DUE,
    "unpaid": SubscriptionStatus.PAST_DUE,
    "cancelled": SubscriptionStatus.CANCELLED,
    "expired": SubscriptionStatus.EXPIRED,
}


def map_ls_status(ls_status: str, default: SubscriptionStatus = SubscriptionStatus.ACTIVE) -> SubscriptionStatus:
    """Map a LemonSqueezy status string to internal SubscriptionStatus."""
    return LEMONSQUEEZY_STATUS_MAP.get(ls_status.lower(), default)


# DRY-2: Subscription lookup by LemonSqueezy subscription ID
async def find_subscription_by_ls_id(
    db: AsyncSession, ls_subscription_id: str
) -> Optional[UserSubscription]:
    """Find a subscription by its LemonSqueezy subscription ID."""
    stmt = select(UserSubscription).where(
        UserSubscription.lemonsqueezy_subscription_id == ls_subscription_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# DRY-3: User lookup from webhook data (UUID then email fallback)
async def find_user_from_webhook(
    db: AsyncSession,
    user_identifier: Optional[str],
    user_email: Optional[str],
    context_id: str,
) -> Users:
    """
    Find a user by UUID identifier (from custom_data) or email fallback.
    Raises ValueError if no user found.
    """
    user = None

    if user_identifier:
        try:
            user_id = UUID(user_identifier)
            stmt = select(Users).where(Users.id == user_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
        except (ValueError, TypeError):
            pass

    if not user and user_email:
        stmt = select(Users).where(Users.email == user_email)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

    if not user:
        raise ValueError(f"User not found for {context_id}")

    return user


# EXTRA-1: Parse LemonSqueezy ISO datetime strings
def parse_ls_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse a LemonSqueezy ISO datetime string, stripping timezone for DB compatibility."""
    if not value:
        return None
    return datetime.fromisoformat(value).replace(tzinfo=None)


# EXTRA-2: Plan lookup by LemonSqueezy variant ID
async def find_plan_by_variant_id(
    db: AsyncSession, variant_id: str
) -> Optional[SubscriptionPlan]:
    """Find a subscription plan by its LemonSqueezy variant ID (monthly or yearly)."""
    stmt = select(SubscriptionPlan).where(
        (SubscriptionPlan.lemonsqueezy_variant_id_monthly == variant_id)
        | (SubscriptionPlan.lemonsqueezy_variant_id_yearly == variant_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# EXTRA-3: Determine billing period from plan and variant
def determine_billing_period(plan: SubscriptionPlan, variant_id: str) -> BillingPeriod:
    """Determine if a subscription is monthly or yearly based on variant ID match."""
    if plan.lemonsqueezy_variant_id_yearly == variant_id:
        return BillingPeriod.YEARLY
    return BillingPeriod.MONTHLY


# EXTRA-6/7/8: Fetch user + plan context from a subscription
async def get_subscription_context(
    db: AsyncSession, subscription: UserSubscription
) -> Tuple[Users, SubscriptionPlan, str, str]:
    """
    Load user and plan for a subscription. Returns (user, plan, user_name, formatted_amount).
    Raises ValueError if user or plan not found.
    """
    stmt = select(Users).where(Users.id == subscription.user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError(f"User {subscription.user_id} not found")

    stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()
    if not plan:
        raise ValueError(f"Plan {subscription.plan_id} not found")

    user_name = user.full_name or user.display_name or user.email

    if subscription.billing_period and subscription.billing_period.value == "monthly":
        amount_cents = plan.price_monthly
    else:
        amount_cents = plan.price_yearly
    amount = f"${float(amount_cents) / 100:.2f}" if amount_cents else "N/A"

    return user, plan, user_name, amount


# EXTRA-5: Update provider customer ID
async def update_provider_customer_id(
    db: AsyncSession, user: Users, customer_id: Optional[str]
) -> None:
    """Set the provider customer ID on a user if not already set."""
    if not user.provider_customer_id and customer_id:
        user.provider_customer_id = customer_id
        await db.flush()
```

### Step 2: Refactor `subscription_handlers.py` to use shared utilities

Replace each duplicated block with calls to the utility functions. For example:

```python
# Before (lines 189-200):
status_map = { ... }
internal_status = status_map.get(status.lower(), SubscriptionStatus.ACTIVE)

# After:
from src.services.webhook_handlers.webhook_utils import map_ls_status
internal_status = map_ls_status(status)
```

```python
# Before (lines 201-205):
stmt = select(UserSubscription).where(...)
result = await db.execute(stmt)
subscription = result.scalar_one_or_none()

# After:
from src.services.webhook_handlers.webhook_utils import find_subscription_by_ls_id
subscription = await find_subscription_by_ls_id(db, lemonsqueezy_subscription_id)
```

```python
# Before (12 occurrences):
datetime.fromisoformat(renews_at).replace(tzinfo=None) if renews_at else None

# After:
from src.services.webhook_handlers.webhook_utils import parse_ls_datetime
parse_ls_datetime(renews_at)
```

### Step 3: Refactor `order_handlers.py` to use shared utilities

Replace the user lookup and plan lookup patterns with `find_user_from_webhook()` and `find_plan_by_variant_id()`.

### Step 4: Refactor `dunning_service.py` to use `get_subscription_context()`

Replace the 3 copies of user/plan lookup + amount formatting in `send_dunning_email_1_day()`, `send_dunning_email_3_days()`, and `send_dunning_email_6_days()`.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/services/webhook_handlers/order_handlers.py` | 105-140 | User lookup + plan lookup — use shared utilities |
| `rext-backend/src/services/dunning_service.py` | 103-130, 194-222, 287-309 | User/plan lookup duplicated 3x — use `get_subscription_context()` |
| `rext-backend/src/services/grace_period_service.py` | 91-145 | User/plan lookup + amount formatting — use `get_subscription_context()` |
| `rext-backend/src/api/tasks/subscription_tasks.py` | 66-74, 145-153 | User/plan lookup — use `get_subscription_context()` |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Count `status_map` occurrences: `grep -c "status_map" rext-backend/src/services/webhook_handlers/subscription_handlers.py` — shows 3+
2. Count subscription lookups: `grep -c "lemonsqueezy_subscription_id ==" rext-backend/src/services/webhook_handlers/subscription_handlers.py` — shows 9+

### After Fix (Verify the Solution):
1. Verify `subscription_handlers.py` file size reduced by ~200+ lines
2. `grep -c "status_map" subscription_handlers.py` — should show 0 (moved to constant)
3. `grep -c "lemonsqueezy_subscription_id ==" subscription_handlers.py` — should show 0 (moved to utility)
4. Trigger each webhook event type and verify correct handling:
   - `subscription_created` — creates subscription with correct status
   - `subscription_updated` — updates status correctly
   - `subscription_cancelled` — cancels subscription
   - `subscription_payment_failed` — triggers dunning flow
   - `subscription_payment_recovered` — restores subscription
5. Verify dunning emails still fire correctly after refactoring

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "webhook or handler or subscription" -v
```

---

## Acceptance Criteria

- [ ] New `webhook_utils.py` module created with all shared utility functions
- [ ] `status_map` defined exactly once as `LEMONSQUEEZY_STATUS_MAP` constant
- [ ] Subscription lookup logic defined once in `find_subscription_by_ls_id()`
- [ ] User lookup logic defined once in `find_user_from_webhook()`
- [ ] Date parsing logic defined once in `parse_ls_datetime()`
- [ ] Plan lookup by variant defined once in `find_plan_by_variant_id()`
- [ ] `subscription_handlers.py` reduced by at least 200 lines
- [ ] All 9 handler functions use the shared utilities
- [ ] `order_handlers.py` uses the shared utilities
- [ ] `dunning_service.py` uses `get_subscription_context()`
- [ ] No behavioral changes — all webhook events still process identically
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python Module Organization Best Practices](https://docs.python.org/3/tutorial/modules.html)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [DRY Principle — Pragmatic Programmer](https://pragprog.com/tips/) — "Every piece of knowledge must have a single, unambiguous, authoritative representation within a system"
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-149 (private `_send_email()` access — some of the same files are involved), TASK-146 (datetime.utcnow deprecation — the `parse_ls_datetime` utility should use timezone-aware parsing once TASK-146 is complete)
