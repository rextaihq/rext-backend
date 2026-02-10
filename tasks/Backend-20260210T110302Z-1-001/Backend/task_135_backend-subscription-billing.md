# Task 135: CLEANUP_ENABLED Flag Gates All Scheduled Tasks Including Critical Billing Automation

## Metadata
- **Task ID:** TASK-135
- **Source:** Backend Subscription & Billing Audit (Finding #16 under P1 High)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `CLEANUP_ENABLED` environment variable in `src/config/cleanup_config.py` (line 23) controls whether **all** scheduled background tasks are initialized, despite its name implying it only controls data cleanup operations. When `ScheduledTaskManager.start()` is called in `src/tasks/scheduled_tasks.py` (line 42), the very first check is `if not cleanup_config.CLEANUP_ENABLED`, which returns immediately without starting the scheduler at all — meaning zero scheduled jobs are registered.

This is a misleading naming problem with operational consequences. The flag gates five completely different scheduled task categories:

1. **Data cleanup** (the only task the flag name describes) — runs at configured time (default 2 AM)
2. **Trial expiration checks** — runs daily at midnight via `run_trial_expiration_task`
3. **Payment dunning reminders** — runs daily at 1 AM via `run_payment_dunning_task`
4. **Grace period expiration** — runs daily at 1:30 AM via `run_grace_period_expiration_task`
5. **Subscription maintenance** (usage resets, trial notifications, trial expirations) — runs daily at 3 AM via `run_daily_subscription_tasks`

An operator who sets `CLEANUP_ENABLED=false` — reasonably believing they are disabling a non-critical data cleanup cron — will silently disable all billing automation. Users will never receive trial expiration warnings, expired trials will remain in "trial" status indefinitely, failed payment dunning reminders will stop, grace periods will never expire, and monthly API usage counters will never reset.

The module docstring in `scheduled_tasks.py` (line 7) reinforces the confusion: *"To enable scheduled tasks, set CLEANUP_ENABLED=true in environment variables."* — this documents the problem but does not fix it.

---

## Current Code

```python
# File: src/config/cleanup_config.py
# Lines: 22-23
    CLEANUP_ENABLED: bool = os.getenv("CLEANUP_ENABLED", "true").lower() == "true"
```

```python
# File: src/tasks/scheduled_tasks.py
# Lines: 40-44
    def start(self):
        """Start the scheduler and register tasks."""
        if not cleanup_config.CLEANUP_ENABLED:
            logger.info("Scheduled tasks disabled (CLEANUP_ENABLED=false)")
            return
```

---

## Why This Matters (Context & Reasoning)

The scheduled task system is the backbone of billing automation. Without it, the subscription lifecycle breaks down: trials never expire, dunning emails never send, grace periods never enforce downgrades, and usage counters never reset. These are revenue-critical operations — a user could remain on a trial indefinitely if the expiration task never runs.

The danger is specifically that the flag name is **actively misleading**. It would be one thing if the flag were named `SCHEDULER_ENABLED` — an operator would think carefully before disabling it. But `CLEANUP_ENABLED` sounds like a housekeeping toggle for purging old logs, which is exactly the kind of thing operators disable in staging or cost-constrained environments.

---

## Impact

- **Severity:** All billing automation silently disabled if `CLEANUP_ENABLED=false`. Trials never expire, dunning emails never send, grace periods never enforce, usage never resets.
- **Affected Users/Flows:** Every user on a trial, every user with a failed payment in dunning, every user in a grace period, every user with monthly usage limits.
- **Blast Radius:** System-wide — affects the entire subscription lifecycle for all users.

---

## Recommended Solution

Separate the single `CLEANUP_ENABLED` flag into granular flags, each controlling a specific task category. Rename the master flag to `SCHEDULER_ENABLED` to accurately describe its scope.

### Step 1: Update `CleanupConfig` with granular task flags

```python
# File: src/config/cleanup_config.py
# Replace lines 22-23 with:

    # Master scheduler switch
    SCHEDULER_ENABLED: bool = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"

    # Individual task category switches (all default to True)
    CLEANUP_ENABLED: bool = os.getenv("CLEANUP_ENABLED", "true").lower() == "true"
    BILLING_TASKS_ENABLED: bool = os.getenv("BILLING_TASKS_ENABLED", "true").lower() == "true"
    TRIAL_TASKS_ENABLED: bool = os.getenv("TRIAL_TASKS_ENABLED", "true").lower() == "true"
    DUNNING_TASKS_ENABLED: bool = os.getenv("DUNNING_TASKS_ENABLED", "true").lower() == "true"
    GRACE_PERIOD_TASKS_ENABLED: bool = os.getenv("GRACE_PERIOD_TASKS_ENABLED", "true").lower() == "true"
```

### Step 2: Update `ScheduledTaskManager.start()` to use granular flags

```python
# File: src/tasks/scheduled_tasks.py
# Replace the start() method (lines 40-124) with:

    def start(self):
        """Start the scheduler and register tasks."""
        if not cleanup_config.SCHEDULER_ENABLED:
            logger.info("Scheduler disabled (SCHEDULER_ENABLED=false). No scheduled tasks will run.")
            return

        if not APSCHEDULER_AVAILABLE:
            logger.warning(
                "APScheduler not installed. Scheduled tasks disabled. "
                "Install with: pip install apscheduler"
            )
            return

        if self.scheduler and self._running:
            logger.warning("Scheduler already running")
            return

        logger.info("Starting scheduled task manager...")

        self.scheduler = AsyncIOScheduler()

        # Schedule daily cleanup at configured time (default 2 AM)
        if cleanup_config.CLEANUP_ENABLED:
            self.scheduler.add_job(
                self._run_data_cleanup,
                trigger=CronTrigger(
                    hour=cleanup_config.CLEANUP_HOUR,
                    minute=cleanup_config.CLEANUP_MINUTE
                ),
                id="data_cleanup",
                name="Daily data cleanup",
                replace_existing=True,
                max_instances=1,
            )
            logger.info("Registered task: data_cleanup")
        else:
            logger.info("Data cleanup task disabled (CLEANUP_ENABLED=false)")

        # Trial expiration check — daily at midnight
        if cleanup_config.TRIAL_TASKS_ENABLED:
            self.scheduler.add_job(
                run_trial_expiration_task,
                trigger=CronTrigger(hour=0, minute=0),
                id="trial_expiration",
                name="Daily trial expiration check",
                replace_existing=True,
                max_instances=1,
            )
            logger.info("Registered task: trial_expiration")
        else:
            logger.info("Trial expiration task disabled (TRIAL_TASKS_ENABLED=false)")

        # Payment dunning reminders — daily at 1 AM
        if cleanup_config.DUNNING_TASKS_ENABLED:
            self.scheduler.add_job(
                run_payment_dunning_task,
                trigger=CronTrigger(hour=1, minute=0),
                id="payment_dunning",
                name="Daily payment dunning",
                replace_existing=True,
                max_instances=1,
            )
            logger.info("Registered task: payment_dunning")
        else:
            logger.info("Payment dunning task disabled (DUNNING_TASKS_ENABLED=false)")

        # Grace period expiration — daily at 1:30 AM
        if cleanup_config.GRACE_PERIOD_TASKS_ENABLED:
            self.scheduler.add_job(
                run_grace_period_expiration_task,
                trigger=CronTrigger(hour=1, minute=30),
                id="grace_period_expiration",
                name="Daily grace period expiration",
                replace_existing=True,
                max_instances=1,
            )
            logger.info("Registered task: grace_period_expiration")
        else:
            logger.info("Grace period expiration task disabled (GRACE_PERIOD_TASKS_ENABLED=false)")

        # Subscription maintenance — daily at 3 AM
        if cleanup_config.BILLING_TASKS_ENABLED:
            self.scheduler.add_job(
                run_daily_subscription_tasks,
                trigger=CronTrigger(hour=3, minute=0),
                id="subscription_maintenance",
                name="Daily subscription maintenance",
                replace_existing=True,
                max_instances=1,
            )
            logger.info("Registered task: subscription_maintenance")
        else:
            logger.info("Subscription maintenance task disabled (BILLING_TASKS_ENABLED=false)")

        # Only start the scheduler if at least one job was registered
        if self.scheduler.get_jobs():
            self.scheduler.start()
            self._running = True
            logger.info(
                f"Scheduled tasks started with {len(self.scheduler.get_jobs())} job(s).",
                extra={
                    "cleanup_hour": cleanup_config.CLEANUP_HOUR,
                    "cleanup_minute": cleanup_config.CLEANUP_MINUTE,
                    "jobs": [job.id for job in self.scheduler.get_jobs()]
                }
            )
        else:
            logger.warning("No scheduled tasks registered. Scheduler not started.")
```

### Step 3: Update module docstring

```python
# File: src/tasks/scheduled_tasks.py
# Replace lines 1-8 with:
"""
Scheduled Tasks

Background scheduled tasks using APScheduler.
Handles data cleanup, billing automation, trial management, and other periodic operations.

Environment variables:
- SCHEDULER_ENABLED: Master switch for all scheduled tasks (default: true)
- CLEANUP_ENABLED: Toggle data cleanup task (default: true)
- BILLING_TASKS_ENABLED: Toggle subscription maintenance tasks (default: true)
- TRIAL_TASKS_ENABLED: Toggle trial expiration tasks (default: true)
- DUNNING_TASKS_ENABLED: Toggle payment dunning reminders (default: true)
- GRACE_PERIOD_TASKS_ENABLED: Toggle grace period expiration (default: true)
"""
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/config/cleanup_config.py` | `23` | The `CLEANUP_ENABLED` flag definition — needs renaming and new flags added |
| `src/tasks/scheduled_tasks.py` | `7, 42-43` | Docstring and flag check that use the misleading name |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Set `CLEANUP_ENABLED=false` in `.env`
2. Start the application and observe logs
3. Confirm log message: `"Scheduled tasks disabled (CLEANUP_ENABLED=false)"`
4. Verify that no scheduled jobs are running (no trial expiration, no dunning, no grace period enforcement)

### After Fix (Verify the Solution):
1. Set `SCHEDULER_ENABLED=true` and `CLEANUP_ENABLED=false` in `.env`
2. Start the application and observe logs
3. Confirm that data cleanup is disabled but all billing tasks (trial, dunning, grace period, subscription maintenance) are still registered and running
4. Verify log messages show individual task registration status
5. Set `SCHEDULER_ENABLED=false` and verify all tasks are disabled with a clear log message

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "scheduled" -v
```

---

## Acceptance Criteria

- [ ] `SCHEDULER_ENABLED=false` disables all scheduled tasks with a clear log message
- [ ] `CLEANUP_ENABLED=false` only disables the data cleanup task, not billing automation
- [ ] Each task category has its own enable/disable flag
- [ ] Each task category logs its registration or skip status on startup
- [ ] Scheduler is not started if no jobs are registered
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [APScheduler 3.x User Guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [APScheduler Job Management — pause/resume individual jobs](https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/base.html)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** TASK-124 (APScheduler Not Declared in Dependencies — must be installable first)
- **Blocks:** None
- **Related:** TASK-133 (Duplicate Trial Expiration — two code paths), TASK-124 (APScheduler dependency)
