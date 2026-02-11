# Task 079: Replace Deprecated `datetime.utcnow()` with `datetime.now(timezone.utc)` in User Management

## Metadata
- **Task ID:** TASK-079
- **Source:** B3 - User Management (Finding #20 under P2 Medium)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P2 Medium
- **Category:** dependency
- **Effort Estimate:** small (< 1 hour)

---

## Description

`datetime.utcnow()` is deprecated as of Python 3.12 (see [Python documentation](https://docs.python.org/3/library/datetime.html#datetime.datetime.utcnow) and the related [deprecation discussion](https://discuss.python.org/t/deprecating-utcnow-and-utcfromtimestamp/26221)). The method returns a **naive** `datetime` object -- one that carries no timezone information -- even though the value it produces represents UTC. This is dangerous because code that receives a naive datetime has no way to know whether it represents UTC, local time, or something else. The replacement, `datetime.now(timezone.utc)`, returns a **timezone-aware** datetime explicitly tagged with the UTC timezone, removing all ambiguity.

The user management module uses `datetime.utcnow()` in **18 locations** across **6 files**:

| File | Lines | Count |
|------|-------|-------|
| `src/services/user_preferences_service.py` | 121 | 1 |
| `src/services/member_service.py` | 112, 113, 177, 293, 423, 575 | 6 |
| `src/api/schema/response_schemas.py` | 166, 332 | 2 |
| `src/api/routes/users/user_status.py` | 65, 257 | 2 |
| `src/api/routes/users/management.py` | 60, 400, 429 | 3 |
| `src/api/routes/users/invitations.py` | 311, 384 | 2 |
| | | **Total: 16 in routes/services + 2 in schema = 18** |

The project currently requires Python `>=3.11,<3.12` (per `pyproject.toml`), so the deprecation warning does not fire yet. However, any upgrade to Python 3.12+ will produce `DeprecationWarning` at every call site, and a future Python version will remove the method entirely, causing `AttributeError` at runtime.

**Note:** The audit report originally listed `user_service.py` as affected, but that file has already been migrated -- it imports `from datetime import datetime, timezone` and uses `datetime.now(timezone.utc)` throughout. The existing correct pattern in `user_service.py` serves as the reference implementation for this task.

**Note on `member_service.py` line 574:** There is an explicit comment in the source that reads `# Use utcnow() for timezone-naive datetime to match TIMESTAMP WITHOUT TIME ZONE column`. This comment should be removed or updated as part of this fix. SQLAlchemy handles timezone-aware datetimes against `TIMESTAMP WITHOUT TIME ZONE` columns by silently stripping the timezone info before storage, so the behavior is functionally equivalent.

---

## Current Code

### `src/services/user_preferences_service.py` (1 occurrence)

```python
# Line 19 (import):
from datetime import datetime

# Line 121:
            preferences.updated_at = datetime.utcnow()
```

### `src/services/member_service.py` (6 occurrences)

```python
# Line 21 (import):
from datetime import datetime

# Lines 112-113:
            joined_at=datetime.utcnow(),
            last_activity_at=datetime.utcnow()

# Line 177:
            "removed_at": datetime.utcnow()

# Line 293:
        member.last_activity_at = datetime.utcnow()

# Line 423:
        member.last_activity_at = datetime.utcnow()

# Lines 574-575:
        # Use utcnow() for timezone-naive datetime to match TIMESTAMP WITHOUT TIME ZONE column
        timestamp = datetime.utcnow()
```

### `src/api/schema/response_schemas.py` (2 occurrences)

```python
# Line 33 (import):
from datetime import datetime

# Line 166:
    timestamp: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
        ...
    )

# Line 332:
    timestamp = int(datetime.utcnow().timestamp())
```

### `src/api/routes/users/user_status.py` (2 occurrences)

```python
# Line 4 (import):
from datetime import datetime, timedelta

# Line 65:
        target_user.updated_at = datetime.utcnow()

# Line 257:
        target_user.updated_at = datetime.utcnow()
```

### `src/api/routes/users/management.py` (3 occurrences)

```python
# Line 6 (import):
from datetime import datetime

# Line 60:
            <p><strong>Generated at:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>

# Line 400:
                "account_age_days": (datetime.utcnow() - db_user.created_at).days if db_user.created_at else 0,

# Line 429:
            requested_at=datetime.utcnow().isoformat(),
```

### `src/api/routes/users/invitations.py` (2 occurrences)

```python
# Line 16 (import):
from datetime import datetime

# Line 311:
            "declined_at": datetime.utcnow().isoformat()

# Line 384:
            "declined_at": datetime.utcnow().isoformat()
```

---

## Why This Matters

1. **Python upgrade blocker.** The project will need to upgrade beyond Python 3.11 for security patches, performance improvements, and ecosystem compatibility. Every `datetime.utcnow()` call is a deprecation warning on 3.12+ and a hard crash on the future version that removes it.

2. **Naive vs aware datetime mixing.** `user_service.py` already returns timezone-aware datetimes via `datetime.now(timezone.utc)`. The remaining files return naive datetimes. Comparing a naive datetime with a timezone-aware datetime raises `TypeError: can't compare offset-naive and offset-aware datetimes`. This is a latent bug waiting to surface in any code path that mixes values from the migrated and un-migrated files.

3. **Semantic correctness.** A naive datetime carries no indication that it represents UTC. Any downstream consumer (logging, serialization, client display) must silently assume UTC. A timezone-aware datetime makes the timezone explicit and machine-verifiable.

4. **Consistency.** The correct pattern already exists in the codebase (`user_service.py`). Applying it uniformly reduces cognitive overhead and prevents new contributors from copying the wrong pattern.

---

## Impact

- **Severity:** No immediate runtime error on Python 3.11, but `DeprecationWarning` on Python 3.12+ and eventual `AttributeError` on removal. Potential `TypeError` when naive datetimes from these files are compared with aware datetimes from `user_service.py`.
- **Affected Users/Flows:** All user management operations that record timestamps -- preferences updates, workspace member join/remove/status changes, role assignments, user suspension/ban, data exports, invitation declines, and API response metadata.
- **Blast Radius:** 18 locations across 6 files in the user management module. The same pattern exists in ~300+ other locations across the full codebase (see cross-references).

---

## Recommended Solution

### Step 1: Update imports in each affected file

Add `timezone` to the `datetime` import in each file that does not already have it.

**`src/services/user_preferences_service.py`** -- line 19:
```python
# Before:
from datetime import datetime

# After:
from datetime import datetime, timezone
```

**`src/services/member_service.py`** -- line 21:
```python
# Before:
from datetime import datetime

# After:
from datetime import datetime, timezone
```

**`src/api/schema/response_schemas.py`** -- line 33:
```python
# Before:
from datetime import datetime

# After:
from datetime import datetime, timezone
```

**`src/api/routes/users/user_status.py`** -- line 4:
```python
# Before:
from datetime import datetime, timedelta

# After:
from datetime import datetime, timedelta, timezone
```

**`src/api/routes/users/management.py`** -- line 6:
```python
# Before:
from datetime import datetime

# After:
from datetime import datetime, timezone
```

**`src/api/routes/users/invitations.py`** -- line 16:
```python
# Before:
from datetime import datetime

# After:
from datetime import datetime, timezone
```

### Step 2: Replace all `datetime.utcnow()` calls

In every file, replace `datetime.utcnow()` with `datetime.now(timezone.utc)`.

**`src/services/user_preferences_service.py`** (1 change):
```python
# Line 121:
preferences.updated_at = datetime.now(timezone.utc)
```

**`src/services/member_service.py`** (6 changes):
```python
# Lines 112-113:
joined_at=datetime.now(timezone.utc),
last_activity_at=datetime.now(timezone.utc)

# Line 177:
"removed_at": datetime.now(timezone.utc)

# Line 293:
member.last_activity_at = datetime.now(timezone.utc)

# Line 423:
member.last_activity_at = datetime.now(timezone.utc)

# Lines 574-575 (also remove/update the stale comment on line 574):
# Before:
# Use utcnow() for timezone-naive datetime to match TIMESTAMP WITHOUT TIME ZONE column
timestamp = datetime.utcnow()

# After:
timestamp = datetime.now(timezone.utc)
```

**`src/api/schema/response_schemas.py`** (2 changes):
```python
# Line 166:
default_factory=lambda: datetime.now(timezone.utc),

# Line 332:
timestamp = int(datetime.now(timezone.utc).timestamp())
```

**`src/api/routes/users/user_status.py`** (2 changes):
```python
# Line 65:
target_user.updated_at = datetime.now(timezone.utc)

# Line 257:
target_user.updated_at = datetime.now(timezone.utc)
```

**`src/api/routes/users/management.py`** (3 changes):
```python
# Line 60:
datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

# Line 400:
(datetime.now(timezone.utc) - db_user.created_at).days if db_user.created_at else 0

# Line 429:
requested_at=datetime.now(timezone.utc).isoformat(),
```

**`src/api/routes/users/invitations.py`** (2 changes):
```python
# Line 311:
"declined_at": datetime.now(timezone.utc).isoformat()

# Line 384:
"declined_at": datetime.now(timezone.utc).isoformat()
```

### Step 3: Handle the `management.py` line 400 subtraction gotcha

On line 400 of `management.py`, the code computes:
```python
(datetime.utcnow() - db_user.created_at).days
```

After migration this becomes:
```python
(datetime.now(timezone.utc) - db_user.created_at).days
```

If `db_user.created_at` is a **naive** datetime (which it will be if the column is `TIMESTAMP WITHOUT TIME ZONE` and the model has not been updated), subtracting a naive datetime from an aware datetime will raise `TypeError`. To handle this safely, either:

- **(a)** Ensure the `created_at` column returns aware datetimes (preferred -- addressed in TASK-045), or
- **(b)** Add a guard: `(datetime.now(timezone.utc) - db_user.created_at.replace(tzinfo=timezone.utc)).days` as a temporary measure.

Verify which approach is appropriate by checking whether the `Users` model's `created_at` column already returns timezone-aware datetimes.

### Step 4: Verify database column compatibility

Check that the database columns storing these timestamps handle timezone-aware datetimes correctly:
- `TIMESTAMP WITH TIME ZONE` columns store timezone info natively.
- `TIMESTAMP WITHOUT TIME ZONE` columns will have the timezone silently stripped by SQLAlchemy/psycopg2 before storage. This is functionally equivalent to the current behavior but worth noting.

No schema migration is required for this change.

---

## Other Affected Locations

The same `datetime.utcnow()` deprecation has been identified in other audit reports and scoped into separate tasks:

| Task | Audit | Scope | Count |
|------|-------|-------|-------|
| **TASK-004** | B1 - Authentication | Auth services: `token_utils.py`, `auth_service.py`, `oauth_service.py`, `session_service.py`, `token_cleanup.py`, and auth model files | ~47 occurrences |
| **TASK-045** | B2 - Database & Migrations | ~30+ model files (column `default=` and `onupdate=` parameters) and ~40+ service files | ~300+ occurrences |
| **TASK-079** (this task) | B3 - User Management | User management services, routes, and schemas | 18 occurrences |

These tasks can be executed independently but should ideally be coordinated to avoid merge conflicts and ensure consistent timezone handling across the codebase.

---

## Testing Instructions

### Before Fix (Confirm Current Behavior):
1. Run `python -W all -c "from datetime import datetime; datetime.utcnow()"` on Python 3.12+ to see the deprecation warning
2. Verify that `datetime.utcnow()` returns a naive datetime: `datetime.utcnow().tzinfo` is `None`

### After Fix (Verify the Solution):
1. **Preferences update:** Call the user preferences update endpoint and verify the `updated_at` timestamp is correct
2. **Member operations:** Add a member to a workspace and verify `joined_at` and `last_activity_at` timestamps are correct
3. **Member removal:** Remove a member and verify the `removed_at` value in the response is a valid UTC timestamp
4. **Member status update:** Change a member's status and verify `last_activity_at` is updated correctly
5. **Role assignment:** Assign a role and verify the `assigned_at` timestamp is correct
6. **User suspend/ban:** Suspend and ban a user (via user_status routes) and verify `updated_at` is correct
7. **Data export:** Request a data export and verify the generated email contains the correct timestamp and `account_age_days` computes without error
8. **Invitation decline:** Decline an invitation and verify the `declined_at` value in the response is valid
9. **Response metadata:** Verify that API responses include the correct `timestamp` field in response metadata
10. **No deprecation warnings:** Run the test suite on Python 3.12+ and confirm no `DeprecationWarning` from any of the 6 affected files

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "user or member or invitation or preferences or status or management" -v
```

### Verify No Remaining Occurrences:
```bash
cd rext-backend && grep -rn "datetime\.utcnow" \
  src/services/user_preferences_service.py \
  src/services/member_service.py \
  src/api/schema/response_schemas.py \
  src/api/routes/users/user_status.py \
  src/api/routes/users/management.py \
  src/api/routes/users/invitations.py
```
This should return no results after the fix.

---

## Acceptance Criteria

- [ ] All 18 `datetime.utcnow()` calls in the 6 affected files are replaced with `datetime.now(timezone.utc)`
- [ ] All 6 affected files import `timezone` from `datetime`
- [ ] The stale comment on `member_service.py` line 574 is removed or updated
- [ ] The `management.py` line 400 subtraction is verified safe against naive/aware mismatch (or a `.replace(tzinfo=timezone.utc)` guard is added)
- [ ] `grep -rn "datetime\.utcnow" <6 files>` returns zero results
- [ ] Timestamps in the database remain correct UTC values
- [ ] No `DeprecationWarning` from the 6 affected files when running on Python 3.12+
- [ ] No new warnings or errors introduced
- [ ] Existing tests pass without modification
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Python Docs:** [datetime.utcnow() deprecation notice](https://docs.python.org/3/library/datetime.html#datetime.datetime.utcnow)
- **Python 3.12 What's New:** [Deprecated datetime.utcnow()](https://docs.python.org/3.12/whatsnew/3.12.html#deprecated)
- **Deprecation Discussion:** [discuss.python.org - Deprecating utcnow and utcfromtimestamp](https://discuss.python.org/t/deprecating-utcnow-and-utcfromtimestamp/26221)
- **Migration Guide:** [It's Time For A Change: datetime.utcnow() Is Now Deprecated -- Miguel Grinberg](https://blog.miguelgrinberg.com/post/it-s-time-for-a-change-datetime-utcnow-is-now-deprecated)
- **Best Practice Reference:** [Python: it is now() time to migrate from utcnow()](https://www.andreagrandi.it/posts/python-now-time-to-migrate-from-utcnow/)
- **Internal Reference:** `src/services/user_service.py` -- already migrated, serves as the pattern to follow

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** Python 3.12+ upgrade
- **Related:**
  - **TASK-004** (B1 - Authentication) -- same `datetime.utcnow()` deprecation in auth service files (`token_utils.py`, `auth_service.py`, `oauth_service.py`, `session_service.py`, `token_cleanup.py`)
  - **TASK-045** (B2 - Database & Migrations) -- same deprecation in ~30+ model files (column `default=` / `onupdate=` parameters) and ~40+ service files
  - All three tasks should be coordinated to ensure consistent timezone handling across the full codebase
