# Task 107: Add Pagination to Workspace List Endpoints

## Metadata
- **Task ID:** TASK-107
- **Source:** Backend Workspace Management Audit (Finding #19 under P2 Medium)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P2 Medium
- **Category:** performance
- **Effort Estimate:** medium (1-4 hours)

---

## Description

Several workspace list endpoints return all records without pagination parameters, meaning every query fetches the complete dataset regardless of size. As the application grows and workspaces accumulate more members, personas, and knowledge items, these unbounded queries will cause progressively slower responses, higher memory consumption, and increased database load.

The affected endpoints are:

1. **`GET /workspace/all`** (`workspace_core.py:35-50`) — Lists all workspaces for the current user. While most users have a small number of workspaces (< 20), there is no upper bound enforced at the API level. The service method `get_user_workspaces()` in `workspace_service.py:299-378` fetches all results with a complex join query involving 4 outer joins across 5 tables. Without pagination, this query scales linearly with workspace count.

2. **`GET /{workspace_id}/members`** (`workspace_members.py:147-176`) — Lists all members of a workspace. Enterprise workspaces could have hundreds of members. The `MemberService.get_workspace_members_with_users()` method returns all rows, and the route serializes every member with user details and role information. Each member requires a join across `WorkspaceMembers`, `Users`, and `Role` tables.

3. **`GET /{workspace_id}/personas`** (`workspace_personas.py:20-52`) — Lists all personas for a workspace. While persona counts are typically small (< 20), the endpoint still lacks any pagination controls. The query at line 42-46 fetches all personas ordered by `created_at DESC` with no limit.

4. **`GET /{workspace_id}/stats`** (`workspace_stats.py:25-119`) — Returns aggregate counts, not a list, so pagination doesn't apply in the traditional sense. However, this endpoint was noted in the audit as lacking pagination on any endpoint. Since stats returns aggregates, no pagination is needed here — this is a false positive for this specific endpoint.

FastAPI recommends using `Query` parameters with defaults for pagination. The standard pattern is `skip: int = 0, limit: int = 50` or `page: int = 1, page_size: int = 50`, with the response including `total_count` so the frontend can calculate total pages.

---

## Current Code

```python
# File: src/api/routes/workspaces/workspace_core.py
# Lines: 35-50
@router.get("/all")
@require_permissions("workspace.read", workspace_scoped=False)
@db_transaction_handler("get workspaces", auto_commit=False)
async def get_workspaces(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    # Use workspace service
    workspace_service = WorkspaceService(db)
    workspace_data = await workspace_service.get_user_workspaces(UUID(user_id))

    # Return raw data - decorator handles success response
    return {"workspaces": workspace_data, "total_count": len(workspace_data)}
```

```python
# File: src/api/routes/workspaces/workspace_members.py
# Lines: 147-176
@router.get(
    "/{workspace_id}/members",
    summary="List workspace members",
)
@require_permissions("member.read", workspace_scoped=True)
@db_transaction_handler("get workspace members", auto_commit=False)
async def list_workspace_members(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Return the members for the given workspace."""
    user_id = user.get("identity")
    await verify_current_user(db, user_id)
    workspace, _membership = await resolve_and_verify_workspace(
        db, workspace_id, UUID(user_id)
    )

    # Get members with user details via service
    member_service = MemberService(db)
    rows = await member_service.get_workspace_members_with_users(workspace.id)

    members = [_serialize_member(member, user, role) for member, user, role in rows]

    return success(
        data={"members": members, "total_count": len(members)},
        request=request,
        message=f"Retrieved {len(members)} member(s)",
    )
```

```python
# File: src/api/routes/workspaces/workspace_personas.py
# Lines: 20-52
@router.get("/{workspace_id}/personas")
@db_transaction_handler("get workspace personas", auto_commit=False)
@require_permissions("workspace.read", workspace_scoped=True)
async def get_workspace_personas(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Get all personas for a workspace."""
    user_id = UUID(str(user.get("identity")))
    await verify_current_user(db, str(user_id))

    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, user_id)

    result = await db.execute(
        select(Persona)
        .where(Persona.workspace_id == workspace.id)
        .order_by(Persona.created_at.desc())
    )
    personas = result.scalars().all()

    return {
        "personas": [p.to_dict() for p in personas],
        "total_count": len(personas)
    }
```

---

## Why This Matters (Context & Reasoning)

These endpoints are called frequently during normal application usage:
- **Workspace list** is loaded on the dashboard and workspace selector dropdown
- **Members list** is loaded on the workspace settings page for member management
- **Personas list** is loaded on the workspace brand voice settings page

Without pagination, the frontend receives the entire dataset on every page load. For workspaces with many members (enterprise use case), the members endpoint could return hundreds of records, each with serialized user and role data. This causes:
1. Slow API response times proportional to member count
2. High memory usage on the server (all ORM objects loaded simultaneously)
3. Large HTTP response payloads sent to the client
4. Frontend rendering performance issues with large lists

The risk of not fixing this is that API response times degrade as the application scales, eventually requiring emergency optimization under pressure.

---

## Impact

- **Severity:** Performance degrades linearly with data growth. Enterprise workspaces with 100+ members will see noticeably slow member list responses.
- **Affected Users/Flows:** Dashboard (workspace list), workspace settings (members, personas), any admin interface listing workspace data.
- **Blast Radius:** Affects 3 list endpoints. The members endpoint has the highest risk due to potentially large datasets.

---

## Recommended Solution

### Step 1: Add pagination parameters to the workspace list endpoint

```python
# File: src/api/routes/workspaces/workspace_core.py
# Replace lines 35-50 with:
@router.get("/all")
@require_permissions("workspace.read", workspace_scoped=False)
@db_transaction_handler("get workspaces", auto_commit=False)
async def get_workspaces(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    # Use workspace service
    workspace_service = WorkspaceService(db)
    workspace_data = await workspace_service.get_user_workspaces(
        UUID(user_id), skip=skip, limit=limit
    )
    total_count = await workspace_service.count_user_workspaces(UUID(user_id))

    # Return raw data - decorator handles success response
    return {
        "workspaces": workspace_data,
        "total_count": total_count,
        "skip": skip,
        "limit": limit,
    }
```

### Step 2: Update `WorkspaceService.get_user_workspaces()` to accept pagination

```python
# File: src/services/workspace_service.py
# Replace the method signature at line 299:
    async def get_user_workspaces(
        self, user_id: UUID, skip: int = 0, limit: int = 50
    ) -> List[Dict[str, Any]]:
```

```python
# File: src/services/workspace_service.py
# Add .offset().limit() to the query before execution.
# Replace line 334 (the group_by line) and add offset/limit after it:
            .group_by(WorkspaceModel.id, Users.id)
            .offset(skip)
            .limit(limit)
        )
```

### Step 3: Add pagination to the members list endpoint

```python
# File: src/api/routes/workspaces/workspace_members.py
# Replace the function signature at lines 153-158:
async def list_workspace_members(
    workspace_id: str,
    request: Request,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
```

The `MemberService.get_workspace_members_with_users()` method should also accept `skip` and `limit` parameters. Update the service call:

```python
# File: src/api/routes/workspaces/workspace_members.py
# Replace lines 167-175:
    # Get members with user details via service
    member_service = MemberService(db)
    rows = await member_service.get_workspace_members_with_users(
        workspace.id, skip=skip, limit=limit
    )
    total_count = await member_service.count_workspace_members(workspace.id)

    members = [_serialize_member(member, usr, role) for member, usr, role in rows]

    return success(
        data={
            "members": members,
            "total_count": total_count,
            "skip": skip,
            "limit": limit,
        },
        request=request,
        message=f"Retrieved {len(members)} member(s)",
    )
```

### Step 4: Add pagination to the personas list endpoint

```python
# File: src/api/routes/workspaces/workspace_personas.py
# Replace the function signature at lines 23-28:
async def get_workspace_personas(
    workspace_id: str,
    request: Request,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
```

```python
# File: src/api/routes/workspaces/workspace_personas.py
# Replace lines 42-52 with:
    # Count total personas
    count_result = await db.execute(
        select(func.count(Persona.id))
        .where(Persona.workspace_id == workspace.id)
    )
    total_count = count_result.scalar() or 0

    # Fetch paginated personas
    result = await db.execute(
        select(Persona)
        .where(Persona.workspace_id == workspace.id)
        .order_by(Persona.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    personas = result.scalars().all()

    return {
        "personas": [p.to_dict() for p in personas],
        "total_count": total_count,
        "skip": skip,
        "limit": limit,
    }
```

### Step 5: Add `func` import to `workspace_personas.py`

```python
# File: src/api/routes/workspaces/workspace_personas.py
# Update line 5 to include func:
from sqlalchemy import select, func
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/member_service.py` | N/A | `get_workspace_members_with_users()` needs `skip`/`limit` params added; a new `count_workspace_members()` method is needed |
| `src/api/routes/workspaces/__init__.py` | 102-135 | RESTful wrapper routes (`GET /workspaces/`) — may need pagination params forwarded if they proxy to the same service methods |
| `src/api/routes/workspaces/workspace_route.py` | 28, 48 | Legacy routes that also list workspaces — should be updated for consistency if still active |
| `rext-admin/` | N/A | Frontend API client will need to pass `skip`/`limit` parameters and handle paginated responses |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a workspace with 100+ members (via direct DB inserts or API)
2. Call `GET /api/v1/workspaces/{workspace_id}/members`
3. Observe that all 100+ members are returned in a single response
4. Note the response time — it will be proportional to member count

### After Fix (Verify the Solution):
1. Call `GET /api/v1/workspaces/{workspace_id}/members?skip=0&limit=10`
2. Verify only 10 members are returned
3. Verify `total_count` in response reflects the actual total (100+)
4. Call with `skip=10&limit=10` — verify the next 10 members are returned
5. Call without `skip`/`limit` params — verify defaults apply (skip=0, limit=50)
6. Test with `limit=0` — should return empty list with correct `total_count`
7. Test with `skip` > total_count — should return empty list

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "workspace" -v
```

---

## Acceptance Criteria

- [ ] `GET /workspace/all` accepts `skip` and `limit` query parameters with defaults (0 and 50)
- [ ] `GET /{workspace_id}/members` accepts `skip` and `limit` query parameters
- [ ] `GET /{workspace_id}/personas` accepts `skip` and `limit` query parameters
- [ ] All paginated responses include `total_count`, `skip`, and `limit` in the response body
- [ ] Default behavior (no params) returns first 50 items
- [ ] Queries use `.offset()` and `.limit()` at the database level
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Query Parameters](https://fastapi.tiangolo.com/tutorial/query-params/) — shows how to define optional query parameters with defaults
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Pagination Patterns](https://fastapi.tiangolo.com/tutorial/query-params/#defaults) — FastAPI query parameters with default values for skip/limit pattern
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-094 (B4: N+1 Queries in `get_workspace_analytics()` — performance optimization in the same area), TASK-078 (B3: N+1 Query Problem in Pending Invitations — similar pagination need)
