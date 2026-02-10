# Task 133: Duplicate Trial Expiration — Two Independent Code Paths Process the Same Trials

## Metadata
- **Task ID:** TASK-133
- **Source:** Backend Subscription & Billing Audit (Finding #9 under P1 High)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P1 High
- **Category:** broken-functionality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

Two completely independent code paths handle trial expiration and trial reminder emails, both registered as scheduled tasks that run daily. They process the same set of expiring/expired trials but use different email services, different email templates, and different processing logic:

**Code Path 1: `TrialExpirationTask`** (`src/api/tasks/trial_expiration_task.py`)
- A class-based task (275 lines) registered to run daily at **midnight** (line 77 in `scheduled_tasks.py`)
- Sends reminder emails at 3 days, 1 day, and 0 days before expiration via `EmailService` (generic email service)
- Also processes already-expired trials (sets status to `EXPIRED` and sends expired notification)
- Uses `TrialService.get_expiring_trials()` and `TrialService.get_expired_trials()` for queries
- Entry point: `run_trial_expiration_task()`

**Code Path 2: `subscription_tasks` functions** (`src/api/tasks/subscription_tasks.py`)
- Function-based tasks (261 lines) registered to run daily at **3 AM** (line 106 in `scheduled_tasks.py`)
- `check_and_notify_expiring_trials()`: Sends 3-day-only reminders via `BillingEmailService`
- `expire_ended_trials()`: Sets expired trial status to `EXPIRED` and sends expired notification via `BillingEmailService`
- Includes additional `reset_monthly_usage()` function (unrelated to trials)
- Individually queries the database for users and plans with separate `SELECT` statements per subscription (N+1 pattern)
- Entry point: `run_daily_subscription_tasks()` (runs all three functions)

Both are registered in `src/tasks/scheduled_tasks.py`:
- Line 75-82: `run_trial_expiration_task` runs at midnight
- Line 104-112: `run_daily_subscription_tasks` runs at 3 AM

The consequences of this duplication:
1. **Duplicate emails:** Users receive two separate trial reminder/expiration emails — one at midnight from `EmailService` and another at 3 AM from `BillingEmailService`. These likely use different templates and different sender names, creating a confusing user experience.
2. **Double expiration processing:** Both paths set `subscription.status = SubscriptionStatus.EXPIRED` for expired trials. The second path encounters already-expired subscriptions (from the midnight run) and either processes them again redundantly or skips them silently.
3. **Different reminder coverage:** Code Path 1 sends reminders at 3, 1, and 0 days. Code Path 2 only sends 3-day reminders. Users get one email at 3 days (from Path 2) plus another (from Path 1), but only one at 1 day (from Path 1).
4. **Debugging difficulty:** If trial expiration breaks, there are two completely separate code paths to investigate, each with its own error handling, logging, and database session management.

---

## Current Code

```python
# File: src/tasks/scheduled_tasks.py
# Lines: 75-82 (Code Path 1 registration)
        # Trial expiration check — daily at midnight
        self.scheduler.add_job(
            run_trial_expiration_task,
            trigger=CronTrigger(hour=0, minute=0),
            id="trial_expiration",
            name="Daily trial expiration check",
            replace_existing=True,
            max_instances=1,
        )
```

```python
# File: src/tasks/scheduled_tasks.py
# Lines: 104-112 (Code Path 2 registration)
        # Subscription maintenance — daily at 3 AM
        self.scheduler.add_job(
            run_daily_subscription_tasks,
            trigger=CronTrigger(hour=3, minute=0),
            id="subscription_maintenance",
            name="Daily subscription maintenance",
            replace_existing=True,
            max_instances=1,
        )
```

```python
# File: src/api/tasks/trial_expiration_task.py
# Lines: 221-249 (run method - Code Path 1)
    async def run(self):
        """Run the trial expiration task."""
        logger.info("=== Trial Expiration Task Started ===")
        try:
            await self.process_expiring_trials(days_remaining=3)
            await self.process_expiring_trials(days_remaining=1)
            await self.process_expiring_trials(days_remaining=0)
            await self.process_expired_trials()
            logger.info("=== Trial Expiration Task Completed Successfully ===")
        except Exception as e:
            logger.error(f"Trial expiration task failed: {str(e)}", ...)
            raise
```

```python
# File: src/api/tasks/subscription_tasks.py
# Lines: 244-260 (run function - Code Path 2)
async def run_daily_subscription_tasks():
    """Run all daily subscription maintenance tasks."""
    logger.info("Starting daily subscription tasks")
    results = {
        "trial_notifications": await check_and_notify_expiring_trials(),
        "trial_expirations": await expire_ended_trials(),
        "usage_resets": await reset_monthly_usage(),
    }
    logger.info(f"Daily subscription tasks completed: {results}")
    return results
```

---

## Why This Matters (Context & Reasoning)

Trial management is a critical part of the subscription funnel. Users start with a 14-day trial, receive reminder emails as the trial approaches its end, and are transitioned to expired status when the trial ends. This flow directly impacts conversion rates:

1. **User experience:** Receiving duplicate reminder emails (from two different services with potentially different templates) appears unprofessional and may cause users to mark emails as spam, reducing the effectiveness of future billing communications.
2. **Email deliverability:** Sending duplicate emails to the same recipient for the same event can trigger spam filters, harming the domain's sender reputation.
3. **Data consistency:** If one code path fails and the other succeeds, the system is in a partially-processed state. For example, if Code Path 1 sends the reminder but fails to commit, and Code Path 2 succeeds 3 hours later, the user has already received a stale notification.
4. **Maintenance cost:** Two code paths means double the surface area for bugs, double the testing required, and confusion about which path is "authoritative."

The correct approach is to keep one comprehensive code path and remove the duplicate.

---

## Impact

- **Severity:** Users receive duplicate trial reminder and expiration emails. Expired trials are processed twice daily, causing redundant database updates. Different email services and templates create inconsistent communication.
- **Affected Users/Flows:** All users on trial subscriptions. The trial reminder email flow (3-day, 1-day, expiration) and the trial-to-expired status transition.
- **Blast Radius:** Affects all trial users. Also affects email deliverability reputation for the entire platform if duplicate sends trigger spam filters.

---

## Recommended Solution

Keep `TrialExpirationTask` (Code Path 1) because it is more comprehensive — it handles 3-day, 1-day, and same-day reminders, plus expiration processing. Remove the duplicate trial functions from `subscription_tasks.py` (Code Path 2), but keep `reset_monthly_usage()` since it's unrelated to trial expiration. Consolidate on `BillingEmailService` for all billing-related emails (it's the purpose-built service with preference checking).

