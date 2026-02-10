# Task 158: Insecure Slug Uniqueness Check in helpers.py — Missing workspace_id Filter

## Metadata
- **Task ID:** TASK-158
- **Source:** Content Management Audit (Finding #4 under P0 Critical)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P0 Critical
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `generate_unique_slug()` function in `src/api/routes/content/modules/helpers.py` at lines 25-37 checks for slug uniqueness **globally across all workspaces** instead of scoping the check to the current workspace. The function accepts only `db` and `base_slug` parameters — it has no `workspace_id` parameter and therefore queries all `Content` rows regardless of which workspace they belong to.

```python
async def generate_unique_slug(db: AsyncSession, base_slug: str) -> str:
    slug = base_slug
    counter = 1
    while True:
        result = await db.execute(select(Content).where(Content.slug == slug, Content.deleted_at == None))
        if not result.scalar_one_or_none():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug
```

This creates two distinct problems:

1. **Multi-tenancy violation (security):** The function checks slug uniqueness across ALL workspaces. If Workspace A has a content item with slug "getting-started", and Workspace B tries to create content with the same title, this function would generate "getting-started-1" for Workspace B — even though slugs should be unique only within a workspace. This leaks information about content slugs across workspace boundaries.

2. **N+1 query pattern (performance):** The function uses a `while True` loop that issues a separate database query for each iteration. If slugs "my-article", "my-article-1", ... "my-article-99" all exist, creating another "my-article" requires 100 sequential database queries.

Additionally, this function is a **duplicate** of `ContentService._generate_unique_slug()` at `src/services/content_service.py:216-222`, which correctly includes a `workspace_id` parameter. A codebase-wide search confirms that nothing imports from `helpers.py` — the function is dead code. However, its existence is dangerous because a developer might reasonably call it in the future, introducing the security bug.

A companion `slugify()` function at `helpers.py:10-22` is also a duplicate of `ContentService._slugify()` at `content_service.py:210-214`. Both are functionally identical, and a third copy exists at `src/utils/slug_utils.py:9-38`. This triple duplication creates maintenance risk and confusion about which implementation to use.

---

## Current Code

```python
# File: src/api/routes/content/modules/helpers.py
# Lines: 1-41 (entire file)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import re

from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.models.content_models import Content


def slugify(text: str) -> str:
    """Convert text to URL-safe slug"""
    text = text.lower()
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'[^a-z0-9-]', '', text)
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')
    return text


async def generate_unique_slug(db: AsyncSession, base_slug: str) -> str:
    """Generate unique slug by appending number if needed"""
    slug = base_slug
    counter = 1

    while True:
        result = await db.execute(select(Content).where(Content.slug == slug, Content.deleted_at == None))
        if not result.scalar_one_or_none():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


# _build_content_response() function removed - replaced with Content.to_dict(include_relationships=[...])
```

The secure version in the service layer for comparison:

```python
# File: src/services/content_service.py
# Lines: 216-222
async def _generate_unique_slug(self, workspace_id: UUID, base_slug: str, exclude_id: Optional[UUID] = None) -> str:
    slug, counter = base_slug, 1
    while True:
        query = select(Content).where(Content.workspace_id == workspace_id, Content.slug == slug, Content.deleted_at == None)
        if exclude_id: query = query.where(Content.id != exclude_id)
        if not (await self.db.execute(query)).scalar_one_or_none(): return slug
        slug, counter = f"{base_slug}-{counter}", counter + 1
```

---

## Why This Matters (Context & Reasoning)

Rext AI is a multi-tenant SaaS application where workspaces are the primary isolation boundary. Each workspace should operate independently — content, slugs, and metadata in one workspace must not affect or leak into another. The `generate_unique_slug()` function in helpers.py breaks this isolation by checking slugs globally.

Even though this function is currently dead code (nothing imports it), its presence in the codebase is a latent security risk. A developer working on content features might discover it and call it, unaware that it lacks workspace scoping. The recommended fix is to delete the entire file, removing the risk and eliminating the code duplication.

The N+1 query pattern in both the helpers.py version and the service version (`content_service.py:216-222`) means that slug generation performance degrades linearly with the number of existing similar slugs. The service version should also be optimized (see TASK-170 for the related P1 performance finding).

---

## Impact

- **Severity:** If this function were called in production, it would allow cross-workspace slug enumeration and cause slug collisions between workspaces. As dead code, it is a latent security risk waiting to be activated.
- **Affected Users/Flows:** Content creation flows if the function were ever called. Currently no direct impact since the function is unused.
- **Blast Radius:** The function is isolated in helpers.py. Removing it has zero impact on current functionality since nothing imports it.

---

## Recommended Solution

The recommended approach is to **delete the entire `helpers.py` file** and **remove its import** from `__init__.py` (if any). The file contains three items — all are either dangerous, duplicated, or obsolete:

1. `slugify()` — duplicate of `ContentService._slugify()` and `slug_utils.slugify()`
2. `generate_unique_slug()` — dangerous duplicate missing `workspace_id`
3. A comment about a removed function — no value

### Step 1: Delete the helpers.py file

```bash
# File to delete:
# src/api/routes/content/modules/helpers.py
```

Delete the file entirely. It is not imported anywhere in the codebase (verified via grep).

### Step 2: Verify no imports reference helpers.py

A codebase search confirms no file imports from `helpers.py`:

```bash
grep -r "from src.api.routes.content.modules.helpers" rext-backend/src/
grep -r "from .helpers" rext-backend/src/api/routes/content/
```

Both return no results. No import cleanup is needed.

### Step 3: Verify ContentService._generate_unique_slug() is the canonical implementation

The `ContentService._generate_unique_slug()` at `src/services/content_service.py:216-222` is the version actually in use. It correctly includes `workspace_id` scoping. Confirm it is called at:
- `content_service.py:57` — during content creation
- `content_service.py:135` — during content title updates

No changes needed to the service version for this task (the N+1 performance issue in the service version is tracked separately).

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/content_service.py` | `210-214` | Third copy of `slugify()` — `_slugify()` method on ContentService |
| `src/services/content_service.py` | `216-222` | Correct `_generate_unique_slug()` with `workspace_id` — but still has N+1 pattern (see related tasks) |
| `src/utils/slug_utils.py` | `9-38` | Another `slugify()` copy used by workspace service |
| `src/utils/slug_utils.py` | `41-82` | Sync `generate_unique_slug()` — also has N+1 pattern and no workspace_id |
| `src/services/workspace_service.py` | `1145+` | Workspace-level `_generate_unique_slug` — different model but same pattern |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Confirm `helpers.py` exists at `src/api/routes/content/modules/helpers.py`
2. Open the file and verify the `generate_unique_slug()` function lacks `workspace_id` parameter
3. Confirm no code imports this function: `grep -r "from.*helpers.*import" rext-backend/src/`

### After Fix (Verify the Solution):
1. Confirm `helpers.py` has been deleted
2. Confirm no import errors: run `python -c "from src.api.routes.content.modules import router"` — should succeed
3. Confirm content creation still works: create a content item via the `/save` endpoint — slug should be generated correctly
4. Confirm content update with title change still generates slugs correctly

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/unit/services/test_content_service.py -v
pytest tests/ -k "content" -v
```

---

## Acceptance Criteria

- [ ] `src/api/routes/content/modules/helpers.py` has been deleted
- [ ] No `ImportError` or `ModuleNotFoundError` occurs anywhere in the application
- [ ] Content creation via `/save` and `/publish` endpoints still generates correct slugs
- [ ] Content title updates still generate correct slugs
- [ ] The insecure `generate_unique_slug()` function (without workspace_id) no longer exists in this file
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy Async Select Queries](https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html)
- **Security Advisory:** [OWASP API1:2023 - Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/) — applies to multi-tenancy slug leakage
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP Multi-Tenancy Security](https://cheatsheetseries.owasp.org/cheatsheets/SaaS_Security_Cheat_Sheet.html) — tenant data isolation requirements
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-170 (B6 Finding 5 — N+1 Query in ContentService._generate_unique_slug, same pattern), TASK-159 (B6 Finding 2 — Global UNIQUE constraints on slug/title, complementary fix)
