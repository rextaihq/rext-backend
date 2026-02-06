# Task 004: Replace Deprecated `datetime.utcnow()` in Authentication Files

## Metadata
- **Task ID:** TASK-004
- **Source:** Authentication & Authorization Audit (Finding #4 under P0 Critical)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P0 Critical
- **Category:** dependency
- **Effort Estimate:** medium (1-4 hours)

---

## Description

`datetime.utcnow()` is deprecated as of Python 3.12 (see [Python 3.12 What's New](https://docs.python.org/3.12/whatsnew/3.12.html#deprecated)) and is scheduled for removal in a future version. The deprecation warning states: *"Use timezone-aware objects to represent datetimes in UTC: `datetime.datetime.now(datetime.UTC)`"*. The function returns a naive datetime object without timezone information, which can cause subtle bugs when comparing timestamps across different contexts (e.g., comparing a naive UTC datetime with a timezone-aware datetime raises `TypeError: can't compare offset-naive and offset-aware datetimes`).

This task scopes the fix to the **authentication-related files** analyzed in the B1 audit. There are 368 total occurrences across 112 files in the entire backend codebase, but this task covers only the files directly related to authentication and authorization:

**Service files (in-code calls):**
- `src/api/security/token_utils.py` — 6 occurrences (lines 84, 109, 132, 150, 192, 226)
- `src/services/auth_service.py` — 15 occurrences (lines 127, 140, 153, 231, 251, 262, 282, 342, 352, 353, 409, 558, 604, 621, 733)
- `src/services/oauth_service.py` — 14 occurrences (lines 120, 124, 158, 159, 165, 185, 187, 199, 216, 217, 225, 356, 371, 435)
- `src/services/session_service.py` — 4 occurrences (lines 123, 131, 182, 218)
- `src/utils/token_cleanup.py` — 1 occurrence (line 48)

**Model files (column defaults):**
- `src/api/models/user_models/users.py` — 2 occurrences (lines 38, 39)
- `src/api/models/user_models/user_sessions.py` — 2 occurrences (lines 39, 40)
- `src/api/models/user_models/token_blacklist.py` — 1 occurrence (line 29)
- `src/api/models/user_models/oauth_accounts.py` — 2 occurrences (lines 47, 48)
- `src/api/models/user_models/roles.py` — 2 occurrences (lines 28, 29)
- `src/api/models/user_models/user_roles.py` — 1 occurrence (line 23)
- `src/api/models/user_models/impersonation_session.py` — 2 occurrences (lines 25, 26)

**Additionally, `token_utils.py` uses `datetime.utcfromtimestamp()`** on lines 192 and 226, which is also deprecated for the same reason and must be replaced with `datetime.fromtimestamp(ts, tz=timezone.utc)`.

The project uses Python `>=3.11,<3.12`, so `datetime.utcnow()` has not yet started emitting deprecation warnings. However, migrating proactively is critical because: (1) the next Python upgrade to 3.12+ will trigger warnings on every call, and (2) naive datetimes can cause comparison bugs with any timezone-aware datetimes introduced by third-party libraries.

---

## Current Code

```python
# File: src/api/security/token_utils.py
# Lines: 84, 109 (representative examples)
    expire = datetime.utcnow() + expires_delta

# Lines: 192, 226 (also deprecated)
        if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
```

```python
# File: src/services/auth_service.py
# Lines: 262, 352-353 (representative examples)
        db_user.last_login_at = datetime.utcnow()
        ...
            created_at=datetime.utcnow(),
            last_activity_at=datetime.utcnow(),
```

```python
# File: src/api/models/user_models/users.py
# Lines: 38-39 (model defaults)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
```

---

## Why This Matters (Context & Reasoning)

The authentication system relies heavily on datetime comparisons for:
- **Token expiration:** `token_utils.py` compares the current time against token expiry to determine if access/refresh tokens are valid
- **Account lockout:** `auth_service.py` compares `locked_until` against current time to enforce login lockouts
- **Session management:** `session_service.py` sets timestamps for session creation and revocation
- **Trial expiration:** `auth_service.py` compares `trial_end_date` against current time

All of these comparisons use naive datetime objects. If any part of the system (database driver, third-party library, or future code) introduces a timezone-aware datetime, the comparison will raise a `TypeError` rather than returning the wrong result. This is a latent bug that becomes acute during Python upgrades.

For SQLAlchemy model defaults, the current pattern `default=datetime.utcnow` (without parentheses) passes the function reference as a callable. The replacement must also be a callable: `default=lambda: datetime.now(timezone.utc)`. Alternatively, SQLAlchemy's `func.now()` can be used for server-side defaults, which delegates timestamp generation to the database.

---

## Impact

- **Severity:** Deprecation warnings in Python 3.12+, potential `TypeError` crashes when naive datetimes are compared with aware datetimes, and eventual removal in a future Python version.
- **Affected Users/Flows:** All authentication flows (login, token generation, token verification, session management, account lockout, password reset)
- **Blast Radius:** All 5 auth service/utility files + 7 auth model files. Note: 368 total occurrences exist across 112 files in the full codebase (covered by other reports' tasks).

---

## Recommended Solution

The replacement is `datetime.now(timezone.utc)` (using `datetime.timezone.utc`, available since Python 3.2). The shorthand `datetime.UTC` is only available in Python 3.11+, which is compatible with this project's `>=3.11,<3.12` requirement, but `timezone.utc` is more portable and equally correct.

For `datetime.utcfromtimestamp(ts)`, the replacement is `datetime.fromtimestamp(ts, tz=timezone.utc)`.

### Step 1: Update `src/api/security/token_utils.py`

Add `timezone` to the datetime import and replace all occurrences:

```python
# File: src/api/security/token_utils.py
# Update the import (find the existing `from datetime import datetime, timedelta` line):
from datetime import datetime, timedelta, timezone

# Replace all 4 occurrences of datetime.utcnow():
# Line 84:  expire = datetime.utcnow() + expires_delta
#        →  expire = datetime.now(timezone.utc) + expires_delta
# Line 109: expire = datetime.utcnow() + expires_delta
#        →  expire = datetime.now(timezone.utc) + expires_delta
# Line 132: expire = datetime.utcnow() + expires_delta
#        →  expire = datetime.now(timezone.utc) + expires_delta
# Line 150: expire = datetime.utcnow() + expires_delta
#        →  expire = datetime.now(timezone.utc) + expires_delta

# Replace 2 occurrences of datetime.utcfromtimestamp():
# Line 192: if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
#        →  if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
# Line 226: if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
#        →  if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
```

### Step 2: Update `src/services/auth_service.py`

```python
# File: src/services/auth_service.py
# Update the import to include timezone:
from datetime import datetime, timedelta, timezone

# Replace all 15 occurrences of datetime.utcnow() with datetime.now(timezone.utc)
# Lines: 127, 140, 153, 231, 251, 262, 282, 342, 352, 353, 409, 558, 604, 621, 733
# Also replace the utcfromtimestamp on line 342:
#   datetime.utcfromtimestamp(exp_timestamp)
# → datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
```

### Step 3: Update `src/services/oauth_service.py`

```python
# File: src/services/oauth_service.py
# Update the import to include timezone:
from datetime import datetime, timedelta, timezone

# Replace all 14 occurrences of datetime.utcnow() with datetime.now(timezone.utc)
# Lines: 120, 124, 158, 159, 165, 185, 187, 199, 216, 217, 225, 356, 371, 435
```

### Step 4: Update `src/services/session_service.py`

```python
# File: src/services/session_service.py
# Update the import to include timezone:
from datetime import datetime, timedelta, timezone

# Replace all 4 occurrences of datetime.utcnow() with datetime.now(timezone.utc)
# Lines: 123, 131, 182, 218
```

### Step 5: Update `src/utils/token_cleanup.py`

```python
# File: src/utils/token_cleanup.py
# Update the import to include timezone:
from datetime import datetime, timezone

# Replace line 48:
#   cutoff_time = datetime.utcnow()
# → cutoff_time = datetime.now(timezone.utc)
```

### Step 6: Update model defaults in auth-related models

For each model file, replace `default=datetime.utcnow` with `default=lambda: datetime.now(timezone.utc)` and add `timezone` to the import.

```python
# File: src/api/models/user_models/users.py
# Update import:
from datetime import datetime, timezone

# Replace lines 38-39:
    created_at = Column(TIMESTAMP, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
```

Repeat the same pattern for:
- `src/api/models/user_models/user_sessions.py` (lines 39-40)
- `src/api/models/user_models/token_blacklist.py` (line 29)
- `src/api/models/user_models/oauth_accounts.py` (lines 47-48)
- `src/api/models/user_models/roles.py` (lines 28-29)
- `src/api/models/user_models/user_roles.py` (line 23)
- `src/api/models/user_models/impersonation_session.py` (lines 25-26)

**Note on `onupdate`:** SQLAlchemy's `onupdate` parameter also accepts a callable, so `onupdate=lambda: datetime.now(timezone.utc)` is correct.

**Alternative for model defaults:** Using `func.now()` from SQLAlchemy (`from sqlalchemy import func`) delegates timestamp generation to the database server. This is arguably better because it uses the database clock (consistent across application instances), but it changes the default type from Python-generated to SQL-generated. Choose based on your team's preference — both approaches solve the deprecation issue.

---

## Other Affected Locations

This task scopes to B1 auth files only. The same pattern exists across the entire codebase:

| File | Occurrences | Description |
|------|-------------|-------------|
| `src/services/subscription_service.py` | 11 | Subscription management timestamps |
| `src/services/user_service.py` | 10 | User management timestamps |
| `src/services/security_service.py` | 10 | Security-related timestamps |
| `src/services/webhook_handlers/subscription_handlers.py` | 22 | Webhook processing timestamps |
| `src/services/invitation_service.py` | 8 | Invitation timestamps |
| 100+ other files | 287 | Various service, model, and route files |

**Total remaining after this task:** ~328 occurrences across ~105 files (covered by datetime.utcnow findings in B2, B3, B4, B5 audit reports).

---

## Testing Instructions

### Before Fix (Confirm the Pattern):
1. Grep for `datetime.utcnow` in the auth files listed above
2. Confirm all occurrences exist

### After Fix (Verify the Solution):
1. Grep for `datetime.utcnow` in the modified files — should return 0 results
2. Grep for `datetime.now(timezone.utc)` — should show all replacements
3. Run the login flow end-to-end: login → use access token → refresh token → logout
4. Verify token expiration still works correctly (tokens expire at the right time)
5. Verify account lockout timing still works
6. Verify session creation timestamps are correct in the database

### Edge Cases:
1. Verify that token expiration comparisons work correctly (no `TypeError` from mixed aware/naive comparisons)
2. Verify that model default timestamps are generated with timezone info
3. Check that existing database records (with naive timestamps) can still be compared with new aware timestamps — **this may require attention if the database stores naive timestamps**

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "auth or token or session" -v
```

---

## Acceptance Criteria

- [ ] All `datetime.utcnow()` calls replaced with `datetime.now(timezone.utc)` in the 5 service/utility files
- [ ] All `datetime.utcfromtimestamp()` calls replaced with `datetime.fromtimestamp(ts, tz=timezone.utc)` in `token_utils.py`
- [ ] All model defaults updated from `default=datetime.utcnow` to `default=lambda: datetime.now(timezone.utc)` in the 7 model files
- [ ] `from datetime import timezone` added to all modified files
- [ ] Token generation, verification, and expiration work correctly
- [ ] Login, session management, and account lockout flows work correctly
- [ ] No `TypeError` from datetime comparisons
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python 3.12 datetime deprecations](https://docs.python.org/3.12/whatsnew/3.12.html#deprecated)
- **Security Advisory:** N/A
- **Migration Guide:** [It's Time For A Change: datetime.utcnow() Is Now Deprecated — Miguel Grinberg](https://blog.miguelgrinberg.com/post/it-s-time-for-a-change-datetime-utcnow-is-now-deprecated)
- **Best Practice Reference:** [Python: it is now() time to migrate from utcnow()](https://www.andreagrandi.it/posts/python-now-time-to-migrate-from-utcnow/)
- **Related Issues/PRs:** [dbt-core #9791 — datetime.utcnow() deprecation](https://github.com/dbt-labs/dbt-core/issues/9791)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** B2 Finding 21 (datetime.utcnow in ~30+ model files), B3 Finding 20 (datetime.utcnow deprecated throughout user management), B4 Finding 8 (inconsistent DateTime usage in workspace management), B5 Finding 18 (datetime.utcnow deprecated throughout billing) — all cover the same pattern in different file scopes and will become separate tasks with cross-references when those reports are processed.
