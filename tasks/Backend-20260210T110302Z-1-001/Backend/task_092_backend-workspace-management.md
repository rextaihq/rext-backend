# Task 092: URL Uniqueness Check Compares Wrong Column

## Metadata
- **Task ID:** TASK-092
- **Source:** B4 - Workspace Management (Finding #4 under P0 Critical)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P0 Critical
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

In the `create_workspace_for_user()` method of `src/services/workspace_service.py` (lines 109-113), the URL uniqueness check queries `Website.workspace_id == user_id`. This comparison is semantically wrong: `Website.workspace_id` is a foreign key referencing `workspace.id` (a workspace UUID), but `user_id` is a user UUID from the `users` table. These are entirely different entity types referencing different tables, and they will almost never match.

The intended logic is to check whether the URL already exists across any of the user's workspaces to prevent duplicate URL registrations. The correct query should join `Website` to `WorkspaceModel` and filter by the workspace owner's user ID (`WorkspaceModel.user_id == user_id`), not compare workspace IDs against user IDs.

Because the condition `Website.workspace_id == user_id` will virtually never be true (a workspace UUID will not match a user UUID), the duplicate URL check is **effectively disabled**. The `DuplicateResourceException` on line 115 is dead code that will never execute. Users can create multiple workspaces with the same URL without any detection, potentially causing confusion in the knowledge base and content pipeline.

The `Website` model (defined in `src/api/models/knowledge_models/knowledge_model.py:90-105`) has `workspace_id` as a foreign key to `workspace.id`, confirming that comparing it with a user UUID is incorrect. The workspace-to-user relationship goes through `WorkspaceModel.user_id`.

---

## Current Code

```python
# File: src/services/workspace_service.py
# Lines: 107-120
        with trace(name="Create Workspace Record"):
            # check if the url for same workspace exists in the knowledge base file
            result = await self.db.execute(
                select(Website).where(
                    Website.workspace_id == user_id,  # BUG: Compares workspace FK against user UUID
                    Website.url == url
                )
            )
            if result.scalar_one_or_none():
                raise DuplicateResourceException(
                    message="Workspace with this URL already exists",
                    resource_type="workspace",
                    conflicting_field="url",
                    conflicting_value=url,
                )
```

```python
# File: src/api/models/knowledge_models/knowledge_model.py
# Lines: 90-97 (Website model — workspace_id is FK to workspace.id, NOT to users.id)
class Website(Base, SerializableMixin):
    __tablename__ = "website"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    knowledge_base_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False)

    url = Column(String, nullable=False)
```

---

## Why This Matters (Context & Reasoning)

When a user creates a new workspace, they provide a URL (typically their website). The `create_workspace_for_user` method is supposed to check whether the user already has a workspace with that same URL to prevent accidental duplicates. This is important because the workspace onboarding pipeline scrapes the URL to extract brand voice, personas, and other data — duplicating this across multiple workspaces wastes resources and creates confusing duplicate data.

The URL uniqueness check is the first validation step before workspace creation. With the check effectively disabled, users can repeatedly create workspaces with the same URL, triggering the same pipeline scraping process each time. This could lead to duplicate knowledge base entries, wasted LLM API calls (for brand voice extraction), and user confusion about which workspace corresponds to which site.

Additionally, the soft-delete filter is missing from this query — even if the column comparison were correct, it should also filter `WorkspaceModel.deleted_at.is_(None)` to only check against active workspaces.

---

## Impact

- **Severity:** The URL duplicate detection is completely non-functional. Users can create unlimited workspaces with the same URL, wasting LLM API credits and creating duplicate knowledge base data.
- **Affected Users/Flows:** Workspace creation flow (`POST /workspaces/create` or the workspace creation pipeline).
- **Blast Radius:** Isolated to workspace creation, but affects downstream knowledge base and brand voice data quality.

---

## Recommended Solution

### Step 1: Fix the URL uniqueness query with proper join

```python
# File: src/services/workspace_service.py
# Replace lines 108-120 with:
            # Check if the URL already exists across any of this user's active workspaces
            result = await self.db.execute(
                select(Website)
                .join(WorkspaceModel, WorkspaceModel.id == Website.workspace_id)
                .where(
                    WorkspaceModel.user_id == user_id,
                    WorkspaceModel.deleted_at.is_(None),
                    Website.url == url,
                )
            )
            if result.scalar_one_or_none():
                raise DuplicateResourceException(
                    message="You already have a workspace with this URL",
                    resource_type="workspace",
                    conflicting_field="url",
                    conflicting_value=url,
                )
```

### Step 2: Remove the now-inaccurate inline comment

The comment on line 108 (`# check if the url for same workspace exists in the knowledge base file`) is misleading — it's checking across all of the user's workspaces, not within a single workspace. Update to:

```python
            # Check if user already has a workspace with this URL
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/workspace_service.py` | `191-260` | `refresh_brand_voice_for_user()` — does not check for URL duplicates before refresh, but this is acceptable since it operates on an existing workspace |
| `src/api/routes/workspaces/workspace_core.py` | N/A | The route handler for workspace creation delegates to this service method — no changes needed in the route |
| `src/api/routes/workspaces/workspace_route.py` | N/A | Legacy route may also create workspaces — verify it uses the same service method |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a workspace with URL `https://example.com` via the API
2. Wait for pipeline to complete
3. Create a second workspace with the same URL `https://example.com`
4. Observe that the second workspace is created successfully (no duplicate error)
5. Query the database: `SELECT w.name, ws.url FROM workspace w JOIN website ws ON ws.workspace_id = w.id WHERE w.user_id = '<user_id>'` — both workspaces have the same URL

### After Fix (Verify the Solution):
1. Create a workspace with URL `https://example.com`
2. Wait for pipeline to complete
3. Attempt to create a second workspace with URL `https://example.com`
4. Observe HTTP 409 error with `DuplicateResourceException`: "You already have a workspace with this URL"
5. Create a workspace with a different URL `https://other-site.com` — should succeed
6. Soft-delete the first workspace, then attempt to create a new workspace with `https://example.com` — should succeed (deleted workspace is excluded)

### Edge Cases:
- URL with trailing slash vs without (e.g., `https://example.com/` vs `https://example.com`) — consider normalizing
- Different users with the same URL — should be allowed (each user can have their own workspace for the same site)
- URL check after workspace soft-delete — deleted workspaces should not block new ones

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "workspace and create"
```

---

## Acceptance Criteria

- [ ] URL uniqueness query joins `Website` to `WorkspaceModel` via `workspace_id`
- [ ] Query filters by `WorkspaceModel.user_id == user_id` (not `Website.workspace_id == user_id`)
- [ ] Query excludes soft-deleted workspaces via `WorkspaceModel.deleted_at.is_(None)`
- [ ] `DuplicateResourceException` fires correctly when a user's existing active workspace has the same URL
- [ ] Different users can create workspaces with the same URL
- [ ] Soft-deleted workspaces do not block new workspace creation with the same URL
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 — Joins](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html#explicit-from-clauses-and-joins)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [SQLAlchemy 2.0 — ORM Querying Guide](https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** TASK-090 (Missing Soft-Delete Filter — the soft-delete filter pattern should be consistent with TASK-090's approach)
- **Blocks:** None
- **Related:** None
