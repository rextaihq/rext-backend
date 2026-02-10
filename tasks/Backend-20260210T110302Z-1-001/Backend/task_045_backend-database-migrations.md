# Task 045: Replace Deprecated datetime.utcnow() Across ~30+ Model Files

## Metadata
- **Task ID:** TASK-045
- **Source:** Backend Database & Migrations Audit (Finding #21 under P2 Medium)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P2 Medium
- **Category:** dependency
- **Effort Estimate:** large (4+ hours)

---

## Description

The `datetime.utcnow()` function is deprecated as of Python 3.12 (see [CPython changelog](https://docs.python.org/3.12/whatsnew/3.12.html) and the associated [discussion on python.org](https://discuss.python.org/t/deprecating-utcnow-and-utcfromtimestamp/26221)). It returns a "naive" datetime object without timezone information, which is dangerous because it looks like a local time to any code that handles timezones. The replacement is `datetime.now(timezone.utc)` (or `datetime.now(datetime.UTC)` in Python 3.11+), which returns a timezone-aware datetime explicitly marked as UTC.

The Rext backend uses `datetime.utcnow` in **over 300 locations** across the codebase:
- **~30 model files** use it in column `default=` and `onupdate=` parameters
- **~40+ service files** use it for timestamp assignments, comparisons, and calculations
- **~10+ route/middleware files** use it for logging, rate limiting, and response timestamps

The project specifies `requires-python = ">=3.11,<3.12"` in `pyproject.toml`, so the deprecation warning does not appear yet. However, upgrading to Python 3.12+ (which is inevitable) will flood the logs with `DeprecationWarning` messages, and the function is scheduled for removal in a future Python version.

Some newer parts of the codebase have already migrated to the correct pattern. The `knowledge_model.py`, `workspace_integration.py`, `content_seo_data.py`, `persona_model.py`, and `embedding_model.py` models use `lambda: datetime.now(timezone.utc)` for column defaults. The `data_cleanup_service.py`, `workspace_service.py`, `content_service.py`, and `sse_service.py` services use `datetime.now(timezone.utc)` directly. This inconsistency means the codebase mixes timezone-naive and timezone-aware datetimes, which is itself a source of comparison bugs.

**Important:** In SQLAlchemy column defaults, `default=datetime.utcnow` (without parentheses) passes the function reference, which SQLAlchemy calls at INSERT time. The replacement must also be a callable: `default=lambda: datetime.now(timezone.utc)`. Using `default=datetime.now(timezone.utc)` (with parentheses) would evaluate once at import time, which is incorrect.

---

## Current Code

### Model Layer Examples

```python
# File: rext-backend/src/api/models/user_models/users.py
# Lines: 38-39
created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
```

```python
# File: rext-backend/src/api/models/user_models/roles.py
# Lines: 28-29
created_at = Column(TIMESTAMP, default=datetime.utcnow)
updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
```

```python
# File: rext-backend/src/api/models/notification/notification_model.py
# Lines: 153-158
created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
updated_at = Column(
    TIMESTAMP,
    default=datetime.utcnow,
    onupdate=datetime.utcnow,
    nullable=False
)
```

### Service Layer Examples

```python
# File: rext-backend/src/services/auth_service.py
# Line: 127
created_at=datetime.utcnow()
```

```python
# File: rext-backend/src/services/subscription_service.py
# Lines: 123-128
start_date=datetime.utcnow(),
trial_end_date=datetime.utcnow() + timedelta(days=trial_days) if is_trial else None,
usage_reset_date=datetime.utcnow() + timedelta(days=30),
created_at=datetime.utcnow(),
updated_at=datetime.utcnow()
```

### Already Correct (Reference Pattern)

```python
# File: rext-backend/src/api/models/knowledge_models/knowledge_model.py
# Lines: 23-24 (KnowledgeBase model — CORRECT pattern)
created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=True)
```

---

## Why This Matters (Context & Reasoning)

The Rext backend handles time-sensitive operations including:
- **Subscription management:** Trial expiration, grace periods, renewal dates
- **Token security:** JWT expiration, token blacklist expiry
- **Session management:** Session timeout, last activity tracking
- **Rate limiting:** Request window calculations
- **Billing:** Payment failure timestamps, cancellation dates

Mixing naive datetimes (from `utcnow()`) with timezone-aware datetimes (from `now(timezone.utc)`) in these calculations can cause:
1. **TypeError:** Comparing naive and aware datetimes raises `TypeError: can't compare offset-naive and offset-aware datetimes` in strict contexts.
2. **Silent bugs:** Some libraries/ORMs convert silently, but the comparison may yield incorrect results if the server timezone is not UTC.
3. **Python 3.12+ breakage:** When the project upgrades Python, every call to `datetime.utcnow()` will emit a `DeprecationWarning`, flooding logs and potentially breaking CI if warnings are treated as errors.

---

## Impact

- **Severity:** Currently a latent issue (Python 3.11 does not emit warnings). Becomes a log-flooding problem on Python 3.12 upgrade. Becomes a breaking change when `utcnow()` is eventually removed.
- **Affected Users/Flows:** All flows that rely on timestamp comparisons — subscription management, authentication, session management, billing, notifications, rate limiting.
- **Blast Radius:** System-wide — 300+ occurrences across models, services, routes, tasks, middleware, and utilities.

---

## Recommended Solution

This task focuses on the **model layer** (~30 files with column defaults). The service/route layer occurrences should be addressed as part of each respective audit area's task extraction.

### Step 1: Update All Model Column Defaults

For every model file, replace `datetime.utcnow` with `lambda: datetime.now(timezone.utc)` in column `default=` and `onupdate=` parameters, and add `from datetime import timezone` to imports.

**Pattern to search and replace:**

```python
# BEFORE (function reference for column default):
default=datetime.utcnow
onupdate=datetime.utcnow

# AFTER:
default=lambda: datetime.now(timezone.utc)
onupdate=lambda: datetime.now(timezone.utc)
```

**Import change in each file:**

```python
# BEFORE:
from datetime import datetime

# AFTER:
from datetime import datetime, timezone
```

### Step 2: Files to Modify (Complete List — Model Layer)

| # | File | Columns Affected |
|---|------|-----------------|
| 1 | `src/api/models/user_models/users.py` | created_at, updated_at |
| 2 | `src/api/models/user_models/roles.py` | created_at, updated_at |
| 3 | `src/api/models/user_models/permissions.py` | created_at |
| 4 | `src/api/models/user_models/user_roles.py` | assigned_at |
| 5 | `src/api/models/user_models/role_permissions.py` | created_at |
| 6 | `src/api/models/user_models/invitations.py` | created_at |
| 7 | `src/api/models/user_models/token_blacklist.py` | revoked_at |
| 8 | `src/api/models/user_models/notification_preferences.py` | created_at, updated_at |
| 9 | `src/api/models/user_models/user_sessions.py` | created_at, last_activity_at |
| 10 | `src/api/models/user_models/oauth_accounts.py` | created_at, updated_at |
| 11 | `src/api/models/user_models/onboarding.py` | started_at, created_at, updated_at |
| 12 | `src/api/models/user_models/user_preferences.py` | created_at, updated_at |
| 13 | `src/api/models/user_models/email_preferences.py` | created_at, updated_at |
| 14 | `src/api/models/user_models/impersonation_session.py` | invalidated_at, created_at |
| 15 | `src/api/models/workspace_models/workspace_model.py` | created_at, updated_at |
| 16 | `src/api/models/workspace_models/workspace_member.py` | joined_at, last_activity_at |
| 17 | `src/api/models/workspace_models/email_template.py` | created_at, updated_at |
| 18 | `src/api/models/content_models/content.py` | created_at, updated_at |
| 19 | `src/api/models/content_models/content_media.py` | created_at |
| 20 | `src/api/models/subscription_models/plans.py` | created_at, updated_at |
| 21 | `src/api/models/subscription_models/subscriptions.py` | start_date, usage_reset_date, created_at, updated_at |
| 22 | `src/api/models/subscription_models/licenses.py` | created_at, updated_at |
| 23 | `src/api/models/subscription_models/payment_methods.py` | created_at, updated_at |
| 24 | `src/api/models/subscription_models/webhooks.py` | created_at, updated_at |
| 25 | `src/api/models/subscription_models/refunds.py` | created_at, updated_at |
| 26 | `src/api/models/subscription_models/trial_conversions.py` | converted_at, created_at |
| 27 | `src/api/models/subscription_models/license_activations.py` | deactivate() method (line 122) |
| 28 | `src/api/models/media_models/media.py` | created_at, updated_at |
| 29 | `src/api/models/audit_models/audit_logs.py` | created_at |
| 30 | `src/api/models/admin_models/admin_invitations.py` | created_at, is_expired() method |
| 31 | `src/api/models/admin_models/customer_note.py` | created_at, updated_at |
| 32 | `src/api/models/admin_models/error_log.py` | timestamp |
| 33 | `src/api/models/notification/notification_model.py` | created_at, updated_at, mark_as_read(), archive(), soft_delete() |
| 34 | `src/api/models/email_models/email_event.py` | received_at, created_at |
| 35 | `src/api/models/email_models/email_log.py` | created_at, updated_at |
| 36 | `src/api/models/base.py` | Line 19 (example code in docstring) |

### Step 3: Update Method Bodies That Call datetime.utcnow()

Some models have methods that call `datetime.utcnow()` directly:

```python
# File: rext-backend/src/api/models/subscription_models/license_activations.py
# Line 122 — deactivate() method
# BEFORE:
    def deactivate(self):
        self.is_active = False
        self.deactivated_at = datetime.utcnow()
# AFTER:
    def deactivate(self):
        self.is_active = False
        self.deactivated_at = datetime.now(timezone.utc)

# File: rext-backend/src/api/models/notification/notification_model.py
# Lines 199, 209, 219 — mark_as_read(), archive(), soft_delete()
# BEFORE:
    def mark_as_read(self):
        self.is_read = True
        self.read_at = datetime.utcnow()
# AFTER:
    def mark_as_read(self):
        self.is_read = True
        self.read_at = datetime.now(timezone.utc)

# File: rext-backend/src/api/models/admin_models/admin_invitations.py
# Line 206 — is_expired property
# BEFORE:
        return datetime.utcnow() > self.expires_at
# AFTER:
        return datetime.now(timezone.utc) > self.expires_at
```

### Step 4: Verify No `datetime.utcnow` References Remain in Model Files

```bash
cd rext-backend && grep -r "datetime.utcnow" src/api/models/ --include="*.py"
```

This command should return no results after the fix is complete.

---

## Other Affected Locations

The service layer, route layer, middleware, and utility files also use `datetime.utcnow()` extensively. These are outside the scope of this task (B2 audit — model/database layer) but should be addressed in their respective audit area tasks:

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/auth_service.py` | 18 lines | Covered by B1 audit (TASK-004) |
| `src/services/subscription_service.py` | 12 lines | Covered by B5 audit |
| `src/services/admin_invitation_service.py` | 8 lines | Covered by B13 audit |
| `src/services/security_service.py` | 10 lines | Covered by B10 audit |
| `src/services/oauth_service.py` | 14 lines | Covered by B1/B3 audit |
| `src/services/trial_service.py` | 8 lines | Covered by B5 audit |
| `src/api/security/token_utils.py` | 6 lines | Covered by B1 audit |
| `src/api/middleware/rate_limiter.py` | 5 lines | Covered by B16 audit |
| `src/services/webhook_handlers/subscription_handlers.py` | 20+ lines | Covered by B5 audit |
| ~30 additional service/route files | Various | Covered by respective audit areas |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Search for deprecated usage: `cd rext-backend && grep -rc "datetime.utcnow" src/api/models/ --include="*.py" | grep -v ":0"`
2. Count total occurrences — should be 30+ files.

### After Fix (Verify the Solution):
1. Re-run the search — should return no results for model files.
2. Verify models still function correctly: `cd rext-backend && python -c "from src.api.models.user_models.users import Users; u = Users(); print(type(Users.created_at.default.arg()))"`
3. The output should show a timezone-aware datetime: `<class 'datetime.datetime'>` with `tzinfo=datetime.timezone.utc`.
4. Run the application and verify timestamps in API responses include timezone information.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v
```

---

## Acceptance Criteria

- [ ] Zero occurrences of `datetime.utcnow` in any model file under `src/api/models/`
- [ ] All column defaults use `lambda: datetime.now(timezone.utc)` pattern
- [ ] All model methods that used `datetime.utcnow()` now use `datetime.now(timezone.utc)`
- [ ] `from datetime import timezone` is imported in every modified file
- [ ] The docstring example in `src/api/models/base.py` is updated
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python 3.12 — datetime.utcnow() deprecation](https://docs.python.org/3.12/library/datetime.html#datetime.datetime.utcnow) — "Deprecated since version 3.12: Use `datetime.now(timezone.utc)` instead."
- **Security Advisory:** N/A
- **Migration Guide:** [It's Time For A Change: datetime.utcnow() Is Now Deprecated](https://blog.miguelgrinberg.com/post/it-s-time-for-a-change-datetime-utcnow-is-now-deprecated) — Miguel Grinberg's comprehensive migration guide
- **Best Practice Reference:** [Python Discussions — Deprecating utcnow and utcfromtimestamp](https://discuss.python.org/t/deprecating-utcnow-and-utcfromtimestamp/26221) — original Python core developer discussion with rationale
- **Related Issues/PRs:** [dbt-core #9791](https://github.com/dbt-labs/dbt-core/issues/9791), [botocore #3201](https://github.com/boto/botocore/issues/3201), [Apache Airflow #32344](https://github.com/apache/airflow/issues/32344) — major projects addressing the same deprecation

---

## Dependencies & Related Tasks

- **Depends on:** None (but should ideally be done alongside TASK-042 for a unified timestamp standardization effort)
- **Blocks:** None
- **Related:** TASK-004 (B1 — datetime.utcnow deprecation in auth code, same root issue), TASK-042 (Inconsistent timestamp column types — changing column types and defaults should be a coordinated effort)
