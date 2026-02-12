# Task 062: Fix Non-Existent User Model Attributes in Pending Invitations

## Metadata
- **Task ID:** TASK-062
- **Source:** Backend User Management Audit (Finding #5 under P0 Critical)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P0 Critical
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

In `src/api/routes/users/invitations.py` at line 183, the pending invitations endpoint constructs an `invited_by` object by accessing three attributes on the `inviter` (a `Users` model instance) that do not exist on the model:

```python
"name": f"{inviter.first_name} {inviter.last_name}".strip() or inviter.username,
```

The `Users` model (defined in `src/api/models/user_models/users.py`) does not have `first_name`, `last_name`, or `username` attributes. The actual attributes are:
- `full_name` (Column `String(200)`) — the user's full name
- `display_name` (Column `String(200)`) — the user's display name
- `email` (Column `String(255)`) — the user's email address

When this line executes, SQLAlchemy raises `AttributeError: 'Users' object has no attribute 'first_name'`. This crashes the entire pending invitations endpoint with a 500 Internal Server Error.

This bug appears to be a frontend-backend naming mismatch. The frontend `User` TypeScript interface (in `rext-admin/lib/api-client/users.ts`) defines `first_name`, `last_name`, and `username` fields, suggesting the backend code was written to match the frontend naming convention rather than the actual database model. However, the backend `Users` model has never had these fields — it uses `full_name` and `display_name` from inception.

---

## Current Code

```python
# File: src/api/routes/users/invitations.py
# Lines: 170-191
        invitation_data = {
            "id": str(invitation.id),
            "workspace": {
                "id": str(workspace.id),
                "name": workspace.name,  # WorkspaceModel uses 'name'
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
```

```python
# File: src/api/models/user_models/users.py (for reference — the actual model)
# Lines: 16-41
class Users(Base, SerializableMixin):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(200))
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(200))
    bio = Column(String(500))
    # ... (no first_name, last_name, or username columns)
```

---

## Why This Matters (Context & Reasoning)

The pending invitations endpoint (`GET /user/invitations/pending`) is called when a user navigates to their invitations page or when the application checks for pending workspace invitations on login. This endpoint lists all pending invitations the user has received, including who invited them (`invited_by`).

Every time this endpoint is called and any invitation has an associated inviter (which is the common case), the endpoint crashes. This means:
1. Users cannot see their pending workspace invitations.
2. Users cannot accept or decline invitations from the invitations list page (since they can't load the list).
3. Any onboarding flow that checks for pending invitations will fail.

The fix is straightforward: replace the non-existent attribute references with the correct `Users` model attributes (`full_name`, `display_name`, `email`).

---

## Impact

- **Severity:** The entire pending invitations endpoint crashes with `AttributeError` whenever any invitation has an inviter. Users cannot view, accept, or decline workspace invitations.
- **Affected Users/Flows:** All users who receive workspace invitations. Affects the invitation acceptance flow, the invitations list page, and any onboarding flow that checks for pending invitations.
- **Blast Radius:** Isolated to `invitations.py:183`. The bug prevents the entire response from being returned — not just the affected invitation, but all pending invitations for the user.

---

## Recommended Solution

Replace `inviter.first_name`, `inviter.last_name`, and `inviter.username` with the correct model attributes. The `Users` model has `full_name` and `display_name` as name fields, and `email` as a fallback identifier.

### Step 1: Fix the inviter name construction (line 183)

```python
# File: src/api/routes/users/invitations.py
# Replace line 183:
# OLD:
                "name": f"{inviter.first_name} {inviter.last_name}".strip() or inviter.username,
# NEW:
                "name": inviter.full_name or inviter.display_name or inviter.email,
```

This replacement:
- Uses `full_name` as the primary name field (the closest equivalent to `first_name + last_name`)
- Falls back to `display_name` if `full_name` is `None` or empty
- Falls back to `email` as a last resort identifier (every user has an email)
- Matches the pattern used in other parts of the codebase for displaying user names

No new imports needed. No other files affected by this specific fix.

---

## Other Affected Locations

The same `first_name`/`last_name`/`username` mismatch exists in the frontend code. These are separate tasks but related:

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/lib/api-client/users.ts` | 9-23 | Frontend `User` interface defines `username`, `first_name`, `last_name` that don't match backend model |
| `rext-admin/lib/api-client/profile.ts` | 14-31 | Frontend profile types include `first_name`, `last_name` |
| `rext-admin/lib/api-client/profile.ts` | 42-50 | Frontend profile update sends `first_name`, `last_name` which backend ignores |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server: `cd rext-backend && uvicorn src.main:app --reload`
2. Create a workspace invitation from an admin user to a test user:
   ```bash
   curl -X POST http://localhost:8000/api/v1/workspaces/<workspace-id>/invitations \
     -H "Authorization: Bearer <admin-token>" \
     -H "Content-Type: application/json" \
     -d '{"email": "testuser@example.com", "role_id": "<role-id>"}'
   ```
3. As the invited user, fetch pending invitations:
   ```bash
   curl -X GET http://localhost:8000/api/v1/user/invitations/pending \
     -H "Authorization: Bearer <invited-user-token>"
   ```
4. Observe a 500 Internal Server Error.
5. Check server logs for `AttributeError: 'Users' object has no attribute 'first_name'`.

### After Fix (Verify the Solution):
1. Repeat step 3 above.
2. Observe a 200 OK response with the invitation list containing proper inviter names:
   ```json
   {
     "invited_by": {
       "id": "...",
       "name": "John Doe",
       "email": "admin@example.com"
     }
   }
   ```
3. Verify `name` field shows `full_name`, or falls back to `display_name`, or `email` if both are null.
4. Verify no `AttributeError` in server logs.

### Edge Cases:
5. Test with an inviter whose `full_name` is null but `display_name` is set — should show `display_name`.
6. Test with an inviter whose both `full_name` and `display_name` are null — should show `email`.
7. Test with an invitation where the inviter has been deleted (inviter is `None`) — the `if inviter else None` guard should handle this.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "invitation" --tb=short
```

---

## Acceptance Criteria

- [ ] `inviter.first_name` and `inviter.last_name` replaced with `inviter.full_name`
- [ ] `inviter.username` replaced with `inviter.display_name or inviter.email` fallback
- [ ] Line 183 reads: `"name": inviter.full_name or inviter.display_name or inviter.email,`
- [ ] Pending invitations endpoint returns 200 OK with correct inviter names
- [ ] Inviter name falls back gracefully (full_name → display_name → email)
- [ ] No `AttributeError` when accessing inviter data
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy ORM — Column and Data Types](https://docs.sqlalchemy.org/en/20/core/type_basics.html)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Response Model — Consistent API Responses](https://fastapi.tiangolo.com/tutorial/response-model/)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** B3 Finding 8 (Frontend-Backend User Type Mismatch) — will be extracted as a future P1 task covering the frontend type alignment
