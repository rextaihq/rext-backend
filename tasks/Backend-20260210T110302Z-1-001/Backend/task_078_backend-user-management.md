# Task 078: N+1 Query Problem in Pending Invitations

## Metadata
- **Task ID:** TASK-078
- **Source:** B3 - User Management (Finding #17 under P2 Medium)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P2 Medium
- **Category:** performance
- **Effort Estimate:** medium (2-4 hours)

---

## Description

The `get_pending_invitations` endpoint in `src/api/routes/users/invitations.py` (lines 40-209) exhibits a classic N+1 query problem. After fetching the current user (1 query) and all pending invitations for that user's email (1 query), the code enters a `for` loop (line 134) where each iteration issues 3 separate database queries: one to fetch workspace details via `WorkspaceModel` (line 142), one to fetch role details via `Role` (line 157), and one to fetch inviter details via `Users` (line 163). For N pending invitations, the endpoint executes 3N+2 total queries (2 initial queries plus 3 per invitation).

With 10 pending invitations, this produces 32 database queries. With 50 invitations, it produces 152. Each query incurs a full async round-trip to PostgreSQL via asyncpg, consumes a connection from the pool, and adds serialization/deserialization overhead. This entire workload can be replaced with a single joined query or at most 4 total queries using SQLAlchemy eager loading strategies. The `UserInvitations` model already defines `relationship()` attributes for `workspace`, `role`, and `invited_by` (lines 28-30 of `src/api/models/user_models/invitations.py`), which means both `selectinload()` and `joinedload()` can be applied directly to the existing query without any model changes.

---

## Current Code

```python
# File: src/api/routes/users/invitations.py
# Lines: 116-191 (query construction and the N+1 loop)

    # Query pending invitations for this email
    query = (
        select(UserInvitations)
        .where(
            and_(
                UserInvitations.email == user_email,
                UserInvitations.status == "pending"
            )
        )
        .order_by(UserInvitations.created_at.desc())
    )

    result = await db.execute(query)
    invitations = result.scalars().all()

    # Build response with workspace, role, and inviter details
    invitation_list = []

    for invitation in invitations:
        # Skip expired invitations (and auto-update status)
        if is_invitation_expired(invitation):
            invitation.status = "expired"
            await db.flush()
            continue

        # Get workspace details — N+1 QUERY #1
        workspace_result = await db.execute(
            select(WorkspaceModel).where(
                and_(
                    WorkspaceModel.id == invitation.workspace_id,
                    WorkspaceModel.deleted_at.is_(None)
                )
            )
        )
        workspace = workspace_result.scalar_one_or_none()

        # Skip if workspace is deleted
        if not workspace:
            continue

        # Get role details — N+1 QUERY #2
        role_result = await db.execute(
            select(Role).where(Role.id == invitation.role_id)
        )
        role = role_result.scalar_one_or_none()

        # Get inviter details — N+1 QUERY #3
        inviter_result = await db.execute(
            select(Users).where(Users.id == invitation.invited_by_user_id)
        )
        inviter = inviter_result.scalar_one_or_none()

        # Build invitation data
        invitation_data = {
            "id": str(invitation.id),
            "workspace": {
                "id": str(workspace.id),
                "name": workspace.name,
                "slug": workspace.slug
            },
            "role": {
                "id": str(role.id),
                "name": role.name,
                "display_name": role.display_name
            } if role else None,
            "invited_by": {
                "id": str(inviter.id),
                "name": f"{inviter.first_name} {inviter.last_name}".strip() or inviter.username,
                "email": inviter.email
            } if inviter else None,
            "token": invitation.invitation_token,
            "expires_at": invitation.expires_at.isoformat() if invitation.expires_at else None,
            "created_at": invitation.created_at.isoformat() if invitation.created_at else None
        }

        invitation_list.append(invitation_data)
```

```python
# File: src/api/models/user_models/invitations.py
# Lines: 27-31 (relationship definitions — these already exist)
    # Relationships
    workspace = relationship("WorkspaceModel", foreign_keys=[workspace_id], back_populates="invitations")
    role = relationship("Role", foreign_keys=[role_id], back_populates="invited_roles")
    invited_by = relationship("Users", foreign_keys=[invited_by_user_id], back_populates="sent_invitations")
    workspace_members = relationship("WorkspaceMembers", back_populates="invitation")
```

---

## Why This Matters (Context & Reasoning)

The pending invitations endpoint (`GET /api/v1/user/invitations/pending`) is invoked from the dashboard invitation widget, the notification badge component, and the invitation prompts on login. It is a high-frequency endpoint that fires on every authenticated page load for users who have pending invitations. Linear query growth means that a user with a modest number of invitations (10-20) triggers dozens of database round-trips per request.

Under concurrent load, the problem compounds. If 100 users each have 10 pending invitations and hit the endpoint simultaneously, that generates 3,200 queries in a short burst. The async connection pool (typically sized at 10-20 connections) can become saturated, causing other endpoints to queue or timeout. Since each individual query is small and fast, database-side metrics (CPU, I/O) may appear normal, making this a silent performance issue that manifests as intermittent latency spikes at the application layer.

SQLAlchemy provides two standard strategies for solving N+1 queries: `joinedload()` (uses SQL JOINs to fetch related objects in a single query) and `selectinload()` (issues a separate IN query per relationship). For async sessions, `selectinload()` is generally preferred because it avoids implicit lazy loading that can trigger `MissingGreenlet` errors and produces simpler SQL that is easier to debug. However, for many-to-one relationships like these (each invitation has exactly one workspace, one role, and one inviter), `joinedload()` is efficient and produces no Cartesian product risk.

Both approaches are viable here because the `UserInvitations` model already defines all three `relationship()` attributes. An alternative approach using explicit JOINs (without relying on relationships) is also provided below for maximum flexibility.

---

## Impact

- **Severity:** Performance degrades linearly with invitation count. 10 invitations produce 32 queries instead of 2-4. 50 invitations produce 152 queries. Under concurrent load, this can exhaust the async database connection pool and cause latency spikes across all endpoints.
- **Affected Users/Flows:** Every authenticated user who views their dashboard, checks the notification badge, or opens the invitations page. The endpoint fires on every page load for users with pending invitations.
- **Blast Radius:** Isolated to the `get_pending_invitations` endpoint in `src/api/routes/users/invitations.py` (lines 116-191). The fix does not affect the `decline_invitation` endpoint or any other route.

---

## Recommended Solution

Two approaches are provided. **Approach A** (recommended) uses `selectinload()` with the existing relationship definitions. **Approach B** uses explicit JOINs with a multi-entity `select()` and does not depend on relationship definitions at all.

### Approach A: Use `selectinload()` with existing relationships (Recommended)

This approach leverages the existing `relationship()` attributes on `UserInvitations` and issues 4 total queries (1 for invitations + 1 IN query per relationship) regardless of invitation count. `selectinload()` is preferred over `joinedload()` for async sessions because it avoids `MissingGreenlet` errors that can occur when lazily-loaded attributes are accessed outside the original query context.

#### Step 1: Add the `selectinload` import

```python
# File: src/api/routes/users/invitations.py
# Add to imports (around line 14):
from sqlalchemy.orm import selectinload
```

#### Step 2: Replace the query and loop (lines 116-191)

```python
# File: src/api/routes/users/invitations.py
# Replace lines 116-191 with:

    # Query pending invitations with eager-loaded relationships (4 queries total)
    query = (
        select(UserInvitations)
        .options(
            selectinload(UserInvitations.workspace),
            selectinload(UserInvitations.role),
            selectinload(UserInvitations.invited_by),
        )
        .where(
            and_(
                UserInvitations.email == user_email,
                UserInvitations.status == "pending"
            )
        )
        .order_by(UserInvitations.created_at.desc())
    )

    result = await db.execute(query)
    invitations = result.scalars().all()

    # Build response from eagerly-loaded results
    invitation_list = []

    for invitation in invitations:
        # Skip expired invitations (and auto-update status)
        if is_invitation_expired(invitation):
            invitation.status = "expired"
            await db.flush()
            continue

        # Workspace is already loaded — filter out deleted workspaces
        workspace = invitation.workspace
        if not workspace or workspace.deleted_at is not None:
            continue

        role = invitation.role
        inviter = invitation.invited_by

        invitation_data = {
            "id": str(invitation.id),
            "workspace": {
                "id": str(workspace.id),
                "name": workspace.name,
                "slug": workspace.slug
            },
            "role": {
                "id": str(role.id),
                "name": role.name,
                "display_name": role.display_name
            } if role else None,
            "invited_by": {
                "id": str(inviter.id),
                "name": inviter.full_name or inviter.display_name or inviter.email,
                "email": inviter.email
            } if inviter else None,
            "token": invitation.invitation_token,
            "expires_at": invitation.expires_at.isoformat() if invitation.expires_at else None,
            "created_at": invitation.created_at.isoformat() if invitation.created_at else None
        }

        invitation_list.append(invitation_data)
```

**Key differences from the original:**
- `selectinload()` options eagerly load all three relationships in 3 additional IN queries (fired automatically by SQLAlchemy when the main query executes)
- The loop accesses `invitation.workspace`, `invitation.role`, and `invitation.invited_by` directly (no per-row queries)
- The `deleted_at` check for workspaces moves from the SQL WHERE clause to a Python-side filter since `selectinload` loads the workspace unconditionally
- The inviter name uses `inviter.full_name or inviter.display_name or inviter.email` (correct `Users` model attributes per TASK-062)

### Approach B: Use explicit JOINs (no relationship dependency)

This approach does not rely on `relationship()` definitions and produces a single SQL query with JOINs. Use this if you prefer full control over the SQL or if relationships are ever removed.

#### Step 1: Replace the query and loop (lines 116-191)

```python
# File: src/api/routes/users/invitations.py
# Replace lines 116-191 with:

    # Single query with explicit JOINs (1 query total for all data)
    query = (
        select(
            UserInvitations,
            WorkspaceModel,
            Role,
            Users
        )
        .join(
            WorkspaceModel,
            and_(
                WorkspaceModel.id == UserInvitations.workspace_id,
                WorkspaceModel.deleted_at.is_(None)
            )
        )
        .outerjoin(Role, Role.id == UserInvitations.role_id)
        .outerjoin(Users, Users.id == UserInvitations.invited_by_user_id)
        .where(
            and_(
                UserInvitations.email == user_email,
                UserInvitations.status == "pending"
            )
        )
        .order_by(UserInvitations.created_at.desc())
    )

    result = await db.execute(query)
    rows = result.all()

    # Build response from joined results
    invitation_list = []

    for invitation, workspace, role, inviter in rows:
        # Skip expired invitations (and auto-update status)
        if is_invitation_expired(invitation):
            invitation.status = "expired"
            await db.flush()
            continue

        invitation_data = {
            "id": str(invitation.id),
            "workspace": {
                "id": str(workspace.id),
                "name": workspace.name,
                "slug": workspace.slug
            },
            "role": {
                "id": str(role.id),
                "name": role.name,
                "display_name": role.display_name
            } if role else None,
            "invited_by": {
                "id": str(inviter.id),
                "name": inviter.full_name or inviter.display_name or inviter.email,
                "email": inviter.email
            } if inviter else None,
            "token": invitation.invitation_token,
            "expires_at": invitation.expires_at.isoformat() if invitation.expires_at else None,
            "created_at": invitation.created_at.isoformat() if invitation.created_at else None
        }

        invitation_list.append(invitation_data)
```

**Key differences from Approach A:**
- Uses `select(UserInvitations, WorkspaceModel, Role, Users)` multi-entity select instead of relationship loading
- INNER JOIN on `WorkspaceModel` filters out deleted workspaces at the SQL level (more efficient)
- OUTER JOINs on `Role` and `Users` allow for null role/inviter
- Result is unpacked as a tuple `(invitation, workspace, role, inviter)` instead of accessed via relationship attributes
- Produces exactly 1 SQL query instead of 4

**Trade-off:** Approach A is more idiomatic SQLAlchemy and keeps the existing code structure closer to the original. Approach B produces fewer queries (1 vs 4) and filters deleted workspaces at the database level, but requires tuple unpacking and more manual SQL construction.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/models/user_models/invitations.py` | 28-30 | `UserInvitations` model relationship definitions (`workspace`, `role`, `invited_by`) used by Approach A |
| `src/api/models/workspace_models/workspace_model.py` | 30 | `WorkspaceModel.invitations` back_populates relationship |
| `src/api/models/user_models/roles.py` | 34 | `Role.invited_roles` back_populates relationship |
| `src/api/models/user_models/users.py` | 47 | `Users.sent_invitations` back_populates relationship |
| `src/api/routes/users/invitations.py` | 183 | `inviter.first_name`/`last_name`/`username` bug — must be fixed in this task or coordinated with TASK-062 |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create 10+ pending invitations for a test user across different workspaces:
   ```bash
   # As various workspace admins, invite the same email
   curl -X POST http://localhost:8000/api/v1/workspaces/<workspace-id>/invitations \
     -H "Authorization: Bearer <admin-token>" \
     -H "Content-Type: application/json" \
     -d '{"email": "testuser@example.com", "role_id": "<role-id>"}'
   ```
2. Enable SQLAlchemy query logging by setting `echo=True` on the async engine or setting the `SQLALCHEMY_ECHO=true` environment variable.
3. As the invited user, fetch pending invitations:
   ```bash
   curl -X GET http://localhost:8000/api/v1/user/invitations/pending \
     -H "Authorization: Bearer <invited-user-token>"
   ```
4. Count the number of SQL queries logged. Expect 32+ queries for 10 invitations (2 initial + 3 per invitation).

### After Fix (Verify the Solution):
1. Repeat the same request with 10+ pending invitations.
2. Count SQL queries in the logs:
   - **Approach A:** Expect 5 queries (1 user lookup + 1 invitations + 1 IN for workspaces + 1 IN for roles + 1 IN for inviters).
   - **Approach B:** Expect 2 queries (1 user lookup + 1 joined query).
3. Verify the response JSON structure is identical to the previous format:
   ```json
   {
     "data": {
       "invitations": [
         {
           "id": "...",
           "workspace": { "id": "...", "name": "...", "slug": "..." },
           "role": { "id": "...", "name": "...", "display_name": "..." },
           "invited_by": { "id": "...", "name": "...", "email": "..." },
           "token": "...",
           "expires_at": "...",
           "created_at": "..."
         }
       ],
       "count": 1
     }
   }
   ```
4. Test with 0 pending invitations -- verify empty list and `count: 0`.
5. Test with expired invitations -- verify they are marked `status = "expired"` and excluded from results.
6. Test with a deleted workspace (soft-deleted via `deleted_at`) -- verify that invitation is excluded.
7. Test with a null role or null inviter -- verify `"role": null` and `"invited_by": null` respectively.
8. Test with an inviter whose `full_name` is null but `display_name` is set -- verify the name falls back correctly.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "invitation" -v --tb=short
```

---

## Acceptance Criteria

- [ ] Pending invitations endpoint executes at most 5 SQL queries (Approach A) or 2 SQL queries (Approach B) regardless of invitation count
- [ ] Query count is constant (O(1)) with respect to the number of pending invitations
- [ ] Response JSON structure is unchanged (same fields, same nesting)
- [ ] Expired invitations are still detected via `is_invitation_expired()` and status-updated to `"expired"`
- [ ] Soft-deleted workspaces (`deleted_at IS NOT NULL`) are still filtered out
- [ ] Role and inviter are handled as nullable (OUTER JOIN or `selectinload` with null check)
- [ ] Inviter name uses correct `Users` model attributes (`full_name`, `display_name`, `email`) -- not `first_name`/`last_name`/`username`
- [ ] `selectinload` import is added (Approach A) or no new imports needed (Approach B)
- [ ] No `MissingGreenlet` or lazy-loading errors in async context
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 -- Relationship Loading Techniques](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html)
- **Official Docs:** [SQLAlchemy 2.0 -- `selectinload()` Strategy](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html#select-in-loading)
- **Official Docs:** [SQLAlchemy 2.0 -- `joinedload()` Strategy](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html#joined-eager-loading)
- **Official Docs:** [SQLAlchemy Async Session -- Preventing Implicit IO](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#preventing-implicit-io-when-using-asyncsession)
- **Best Practice Reference:** [Defeating N+1 with selectinload, joinedload, and subqueryload](https://hevalhazalkurt.com/blog/how-to-defeat-the-n1-problem-with-joinedload-selectinload-and-subqueryload/)
- **Security Advisory:** N/A
- **Migration Guide:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** TASK-062 (Fix non-existent User model attributes `first_name`/`last_name`/`username` in the same code block at line 183 -- must be fixed first or simultaneously, as this task's solution also corrects those attribute references)
- **Blocks:** None
- **Related:** TASK-062 (same file, same function, same code block -- the inviter attribute bug at line 183 is addressed in both tasks' solutions)