### Step 1: Remove duplicate trial functions from subscription_tasks.py

```python
# File: src/api/tasks/subscription_tasks.py
# Replace the ENTIRE file with:

"""
Subscription Background Tasks

Handles automated subscription management tasks:
- Usage reset

Note: Trial expiration and notifications are handled by
src/api/tasks/trial_expiration_task.py (runs at midnight).
Do NOT add trial logic here to avoid duplication.
"""

from datetime import datetime, timedelta
from typing import Dict
from sqlalchemy import select, and_

from src.api.database.async_database import get_async_db_context
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus
)
from src.utils.logger import logger


async def reset_monthly_usage():
    """
    Reset API call usage for all active subscriptions on their monthly reset date.

    Should be run daily.

    Returns:
        Dict with reset counts
    """
    async with get_async_db_context() as db:
        try:
            now = datetime.utcnow()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

            # Find subscriptions with usage reset date = today
            query = select(UserSubscription).where(
                and_(
                    UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
                    UserSubscription.usage_reset_date >= today_start,
                    UserSubscription.usage_reset_date <= today_end
                )
            )

            result = await db.execute(query)
            subscriptions_to_reset = result.scalars().all()

            logger.info(f"Found {len(subscriptions_to_reset)} subscription(s) to reset usage")

            reset_count = 0

            for subscription in subscriptions_to_reset:
                try:
                    # Reset API call counter
                    subscription.current_api_calls = 0
                    subscription.usage_reset_date = now + timedelta(days=30)

                    reset_count += 1

                except Exception as e:
                    logger.error(f"Error resetting usage for subscription {subscription.id}: {e}")
                    continue

            await db.commit()

            logger.info(f"Reset usage for {reset_count} subscription(s)")

            return {
                "subscriptions_reset": reset_count,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error in reset_monthly_usage: {e}")
            await db.rollback()
            raise


async def run_daily_subscription_tasks():
    """
    Run daily subscription maintenance tasks (excluding trial management).

    Trial expiration and notifications are handled separately by
    TrialExpirationTask (scheduled at midnight).
    """
    logger.info("Starting daily subscription maintenance tasks")

    results = {
        "usage_resets": await reset_monthly_usage(),
    }

    logger.info(f"Daily subscription maintenance completed: {results}")

    return results
```

