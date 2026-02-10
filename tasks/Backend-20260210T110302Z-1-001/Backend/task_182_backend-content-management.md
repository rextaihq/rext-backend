# Task 182: Consolidate Duplicate slugify Functions into Shared Utility

## Metadata
- **Task ID:** TASK-182
- **Source:** Backend Content Management Audit (Finding #18 under P2 Medium)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The content management area contains two independent implementations of slug generation logic that duplicate functionality already available in a shared utility module. The first duplicate is in `src/api/routes/content/modules/helpers.py` at lines 10-22, which defines a standalone `slugify()` function, and lines 25-37 which define `generate_unique_slug()`. The second duplicate is in `src/services/content_service.py` at lines 210-214, which defines `ContentService._slugify()`, and lines 216-222 which define `ContentService._generate_unique_slug()`.

Critically, the project already has a canonical shared utility at `src/utils/slug_utils.py` that provides `slugify()`, `generate_unique_slug()`, and `generate_workspace_slug()`. Additionally, `src/services/workspace_service.py` line 1128 contains yet another `_slugify()` method. This means the same slug generation logic exists in **4 separate locations** across the codebase (helpers.py, content_service.py, workspace_service.py, and slug_utils.py), each with slight implementation differences.

The `helpers.py` version of `generate_unique_slug()` is particularly problematic because it does not filter by `workspace_id`, checking slug uniqueness globally rather than per-workspace. This is a security-adjacent bug: it can cause slug collisions across workspaces and leaks information about content existence in other workspaces. Furthermore, neither the `helpers.py` `slugify()` nor the `helpers.py` `generate_unique_slug()` function appears to be imported or called anywhere in the codebase (no import references were found), making them dead code that could mislead future developers.

According to DRY (Don't Repeat Yourself) principles and the Python packaging best practice of maintaining a single canonical utility module, all slug generation should be consolidated into `src/utils/slug_utils.py`. The `slug_utils.py` version is the most robust, with proper docstrings, a fallback for empty slugs, and a model-agnostic `generate_unique_slug()` signature. However, it currently uses synchronous SQLAlchemy (`db.query()`) which is incompatible with the async session used throughout the content management code. An async variant needs to be added.

---

## Current Code

```python
# File: src/api/routes/content/modules/helpers.py
# Lines: 10-37
def slugify(text: str) -> str:
    """Convert text to URL-safe slug"""
    # Convert to lowercase
    text = text.lower()
    # Replace spaces and underscores with hyphens
    text = re.sub(r'[\s_]+', '-', text)
    # Remove non-alphanumeric characters except hyphens
    text = re.sub(r'[^a-z0-9-]', '', text)
    # Remove multiple consecutive hyphens
    text = re.sub(r'-+', '-', text)
    # Strip hyphens from start and end
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
```

```python
# File: src/services/content_service.py
# Lines: 210-222
    def _slugify(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r"[\s_]+", "-", text)
        text = re.sub(r"[^a-z0-9-]", "", text)
        return text.strip("-")

    async def _generate_unique_slug(self, workspace_id: UUID, base_slug: str, exclude_id: Optional[UUID] = None) -> str:
        slug, counter = base_slug, 1
        while True:
            query = select(Content).where(Content.workspace_id == workspace_id, Content.slug == slug, Content.deleted_at == None)
            if exclude_id: query = query.where(Content.id != exclude_id)
            if not (await self.db.execute(query)).scalar_one_or_none(): return slug
            slug, counter = f"{base_slug}-{counter}", counter + 1
```

```python
# File: src/utils/slug_utils.py (existing shared utility)
# Lines: 9-38
def slugify(text: str) -> str:
    """Convert text to URL-safe slug"""
    text = text.lower()
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'[^a-z0-9-]', '', text)
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')
    if not text:
        text = 'workspace'
    return text
```

---

## Why This Matters (Context & Reasoning)

Slug generation is a core utility used across multiple features (content management, workspace management) to produce URL-safe identifiers. Having 4 independent implementations creates maintenance overhead: if the slugify logic needs to change (e.g., to support Unicode or set a max length), developers must find and update all copies. Worse, the `helpers.py` version has a security-relevant bug (missing workspace_id filter) that a developer might accidentally use, and the slight implementation differences (some handle empty results, some don't) can cause subtle behavior discrepancies. Consolidation reduces bug surface and ensures consistent behavior.

---

## Impact

- **Severity:** Maintenance burden and risk of inconsistent slug behavior across features. The helpers.py version has a security-adjacent bug (global slug check). Future developers may use the wrong implementation.
- **Affected Users/Flows:** Content creation, content updates, workspace creation - any flow that generates slugs.
- **Blast Radius:** Localized to slug generation, but touches content service, helpers module, workspace service, and the shared utility.

---

## Recommended Solution

### Step 1: Add async `generate_unique_slug_async()` to `src/utils/slug_utils.py`

```python
# File: src/utils/slug_utils.py
# Add at the end of file, after existing functions:
from typing import Optional, Type, Set
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def generate_unique_slug_async(
    db: AsyncSession,
    base_slug: str,
    model_class,
    slug_field: str = 'slug',
    exclude_id: Optional[UUID] = None,
    workspace_id: Optional[UUID] = None,
    workspace_field: str = 'workspace_id',
) -> str:
    """
    Generate a unique slug using async database session.

    Fetches all matching slugs in a single query, then finds
    the first available slug in memory (avoids N+1 queries).

    Args:
        db: Async database session
        base_slug: Base slug to make unique
        model_class: SQLAlchemy model class to check against
        slug_field: Name of the slug field in the model
        exclude_id: Optional ID to exclude from uniqueness check (for updates)
        workspace_id: Optional workspace ID for scoped uniqueness
        workspace_field: Name of the workspace_id field in the model

    Returns:
        Unique slug string
    """
    slug_col = getattr(model_class, slug_field)
    pattern = f"{base_slug}%"

    query = select(slug_col).where(
        slug_col.like(pattern),
        model_class.deleted_at == None,
    )

    if workspace_id is not None:
        query = query.where(getattr(model_class, workspace_field) == workspace_id)

    if exclude_id is not None:
        query = query.where(model_class.id != exclude_id)

    result = await db.execute(query)
    existing_slugs: Set[str] = {row[0] for row in result.fetchall()}

    if base_slug not in existing_slugs:
        return base_slug

    counter = 1
    while f"{base_slug}-{counter}" in existing_slugs:
        counter += 1
    return f"{base_slug}-{counter}"
```

Note: The imports for `Session` (sync) at the top of the file can remain for the existing sync function. Add the async imports inside the function or at the top of the file.

### Step 2: Update `ContentService` to use the shared utility

```python
# File: src/services/content_service.py
# Replace the import section (add slug_utils import):
from src.utils.slug_utils import slugify, generate_unique_slug_async

# Remove the _slugify method (lines 210-214) and _generate_unique_slug method (lines 216-222).
# Update all call sites in the class:

# In create_content (around line 56-57), change:
#   base_slug = self._slugify(data.title)
#   unique_slug = await self._generate_unique_slug(workspace_id, base_slug)
# To:
        base_slug = slugify(data.title)
        unique_slug = await generate_unique_slug_async(
            db=self.db,
            base_slug=base_slug,
            model_class=Content,
            workspace_id=workspace_id,
        )

# In update_content (around line 135), change:
#   content.slug = await self._generate_unique_slug(workspace_id, self._slugify(data.title), exclude_id=content.id)
# To:
            content.slug = await generate_unique_slug_async(
                db=self.db,
                base_slug=slugify(data.title),
                model_class=Content,
                workspace_id=workspace_id,
                exclude_id=content.id,
            )
```

### Step 3: Remove the duplicate functions from helpers.py

```python
# File: src/api/routes/content/modules/helpers.py
# Replace entire file contents with:
# This module previously contained slugify and generate_unique_slug functions
# that have been consolidated into src/utils/slug_utils.py.
# This file is intentionally left minimal. If no other helpers are needed,
# consider removing this file entirely.
```

Since `helpers.py` is not imported anywhere (confirmed by grep), the file can be deleted entirely. However, if you prefer a cautious approach, empty it first and remove it in a follow-up.

### Step 4: Remove the `import re` from content_service.py if no longer needed

After removing `_slugify`, check if `re` is still used elsewhere in the file. If not, remove the `import re` on line 12.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/workspace_service.py` | `1128-1139` | Contains another duplicate `_slugify()` method that should also be consolidated to use `slug_utils.slugify()` |
| `src/utils/slug_utils.py` | `41-82` | Existing sync `generate_unique_slug()` — should remain for sync callers but the async version fills the gap |
| `tests/unit/test_slug_utils.py` | `11+` | Existing tests for slug_utils — add tests for the new async function |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Confirm the duplication exists by searching: `grep -rn "def slugify\|def _slugify" rext-backend/src/`
2. Verify helpers.py functions are not imported anywhere: `grep -rn "from.*helpers import" rext-backend/src/`

### After Fix (Verify the Solution):
1. Confirm only one `slugify` exists in utils: `grep -rn "def slugify" rext-backend/src/utils/`
2. Confirm content_service.py imports from slug_utils: `grep "from src.utils.slug_utils" rext-backend/src/services/content_service.py`
3. Confirm helpers.py no longer has slugify: `cat rext-backend/src/api/routes/content/modules/helpers.py`
4. Test content creation still generates correct slugs by running the content service tests.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/test_slug_utils.py -v
cd rext-backend && python -m pytest tests/unit/services/test_content_service.py -v
```

---

## Acceptance Criteria

- [ ] `helpers.py` no longer contains `slugify()` or `generate_unique_slug()` functions
- [ ] `ContentService._slugify()` and `ContentService._generate_unique_slug()` are removed
- [ ] `ContentService` imports and uses `slugify` and `generate_unique_slug_async` from `src/utils/slug_utils`
- [ ] `src/utils/slug_utils.py` contains the new `generate_unique_slug_async()` function
- [ ] The new async function uses a single query (not N+1 loop) for slug uniqueness
- [ ] The new async function supports workspace-scoped uniqueness
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [python-slugify on PyPI](https://pypi.org/project/python-slugify/) — the standard Python slug library (project currently uses hand-rolled regex)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Using Model Callbacks in SQLAlchemy to Generate Slugs](https://michaelcho.me/article/using-model-callbacks-in-sqlalchemy-to-generate-slugs/) — pattern for slug generation in SQLAlchemy projects
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-158 (N+1 Query in helpers.py slug generation — the helpers.py functions being removed here are the same ones flagged in TASK-158), TASK-168 (N+1 Query in ContentService slug generation — the _generate_unique_slug being replaced here)
