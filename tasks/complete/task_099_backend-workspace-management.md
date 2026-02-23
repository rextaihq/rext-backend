# Task 099: Stats Route Duplicates Analytics Logic Already in Service Layer

## Metadata
- **Task ID:** TASK-099
- **Source:** B4 - Workspace Management (Finding #7 under P1 High)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P1 High
- **Category:** code-quality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `workspace_stats.py` route handler (`GET /{workspace_id}/stats`) executes 4 separate inline database count queries directly in the route layer (lines 56-94) to compute workspace statistics: content count, web knowledge count, files count, text knowledge count, and members count. This logic is a near-exact duplicate of `WorkspaceService.get_workspace_analytics()` in `src/services/workspace_service.py` (lines 396-428), which performs the same 5 count queries for the same models with the same filters.

This violates the project's own stated architecture — the docstring in `workspace_service.py` (line 13) explicitly says routes should **not** contain business logic, yet the stats route bypasses the service layer entirely and queries the database directly. The duplication means any bug fix or optimization applied to `get_workspace_analytics()` (such as combining the 5 queries into a single aggregated query per TASK-094) would need to be manually replicated in `workspace_stats.py`. There is already a divergence: the service method counts `Content` items with a `deleted_at == None` filter (line 425), while the stats route also does this (line 59), but if either changes, the other won't follow.

Additionally, the stats route uses `Content.deleted_at == None` (Python `==` comparison with `None`) instead of the SQLAlchemy-idiomatic `.is_(None)`, which is a lint issue that produces a SAWarning in newer SQLAlchemy versions. The service layer has the same issue on line 425.

The stats route also adds subscription/feature-check logic (lines 97-109) on top of the analytics counts. This subscription check is legitimate and separate from the analytics, but the count queries should delegate to the existing service method rather than duplicating them.

---

## Current Code

```python
# File: rext-backend/src/api/routes/workspaces/workspace_stats.py
# Lines: 56-94
    # Count content items (non-deleted)
    result = await db.execute(
        select(func.count(Content.id)).where(
            Content.workspace_id == workspace_uuid,
            Content.deleted_at == None
        )
    )
    content_count = result.scalar() or 0

    # Count knowledge items (all types combined)
    result = await db.execute(
        select(func.count(Website.id)).where(
            Website.workspace_id == workspace_uuid
        )
    )
    web_knowledge_count = result.scalar() or 0

    result = await db.execute(
        select(func.count(KnowledgeFiles.id)).where(
            KnowledgeFiles.workspace_id == workspace_uuid
        )
    )
    files_count = result.scalar() or 0

    result = await db.execute(
        select(func.count(TextKnowledge.id)).where(
            TextKnowledge.workspace_id == workspace_uuid
        )
    )
    text_knowledge_count = result.scalar() or 0

    knowledge_items_count = web_knowledge_count + files_count + text_knowledge_count

    # Count workspace members
    result = await db.execute(
        select(func.count(WorkspaceMembers.id)).where(
            WorkspaceMembers.workspace_id == workspace_uuid
        )
    )
    members_count = result.scalar() or 0
```

---

## Why This Matters (Context & Reasoning)

The stats endpoint powers the workspace onboarding dashboard and displays real-time counts of content, knowledge items, and team members. It is called frequently during the onboarding flow when users first set up their workspace. The `WorkspaceService.get_workspace_analytics()` method serves the same data for workspace detail pages via 3 different route handlers in `workspace_core.py`.

Having two separate codepaths for the same data means:
1. **Bug fixes applied to one location may miss the other.** If TASK-094 (N+1 query optimization) consolidates the analytics queries in the service, the stats route will still have 4 separate queries.
2. **The service layer abstraction is violated.** Routes importing and querying ORM models directly bypasses the service boundary, making it harder to add caching, audit logging, or other cross-cutting concerns.
3. **The stats response uses different field names** (`content_count`, `knowledge_items_count`, `members_count`) than the analytics response (`knowledge_stats.total`, `members_count`, `content_count`), creating inconsistency for frontend consumers.

---

## Impact

- **Severity:** Any optimization or bug fix to analytics counts must be applied in two separate locations. If missed, stats and workspace detail pages will show different numbers for the same workspace.
- **Affected Users/Flows:** Workspace onboarding dashboard, workspace detail pages.
- **Blast Radius:** Moderate — affects consistency of data displayed across multiple workspace UI views.

---

## Recommended Solution

Replace the inline queries in `workspace_stats.py` with a call to `WorkspaceService.get_workspace_analytics()`, then map the response to the stats format. Keep the subscription/feature check logic in the route.

### Step 1: Refactor the stats route to delegate to the service layer

```python
# File: rext-backend/src/api/routes/workspaces/workspace_stats.py
# Replace the entire file with:
"""
Workspace Stats Routes - Onboarding & Dashboard Statistics

Provides real-time statistics for workspace onboarding tracking and dashboard.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.workspace_service import WorkspaceService
from src.services.subscription_service import SubscriptionService
from src.utils.auth_utils import verify_current_user
from src.utils.route_decorators import db_transaction_handler, require_permissions

router = APIRouter()


@router.get("/{workspace_id}/stats")
@require_permissions("workspace.read", workspace_scoped=True)
@db_transaction_handler("get workspace stats", auto_commit=False)
async def get_workspace_stats(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Get workspace statistics for onboarding tracking and dashboard.

    Returns real-time counts for:
    - Content items
    - Knowledge base items
    - Team members
    - Feature availability (content builder)

    Args:
        workspace_id: Workspace UUID (path parameter)

    Returns:
        Statistics object with all counts
    """
    user_id = user.get("identity")
    await verify_current_user(db, user_id)

    workspace_uuid = UUID(workspace_id)

    # Delegate analytics to the service layer (single source of truth)
    workspace_service = WorkspaceService(db)
    analytics = await workspace_service.get_workspace_analytics(workspace_uuid)

    # Check feature availability from user's subscription
    subscription_service = SubscriptionService(db)
    user_subscription = await subscription_service.get_subscription_by_user(UUID(user_id))

    # Default to True if no subscription (free tier) or if plan doesn't specify
    has_content_builder = True

    if user_subscription and user_subscription.plan:
        plan_features = user_subscription.plan.features or {}

        # Check if features are explicitly set to False (disabled)
        # If not set, default to True (enabled)
        if 'content_builder' in plan_features:
            has_content_builder = bool(plan_features.get('content_builder'))

    stats = {
        "workspace_exists": True,
        "content_count": analytics["content_count"],
        "knowledge_items_count": analytics["knowledge_stats"]["total"],
        "members_count": analytics["members_count"],
        "has_content_builder": has_content_builder,
    }

    return stats
```

### Step 2: Remove unused imports from workspace_stats.py

The refactored version above already removes the unused imports (`select`, `func`, `Content`, `Website`, `KnowledgeFiles`, `TextKnowledge`, `WorkspaceMembers`, `success`). No additional import cleanup is needed since the new file only imports what it uses.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/services/workspace_service.py` | `396-428` | The canonical `get_workspace_analytics()` method — this is the source of truth that stats should delegate to |
| `rext-backend/src/api/routes/workspaces/workspace_core.py` | `80-95, 125-141, 178-194` | Three route handlers that already call `get_workspace_analytics()` — these demonstrate the correct pattern |
| `rext-backend/src/services/workspace_service.py` | `425` | Uses `Content.deleted_at == None` instead of `.is_(None)` — same lint issue as the stats route |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Identify that `workspace_stats.py` contains inline count queries by reading lines 56-94.
2. Compare these queries to `workspace_service.py` lines 396-428 — they perform identical operations.
3. Note that the stats route imports 5 ORM models directly (`Content`, `Website`, `KnowledgeFiles`, `TextKnowledge`, `WorkspaceMembers`).

### After Fix (Verify the Solution):
1. Call `GET /workspaces/{workspace_id}/stats` and verify the response still contains `workspace_exists`, `content_count`, `knowledge_items_count`, `members_count`, and `has_content_builder`.
2. Call `GET /workspace/detail?workspace_id={id}` and verify the analytics counts match the stats endpoint for the same workspace.
3. Create a content item in the workspace and verify both endpoints reflect the updated count.
4. Verify the stats route no longer imports any ORM models directly.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "workspace" -v
```

---

## Acceptance Criteria

- [ ] `workspace_stats.py` no longer contains any direct database count queries
- [ ] `workspace_stats.py` delegates to `WorkspaceService.get_workspace_analytics()` for all analytics data
- [ ] The stats endpoint response format remains unchanged (`workspace_exists`, `content_count`, `knowledge_items_count`, `members_count`, `has_content_builder`)
- [ ] Stats endpoint and workspace detail endpoint return consistent counts for the same workspace
- [ ] Subscription/feature check logic is preserved in the route layer
- [ ] No ORM model imports remain in `workspace_stats.py` (only service imports)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Bigger Applications - Multiple Files](https://fastapi.tiangolo.com/tutorial/bigger-applications/) — demonstrates proper separation between routes and business logic
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Best Practices - zhanymkanov](https://github.com/zhanymkanov/fastapi-best-practices) — recommends keeping routes thin and delegating to services
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None (can be done independently, but coordinating with TASK-094 is recommended)
- **Blocks:** None
- **Related:** TASK-094 (N+1 Queries in `get_workspace_analytics()`), TASK-100 (Analytics Assembly Code Copy-Pasted 3 Times)
