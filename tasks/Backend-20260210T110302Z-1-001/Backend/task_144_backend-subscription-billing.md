# Task 144: Fix N+1 Queries in Subscription Background Tasks

## Metadata
- **Task ID:** TASK-144
- **Source:** Subscription & Billing (Finding #22 under P2 Medium)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P2 Medium
- **Category:** performance
- **Effort Estimate:** small (< 1 hour)

---

## Description

The subscription background tasks in `rext-backend/src/api/tasks/subscription_tasks.py` contain classic N+1 query patterns in two functions: `check_and_notify_expiring_trials()` (lines 63-74) and `expire_ended_trials()` (lines 138-153). Both functions first query a list of `UserSubscription` records, then iterate over each record and execute two additional individual queries to load the related `Users` and `SubscriptionPlan` objects:

```python
for subscription in expiring_trials:
    user_result = await db.execute(
        select(Users).where(Users.id == subscription.user_id)
    )
    user = user_result.scalar_one_or_none()

    plan_result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
    )
    plan = plan_result.scalar_one_or_none()
```

This generates `1 + (N × 2)` database queries where N is the number of matching subscriptions. For 100 expiring trials, this produces 201 separate queries instead of the 1-3 queries that eager loading would require. The `UserSubscription` model already defines proper relationships (`user` and `plan` via SQLAlchemy `relationship()`) that support eager loading, and the codebase already uses `selectinload` in other services (e.g., `subscription_service.py` line 846, `usage_tracking_service.py` line 52, `refund_service.py` line 239) — so the infrastructure is in place.

SQLAlchemy 2.0.44 is installed (confirmed in `pyproject.toml`), which fully supports both `selectinload()` and `joinedload()` with async sessions. The `selectinload` strategy is preferred here because it avoids result set duplication and works cleanly with `.scalars().all()` — consistent with the existing patterns in the codebase.

---

## Current Code

```python
# File: rext-backend/src/api/tasks/subscription_tasks.py
# Lines: 46-74 — check_and_notify_expiring_trials() with N+1 pattern
query = select(UserSubscription).where(
    and_(
        UserSubscription.status == SubscriptionStatus.TRIAL,
        UserSubscription.trial_end_date >= start_of_day,
        UserSubscription.trial_end_date <= end_of_day
    )
)

result = await db.execute(query)
expiring_trials = result.scalars().all()

# N+1: For each subscription, 2 individual queries
for subscription in expiring_trials:
    try:
        user_result = await db.execute(
            select(Users).where(Users.id == subscription.user_id)
        )
        user = user_result.scalar_one_or_none()

        plan_result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
        )
        plan = plan_result.scalar_one_or_none()
```

```python
# File: rext-backend/src/api/tasks/subscription_tasks.py
# Lines: 124-153 — expire_ended_trials() with same N+1 pattern
query = select(UserSubscription).where(
    and_(
        UserSubscription.status == SubscriptionStatus.TRIAL,
        UserSubscription.trial_end_date < now
    )
)

result = await db.execute(query)
expired_trials = result.scalars().all()

for subscription in expired_trials:
    try:
        user_result = await db.execute(
            select(Users).where(Users.id == subscription.user_id)
        )
        user = user_result.scalar_one_or_none()

        plan_result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
        )
        plan = plan_result.scalar_one_or_none()
```

---

## Why This Matters (Context & Reasoning)

These background tasks run daily via APScheduler (once the APScheduler dependency issue from TASK-124 is resolved). They process every trial subscription that is expiring or has expired. As the user base grows, the number of trial subscriptions processed per run scales linearly, and the N+1 pattern causes the database query count to scale at `2N + 1`. At scale:

- 10 trials → 21 queries (manageable)
- 100 trials → 201 queries (noticeable latency)
- 1,000 trials → 2,001 queries (database connection pool exhaustion risk)

Each individual query has overhead from connection pool checkout, query parsing, network round-trip, and result deserialization. With eager loading, the same work is done in 1-3 queries regardless of N. This is especially important for background tasks because they run in a constrained context (potentially single database connection) and should be optimized for throughput.

---

## Impact

- **Severity:** At current scale, this causes slow task execution. At scale (hundreds of trials), it risks database connection pool exhaustion and task timeouts, potentially causing missed trial expirations and notification failures.
- **Affected Users/Flows:** Trial users approaching expiration (missed notification emails), expired trial users (delayed status transitions), system health (database load during task execution windows).
- **Blast Radius:** Contained to the background task execution window. Does not affect interactive API requests, but shares the database connection pool.

---

## Recommended Solution

### Step 1: Add selectinload to check_and_notify_expiring_trials() initial query

```python
# File: rext-backend/src/api/tasks/subscription_tasks.py
# Add import at top of file (line 4, after existing imports):
from sqlalchemy.orm import selectinload

# Replace lines 46-55 with:
query = select(UserSubscription).options(
    selectinload(UserSubscription.user),
    selectinload(UserSubscription.plan)
).where(
    and_(
        UserSubscription.status == SubscriptionStatus.TRIAL,
        UserSubscription.trial_end_date >= start_of_day,
        UserSubscription.trial_end_date <= end_of_day
    )
)

result = await db.execute(query)
expiring_trials = result.scalars().all()
```

### Step 2: Replace per-subscription queries with relationship access in check_and_notify_expiring_trials()

```python
# File: rext-backend/src/api/tasks/subscription_tasks.py
# Replace lines 63-95 (the for loop) with:

for subscription in expiring_trials:
    try:
        user = subscription.user
        plan = subscription.plan

        if not user or not plan:
            continue

        # Send trial ending email
        success = await email_service.send_trial_ending_email(
            user_id=user.id,
            plan_name=plan.display_name,
            days_remaining=3,
            trial_end_date=subscription.trial_end_date.strftime("%B %d, %Y")
        )

        if success:
            success_count += 1
            logger.info(f"Sent trial ending email to {user.email}")
        else:
            logger.warning(f"Failed to send trial ending email to {user.email}")

    except Exception as e:
        logger.error(f"Error sending trial notification for subscription {subscription.id}: {e}")
        continue
```

### Step 3: Add selectinload to expire_ended_trials() initial query

```python
# File: rext-backend/src/api/tasks/subscription_tasks.py
# Replace lines 124-132 with:

query = select(UserSubscription).options(
    selectinload(UserSubscription.user),
    selectinload(UserSubscription.plan)
).where(
    and_(
        UserSubscription.status == SubscriptionStatus.TRIAL,
        UserSubscription.trial_end_date < now
    )
)

result = await db.execute(query)
expired_trials = result.scalars().all()
```

### Step 4: Replace per-subscription queries with relationship access in expire_ended_trials()

```python
# File: rext-backend/src/api/tasks/subscription_tasks.py
# Replace lines 138-168 (the for loop) with:

for subscription in expired_trials:
    try:
        # Mark as expired
        subscription.status = SubscriptionStatus.EXPIRED
        subscription.end_date = subscription.trial_end_date

        user = subscription.user
        plan = subscription.plan

        if user and plan:
            # Send trial expired email
            email_service = BillingEmailService(db)
            await email_service.send_trial_expired_email(
                user_id=user.id,
                plan_name=plan.display_name
            )

        expired_count += 1
        logger.info(f"Expired trial subscription {subscription.id}")

    except Exception as e:
        logger.error(f"Error expiring trial {subscription.id}: {e}")
        continue
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/tasks/trial_expiration_task.py` | Various | The duplicate trial expiration task (TASK-133) — check for similar N+1 patterns |
| `rext-backend/src/api/tasks/subscription_tasks.py` | `185-240` | `reset_monthly_usage()` does not load user/plan, so no N+1 issue there |
| `rext-backend/src/services/subscription_service.py` | `846-858` | Already uses `selectinload(UserSubscription.plan)` — good reference pattern |
| `rext-backend/src/services/usage_tracking_service.py` | `52-58` | Already uses `selectinload(UserSubscription.plan)` — good reference pattern |
| `rext-backend/src/services/refund_service.py` | `239-247` | Uses `joinedload` for nested relationships — alternative approach reference |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Enable SQL query logging in SQLAlchemy by setting `echo=True` on the engine or configuring `logging.getLogger("sqlalchemy.engine").setLevel(logging.DEBUG)`
2. Seed the database with 10+ trial subscriptions expiring in 3 days
3. Run `check_and_notify_expiring_trials()` manually
4. Count the number of SQL queries logged — should be 1 + (10 × 2) = 21

### After Fix (Verify the Solution):
1. Keep SQL logging enabled
2. Run `check_and_notify_expiring_trials()` with the same test data
3. Count the SQL queries — should be exactly 3 (1 main query + 2 selectinload queries)
4. Verify all trial notification emails are still sent correctly
5. Run `expire_ended_trials()` and verify the same reduction in queries
6. Verify expired trials have their status updated to EXPIRED

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "subscription_task" -v
cd rext-backend && python -m pytest tests/ -k "trial" -v
```

---

## Acceptance Criteria

- [ ] `selectinload` import added to `subscription_tasks.py`
- [ ] `check_and_notify_expiring_trials()` uses `.options(selectinload(UserSubscription.user), selectinload(UserSubscription.plan))` in its initial query
- [ ] `expire_ended_trials()` uses `.options(selectinload(UserSubscription.user), selectinload(UserSubscription.plan))` in its initial query
- [ ] All per-subscription `select(Users).where(...)` and `select(SubscriptionPlan).where(...)` queries removed from both functions
- [ ] Relationship access via `subscription.user` and `subscription.plan` used instead
- [ ] Query count reduced from `1 + (N × 2)` to 3 (or fewer) regardless of N
- [ ] Email sending functionality preserved — all notifications still sent correctly
- [ ] Trial expiration status updates preserved
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 Relationship Loading Techniques](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html) — comprehensive guide on selectinload, joinedload, and other eager loading strategies
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Advanced SQLAlchemy 2.0: SelectinLoad and WithParent Strategies](https://www.johal.in/advanced-sqlalchemy-2-0-selectinload-and-withparent-strategies-2025/) — practical guide on when to use selectinload vs joinedload
- **Related Issues/PRs:** None identified

---

## Dependencies & Related Tasks

- **Depends on:** TASK-124 (APScheduler Not Declared in Dependencies — these tasks can only run when APScheduler is properly installed)
- **Blocks:** None
- **Related:** TASK-133 (Duplicate Trial Expiration — the duplicate trial_expiration_task.py may have similar N+1 patterns), TASK-137 (Email Sent Before Commit in Tasks — another issue in the same subscription_tasks.py file)
