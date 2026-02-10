# Task 094: Fix N+1 Queries in `get_workspace_analytics()` — Combine 5-7 Separate Count Queries into 1-2

## Metadata
- **Task ID:** TASK-094
- **Source:** Backend Workspace Management (Finding #6 under P1 High)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P1 High
- **Category:** performance
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `WorkspaceService.get_workspace_analytics()` method in `src/services/workspace_service.py` (lines 380-484) executes **5 separate database queries** to count records across different tables (`Website`, `KnowledgeFiles`, `TextKnowledge`, `WorkspaceMembers`, `Content`), and when the `include_word_counts=True` parameter is passed, it adds **2 additional queries** for word count statistics from `Website` and `KnowledgeFiles`. This results in 5-7 individual database round-trips every time a workspace detail page loads.

This method is called from **3 separate route handlers** in `workspace_core.py` (lines 80, 126, and 179) — `get_workspace_by_id`, `get_workspace_by_slug`, and `get_workspace_by_id_path` — all of which pass `include_word_counts=True`. This means every workspace detail page view triggers 7 database queries just for analytics. Additionally, the `workspace_stats.py` route (lines 56-94) duplicates 4 of these same count queries inline rather than delegating to the service method, creating a DRY violation on top of the performance issue.

According to SQLAlchemy 2.0 documentation, multiple `func.count()` expressions can be combined into a single `SELECT` statement using subqueries or case expressions. The current pattern of executing separate `SELECT COUNT(id) FROM table WHERE workspace_id = ?` queries for each table is a classic N+1 anti-pattern that can be collapsed into 1-2 queries. Each query requires a network round-trip to the PostgreSQL database (via asyncpg), adding latency proportional to the number of queries.

A secondary issue is that line 425 uses `Content.deleted_at == None` instead of the SQLAlchemy-idiomatic `.is_(None)`, which triggers a Python `SyntaxWarning` in Python 3.12+ and may behave unexpectedly with some SQLAlchemy backends.

---

## Current Code

```python
# File: src/services/workspace_service.py
# Lines: 396-474
    # Get counts in separate queries (simplified version)
    result = await self.db.execute(
        select(func.count(Website.id)).where(Website.workspace_id == workspace_id)
    )
    web_count = result.scalar() or 0

    result = await self.db.execute(
        select(func.count(KnowledgeFiles.id)).where(
            KnowledgeFiles.workspace_id == workspace_id
        )
    )
    files_count = result.scalar() or 0

    result = await self.db.execute(
        select(func.count(TextKnowledge.id)).where(
            TextKnowledge.workspace_id == workspace_id
        )
    )
    text_count = result.scalar() or 0

    result = await self.db.execute(
        select(func.count(WorkspaceMembers.id)).where(
            WorkspaceMembers.workspace_id == workspace_id
        )
    )
    members_count = result.scalar() or 0

    result = await self.db.execute(
        select(func.count(Content.id)).where(
            Content.workspace_id == workspace_id, Content.deleted_at == None
        )
    )
    content_count = result.scalar() or 0
```

```python
# File: src/api/routes/workspaces/workspace_stats.py
# Lines: 56-94 (duplicate logic in route layer)
    result = await db.execute(
        select(func.count(Content.id)).where(
            Content.workspace_id == workspace_uuid,
            Content.deleted_at == None
        )
    )
    content_count = result.scalar() or 0

    result = await db.execute(
        select(func.count(Website.id)).where(
            Website.workspace_id == workspace_uuid
        )
    )
    web_knowledge_count = result.scalar() or 0
    # ... repeated for KnowledgeFiles, TextKnowledge, WorkspaceMembers
```

---

## Why This Matters (Context & Reasoning)

The `get_workspace_analytics()` method is a high-traffic code path — it fires on every workspace detail page load across 3 different route handlers. With each invocation causing 7 sequential database round-trips, this directly impacts perceived page load speed. For users with high-latency database connections (e.g., multi-region deployments), the cumulative latency of 7 queries is significant.

The DRY violation in `workspace_stats.py` means the same counting logic exists in two places, creating a maintenance burden where any bug fix (like the `== None` vs `.is_(None)` issue) must be applied twice.

---

## Impact

- **Severity:** 5-7 unnecessary database round-trips per workspace detail page load, multiplied across 3 route handlers. For N concurrent users viewing workspace details, this creates 7N queries instead of N.
- **Affected Users/Flows:** Every user viewing workspace detail pages (onboarding dashboard, workspace settings, workspace overview).
- **Blast Radius:** Affects 4 endpoints: `GET /workspace/detail`, `GET /workspace/slug/{slug}`, `GET /workspaces/{id}`, and `GET /workspaces/{id}/stats`.

---

## Recommended Solution

### Step 1: Combine the 5 count queries into a single query using scalar subqueries

```python
# File: src/services/workspace_service.py
# Replace lines 396-428 with:

from sqlalchemy import select, func, case
from sqlalchemy.sql import expression

        # Combine all counts into a single query using scalar subqueries
        web_count_subq = (
            select(func.count(Website.id))
            .where(Website.workspace_id == workspace_id)
            .correlate(None)
            .scalar_subquery()
        )
        files_count_subq = (
            select(func.count(KnowledgeFiles.id))
            .where(KnowledgeFiles.workspace_id == workspace_id)
            .correlate(None)
            .scalar_subquery()
        )
        text_count_subq = (
            select(func.count(TextKnowledge.id))
            .where(TextKnowledge.workspace_id == workspace_id)
            .correlate(None)
            .scalar_subquery()
        )
        members_count_subq = (
            select(func.count(WorkspaceMembers.id))
            .where(WorkspaceMembers.workspace_id == workspace_id)
            .correlate(None)
            .scalar_subquery()
        )
        content_count_subq = (
            select(func.count(Content.id))
            .where(
                Content.workspace_id == workspace_id,
                Content.deleted_at.is_(None),
            )
            .correlate(None)
            .scalar_subquery()
        )

        result = await self.db.execute(
            select(
                web_count_subq.label("web_count"),
                files_count_subq.label("files_count"),
                text_count_subq.label("text_count"),
                members_count_subq.label("members_count"),
                content_count_subq.label("content_count"),
            )
        )
        row = result.one()
        web_count = row.web_count or 0
        files_count = row.files_count or 0
        text_count = row.text_count or 0
        members_count = row.members_count or 0
        content_count = row.content_count or 0
```

### Step 2: Combine the 2 word count queries into a single query

```python
# File: src/services/workspace_service.py
# Replace lines 444-457 with:

        if include_word_counts:
            word_stats_query = select(
                func.coalesce(
                    select(func.sum(Website.word_count))
                    .where(Website.workspace_id == workspace_id)
                    .correlate(None)
                    .scalar_subquery(),
                    0,
                ).label("total_web_words"),
                func.coalesce(
                    select(func.avg(Website.word_count))
                    .where(Website.workspace_id == workspace_id)
                    .correlate(None)
                    .scalar_subquery(),
                    0,
                ).label("avg_web_words"),
                func.coalesce(
                    select(func.sum(KnowledgeFiles.word_count))
                    .where(KnowledgeFiles.workspace_id == workspace_id)
                    .correlate(None)
                    .scalar_subquery(),
                    0,
                ).label("total_file_words"),
                func.coalesce(
                    select(func.avg(KnowledgeFiles.word_count))
                    .where(KnowledgeFiles.workspace_id == workspace_id)
                    .correlate(None)
                    .scalar_subquery(),
                    0,
                ).label("avg_file_words"),
            )
            result = await self.db.execute(word_stats_query)
            word_row = result.one()

            total_web_words = int(word_row.total_web_words)
            avg_web_words = int(word_row.avg_web_words)
            total_file_words = int(word_row.total_file_words)
            avg_file_words = int(word_row.avg_file_words)

            total_words = total_web_words + total_file_words
            estimated_reading_time = total_words // 200

            analytics["content_metrics"] = {
                "total_words": total_words,
                "web_content_words": total_web_words,
                "file_content_words": total_file_words,
                "avg_web_article_words": avg_web_words,
                "avg_file_words": avg_file_words,
                "estimated_reading_time_minutes": estimated_reading_time,
            }
```

### Step 3: Replace duplicate queries in workspace_stats.py with a call to the service method

```python
# File: src/api/routes/workspaces/workspace_stats.py
# Replace lines 49-94 with:

    user_id = user.get("identity")
    await verify_current_user(db, user_id)

    workspace_uuid = UUID(workspace_id)

    # Delegate to service layer instead of inline queries
    from src.services.workspace_service import WorkspaceService
    workspace_service = WorkspaceService(db)
    analytics = await workspace_service.get_workspace_analytics(workspace_uuid)

    content_count = analytics["content_count"]
    knowledge_items_count = analytics["knowledge_stats"]["total"]
    members_count = analytics["members_count"]
```

Also add the import at the top of the file:
```python
# File: src/api/routes/workspaces/workspace_stats.py
# Add to imports (replace direct model imports that are no longer needed):
from src.services.workspace_service import WorkspaceService
```

### Step 4: Fix the `== None` comparison in the original code

This is handled in Step 1 where `Content.deleted_at == None` is replaced with `Content.deleted_at.is_(None)`.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/workspaces/workspace_core.py` | `80, 126, 179` | Three callers of `get_workspace_analytics()` — will benefit from the performance improvement |
| `src/api/routes/workspaces/workspace_stats.py` | `56-94` | Duplicate inline count queries that should delegate to the service method |
| `tests/unit/services/test_workspace_service.py` | `111-120` | Existing unit test for `get_workspace_analytics` — verify still passes after refactor |
| `tests/security/test_tenant_isolation.py` | `515-550` | Tenant isolation test for analytics — verify still passes |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Enable SQLAlchemy query logging by setting `echo=True` on the engine or adding a logging handler for `sqlalchemy.engine`.
2. Call `GET /workspaces/{workspace_id}` for any workspace.
3. Observe 7 separate `SELECT COUNT(...)` queries in the SQL log output (5 count queries + 2 word stat queries).

### After Fix (Verify the Solution):
1. Call `GET /workspaces/{workspace_id}` for the same workspace.
2. Observe only 2 SQL queries in the log: one for all 5 counts (as scalar subqueries), one for word statistics.
3. Verify the response JSON contains the same `knowledge_stats`, `analytics.knowledge_counts`, `analytics.content_metrics`, and `analytics.team_metrics` values as before.
4. Call `GET /workspaces/{workspace_id}/stats` and verify it returns the same counts as before.
5. Test with a workspace that has zero knowledge items, zero content, and zero members to verify `COALESCE` handles nulls correctly.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/services/test_workspace_service.py::TestWorkspaceAnalytics -v
cd rext-backend && python -m pytest tests/security/test_tenant_isolation.py::TestTenantIsolation::test_get_workspace_analytics_only_shows_own_data -v
```

---

## Acceptance Criteria

- [ ] `get_workspace_analytics()` executes at most 2 database queries (1 for counts, 1 for word stats when `include_word_counts=True`)
- [ ] `Content.deleted_at == None` is replaced with `Content.deleted_at.is_(None)`
- [ ] `workspace_stats.py` delegates to `WorkspaceService.get_workspace_analytics()` instead of executing inline queries
- [ ] All analytics response values (counts, word stats, reading time) remain unchanged
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 — Scalar Subqueries](https://docs.sqlalchemy.org/en/20/core/selectable.html#sqlalchemy.sql.expression.ScalarSelect) — documentation on using `.scalar_subquery()` to embed subqueries in a single SELECT
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [SQLAlchemy 2.0 — Using SELECT Statements — Aggregate Functions](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html#aggregate-functions-with-group-by-having) — official tutorial on combining aggregation functions
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-078 (N+1 Query Problem in Pending Invitations from B3) — similar N+1 pattern
