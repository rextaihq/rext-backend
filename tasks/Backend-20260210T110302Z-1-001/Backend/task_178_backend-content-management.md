# Task 178: Replace Deprecated datetime.utcnow() in Content Models

## Metadata
- **Task ID:** TASK-178
- **Source:** Backend Content Management Audit (Finding #19 under P2 Medium)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P2 Medium
- **Category:** dependency
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `Content` model in `src/api/models/content_models/content.py` (lines 43-44) and the `ContentMedia` model in `src/api/models/content_models/content_media.py` (line 60) use `datetime.utcnow` as the default value for their timestamp columns. The `datetime.utcnow()` method was officially deprecated in Python 3.12 (per [PEP 728](https://docs.python.org/3/library/datetime.html#datetime.datetime.utcnow) and the deprecation notice in the Python docs). While the project currently targets Python `>=3.11,<3.12` per `pyproject.toml`, this is a forward-compatibility issue — upgrading to Python 3.12+ will produce `DeprecationWarning` on every model instantiation.

The fundamental problem with `datetime.utcnow()` is that it returns a **naive** datetime object (no timezone information) that represents UTC time. This is problematic because naive datetimes cannot be reliably compared with timezone-aware datetimes, and Python's standard library functions may interpret them as local time rather than UTC. The correct replacement is `datetime.now(timezone.utc)`, which returns a **timezone-aware** datetime explicitly tagged as UTC.

In the `Content` model, line 43 uses `default=datetime.utcnow` (without parentheses — passed as a callable) for `created_at`, and line 44 uses it for both `default` and `onupdate` on `updated_at`. In the `ContentMedia` model, line 60 uses `default=datetime.utcnow` for `created_at`. All three occurrences need to be updated to use `lambda: datetime.now(timezone.utc)` since SQLAlchemy's `default` parameter expects a callable.

An even better approach for production is to use `server_default=func.now()` which delegates timestamp generation to the database server. This ensures consistency across application instances and avoids clock-skew issues. However, changing from `default` to `server_default` requires an Alembic migration to add the DEFAULT clause to the database column, so the simpler `lambda: datetime.now(timezone.utc)` approach is recommended as a first step, with `server_default` as a follow-up optimization.

Note: The `ContentService` already correctly uses `datetime.now(timezone.utc)` at lines 74-75 and elsewhere, so the models are inconsistent with the service layer.

---

## Current Code

```python
# File: src/api/models/content_models/content.py
# Lines: 43-44
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)
```

```python
# File: src/api/models/content_models/content_media.py
# Lines: 58-62
    created_at = Column(
        TIMESTAMP(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
```

---

## Why This Matters (Context & Reasoning)

These timestamp columns track when content and content-media associations are created and updated. Accurate timestamps are critical for:
- Displaying "last modified" information to users
- Sorting content by creation date (used in `ContentService.list_content()` line 188)
- Audit trails and debugging
- Soft-delete logic (comparison with `deleted_at`)

Using `datetime.utcnow` produces naive datetimes that, when stored in a `DateTime(timezone=True)` column, may be interpreted differently by PostgreSQL depending on the server's timezone setting. While PostgreSQL typically handles this correctly by assuming UTC for naive timestamps stored in `timestamptz` columns, the behavior is implementation-dependent and fragile. Using timezone-aware datetimes eliminates this ambiguity.

The inconsistency between the model defaults (`datetime.utcnow`) and the service layer (`datetime.now(timezone.utc)`) means that timestamps may have subtly different timezone handling depending on whether they come from the model default or the service code path.

---

## Impact

- **Severity:** No immediate runtime error on Python 3.11, but upgrading to Python 3.12+ will produce DeprecationWarnings on every model instantiation. Naive datetimes may cause subtle comparison bugs with timezone-aware datetimes.
- **Affected Users/Flows:** All content creation and content-media association flows.
- **Blast Radius:** Isolated to the two content model files. However, this same pattern exists across 30+ model files in the codebase (see TASK-045 for the broader migration effort).

---

## Recommended Solution

### Step 1: Update `content.py` imports

```python
# File: src/api/models/content_models/content.py
# Replace line 6:
from datetime import datetime

# With:
from datetime import datetime, timezone
```

### Step 2: Update `content.py` timestamp columns

```python
# File: src/api/models/content_models/content.py
# Replace lines 43-44:
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
```

### Step 3: Update `content_media.py` imports

```python
# File: src/api/models/content_models/content_media.py
# Replace line 13:
from datetime import datetime

# With:
from datetime import datetime, timezone
```

### Step 4: Update `content_media.py` timestamp column

```python
# File: src/api/models/content_models/content_media.py
# Replace lines 58-62:
    created_at = Column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/models/content_models/content_seo_data.py` | Unknown | Check if this model also uses `datetime.utcnow` for timestamps |
| `src/services/content_service.py` | `74-75` | Already uses `datetime.now(timezone.utc)` correctly — no change needed |
| 30+ other model files | Various | Same `datetime.utcnow` pattern exists across the entire models directory (covered by TASK-045) |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open a Python 3.12+ shell (if available) and import the Content model.
2. Observe `DeprecationWarning: datetime.datetime.utcnow() is deprecated`.
3. Alternatively, inspect the model code and confirm `default=datetime.utcnow` is used.

### After Fix (Verify the Solution):
1. Create a new Content record via the API or directly in a test.
2. Verify `created_at` and `updated_at` are timezone-aware (have `+00:00` suffix in ISO format).
3. Update the content and verify `updated_at` changes to a new timezone-aware timestamp.
4. Create a ContentMedia record and verify `created_at` is timezone-aware.
5. On Python 3.12+ (if available), confirm no `DeprecationWarning` is emitted.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/services/test_content_service.py -v
```

---

## Acceptance Criteria

- [ ] `content.py` uses `lambda: datetime.now(timezone.utc)` for `created_at` default
- [ ] `content.py` uses `lambda: datetime.now(timezone.utc)` for `updated_at` default and onupdate
- [ ] `content_media.py` uses `lambda: datetime.now(timezone.utc)` for `created_at` default
- [ ] `timezone` is imported from `datetime` in both files
- [ ] No references to `datetime.utcnow` remain in content model files
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python datetime.utcnow() deprecation notice](https://docs.python.org/3/library/datetime.html#datetime.datetime.utcnow)
- **Security Advisory:** N/A
- **Migration Guide:** [It's Time For A Change: datetime.utcnow() Is Now Deprecated](https://blog.miguelgrinberg.com/post/it-s-time-for-a-change-datetime-utcnow-is-now-deprecated) — Detailed explanation by Miguel Grinberg
- **Best Practice Reference:** [Python Deprecations Index](https://docs.python.org/3/deprecations/index.html)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-004 (deprecated `datetime.utcnow()` in auth module — B1), TASK-045 (deprecated `datetime.utcnow()` in ~30+ model files — B2), TASK-079 (deprecated `datetime.utcnow()` in user management — B3), TASK-101 (inconsistent DateTime usage in workspace management — B4), TASK-146 (deprecated `datetime.utcnow()` in subscription/billing — B5)
