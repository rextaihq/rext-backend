# Task 066: Add Missing `get_workspace_member` Method to MemberService

## Metadata
- **Task ID:** TASK-066
- **Source:** Backend User Management Audit (Finding #6 under P1 High)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

The user workspaces route at `src/api/routes/users/workspaces.py:112` calls `member_service.get_workspace_member(workspace_id=workspace_id, user_id=user_id)`, but `MemberService` in `src/services/member_service.py` does not define a `get_workspace_member` method. The class inherits from `InvitationService` (line 37), which also does not define this method. At runtime, this call produces `AttributeError: 'MemberService' object has no attribute 'get_workspace_member'`.

The `GET /api/v1/user/workspaces` endpoint uses this method inside a loop over all workspaces to enrich each workspace with the user's role information (lines 107-149). For each workspace, it calls `get_workspace_member` and then extracts the `workspace_role` key from the returned dict (lines 119-124). The expected return format is a dictionary containing at minimum a `"workspace_role"` key, which itself is a dictionary with `"id"`, `"name"`, and `"display_name"` fields.

The `MemberService` has several related methods that could serve as a basis:
- `get_workspace_members(workspace_id, status, limit, offset)` at line 180 — returns a list of `WorkspaceMembers` objects for a workspace, but doesn't include role data and returns multiple members.
- `get_workspace_members_with_users(workspace_id, status)` at line 628 — returns `(WorkspaceMembers, Users, Role)` tuples using a join through `UserRole` and `Role`, but returns all members for a workspace.
- `remove_member(workspace_id, user_id)` at line 130 — queries a single member by workspace_id + user_id, which is the right query pattern but then deletes it.

The `WorkspaceMembers` model does NOT have a `role_id` column. Workspace roles are assigned through the `UserRole` join table (`user_roles` table), which maps `user_id` + `workspace_id` → `role_id`. The `Role` model has `id`, `name`, and `display_name` fields. The join pattern is already established in `get_workspace_members_with_users` at lines 647-659:

```python
select(WorkspaceMembers, Users, Role)
    .join(Users, Users.id == WorkspaceMembers.user_id)
    .outerjoin(UserRole, and_(UserRole.user_id == WorkspaceMembers.user_id, UserRole.workspace_id == workspace_id))
    .outerjoin(Role, Role.id == UserRole.role_id)
    .where(WorkspaceMembers.workspace_id == workspace_id)
```

The `AttributeError` is caught by the `except Exception as e:` block at line 141, which logs a warning and continues without the role data. So the endpoint doesn't crash entirely — but every workspace in the response will have `user_role: null` because the method call always fails.

---

## Current Code

```python
# File: src/api/routes/users/workspaces.py
# Lines: 107-149 (the loop that calls the missing method)
    for workspace_data in workspaces:
        workspace_id = UUID(workspace_data["id"])

        # Get user's role in this workspace
        try:
            membership = await member_service.get_workspace_member(
                workspace_id=workspace_id,
                user_id=user_id
            )

            # Get role details
            role_data = None
            if membership.get("workspace_role"):
                role = membership["workspace_role"]
                role_data = {
                    "id": role.get("id"),
                    "name": role.get("name"),
                    "display_name": role.get("display_name")
                }

            # Add role information to workspace data
            workspace_data["user_role"] = role_data

            # Determine if user is owner
            is_owner = workspace_data["user_id"] == str(user_id)
            workspace_data["is_owner"] = is_owner

            if is_owner:
                owned_count += 1
            else:
                member_count += 1

            enhanced_workspaces.append(workspace_data)

        except Exception as e:
            logger.warning(
                f"Failed to get role for workspace {workspace_id}: {str(e)}",
                extra={"user_id": str(user_id), "workspace_id": str(workspace_id)}
            )
            # Include workspace without role info rather than failing completely
            workspace_data["user_role"] = None
            workspace_data["is_owner"] = False
            enhanced_workspaces.append(workspace_data)
```

```python
# File: src/services/member_service.py
# Lines: 37-47 (class definition — no get_workspace_member method)
class MemberService(InvitationService):
    """Service for workspace member business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize MemberService.

        Args:
            db: Async database session
        """
        self.db = db
```

---

## Why This Matters (Context & Reasoning)

The `GET /api/v1/user/workspaces` endpoint powers the workspace switcher component and dashboard workspace listing in the frontend. It's called every time a user navigates to their dashboard or switches workspaces. The response is supposed to include the user's role in each workspace (`user_role` field), which the frontend uses to:

1. Display role badges in the workspace switcher
2. Determine which UI elements to show/hide based on the user's permissions
3. Identify which workspaces the user owns vs. is a member of

Because `get_workspace_member` doesn't exist, every workspace in the response has `user_role: null`, `is_owner: false`, and the owned/member counts are wrong. The frontend may misidentify workspace owners as regular members and hide admin-only UI elements.

The `except Exception as e:` fallback prevents a total endpoint failure, but it silently degrades every response. There are no error indicators in the API response — the client has no way to know the role data is missing due to a server bug rather than the user genuinely having no role.

---

## Impact

- **Severity:** The workspace listing endpoint silently returns incomplete data for every workspace. User roles are always `null`, owner detection is always `false`, and owned/member counts are always 0/0. This affects workspace switcher display and role-based UI rendering.
- **Affected Users/Flows:** Every authenticated user who accesses their workspace list. The workspace switcher component, dashboard workspace listing, and any UI that depends on `user_role` data from this endpoint.
- **Blast Radius:** Isolated to `GET /api/v1/user/workspaces`. The missing method only affects this one endpoint. Other workspace member operations use different methods.

---

## Recommended Solution

Add a `get_workspace_member` method to `MemberService` that queries a single member by `workspace_id` + `user_id` and joins through `UserRole` → `Role` to include the workspace role. The method should return a dictionary matching the format expected by the route.

### Step 1: Add `get_workspace_member` method to MemberService

```python
# File: src/services/member_service.py
# Add this method after the existing `remove_member` method (after line 178):

    async def get_workspace_member(
        self,
        workspace_id: UUID,
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Get a single workspace member with their role information.

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID

        Returns:
            Dict containing member data and workspace_role

        Raises:
            ResourceNotFoundException: If member not found in workspace
        """
        from src.api.models.user_models.user_roles import UserRole
        from src.api.models.user_models.roles import Role

        # Query the membership
        result = await self.db.execute(
            select(WorkspaceMembers).where(
                and_(
                    WorkspaceMembers.workspace_id == workspace_id,
                    WorkspaceMembers.user_id == user_id
                )
            )
        )
        member = result.scalar_one_or_none()

        if not member:
            raise ResourceNotFoundException(
                resource_type="WorkspaceMember",
                resource_id=str(user_id),
                context={"workspace_id": str(workspace_id)}
            )

        # Get the user's role in this workspace via UserRole join table
        role_result = await self.db.execute(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                and_(
                    UserRole.user_id == user_id,
                    UserRole.workspace_id == workspace_id
                )
            )
        )
        role = role_result.scalar_one_or_none()

        # Build the response dict matching the expected format
        member_dict = member.to_dict()
        member_dict["workspace_role"] = {
            "id": str(role.id),
            "name": role.name,
            "display_name": role.display_name
        } if role else None

        logger.debug(
            f"Retrieved workspace member: user={user_id}, workspace={workspace_id}, role={role.name if role else 'none'}",
            extra={
                "user_id": str(user_id),
                "workspace_id": str(workspace_id),
                "has_role": role is not None
            }
        )

        return member_dict
```

This method follows the same patterns used elsewhere in `MemberService`:
- Uses `select(WorkspaceMembers).where(and_(...))` for membership lookup (same as `remove_member` at line 148)
- Joins through `UserRole` → `Role` for role data (same join pattern as `get_workspace_members_with_users` at line 647)
- Returns a dict (same return type as `remove_member` at line 174)
- Raises `ResourceNotFoundException` when member not found (same error pattern as `remove_member` at line 158)
- Uses deferred imports for `UserRole` and `Role` (same pattern as `get_workspace_members_with_users` at line 644)

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/workspaces/workspace_members.py` | 168 | Uses `get_workspace_members_with_users` — a different method that works correctly. Not affected. |
| `src/api/middleware/permissions.py` | 362 | Defines a separate `get_workspace_members` function (not a method on MemberService) — used for permission checks. Not affected. |
| `tests/unit/services/test_member_service.py` | 165-240 | Tests for `get_workspace_members` exist but no tests for the new `get_workspace_member` method. A new test should be added. |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server locally.
2. Log in as any user who is a member of at least one workspace.
3. Call the workspaces endpoint:
```bash
curl -X GET http://localhost:8000/api/v1/user/workspaces \
  -H "Authorization: Bearer <valid_token>" | python -m json.tool
```
4. Observe that every workspace has `"user_role": null` and `"is_owner": false`.
5. Check server logs — there should be warning messages: `"Failed to get role for workspace <id>: 'MemberService' object has no attribute 'get_workspace_member'"`.

### After Fix (Verify the Solution):
1. Call the same endpoint after the fix.
2. Verify each workspace now includes `"user_role"` with `"id"`, `"name"`, and `"display_name"` fields.
3. Verify `"is_owner"` correctly reflects workspace ownership.
4. Verify `"owned_count"` and `"member_count"` are accurate.
5. No warning messages in server logs about failed role retrieval.

### Edge Cases:
- User who is a member but has no role assigned (should return `"user_role": null` gracefully)
- User who is a member of multiple workspaces (each should have its own correct role)
- User who owns a workspace (should have `"is_owner": true`)

### Run Existing Tests:
```bash
cd rext-backend
python -m pytest tests/unit/services/test_member_service.py -v --no-header
python -m pytest tests/ -v -k "workspaces" --no-header
```

---

## Acceptance Criteria

- [ ] `MemberService` has a `get_workspace_member(workspace_id, user_id)` method
- [ ] The method returns a dict with a `workspace_role` key containing `id`, `name`, `display_name`
- [ ] The method raises `ResourceNotFoundException` when the member is not found
- [ ] The method returns `workspace_role: None` when the user has no role assigned
- [ ] `GET /api/v1/user/workspaces` returns correct role data for each workspace
- [ ] `is_owner` and count fields are accurate in the response
- [ ] No `AttributeError` warnings in server logs when calling the endpoint
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy Querying Guide — Selecting ORM Entities](https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html) — the query patterns used in the recommended solution
- **Official Docs:** [SQLAlchemy — Using Joins](https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html#joins) — the `outerjoin` pattern for optional role lookup
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Service Layer Pattern](https://fastapi.tiangolo.com/tutorial/bigger-applications/) — architectural pattern for service methods called from routes

---

## Dependencies & Related Tasks

- **Depends on:** None (can be implemented independently)
- **Blocks:** None
- **Related:**
  - B4 (Workspace Management) audit notes: "The `get_workspace_member` method missing from `MemberService` (Finding 6) will affect workspace management audit." The method added here will also serve B4's needs.
  - TASK-062 (B3 Finding 5): "Non-Existent User Model Attributes" — related to the same workspaces/members area with model attribute mismatches.
