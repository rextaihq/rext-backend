# Task 146: Replace Deprecated `datetime.utcnow()` Across Billing Codebase

## Metadata
- **Task ID:** TASK-146
- **Source:** B5 - Subscription & Billing (Finding #18 under P2 Medium)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P2 Medium
- **Category:** deprecated-deps
- **Effort Estimate:** large (4+ hours)

---

## Description

`datetime.utcnow()` is deprecated since Python 3.12 (PEP 587 / CPython issue #80406). It returns a naive datetime (no timezone info), which can cause subtle bugs when compared with timezone-aware datetimes from external APIs like LemonSqueezy. The entire billing subsystem uses `datetime.utcnow()` pervasively — approximately **75+ occurrences** across 20+ billing-related files including services, models, tasks, routes, and middleware.

The project requires Python `>=3.11,<3.12` (per `pyproject.toml`), so the deprecation warning is not yet emitted at runtime. However, this will break when the project upgrades to Python 3.12+, and the naive-vs-aware datetime mismatch already poses a risk: LemonSqueezy webhook data contains ISO 8601 timestamps with timezone info, and the `subscription_handlers.py` file explicitly strips timezone info via `.replace(tzinfo=None)` to match the naive datetimes stored in the database. This is a fragile workaround that masks the real issue.

The correct replacement is `datetime.now(datetime.timezone.utc)`, which returns a timezone-aware UTC datetime. For SQLAlchemy model column defaults, `func.now()` (server-side default) or `datetime.now(timezone.utc)` should be used.

This is the **fourth** occurrence of this finding across audit reports (B1-Finding 4 as TASK-004, B2-Finding 21 as TASK-045, B3-Finding 20 as TASK-079, B4-Finding 8 as TASK-101). This task covers ONLY the billing-specific files not addressed by previous tasks.

---

## Current Code

The pattern is identical everywhere. Representative examples:

```python
# File: rext-backend/src/services/subscription_management_service.py
# Lines: 48-61
trial_end = datetime.utcnow() + timedelta(days=payload.trial_days)
# ...
start_date=datetime.utcnow(),
usage_reset_date=datetime.utcnow() + timedelta(days=30),
created_at=datetime.utcnow(),
updated_at=datetime.utcnow(),
```

```python
# File: rext-backend/src/api/models/subscription_models/subscriptions.py
# Lines: 43, 68, 73-74
start_date = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
usage_reset_date = Column(TIMESTAMP, default=datetime.utcnow)
created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
```

```python
# File: rext-backend/src/services/subscription_analytics_service.py
# Lines: 41, 93-94
thirty_days_ago = datetime.utcnow() - timedelta(days=30)
period_start = datetime.utcnow() - timedelta(days=period_days)
period_end = datetime.utcnow()
```

---

## Why This Matters (Context & Reasoning)

The billing system is the most critical financial component of the application. Timestamp accuracy directly affects:
- **Trial expiration calculations:** A naive UTC datetime compared with a timezone-aware datetime raises `TypeError` in Python
- **Grace period enforcement:** Incorrect timezone handling could extend or shorten grace periods
- **Usage reset dates:** Reset date calculations must be accurate to prevent premature or delayed usage resets
- **Revenue analytics:** Time-based revenue queries depend on consistent datetime handling
- **Webhook processing:** LemonSqueezy sends timezone-aware timestamps; the current code strips timezone info as a workaround

When the project upgrades to Python 3.12+, every call to `datetime.utcnow()` will emit a `DeprecationWarning`, and in a future Python version it will be removed entirely.

---

## Impact

- **Severity:** Deprecation warnings in Python 3.12+. Future removal will cause `AttributeError`. Potential for timezone comparison bugs when interacting with LemonSqueezy API responses.
- **Affected Users/Flows:** All billing flows: subscription creation, trial management, dunning, grace periods, usage tracking, license activation, webhook processing, analytics, exports.
- **Blast Radius:** Extensive — 20+ files across the billing subsystem. However, each replacement is mechanical and low-risk.

---

## Recommended Solution

This is a mechanical find-and-replace with two patterns:

**Pattern A (service/task code):** Replace `datetime.utcnow()` with `datetime.now(timezone.utc)`.

**Pattern B (model column defaults):** Replace `default=datetime.utcnow` with `default=lambda: datetime.now(timezone.utc)` or use `server_default=func.now()`.

### Step 1: Update imports in every affected file

In every file that uses `from datetime import datetime, timedelta`, add `timezone`:

```python
from datetime import datetime, timedelta, timezone
```

### Step 2: Replace all `datetime.utcnow()` calls (Pattern A)

In all service, task, route, and middleware files, replace:
```python
datetime.utcnow()
```
With:
```python
datetime.now(timezone.utc)
```

### Step 3: Replace model column defaults (Pattern B)

In all model files, replace:
```python
Column(TIMESTAMP, default=datetime.utcnow)
```
With:
```python
Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
```

And replace:
```python
Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
```
With:
```python
Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
```

### Complete File List (billing-specific files only)

| # | File | Occurrences | Lines |
|---|------|-------------|-------|
| 1 | `src/services/subscription_management_service.py` | 9 | 48, 55, 58, 60, 61, 99, 104, 133, 135 |
| 2 | `src/services/subscription_analytics_service.py` | 8 | 41, 93, 94, 119, 210, 372, 422, 474 |
| 3 | `src/api/tasks/subscription_tasks.py` | 6 | 41, 102, 121, 176, 196, 234 |
| 4 | `src/utils/trial_manager.py` | 6 | 54, 78, 155, 222, 271, 292 |
| 5 | `src/services/webhook_monitoring_service.py` | 5 | 68, 169, 265, 276, 339 |
| 6 | `src/services/webhook_security_monitor.py` | 4 | 86, 124, 153, 218 |
| 7 | `src/services/trial_service.py` | 7 | 48, 70, 120, 121, 171, 247, 262 |
| 8 | `src/services/license_service.py` | 3 | 129, 163, 177 |
| 9 | `src/services/subscription_plan_service.py` | 3 | 67, 68, 148 |
| 10 | `src/services/subscription_export_service.py` | 2 | 277, 342 |
| 11 | `src/services/grace_period_service.py` | 2 | 49, 108 |
| 12 | `src/services/dunning_service.py` | 2 | 58, 210 |
| 13 | `src/services/refund_service.py` | 3 | 118, 121, 157 |
| 14 | `src/services/usage_tracking_service.py` | 1 | 183 |
| 15 | `src/services/billing_email_service.py` | 1 | 225 |
| 16 | `src/api/middleware/usage_limiter.py` | 2 | 319, 321 |
| 17 | `src/api/tasks/grace_period_expiration_task.py` | 2 | 54, 61 |
| 18 | `src/api/routes/subscriptions/admin/webhook_monitoring_routes.py` | 4 | 176, 231, 302, 338 |
| 19 | `src/api/models/subscription_models/subscriptions.py` | 5 | 43, 68, 73, 74 (x2 on line 74) |
| 20 | `src/api/models/subscription_models/plans.py` | 3 | 46, 47 (x2 on line 47) |
| 21 | `src/api/models/subscription_models/webhooks.py` | 3 | 30, 31 (x2 on line 31) |
| 22 | `src/api/models/subscription_models/refunds.py` | 3 | 95, 96 (x2 on line 96) |
| 23 | `src/api/models/subscription_models/licenses.py` | 4 | 46, 47 (x2), 72, 81 |
| 24 | `src/api/models/subscription_models/trial_conversions.py` | 2 | 57, 98 |
| 25 | `src/api/models/subscription_models/license_activations.py` | 1 | 122 |

**Total: ~82 occurrences across 25 files**

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/webhook_handlers/subscription_handlers.py` | 24 | Already imports `timezone` — already partially migrated with `datetime.now(timezone.utc)` |
| TASK-004 (B1) | Auth files | Same pattern in authentication code |
| TASK-045 (B2) | Model files | Same pattern in database model defaults |
| TASK-079 (B3) | User mgmt files | Same pattern in user management code |
| TASK-101 (B4) | Workspace files | Same pattern in workspace code |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Search codebase: `grep -rn "utcnow" rext-backend/src/services/subscription*.py` — confirms deprecated usage
2. Run with Python 3.12+ (if available) and observe `DeprecationWarning` in logs

### After Fix (Verify the Solution):
1. Run `grep -rn "utcnow" rext-backend/src/services/ rext-backend/src/api/tasks/ rext-backend/src/api/models/subscription_models/` — should return zero billing-related matches
2. Verify all timestamps in new subscriptions are timezone-aware (have `+00:00` suffix)
3. Create a trial subscription and verify `trial_end_date` is calculated correctly
4. Trigger a usage reset and verify the new `usage_reset_date` is 30 days from now with timezone info
5. Verify analytics queries still return correct results (time window calculations unchanged)

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "subscription or trial or billing or dunning or grace" -v
```

---

## Acceptance Criteria

- [ ] Zero occurrences of `datetime.utcnow()` in any billing-related file
- [ ] All replacements use `datetime.now(timezone.utc)` for runtime calls
- [ ] All model column defaults use `lambda: datetime.now(timezone.utc)` or `server_default=func.now()`
- [ ] All files import `timezone` from `datetime` module
- [ ] No timezone comparison errors (`TypeError: can't compare offset-naive and offset-aware datetimes`)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python datetime.utcnow() deprecation notice](https://docs.python.org/3.12/library/datetime.html#datetime.datetime.utcnow)
- **Security Advisory:** N/A
- **Migration Guide:** [CPython Issue #80406 — datetime.utcnow() deprecation](https://github.com/python/cpython/issues/80406)
- **Best Practice Reference:** [Python 3.12 What's New — datetime deprecations](https://docs.python.org/3.12/whatsnew/3.12.html#deprecated)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None (can be done independently)
- **Blocks:** None
- **Related:** TASK-004 (B1 auth files), TASK-045 (B2 model files), TASK-079 (B3 user mgmt files), TASK-101 (B4 workspace files) — all address the same deprecation in different parts of the codebase
