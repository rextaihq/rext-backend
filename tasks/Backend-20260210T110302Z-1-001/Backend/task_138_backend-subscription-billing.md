# Task 138: trial_manager.py Uses Synchronous Session — Cannot Run in Async Context (Dead Code)

## Metadata
- **Task ID:** TASK-138
- **Source:** Backend Subscription & Billing Audit (Finding #29 under P2 Medium)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The entire `src/utils/trial_manager.py` module (504 lines) uses synchronous SQLAlchemy patterns (`Session`, `db.query()`, `db.commit()`) while the rest of the application exclusively uses `AsyncSession` with `await`-based queries. The module also contains "legacy sync wrapper" functions (lines 478-503) that call `asyncio.run()` to bridge sync-to-async:

```python
def send_trial_expiring_notification(user_email, days_remaining, plan_name, user_id=None):
    import asyncio
    if not user_id:
        logger.warning(...)
        return False
    return asyncio.run(send_trial_expiring_notification_async(user_email, user_id, days_remaining, plan_name))
```

Calling `asyncio.run()` from within an already-running event loop (as is the case in FastAPI/Uvicorn) raises `RuntimeError: asyncio.run() cannot be called from a running event loop`. This means these sync wrappers are guaranteed to crash if called from any route handler, service, or background task in the current architecture. Per Python's official asyncio documentation, `asyncio.run()` is designed to be called from the main thread of a non-async application only — it cannot be nested inside an existing event loop.

The module is effectively **dead code**. A codebase search confirms it is not imported by any other Python file. Its functionality is fully duplicated by `src/services/trial_service.py` (382 lines), which is the async counterpart that uses `AsyncSession` and is properly integrated with the rest of the application. Specifically:

| `trial_manager.py` function | `trial_service.py` equivalent |
|------------------------------|-------------------------------|
| `expire_trial_subscriptions(db: Session)` | `TrialService.expire_trial(subscription_id)` |
| `get_trials_expiring_soon(db: Session)` | `TrialService.get_expiring_trials(days_until_expiry)` |
| `extend_trial(db: Session, ...)` | `TrialService.extend_trial(subscription_id, ...)` |
| `convert_trial_to_active(db: Session, ...)` | No direct equivalent (handled by webhook handlers) |
| `get_trial_statistics(db: Session)` | `TrialService.get_trial_conversion_stats(...)` |
| `check_trial_expiration(subscription, plan)` | No equivalent needed (inline logic) |

Additionally, `trial_manager.py` contains 7 calls to `datetime.utcnow()` (deprecated since Python 3.12, PEP 587), and uses the legacy `db.query()` API pattern instead of `select()`.

Keeping this dead module in the codebase causes confusion — a developer might accidentally import it thinking it's the active trial management module, only to encounter runtime crashes from the sync/async mismatch.

---

## Current Code

```python
# File: src/utils/trial_manager.py
# Lines: 1-11 (imports — sync Session)
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus,
    BillingPeriod
)
```

```python
# File: src/utils/trial_manager.py
# Lines: 66-84 (sync query pattern)
def expire_trial_subscriptions(db: Session) -> Dict[str, int]:
    now = datetime.utcnow()
    expired_trials = db.query(UserSubscription).filter(
        UserSubscription.status == SubscriptionStatus.TRIAL,
        UserSubscription.trial_end_date < now
    ).all()
```

```python
# File: src/utils/trial_manager.py
# Lines: 477-503 (sync wrappers that will crash in async context)
def send_trial_expiring_notification(user_email: str, days_remaining: int, plan_name: str, user_id: Optional[str] = None) -> bool:
    import asyncio
    if not user_id:
        logger.warning(f"user_id not provided for trial expiring notification to {user_email}")
        return False
    return asyncio.run(send_trial_expiring_notification_async(user_email, user_id, days_remaining, plan_name))


def send_trial_expired_notification(user_email: str, downgraded_to_free: bool, plan_name: str = "Premium", user_id: Optional[str] = None) -> bool:
    import asyncio
    if not user_id:
        logger.warning(f"user_id not provided for trial expired notification to {user_email}")
        return False
    return asyncio.run(send_trial_expired_notification_async(user_email, user_id, downgraded_to_free, plan_name))
```

---

## Why This Matters (Context & Reasoning)

Dead code that looks like active code is a maintenance hazard. `trial_manager.py` occupies 504 lines in the `src/utils/` directory, making it look like a legitimate utility module. A developer working on trial functionality might import from it instead of `TrialService`, leading to runtime crashes that only manifest at call time (not at import time). The file also contains hardcoded HTML email templates (lines 375-388, 434-458) that duplicate the template system used by `BillingEmailService`.

Removing the file eliminates confusion, reduces the codebase by 504 lines, and prevents accidental usage of incompatible sync patterns.

---

## Impact

- **Severity:** Dead code that will crash if accidentally used. No production impact currently, but creates confusion and maintenance risk.
- **Affected Users/Flows:** None currently (module is not imported anywhere). Risk is developer confusion leading to future bugs.
- **Blast Radius:** Isolated to this single file. No callers will break.

---

## Recommended Solution

Delete the entire `src/utils/trial_manager.py` file. Since it is not imported by any other module, this is a safe deletion with zero runtime impact.

### Step 1: Verify no imports exist (safety check)

```bash
cd rext-backend && grep -r "trial_manager" --include="*.py" src/
```

Expected result: no matches (confirming zero imports).

### Step 2: Delete the file

```bash
rm src/utils/trial_manager.py
```

### Step 3: Verify `trial_service.py` covers all needed functionality

Confirm that `src/services/trial_service.py` (the async replacement) provides equivalent methods:

- `get_expiring_trials()` — replaces `get_trials_expiring_soon()`
- `get_expired_trials()` — replaces the query in `expire_trial_subscriptions()`
- `expire_trial()` — replaces the status update in `expire_trial_subscriptions()`
- `extend_trial()` — replaces `extend_trial()`
- `check_trial_eligibility()` — new functionality not in `trial_manager.py`
- `track_trial_conversion()` — new functionality not in `trial_manager.py`
- `get_trial_conversion_stats()` — replaces `get_trial_statistics()`

The only function in `trial_manager.py` without a direct equivalent is `convert_trial_to_active()`, which is handled by the webhook subscription handlers when a payment is confirmed. No action needed.

### Step 4: Remove from test coverage exclusions (if any)

If `trial_manager.py` is listed in any coverage configuration or test exclusion files, remove those references.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/trial_service.py` | All | The async replacement — verify it has full feature parity |
| `test_output.txt` | `863` | Coverage report references `trial_manager.py` — will auto-update after deletion |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open a Python REPL within the FastAPI application context
2. Attempt to import and call a sync function:
   ```python
   from src.utils.trial_manager import send_trial_expiring_notification
   send_trial_expiring_notification("test@test.com", 3, "Premium", "some-uuid")
   ```
3. Observe `RuntimeError: asyncio.run() cannot be called from a running event loop`

### After Fix (Verify the Solution):
1. Verify the file is deleted: `ls src/utils/trial_manager.py` should show "No such file"
2. Verify no import errors on application startup: `python -c "from src.services.trial_service import TrialService; print('OK')"`
3. Run existing tests to confirm nothing depended on the deleted module

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "trial" -v
```

---

## Acceptance Criteria

- [ ] `src/utils/trial_manager.py` is deleted from the codebase
- [ ] No import errors or runtime errors introduced by the deletion
- [ ] `src/services/trial_service.py` provides equivalent async functionality for all needed operations
- [ ] Application starts successfully without the file
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python asyncio.run() documentation](https://docs.python.org/3/library/asyncio-runner.html#asyncio.run) — states it cannot be called when another event loop is running
- **Security Advisory:** N/A
- **Migration Guide:** [SQLAlchemy Async I/O documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- **Best Practice Reference:** [FastAPI Async/Await documentation](https://fastapi.tiangolo.com/async/)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-133 (Duplicate Trial Expiration — `trial_manager.py` is one of the two duplicate code paths), TASK-079 (datetime.utcnow() deprecated — `trial_manager.py` has 7 instances, but deletion resolves them)
