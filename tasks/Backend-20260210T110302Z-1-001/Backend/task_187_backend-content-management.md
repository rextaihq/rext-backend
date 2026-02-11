# Task 187: Move Inline Imports to Module Level in Content Management Files

## Metadata
- **Task ID:** TASK-187
- **Source:** Backend Content Management Audit (Finding #33 under P3 Low)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

Three files in the content management area contain `import` statements inside function bodies instead of at the top of the module: `publish_content.py` at line 245, `sites.py` at line 281, and `content_service.py` at line 164. In each case, a standard library or project-internal import is deferred into a function rather than being placed with the rest of the module-level imports.

Specifically:
1. In `src/api/routes/content/modules/publish_content.py:245`, the statement `from src.api.schema.content_schema import ContentSEODataSchema` appears inside `publish_existing_content()`. `ContentSEODataSchema` is already available in the same schema module that is imported at the top of the file (lines 12-19), so this is simply a missed consolidation.
2. In `src/api/routes/content/modules/sites.py:281`, the statement `from datetime import timezone` appears inside `publish_to_site()`. The `datetime` module is not imported at the module level in this file at all, yet `timezone` is only used in one place (line 292).
3. In `src/services/content_service.py:164`, the statement `from sqlalchemy import delete` appears inside `update_content()`. The `sqlalchemy` package is already imported at line 14 (`from sqlalchemy import select, func`), so `delete` can simply be added to that existing import.

PEP 8 (Python's official style guide) states: "Imports are always put at the top of the file, just after any module comments and docstrings, and before module globals and constants." While inline imports are an acceptable pattern for avoiding circular dependencies or lazy-loading heavy modules, none of the three cases here fall into those categories — `datetime.timezone`, `sqlalchemy.delete`, and a project-internal schema are all lightweight imports with no circular dependency risk.

Moving these imports to the top of each file makes dependencies immediately visible, ensures import errors are caught at startup rather than at runtime during a specific code path, and aligns with the PEP 8 convention followed by the rest of the codebase.

---

## Current Code

```python
# File: src/api/routes/content/modules/publish_content.py
# Line: 245
    from src.api.schema.content_schema import ContentSEODataSchema
```

```python
# File: src/api/routes/content/modules/sites.py
# Line: 281
            from datetime import timezone
```

```python
# File: src/services/content_service.py
# Line: 164
            from sqlalchemy import delete
```

---

## Why This Matters (Context & Reasoning)

These three files are part of the content management subsystem — `publish_content.py` handles saving and publishing content to WordPress, `sites.py` manages connected WordPress site CRUD operations, and `content_service.py` contains the core business logic for content creation, updates, and deletion.

Inline imports obscure a module's true dependency set. A developer scanning the top of `sites.py` would not realize the file depends on `datetime.timezone` until they read deep into the `publish_to_site` function. This increases cognitive load during code review, makes dependency auditing harder, and means import-time errors (e.g., a removed module or typo) are only discovered when that specific function is called — potentially in production. Consolidating all imports at the top of the file is a straightforward improvement to code clarity and aligns with the project's dominant pattern.

---

## Impact

- **Severity:** Low — no runtime behavior change; purely a code organization improvement.
- **Affected Users/Flows:** No user-facing impact. Affects developer experience when reading, reviewing, or maintaining these files.
- **Blast Radius:** Isolated to three files. No functional change.

---

## Recommended Solution

### Step 1: Move `ContentSEODataSchema` import to top of `publish_content.py`

```python
# File: src/api/routes/content/modules/publish_content.py
# Add ContentSEODataSchema to the existing import block at lines 12-19.
# Replace the existing import:
from src.api.schema.content_schema import (
    ContentCreate,
    ContentUpdate,
    ContentResponse,
    PublishToSiteRequest,
    PublishResponse,
    PublishToSitesResponse
)
# With:
from src.api.schema.content_schema import (
    ContentCreate,
    ContentUpdate,
    ContentResponse,
    ContentSEODataSchema,
    PublishToSiteRequest,
    PublishResponse,
    PublishToSitesResponse
)
```

Then remove line 245 (`from src.api.schema.content_schema import ContentSEODataSchema`) from inside the `publish_existing_content()` function.

### Step 2: Move `timezone` import to top of `sites.py`

```python
# File: src/api/routes/content/modules/sites.py
# Add after the existing imports at line 4 (after `from typing import List`):
from datetime import datetime, timezone
```

Then remove line 281 (`from datetime import timezone`) from inside the `publish_to_site()` function. Note: `datetime` is used at line 292 (`datetime.now(timezone.utc)`), so import both `datetime` and `timezone`.

### Step 3: Add `delete` to the existing SQLAlchemy import in `content_service.py`

```python
# File: src/services/content_service.py
# Line 14 — change:
from sqlalchemy import select, func
# To:
from sqlalchemy import delete, select, func
```

Then remove line 164 (`from sqlalchemy import delete`) from inside the `update_content()` method.

---

## Other Affected Locations

The codebase has approximately 311 inline imports across 96 files. This task addresses only the three in the content management area. Other notable concentrations include:

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/registry/routes.py` | `10-72` | 63 inline route imports (likely intentional for lazy loading) |
| `src/services/user_service.py` | `179, 335, 336, 392, 419-421, 467, 539, 578` | Multiple inline imports |
| `src/services/email_helpers.py` | `47, 54, 170, 192, 206, 283` | Multiple inline imports |
| `src/api/routes/users/auth.py` | `56, 57, 90, 91, 394, 399, 400, 808, 809, 846, 947, 948, 1017` | 13 inline imports |
| `src/services/member_service.py` | `326, 486, 529-531, 607, 643-645, 684, 685` | Multiple inline imports |

Many of these may be intentional to avoid circular imports. A codebase-wide cleanup of inline imports should be a separate, larger task.

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open `src/api/routes/content/modules/publish_content.py` and verify that `ContentSEODataSchema` is imported inside the function at line 245.
2. Open `src/api/routes/content/modules/sites.py` and verify that `from datetime import timezone` is inside the function at line 281.
3. Open `src/services/content_service.py` and verify that `from sqlalchemy import delete` is inside the method at line 164.

### After Fix (Verify the Solution):
1. Confirm all three imports have been moved to the top of their respective files.
2. Confirm the inline import statements have been removed from inside the functions.
3. Run the application to ensure no import errors at startup.

### Run Existing Tests:
```bash
cd rext-backend
python -m pytest tests/unit/services/test_content_service.py -v
```

---

## Acceptance Criteria

- [ ] `ContentSEODataSchema` is imported at the module level in `publish_content.py` and removed from line 245
- [ ] `datetime` and `timezone` are imported at the module level in `sites.py` and removed from line 281
- [ ] `delete` is added to the existing `sqlalchemy` import in `content_service.py` and removed from line 164
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [PEP 8 — Imports](https://peps.python.org/pep-0008/#imports) — "Imports are always put at the top of the file"
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Python Import Best Practices](https://ispeakcode.substack.com/p/python-import-best-practices) — Covers when inline imports are and aren't appropriate
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-087 (Unused `import os` in Multiple Files, B3), TASK-026 (Unused Import `os` in Auth Routes, B1)
