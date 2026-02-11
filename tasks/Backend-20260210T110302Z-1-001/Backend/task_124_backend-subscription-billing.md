# Task 124: Add APScheduler to Project Dependencies — All Billing Automation Non-Functional

## Metadata
- **Task ID:** TASK-124
- **Source:** Backend Subscription & Billing Audit (Finding #1 under P0 Critical)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P0 Critical
- **Category:** dependency
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `apscheduler` package is used by `src/tasks/scheduled_tasks.py` to run 5 critical billing automation jobs, but it is **not declared in `pyproject.toml`** as a project dependency. This means the package is not installed in production environments when the project is deployed via `pip install`, and all billing automation silently fails to start.

The `scheduled_tasks.py` file at lines 13-20 imports APScheduler with a graceful fallback:

```python
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
```

When APScheduler is not installed, `APSCHEDULER_AVAILABLE` is set to `False`. The `start()` method at line 46-51 checks this flag and logs a warning: `"APScheduler not installed. Scheduled tasks disabled."` — but this warning is easily missed in a sea of startup logs. No alert is raised, no health check fails, and the application appears to run normally.

The 5 critical jobs that never execute without APScheduler:

1. **Data cleanup** — Daily at 2 AM: Removes expired sessions, stale data, and orphaned records.
2. **Trial expiration** — Daily at midnight: Transitions expired trials to inactive status and sends reminder emails (3-day, 1-day, same-day).
3. **Payment dunning** — Daily at 1 AM: Sends escalating payment failure notifications and manages dunning sequences for subscriptions with failed payments.
4. **Grace period expiration** — Daily at 1:30 AM: Suspends subscriptions whose grace period has ended after payment failure.
5. **Subscription maintenance** — Daily at 3 AM: Monthly usage counter resets, stale subscription cleanup, and trial expiration checks.

The `pyproject.toml` currently lists 64 dependencies (lines 11-64), including `tenacity>=8.2.0` (which is also installed but never used — see Finding 8). The APScheduler package was likely installed in the developer's local environment via `pip install apscheduler` but never added to the project's dependency file, so it works locally but not in fresh deployments.

The current latest stable version of APScheduler is **3.11.2** on PyPI. The code uses the 3.x API (`AsyncIOScheduler`, `CronTrigger`), not the 4.x rewrite (which has a completely different API). The version constraint should be `>=3.10.0,<4.0.0` to ensure compatibility with the 3.x API while allowing patch updates.

---

## Current Code

```python
# File: src/tasks/scheduled_tasks.py
# Lines: 13-20 — Graceful fallback when APScheduler is missing
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    AsyncIOScheduler = None
    CronTrigger = None
```

```python
# File: src/tasks/scheduled_tasks.py
# Lines: 40-51 — Scheduler start with silent skip when unavailable
    def start(self):
        """Start the scheduler and register tasks."""
        if not cleanup_config.CLEANUP_ENABLED:
            logger.info("Scheduled tasks disabled (CLEANUP_ENABLED=false)")
            return

        if not APSCHEDULER_AVAILABLE:
            logger.warning(
                "APScheduler not installed. Scheduled tasks disabled. "
                "Install with: pip install apscheduler"
            )
            return
```

```toml
# File: pyproject.toml
# Lines: 11-64 — Dependencies (apscheduler is ABSENT)
dependencies = [
    "language-tool-python",
    "alembic>=1.13.0",
    "crawl4ai>=0.7.2",
    # ... 61 other packages ...
    "aiosmtplib>=3.0.0",
]
# NOTE: "apscheduler" is NOT listed anywhere in this file
```

---

## Why This Matters (Context & Reasoning)

The billing automation system is the backbone of subscription lifecycle management. Without these scheduled tasks running:

- **Users on expired trials continue using the product for free.** The trial expiration task transitions trials to inactive status. Without it, trial users never get cut off.
- **Failed payments are never followed up.** The dunning task sends escalating reminders (day 1, day 3, day 6) to users with failed payments. Without it, revenue is silently lost.
- **Grace periods never end.** After a payment failure, users get a grace period (typically 7 days). The grace period expiration task suspends access when this period ends. Without it, users with permanently failed payments retain full access indefinitely.
- **Usage counters never reset.** Monthly API call counters, content item counts, etc. are reset by the subscription maintenance task. Without it, users hit limits that never reset, or (if resets are handled elsewhere) potentially get unlimited usage.
- **Stale data accumulates.** Expired sessions, old webhook events, and orphaned records are never cleaned up, degrading database performance over time.

This is particularly insidious because the application starts and serves requests normally — there's no crash, no error page, no failed health check. The only indication is a single `WARNING` log line at startup. In a production environment with thousands of log lines, this is easy to miss.

---

## Impact

- **Severity:** All 5 billing automation jobs are non-functional in production. Trial users never expire, payment failures are never dunned, grace periods never end, usage counters never reset, and stale data accumulates.
- **Affected Users/Flows:** Every subscription lifecycle transition that depends on scheduled automation: trial expiration, payment failure handling, grace period enforcement, monthly usage resets, data cleanup.
- **Blast Radius:** System-wide. Every paying customer is potentially affected by missing dunning, every trial user benefits from never-expiring trials, every subscription accumulates stale usage data.

---

## Recommended Solution

### Step 1: Add `apscheduler` to project dependencies

```toml
# File: pyproject.toml
# Add to the dependencies list (after "aiosmtplib>=3.0.0" on line 64, or in alphabetical order):
    "apscheduler>=3.10.0,<4.0.0",
```

The version constraint `>=3.10.0,<4.0.0` is important because:
- `>=3.10.0` ensures compatibility with the `AsyncIOScheduler` API used in the codebase.
- `<4.0.0` prevents accidentally upgrading to APScheduler 4.x, which has a completely rewritten API and would break all existing scheduler code.

### Step 2: Install the dependency

```bash
cd rext-backend && pip install -e .
```

### Step 3: Verify scheduler starts correctly

After adding the dependency, restart the application and verify:

1. The startup log should show `"Starting scheduled task manager..."` followed by `"Scheduled tasks started."` — NOT the `"APScheduler not installed"` warning.
2. The scheduler should register all 5 jobs.

### Step 4: (Recommended) Add a health check for the scheduler

Add a simple health check to verify the scheduler is running in production:

```python
# File: src/tasks/scheduled_tasks.py
# Add after the shutdown method (after line 132):

    def get_status(self) -> dict:
        """Get scheduler status for health checks."""
        if not self._running or not self.scheduler:
            return {
                "running": False,
                "jobs": [],
                "reason": "Scheduler not started" if not APSCHEDULER_AVAILABLE else "CLEANUP_ENABLED is False"
            }

        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None
            })

        return {
            "running": True,
            "job_count": len(jobs),
            "jobs": jobs
        }
```

### Step 5: (Recommended) Upgrade the startup log level for missing APScheduler

Change the warning to an error-level log with a more prominent message, since missing billing automation is a critical issue:

```python
# File: src/tasks/scheduled_tasks.py
# Replace lines 47-51 with:

        if not APSCHEDULER_AVAILABLE:
            logger.error(
                "CRITICAL: APScheduler not installed — ALL billing automation is disabled! "
                "Trial expiration, payment dunning, grace period enforcement, usage resets, "
                "and data cleanup will NOT run. Install with: pip install 'apscheduler>=3.10.0,<4.0.0'"
            )
            return
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/tasks/trial_expiration_task.py` | All | Trial expiration task — registered by scheduler, will start running once APScheduler is installed |
| `src/api/tasks/payment_dunning_task.py` | All | Payment dunning task — same as above |
| `src/api/tasks/grace_period_expiration_task.py` | All | Grace period expiration task — same as above |
| `src/api/tasks/subscription_tasks.py` | All | Subscription maintenance tasks — same as above |
| `src/services/data_cleanup_service.py` | All | Data cleanup service — called by the cleanup scheduled task |
| `src/config/cleanup_config.py` | All | Cleanup configuration — controls `CLEANUP_ENABLED` flag and schedule timing |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a fresh Python virtual environment: `python -m venv test_env && source test_env/bin/activate`
2. Install the project: `cd rext-backend && pip install -e .`
3. Run `python -c "import apscheduler"` — expect `ModuleNotFoundError: No module named 'apscheduler'`.
4. Start the application and check logs — expect to see: `"APScheduler not installed. Scheduled tasks disabled."`.

### After Fix (Verify the Solution):
1. Create a fresh virtual environment and install: `pip install -e .`
2. Run `python -c "import apscheduler; print(apscheduler.__version__)"` — expect version `3.10.x` or `3.11.x`.
3. Start the application and check logs — expect to see: `"Starting scheduled task manager..."` and `"Scheduled tasks started."`.
4. Verify all 5 jobs are registered by checking the log output or the health check endpoint.
5. Set `CLEANUP_ENABLED=false` and restart — verify the scheduler correctly skips starting (expected behavior for the flag).

### Run Existing Tests:
```bash
cd rext-backend && pip install -e . && python -m pytest tests/ -v -k "scheduled or task or cleanup" --no-header
```

---

## Acceptance Criteria

- [ ] `apscheduler>=3.10.0,<4.0.0` is listed in `pyproject.toml` under `[project.dependencies]`
- [ ] `pip install -e .` in a fresh virtual environment successfully installs APScheduler
- [ ] Application startup with `CLEANUP_ENABLED=true` shows scheduler starting with 5 registered jobs
- [ ] Application startup with `CLEANUP_ENABLED=false` shows scheduler disabled (existing behavior preserved)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [APScheduler 3.x AsyncIOScheduler](https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/asyncio.html) — Documentation for the async scheduler used in the codebase
- **Security Advisory:** N/A
- **Migration Guide:** N/A (adding a new dependency, not migrating)
- **Best Practice Reference:** [APScheduler PyPI](https://pypi.org/project/APScheduler/) — PyPI page showing latest version (3.11.2) and compatibility information
- **Related Issues/PRs:** [APScheduler GitHub Repository](https://github.com/agronholm/apscheduler) — Source code and issue tracker

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** All tasks related to billing automation: any fix to trial expiration, dunning, grace period, or usage reset tasks depends on the scheduler actually running
- **Related:** TASK-004 (B1: Deprecated datetime.utcnow — used in scheduled task files), TASK-079 (B3: datetime.utcnow deprecated — same pattern in task files)