### Step 2: Update TrialExpirationTask to use BillingEmailService

```python
# File: src/api/tasks/trial_expiration_task.py
# Replace the imports (lines 1-16) with:

"""
Trial expiration background task.

This is the SOLE code path for trial expiration and reminders.
Runs daily at midnight UTC. Handles:
- 3-day, 1-day, and same-day trial reminder emails
- Expired trial status transitions

Uses BillingEmailService for all email sending (includes preference checking).
"""
import asyncio
from datetime import datetime
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db_context
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.services.trial_service import TrialService
from src.services.billing_email_service import BillingEmailService
from src.utils.logger import logger
```

```python
# File: src/api/tasks/trial_expiration_task.py
# Replace __init__ (lines 22-26) with:

    def __init__(self, db: AsyncSession):
        """Initialize task with database session."""
        self.db = db
        self.trial_service = TrialService(db)
        self.email_service = BillingEmailService(db)
```

```python
# File: src/api/tasks/trial_expiration_task.py
# Replace send_trial_reminder_email method (lines 28-101) with:

    async def send_trial_reminder_email(
        self,
        subscription: UserSubscription,
        days_remaining: int
    ) -> bool:
        """
        Send trial reminder email to user via BillingEmailService.

        Args:
            subscription: User subscription
            days_remaining: Days remaining in trial

        Returns:
            True if email sent successfully
        """
        try:
            user = subscription.user
            if not user or not user.email:
                logger.warning(
                    f"Cannot send trial reminder - user/email not found for subscription {subscription.id}"
                )
                return False

            plan_name = subscription.plan.name if subscription.plan else "Unknown Plan"
            trial_end_date = (
                subscription.trial_end_date.strftime("%B %d, %Y")
                if subscription.trial_end_date
                else "Unknown"
            )

            success = await self.email_service.send_trial_ending_email(
                user_id=user.id,
                plan_name=plan_name,
                trial_end_date=trial_end_date,
                days_remaining=days_remaining,
            )

            if success:
                logger.info(
                    f"Trial reminder email sent to {user.email}",
                    extra={
                        "user_id": str(user.id),
                        "subscription_id": str(subscription.id),
                        "days_remaining": days_remaining
                    }
                )

            return success

        except Exception as e:
            logger.error(
                f"Failed to send trial reminder email: {str(e)}",
                extra={
                    "subscription_id": str(subscription.id),
                    "days_remaining": days_remaining,
                    "error": str(e)
                }
            )
            return False
```

