# Task 168: N+1 Query Pattern in ContentService Slug Generation

## Metadata
- **Task ID:** TASK-168
- **Source:** Content Management Audit (Finding #5 under P1 High)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P1 High
- **Category:** performance
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `ContentService._generate_unique_slug()` method at `src/services/content_service.py:216-222` uses a while-loop that issues a separate database query on each iteration to check whether a candidate slug already exists. If a workspace already has content with slugs `"my-article"`, `"my-article-1"`, `"my-article-2"`, ... through `"my-article-99"`, then creating a new content item titled "My Article" will trigger 100 sequential database queries before finding `"my-article-100"` as available. Each iteration executes `SELECT * FROM content WHERE workspace_id = ? AND slug = ? AND deleted_at IS NULL`, waits for the result, increments the counter, and repeats.

This is a classic N+1 query anti-pattern applied to slug generation. The correct approach, as documented in SQLAlchemy 2.0's query guide, is to fetch all matching slugs in a single query using a `LIKE` pattern match, then determine the next available slug number in application memory. SQLAlchemy 2.0 provides the `Column.like()` method for this purpose, which maps to a SQL `LIKE` clause. On PostgreSQL (which this project uses via `asyncpg`), this is efficiently handled by the database engine, especially when the `slug` column is indexed (which it is — `content.py:20` has `index=True`).

Additionally, there is a duplicate `generate_unique_slug()` function at `src/api/routes/content/modules/helpers.py:25-37` that has the same N+1 problem plus an additional security bug: it checks slug uniqueness globally (no `workspace_id` filter), which could cause cross-workspace slug collisions. The helpers.py version appears unused — the service method is the one actually called — but it should be removed as part of this fix to prevent future accidental use.

---

## Current Code

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

```python
# File: src/api/routes/content/modules/helpers.py
# Lines: 25-37
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

---

## Why This Matters (Context & Reasoning)

Slug generation runs on every content creation and every title update (when the title changes). In a workspace with a large content library — which is the expected use case for a content automation platform — slug collisions become increasingly likely. A workspace producing daily articles for a year would have 365+ content items. If many articles share common title prefixes (e.g., "How to...", "Guide to...", "Best..."), the collision count can grow rapidly. Each collision adds a sequential database round-trip, turning content creation into an operation that scales linearly with the number of existing content items sharing a slug prefix. This directly impacts API response times and user experience during content creation.

---

## Impact

- **Severity:** Content creation latency grows linearly with the number of existing slug collisions. With 100 collisions, this adds ~100 sequential database queries (~200-500ms additional latency in production). With 1000 collisions, the endpoint could timeout.
- **Affected Users/Flows:** All content creation and title-update operations in all workspaces.
- **Blast Radius:** Affects two endpoints: `POST /api/v1/content/save` and `PATCH /api/v1/content/{content_id}` (when title changes). Performance degrades proportionally to workspace content volume.

---

## Recommended Solution

Replace the while-loop with a single `LIKE`-based query that fetches all matching slugs at once, then determine the next available slug in memory.

### Step 1: Replace `_generate_unique_slug` in ContentService

```python
# File: src/services/content_service.py
# Replace lines 216-222 with:

    async def _generate_unique_slug(
        self, workspace_id: UUID, base_slug: str, exclude_id: Optional[UUID] = None
    ) -> str:
        """
        Generate a unique slug within a workspace using a single database query.

        Fetches all existing slugs matching the base pattern in one query,
        then finds the next available number suffix in memory.
        """
        pattern = f"{base_slug}%"
        query = select(Content.slug).where(
            Content.workspace_id == workspace_id,
            Content.slug.like(pattern),
            Content.deleted_at.is_(None),
        )
        if exclude_id:
            query = query.where(Content.id != exclude_id)

        result = await self.db.execute(query)
        existing_slugs = {row[0] for row in result.fetchall()}

        if base_slug not in existing_slugs:
            return base_slug

        counter = 1
        while f"{base_slug}-{counter}" in existing_slugs:
            counter += 1
        return f"{base_slug}-{counter}"
```

### Step 2: Remove the Duplicate Function in helpers.py

```python
# File: src/api/routes/content/modules/helpers.py
# Replace the entire file content with:

from uuid import UUID
import re

from src.api.middleware.exceptions import ResourceNotFoundException


def slugify(text: str) -> str:
    """Convert text to URL-safe slug."""
    text = text.lower()
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'[^a-z0-9-]', '', text)
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')
    return text
```

Note: The `generate_unique_slug` function and its imports (`AsyncSession`, `select`, `Content`) are removed. The `slugify` function is kept because it may be imported elsewhere (verify with a codebase search). The unused import of `ResourceNotFoundException` is also removed. The `Content` import and `select` import are no longer needed.

### Step 3: Verify No Callers of the Removed helpers.py Function

Search the codebase for any imports of `generate_unique_slug` from helpers. If found, update them to use `ContentService._generate_unique_slug` instead.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/content/modules/helpers.py` | `25-37` | Duplicate `generate_unique_slug` with security bug (no workspace_id filter) — remove |
| `src/api/routes/content/modules/helpers.py` | `1-7` | Imports for `AsyncSession`, `select`, `Content` become unused after removing `generate_unique_slug` — clean up |
| `src/services/content_service.py` | `56-57` | `create_content` calls `_generate_unique_slug` — will use the optimized version |
| `src/services/content_service.py` | `135` | `update_content` calls `_generate_unique_slug` when title changes — will use the optimized version |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create 50+ content items in a workspace with titles like "Test Article", "Test Article", "Test Article" (the system will auto-generate slugs "test-article", "test-article-1", ..., "test-article-49")
2. Enable SQL query logging by setting `echo=True` on the SQLAlchemy engine
3. Create another content item titled "Test Article"
4. Observe 50+ individual SELECT queries in the logs before the slug "test-article-50" is determined

### After Fix (Verify the Solution):
1. With the same 50+ content items, create another "Test Article"
2. Observe only ONE SELECT query with a `LIKE 'test-article%'` clause in the logs
3. Verify the returned slug is "test-article-50" (or the next available number)
4. Test edge cases:
   - First content with a unique title → should return the base slug without suffix
   - Content with title "Test" when "Test Article" slugs exist → should not falsely match (LIKE pattern is `test%` which could match `test-article` — but the in-memory set check handles this correctly)
   - Update a content title to a title with many existing slugs → verify single query

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/services/test_content_service.py -v
```

---

## Acceptance Criteria

- [ ] `_generate_unique_slug` uses a single database query with `LIKE` pattern matching
- [ ] The duplicate `generate_unique_slug` function in `helpers.py` is removed
- [ ] Unused imports in `helpers.py` are cleaned up
- [ ] Slug generation returns correct results for: no collision, single collision, many collisions
- [ ] The `LIKE` pattern correctly uses workspace scoping (only matches within the same workspace)
- [ ] The `deleted_at` filter uses `.is_(None)` instead of `== None` (SQLAlchemy best practice)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 Operator Reference — LIKE](https://docs.sqlalchemy.org/en/20/core/operators.html) — documentation for `Column.like()` method
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [SQLAlchemy Query Optimization — Select Statements](https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html) — guidance on efficient query patterns
- **Related Issues/PRs:** None identified

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-158 (N+1 Query in helpers.py Slug Generation — Missing workspace_id) — the helpers.py function removed in this task was the subject of TASK-158; this task completes the cleanup by removing the duplicate entirely
