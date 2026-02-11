# Task 137: Email Sent Before Database Commit in Subscription Tasks — Orphaned Notifications

## Metadata
- **Task ID:** TASK-137
- **Source:** Backend Subscription & Billing Audit (Finding #23 under P2 Medium)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P2 Medium
- **Category:** data-integrity
- **Effort Estimate:** medium (1-4 hours)

---

## Description

In `src/api/tasks/subscription_tasks.py`, notification emails are sent to users **before** the database transaction is committed, creating a window where users receive emails about actions that never actually persisted to the database.

The most critical instance is in the `expire_ended_trials()` function (lines 138-170). The function iterates over expired trial subscriptions, and for each one:
1. Updates the subscription status to `EXPIRED` (line 141)
2. Sends a "trial expired" email to the user (line 158)
3. Only after **all** iterations completes, calls `await db.commit()` (line 170)

If the commit at line 170 fails — due to a database error, constraint violation, connection timeout, or any other issue — all the emails sent during the loop have already been delivered. Users receive "your trial has expired" emails while their trial status remains unchanged in the database (still `TRIAL`). This is the classic "dual write" problem where two side effects (database update + email send) are not atomically coupled.

The `check_and_notify_expiring_trials()` function (lines 29-107) has a similar pattern but is less severe because it only reads data without modifying it — though it still sends emails based on data that could change between the read and the email send.

Additionally, in `expire_ended_trials()`, a new `BillingEmailService` instance is created inside the loop on every iteration (line 157: `email_service = BillingEmailService(db)`), which is wasteful compared to creating it once before the loop.

The standard solution to this problem is to move email sending **after** the commit, or to use a transactional outbox pattern where email tasks are recorded in the database within the same transaction and processed separately after commit.

---

## Current Code

```python
# File: src/api/tasks/subscription_tasks.py
# Lines: 138-170 (expire_ended_trials — email before commit)
            for subscription in expired_trials:
                try:
                    # Mark as expired
                    subscription.status = SubscriptionStatus.EXPIRED
                    subscription.end_date = subscription.trial_end_date

                    # Get user for email
                    user_result = await db.execute(
                        select(Users).where(Users.id == subscription.user_id)
                    )
                    user = user_result.scalar_one_or_none()

                    plan_result = await db.execute(
                        select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
                    )
                    plan = plan_result.scalar_one_or_none()

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

            await db.commit()
```

```python
# File: src/api/tasks/subscription_tasks.py
# Lines: 63-95 (check_and_notify_expiring_trials — email in loop, no explicit commit needed but pattern is problematic)
            for subscription in expiring_trials:
                try:
                    # Get user and plan details
                    user_result = await db.execute(
                        select(Users).where(Users.id == subscription.user_id)
                    )
                    user = user_result.scalar_one_or_none()

                    plan_result = await db.execute(
                        select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
                    )
                    plan = plan_result.scalar_one_or_none()

                    if not user or not plan:
                        continue

                    # Send trial ending email
                    success = await email_service.send_trial_ending_email(
                        user_id=user.id,
                        plan_name=plan.display_name,
                        days_remaining=3,
                        trial_end_date=subscription.trial_end_date.strftime("%B %d, %Y")
                    )
```

---

## Why This Matters (Context & Reasoning)

Email notifications about subscription state changes are user-facing communications that set expectations. When a user receives "your trial has expired," they expect the trial to actually be expired. If the database commit fails and the trial is still active, the user may:
- Contact support about a "false alarm" email
- Attempt to upgrade unnecessarily
- Lose trust in the platform's reliability

In the payment/billing domain, consistency between state changes and notifications is critical. The transactional outbox pattern is the industry-standard solution for this class of problem, recommended by microservices architecture guides (e.g., Chris Richardson's Microservices Patterns, AWS Prescriptive Guidance).

For this codebase, a full outbox table may be overengineered. The simpler approach is to collect email tasks during the loop, commit the database changes, and then send the emails only after a successful commit. If the commit fails, no emails are sent. If email sending fails after commit, the database state is still correct and emails can be retried.

---

## Impact

- **Severity:** Users receive notification emails about subscription state changes that never actually persisted. Creates confusion, support tickets, and trust issues.
- **Affected Users/Flows:** All users with expiring trials (daily task), all users whose trials expire (daily task).
- **Blast Radius:** Every trial expiration and trial notification cycle. The problem scales with the number of trial users.

---

## Recommended Solution

Restructure the task functions to collect email payloads during processing, commit the database transaction, and only then send the emails. This ensures emails are only sent for changes that actually persisted.

### Step 1: Fix `expire_ended_trials()` — collect emails, commit, then send

```python
# File: src/api/tasks/subscription_tasks.py
# Replace the expire_ended_trials() function (lines 110-182) with:

async def expire_ended_trials():
    """
    Find trials that have ended and convert them to free plan or expired status.

    Should be run daily.

    Returns:
        Dict with conversion counts
    """
    async with get_async_db_context() as db:
        try:
            now = datetime.utcnow()

            # Find trials that have ended
            query = select(UserSubscription).where(
                and_(
                    UserSubscription.status == SubscriptionStatus.TRIAL,
                    UserSubscription.trial_end_date < now
                )
            )

            result = await db.execute(query)
            expired_trials = result.scalars().all()

            logger.info(f"Found {len(expired_trials)} expired trial(s)")

            expired_count = 0
            # Collect email tasks to send AFTER commit
            pending_emails = []

            email_service = BillingEmailService(db)

            for subscription in expired_trials:
                try:
                    # Mark as expired
                    subscription.status = SubscriptionStatus.EXPIRED
                    subscription.end_date = subscription.trial_end_date

                    # Get user for email
                    user_result = await db.execute(
                        select(Users).where(Users.id == subscription.user_id)
                    )
                    user = user_result.scalar_one_or_none()

                    plan_result = await db.execute(
                        select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
                    )
                    plan = plan_result.scalar_one_or_none()

                    if user and plan:
                        # Queue email for sending after commit
                        pending_emails.append({
                            "user_id": user.id,
                            "plan_name": plan.display_name,
                        })

                    expired_count += 1
                    logger.info(f"Expired trial subscription {subscription.id}")

                except Exception as e:
                    logger.error(f"Error expiring trial {subscription.id}: {e}")
                    continue

            # Commit all status changes first
            await db.commit()

            # Only send emails AFTER successful commit
            email_success_count = 0
            for email_data in pending_emails:
                try:
                    await email_service.send_trial_expired_email(
                        user_id=email_data["user_id"],
                        plan_name=email_data["plan_name"],
                    )
                    email_success_count += 1
                except Exception as e:
                    logger.error(
                        f"Failed to send trial expired email to user {email_data['user_id']}: {e}"
                    )

            logger.info(
                f"Expired {expired_count} trial subscription(s), "
                f"sent {email_success_count}/{len(pending_emails)} notification emails"
            )

            return {
                "trials_expired": expired_count,
                "emails_sent": email_success_count,
                "emails_failed": len(pending_emails) - email_success_count,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error in expire_ended_trials: {e}")
            await db.rollback()
            raise
```

### Step 2: Fix `check_and_notify_expiring_trials()` — same pattern

Although this function doesn't modify data, apply the same pattern for consistency and to prevent issues if the function is later modified to track notification state:

```python
# File: src/api/tasks/subscription_tasks.py
# Replace check_and_notify_expiring_trials() function (lines 29-107) with:

async def check_and_notify_expiring_trials():
    """
    Check for trials expiring in 3 days and send notification emails.

    Should be run daily.

    Returns:
        Dict with notification counts
    """
    async with get_async_db_context() as db:
        try:
            # Get trials expiring in exactly 3 days
            three_days_from_now = datetime.utcnow() + timedelta(days=3)
            start_of_day = three_days_from_now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = three_days_from_now.replace(hour=23, minute=59, second=59, microsecond=999999)

            # Find trials expiring in 3 days
            query = select(UserSubscription).where(
                and_(
                    UserSubscription.status == SubscriptionStatus.TRIAL,
                    UserSubscription.trial_end_date >= start_of_day,
                    UserSubscription.trial_end_date <= end_of_day
                )
            )

            result = await db.execute(query)
            expiring_trials = result.scalars().all()

            logger.info(f"Found {len(expiring_trials)} trial(s) expiring in 3 days")

            # Collect email data first (read phase)
            email_tasks = []
            email_service = BillingEmailService(db)

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

                    if not user or not plan:
                        continue

                    email_tasks.append({
                        "user_id": user.id,
                        "user_email": user.email,
                        "plan_name": plan.display_name,
                        "trial_end_date": subscription.trial_end_date.strftime("%B %d, %Y"),
                    })

                except Exception as e:
                    logger.error(f"Error preparing trial notification for subscription {subscription.id}: {e}")
                    continue

            # Send emails (send phase — after all reads complete)
            success_count = 0
            for email_data in email_tasks:
                try:
                    success = await email_service.send_trial_ending_email(
                        user_id=email_data["user_id"],
                        plan_name=email_data["plan_name"],
                        days_remaining=3,
                        trial_end_date=email_data["trial_end_date"]
                    )

                    if success:
                        success_count += 1
                        logger.info(f"Sent trial ending email to {email_data['user_email']}")
                    else:
                        logger.warning(f"Failed to send trial ending email to {email_data['user_email']}")

                except Exception as e:
                    logger.error(f"Error sending trial notification to {email_data['user_email']}: {e}")
                    continue

            logger.info(f"Successfully sent {success_count}/{len(email_tasks)} trial ending emails")

            return {
                "total_expiring": len(expiring_trials),
                "emails_sent": success_count,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error in check_and_notify_expiring_trials: {e}")
            raise
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/tasks/subscription_tasks.py` | `29-107` | `check_and_notify_expiring_trials()` — same email-before-read-complete pattern |
| `src/api/tasks/trial_expiration_task.py` | Various | May have similar email-before-commit patterns (needs verification) |
| `src/api/tasks/payment_dunning_task.py` | Various | Dunning emails may follow the same pattern |
| `src/api/tasks/grace_period_expiration_task.py` | Various | Grace period notifications may follow the same pattern |
| `src/services/webhook_handlers/subscription_handlers.py` | Various | Webhook handlers may send emails before state changes are committed |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a user with a trial subscription that has an expired `trial_end_date`
2. Temporarily introduce a database constraint violation in the commit path (e.g., set an invalid value on a non-nullable field before commit)
3. Run `expire_ended_trials()` manually
4. Observe that the email is sent but the database commit fails and the subscription status remains `TRIAL`
5. The user received a "trial expired" email while their trial is still active

### After Fix (Verify the Solution):
1. Repeat the same setup
2. Run `expire_ended_trials()` manually
3. Verify that when the commit fails, no email is sent
4. Fix the constraint violation and run again
5. Verify the commit succeeds AND then the email is sent
6. Check logs for email send counts matching committed changes

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "subscription_tasks or trial" -v
```

---

## Acceptance Criteria

- [ ] In `expire_ended_trials()`, emails are sent only after a successful `db.commit()`
- [ ] In `check_and_notify_expiring_trials()`, email data is collected during read phase and sent after all reads complete
- [ ] `BillingEmailService` is instantiated once per function call, not inside the loop
- [ ] Failed email sends after commit are logged but do not cause the task to fail
- [ ] Return dict includes `emails_sent` and `emails_failed` counts
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy ORM Events — after_commit](https://docs.sqlalchemy.org/en/20/orm/events.html#sqlalchemy.orm.SessionEvents.after_commit)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Transactional Outbox Pattern — Microservices.io](https://microservices.io/patterns/data/transactional-outbox.html)
- **Related Issues/PRs:** [AWS Prescriptive Guidance — Transactional Outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-133 (Duplicate Trial Expiration — two independent code paths that both have this pattern), TASK-135 (CLEANUP_ENABLED gates all tasks — affects whether these tasks even run)