```python
# File: src/api/tasks/trial_expiration_task.py
# Replace send_trial_expired_email method (lines 103-153) with:

    async def send_trial_expired_email(
        self,
        subscription: UserSubscription
    ) -> bool:
        """
        Send trial expired email to user via BillingEmailService.

        Args:
            subscription: Expired subscription

        Returns:
            True if email sent successfully
        """
        try:
            user = subscription.user
            if not user or not user.email:
                return False

            plan_name = subscription.plan.name if subscription.plan else "Unknown Plan"

            success = await self.email_service.send_trial_expired_email(
                user_id=user.id,
                plan_name=plan_name,
            )

            if success:
                logger.info(
                    f"Trial expired email sent to {user.email}",
                    extra={
                        "user_id": str(user.id),
                        "subscription_id": str(subscription.id)
                    }
                )

            return success

        except Exception as e:
            logger.error(
                f"Failed to send trial expired email: {str(e)}",
                extra={
                    "subscription_id": str(subscription.id),
                    "error": str(e)
                }
            )
            return False
```

### Step 3: Remove unused imports from scheduled_tasks.py

The import of `run_daily_subscription_tasks` from `subscription_tasks.py` remains valid since we kept the function (just simplified it). No import changes needed in `scheduled_tasks.py`.

### Step 4: Remove the _get_app_url helper (no longer needed)

The `_get_app_url()` method (lines 251-254) in `trial_expiration_task.py` is no longer needed since `BillingEmailService` handles URL construction internally. Remove it.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/tasks/scheduled_tasks.py` | 25-28 | Imports from both task files — the import of `run_daily_subscription_tasks` still works (function still exists but simplified) |
| `src/services/billing_email_service.py` | 176-204 | `send_trial_ending_email()` — the method TrialExpirationTask will now use; already includes preference checking |
| `src/services/billing_email_service.py` | 206-234 | `send_trial_expired_email()` — already exists and handles preference checking |
| `src/services/email_service.py` | varies | The generic `EmailService` is no longer used for trial emails after this change |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a test user with a trial subscription ending in 3 days
2. Wait for midnight — `TrialExpirationTask` runs, sending a 3-day reminder via `EmailService`
3. Wait for 3 AM — `subscription_tasks.check_and_notify_expiring_trials()` runs, sending another 3-day reminder via `BillingEmailService`
4. Check the user's email — they received two separate reminder emails with different templates
5. Alternatively, check the logs: both tasks log "Sent trial ending email" for the same subscription

### After Fix (Verify the Solution):
1. Create a test user with a trial subscription ending in 3 days
2. Run the midnight task: `python -m src.api.tasks.trial_expiration_task`
3. Verify: One reminder email sent via `BillingEmailService`
4. Run the 3 AM task: `python -c "import asyncio; from src.api.tasks.subscription_tasks import run_daily_subscription_tasks; asyncio.run(run_daily_subscription_tasks())"`
5. Verify: No trial-related emails sent (only usage reset runs)
6. Check logs: No duplicate processing

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "trial or subscription_task or expir" -v
```

---

## Acceptance Criteria

- [ ] `subscription_tasks.py` no longer contains `check_and_notify_expiring_trials()` or `expire_ended_trials()`
- [ ] `run_daily_subscription_tasks()` only runs `reset_monthly_usage()`
- [ ] `TrialExpirationTask` is the sole code path for trial reminders and expiration
- [ ] `TrialExpirationTask` uses `BillingEmailService` (not `EmailService`) for all emails
- [ ] `BillingEmailService` preference checking is active for trial emails
- [ ] Users receive exactly one reminder email per milestone (3 days, 1 day, 0 days)
- [ ] Expired trials are processed exactly once per day
- [ ] `reset_monthly_usage()` still runs daily at 3 AM (preserved in `subscription_tasks.py`)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** https://apscheduler.readthedocs.io/en/stable/ — APScheduler documentation for scheduled task management
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** https://docs.python.org/3/library/asyncio.html — Python asyncio for understanding the async task execution model
- **Related Issues/PRs:** TASK-124 (APScheduler Not Declared in Dependencies — the scheduler that runs these tasks)

---

## Dependencies & Related Tasks

- **Depends on:** TASK-124 (APScheduler must be installed for scheduled tasks to run at all)
- **Blocks:** None
- **Related:** TASK-124 (APScheduler dependency), TASK-079 (datetime.utcnow() deprecated — both task files use it)
