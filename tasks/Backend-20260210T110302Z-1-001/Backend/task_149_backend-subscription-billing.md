# Task 149: Add Public Methods to BillingEmailService Instead of Calling Private `_send_email()`

## Metadata
- **Task ID:** TASK-149
- **Source:** B5 - Subscription & Billing (Finding #28 under P2 Medium)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

Five call sites across three service files directly access `BillingEmailService._send_email()` — a private method indicated by the leading underscore. This violates Python's encapsulation convention (PEP 8) and bypasses important business logic that the public methods provide.

The `BillingEmailService` has 7 public methods (e.g., `send_payment_failed_email()`, `send_trial_ending_email()`) that each follow a consistent pattern:
1. Resolve the user via `_get_user(user_id)`
2. Check email preferences via `_check_preferences(user_id, 'billing_notifications')`
3. Render an HTML template
4. Call `_send_email()` to dispatch

When callers bypass the public methods and call `_send_email()` directly, they **skip email preference checking**. This means dunning emails, suspension notices, and payment recovery emails are sent even if the user has explicitly opted out of billing notifications. This is a user consent violation.

The root cause is that 5 email types were added after the initial service was built, and developers chose to call `_send_email()` directly instead of adding corresponding public methods:
- `render_payment_dunning_1_day_email`
- `render_payment_dunning_3_days_email`
- `render_payment_dunning_6_days_email`
- `render_subscription_suspended_email`
- `render_payment_recovered_email`

---

## Current Code

### The private method being accessed (billing_email_service.py):
```python
# File: rext-backend/src/services/billing_email_service.py
# Lines: 286-315
async def _send_email(
    self,
    to_email: str,
    subject: str,
    html_content: str,
    background_tasks: Optional[BackgroundTasks] = None
) -> bool:
    """Send email via email provider."""
    try:
        if background_tasks:
            background_tasks.add_task(
                self.email_provider.send_email,
                to_email=to_email,
                subject=subject,
                html_content=html_content
            )
            logger.info(f"Billing email queued: {subject} to {to_email}")
        else:
            await self.email_provider.send_email(
                to_email=to_email,
                subject=subject,
                html_content=html_content
            )
            logger.info(f"Billing email sent: {subject} to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send billing email to {to_email}: {str(e)}")
        return False
```

### Call site 1 — dunning_service.py line 145 (1-day dunning):
```python
# File: rext-backend/src/services/dunning_service.py
# Line: 145
email_service = BillingEmailService(self.db)
success = await email_service._send_email(
    to_email=user.email,
    subject=f"Payment Issue - Action Needed for {plan_name}",
    html_content=html_content
)
```

### Call site 2 — dunning_service.py line 237 (3-day dunning):
```python
# File: rext-backend/src/services/dunning_service.py
# Line: 237
email_service = BillingEmailService(self.db)
success = await email_service._send_email(
    to_email=user.email,
    subject=f"Urgent: Update Payment Method for {plan_name}",
    html_content=html_content
)
```

### Call site 3 — dunning_service.py line 323 (6-day final notice):
```python
# File: rext-backend/src/services/dunning_service.py
# Line: 323
email_service = BillingEmailService(self.db)
success = await email_service._send_email(
    to_email=user.email,
    subject=f"FINAL NOTICE: {plan_name} Suspension Tomorrow",
    html_content=html_content
)
```

### Call site 4 — grace_period_service.py line 156 (suspension notice):
```python
# File: rext-backend/src/services/grace_period_service.py
# Line: 156
email_service = BillingEmailService(self.db)
await email_service._send_email(
    to_email=user.email,
    subject=f"Your {plan_name} Subscription Has Been Suspended",
    html_content=html_content
)
```

### Call site 5 — subscription_handlers.py line 1117 (payment recovery):
```python
# File: rext-backend/src/services/webhook_handlers/subscription_handlers.py
# Line: 1117
email_service = BillingEmailService(db)
await email_service._send_email(
    to_email=user.email,
    subject=f"Payment Successful - {plan_name} Reactivated!",
    html_content=html_content
)
```

---

## Why This Matters (Context & Reasoning)

Python's single-underscore naming convention signals that `_send_email()` is an internal implementation detail. The method's signature is intentionally simple (it takes a pre-resolved email address, not a user_id) because it was designed to be called only by the public methods that handle user resolution and preference checking upstream.

By accessing `_send_email()` directly, the 5 callers:
1. **Skip email preference checking** — users who opted out of billing notifications still receive dunning/suspension/recovery emails
2. **Duplicate user resolution logic** — each caller independently fetches the user and constructs `user.email`, duplicating what `_get_user()` does
3. **Duplicate plan lookup and amount formatting** — each caller independently computes plan names and amounts
4. **Create fragile coupling** — if `_send_email()` adds a required parameter (e.g., `email_type` for analytics tracking), all 5 callers break

The correct approach is to add 5 new public methods to `BillingEmailService` — one for each email type — following the same pattern as the existing 7 public methods.

---

## Impact

- **Severity:** Users who opted out of billing emails still receive dunning and suspension notifications — a consent violation. If `_send_email()` interface changes, 5 external callers silently break.
- **Affected Users/Flows:** Users with payment failures (receive dunning emails regardless of preferences), users whose grace periods expire (receive suspension notice regardless of preferences), users whose payments recover (receive reactivation notice regardless of preferences).
- **Blast Radius:** 3 files with external calls + the email service itself. Adding public methods is backward-compatible.

---

## Recommended Solution

Add 5 new public methods to `BillingEmailService`, one for each email type that is currently sent via `_send_email()` directly. Then update all callers.

### Step 1: Add 5 public methods to `BillingEmailService`

```python
# File: rext-backend/src/services/billing_email_service.py
# Add after the existing public methods (after line ~265):

async def send_dunning_1_day_email(
    self,
    user_id: UUID,
    plan_name: str,
    amount: str,
    grace_period_end_date: str,
    background_tasks: Optional[BackgroundTasks] = None,
) -> bool:
    """Send 1-day dunning reminder email."""
    user = await self._get_user(user_id)
    if not user:
        logger.warning(f"User {user_id} not found for dunning 1-day email")
        return False

    if not await self._check_preferences(user_id, "billing_notifications"):
        logger.info(f"User {user_id} has opted out of billing notifications")
        return False

    html_content = render_payment_dunning_1_day_email(
        user_name=user.full_name or user.display_name or user.email,
        plan_name=plan_name,
        amount=amount,
        grace_period_end_date=grace_period_end_date,
    )
    return await self._send_email(
        to_email=user.email,
        subject=f"Payment Issue - Action Needed for {plan_name}",
        html_content=html_content,
        background_tasks=background_tasks,
    )

async def send_dunning_3_days_email(
    self,
    user_id: UUID,
    plan_name: str,
    amount: str,
    days_until_suspension: int,
    grace_period_end_date: str,
    background_tasks: Optional[BackgroundTasks] = None,
) -> bool:
    """Send 3-day dunning reminder email (urgent)."""
    user = await self._get_user(user_id)
    if not user:
        logger.warning(f"User {user_id} not found for dunning 3-day email")
        return False

    if not await self._check_preferences(user_id, "billing_notifications"):
        logger.info(f"User {user_id} has opted out of billing notifications")
        return False

    html_content = render_payment_dunning_3_days_email(
        user_name=user.full_name or user.display_name or user.email,
        plan_name=plan_name,
        amount=amount,
        days_until_suspension=days_until_suspension,
        grace_period_end_date=grace_period_end_date,
    )
    return await self._send_email(
        to_email=user.email,
        subject=f"Urgent: Update Payment Method for {plan_name}",
        html_content=html_content,
        background_tasks=background_tasks,
    )

async def send_dunning_6_days_email(
    self,
    user_id: UUID,
    plan_name: str,
    amount: str,
    grace_period_end_date: str,
    background_tasks: Optional[BackgroundTasks] = None,
) -> bool:
    """Send 6-day final dunning warning email."""
    user = await self._get_user(user_id)
    if not user:
        logger.warning(f"User {user_id} not found for dunning 6-day email")
        return False

    if not await self._check_preferences(user_id, "billing_notifications"):
        logger.info(f"User {user_id} has opted out of billing notifications")
        return False

    html_content = render_payment_dunning_6_days_email(
        user_name=user.full_name or user.display_name or user.email,
        plan_name=plan_name,
        amount=amount,
        grace_period_end_date=grace_period_end_date,
    )
    return await self._send_email(
        to_email=user.email,
        subject=f"FINAL NOTICE: {plan_name} Suspension Tomorrow",
        html_content=html_content,
        background_tasks=background_tasks,
    )

async def send_subscription_suspended_email(
    self,
    user_id: UUID,
    plan_name: str,
    amount: str,
    suspension_date: str,
    background_tasks: Optional[BackgroundTasks] = None,
) -> bool:
    """Send subscription suspended notification email."""
    user = await self._get_user(user_id)
    if not user:
        logger.warning(f"User {user_id} not found for suspension email")
        return False

    if not await self._check_preferences(user_id, "billing_notifications"):
        logger.info(f"User {user_id} has opted out of billing notifications")
        return False

    html_content = render_subscription_suspended_email(
        user_name=user.full_name or user.display_name or user.email,
        plan_name=plan_name,
        amount=amount,
        suspension_date=suspension_date,
    )
    return await self._send_email(
        to_email=user.email,
        subject=f"Your {plan_name} Subscription Has Been Suspended",
        html_content=html_content,
        background_tasks=background_tasks,
    )

async def send_payment_recovered_email(
    self,
    user_id: UUID,
    plan_name: str,
    amount: str,
    recovery_date: str,
    next_billing_date: Optional[str] = None,
    background_tasks: Optional[BackgroundTasks] = None,
) -> bool:
    """Send payment recovered / subscription reactivated email."""
    user = await self._get_user(user_id)
    if not user:
        logger.warning(f"User {user_id} not found for payment recovered email")
        return False

    if not await self._check_preferences(user_id, "billing_notifications"):
        logger.info(f"User {user_id} has opted out of billing notifications")
        return False

    html_content = render_payment_recovered_email(
        user_name=user.full_name or user.display_name or user.email,
        plan_name=plan_name,
        amount=amount,
        recovery_date=recovery_date,
        next_billing_date=next_billing_date,
    )
    return await self._send_email(
        to_email=user.email,
        subject=f"Payment Successful - {plan_name} Reactivated!",
        html_content=html_content,
        background_tasks=background_tasks,
    )
```

### Step 2: Add necessary template imports

```python
# File: rext-backend/src/services/billing_email_service.py
# Add to imports at top of file:
from src.services.email_templates import (
    render_payment_dunning_1_day_email,
    render_payment_dunning_3_days_email,
    render_payment_dunning_6_days_email,
    render_subscription_suspended_email,
    render_payment_recovered_email,
)
```

### Step 3: Update `dunning_service.py` to use public methods

```python
# File: rext-backend/src/services/dunning_service.py

# Replace line 145 block in send_dunning_email_1_day():
email_service = BillingEmailService(self.db)
success = await email_service.send_dunning_1_day_email(
    user_id=subscription.user_id,
    plan_name=plan_name,
    amount=amount,
    grace_period_end_date=grace_period_end_date,
)

# Replace line 237 block in send_dunning_email_3_days():
email_service = BillingEmailService(self.db)
success = await email_service.send_dunning_3_days_email(
    user_id=subscription.user_id,
    plan_name=plan_name,
    amount=amount,
    days_until_suspension=days_until_suspension,
    grace_period_end_date=grace_period_end_date,
)

# Replace line 323 block in send_dunning_email_6_days():
email_service = BillingEmailService(self.db)
success = await email_service.send_dunning_6_days_email(
    user_id=subscription.user_id,
    plan_name=plan_name,
    amount=amount,
    grace_period_end_date=grace_period_end_date,
)
```

### Step 4: Update `grace_period_service.py` to use public method

```python
# File: rext-backend/src/services/grace_period_service.py

# Replace line 156 block in suspend_subscription():
email_service = BillingEmailService(self.db)
await email_service.send_subscription_suspended_email(
    user_id=subscription.user_id,
    plan_name=plan_name,
    amount=amount,
    suspension_date=datetime.now(timezone.utc).strftime("%B %d, %Y"),
)
```

### Step 5: Update `subscription_handlers.py` to use public method

```python
# File: rext-backend/src/services/webhook_handlers/subscription_handlers.py

# Replace line 1117 block in handle_subscription_payment_recovered():
email_service = BillingEmailService(db)
await email_service.send_payment_recovered_email(
    user_id=user.id,
    plan_name=plan.name,
    amount=amount,
    recovery_date=datetime.now(timezone.utc).strftime("%B %d, %Y"),
)
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/services/billing_email_service.py` | 268-284 | `_get_user()` and `_check_preferences()` private helpers — used by new public methods |
| `rext-backend/src/services/email_templates.py` or equivalent | Various | Template rendering functions must exist for the 5 email types |
| `rext-backend/src/api/tasks/subscription_tasks.py` | 60, 80, 157 | Already uses public methods correctly — no changes needed |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Set up a test user with email preferences where `billing_notifications = False`
2. Trigger a payment failure for that user's subscription (via webhook or test)
3. Observe that dunning emails ARE sent despite the opt-out (because `_send_email()` is called directly, bypassing `_check_preferences()`)

### After Fix (Verify the Solution):
1. Same test user with `billing_notifications = False`
2. Trigger a payment failure
3. Verify that NO dunning email is sent (the new public method checks preferences first)
4. Set `billing_notifications = True` and trigger again
5. Verify that the dunning email IS sent
6. Repeat for all 5 email types: 1-day dunning, 3-day dunning, 6-day dunning, suspension, payment recovery
7. Verify email content matches the original (same templates, same subject lines)

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "email or dunning or grace or billing" -v
```

---

## Acceptance Criteria

- [ ] 5 new public methods added to `BillingEmailService`
- [ ] All 5 external call sites updated to use the new public methods
- [ ] No code outside `BillingEmailService` calls `_send_email()` directly
- [ ] Email preference checking (`_check_preferences`) applied to all 5 email types
- [ ] Each new public method accepts `user_id` (not `email`) and resolves the user internally
- [ ] All email subjects and templates match the originals
- [ ] Users with `billing_notifications = False` no longer receive dunning/suspension/recovery emails
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [PEP 8 — Naming Conventions (leading underscore)](https://peps.python.org/pep-0008/#descriptive-naming-styles)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Python Classes — Encapsulation (Real Python)](https://realpython.com/python-classes/#encapsulation) — "Methods prefixed with `_` are not intended for use from outside the containing class"
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-148 (DRY violations in handlers — same files involved), TASK-137 (email sent before commit — email timing issue in tasks)
