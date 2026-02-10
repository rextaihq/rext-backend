# Task 067: Add Missing `GET /user/{userId}` Backend Endpoint

## Metadata
- **Task ID:** TASK-067
- **Source:** Backend User Management Audit (Finding #7 under P1 High)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The frontend API client at `rext-admin/lib/api-client/users.ts:65-68` defines a `users.get(userId)` method that calls `GET /api/v1/user/{userId}`, but no backend route handles this path. The backend has `GET /api/v1/user/users` (list all users, in `management.py:92`) and `GET /api/v1/user/profile` (get current user's profile, in `profile.py`), but no endpoint for retrieving a single user by ID.

The frontend `users.get()` method:
```typescript
get: async (userId: string): Promise<User> => {
  return client.request<User>(`/api/v1/user/${userId}`, { method: "GET" });
}
```

When this method is called, the request hits `GET /api/v1/user/{userId}`. The `__init__.py` router mounts all sub-routers under the `/user` prefix (line 22). Since no sub-router has a `GET /{user_id}` route, FastAPI will either return a 404 or the request could unintentionally match another route if the `userId` value collides with an existing path segment (e.g., if `userId` happened to be `"users"` or `"profile"`, it would hit those endpoints instead).

A codebase search for `users.get(` across the frontend found no current call sites (the method is defined but not yet called from any component). However, the `User` interface and the `get()` method are part of the public API client contract — any component could start using it, and it would silently fail. The method's existence indicates the frontend was designed to support individual user retrieval.

The backend already has the necessary service method: `UserService.get_user_by_id(user_id: UUID)` in `src/services/user_service.py:50-77`, which queries the `Users` model by ID and raises `ResourceNotFoundException` if not found. The `Users` model also has a `to_dict()` method (inherited from `SerializableMixin`) that excludes sensitive fields (`password_hash`, `reset_token`) from serialization.

---

## Current Code

```typescript
// File: rext-admin/lib/api-client/users.ts
// Lines: 62-69
    /**
     * Get a single user by ID
     */
    get: async (userId: string): Promise<User> => {
      return client.request<User>(`/api/v1/user/${userId}`, {
        method: "GET",
      });
    },
```

```python
# File: src/api/routes/users/management.py
# Lines: 92-131 — existing GET /users (list) endpoint — nearest related route
@router.get("/users")
@require_permissions("user.read")
async def get_users(
    request: Request,
    workspace_id: str = None,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Retrieve users, optionally filtered by workspace. Supports pagination.
    Requires authentication.
    """
    # ... implementation
```

```python
# File: src/services/user_service.py
# Lines: 50-77 — existing service method that the new endpoint should use
async def get_user_by_id(
    self,
    user_id: UUID
) -> Users:
    """
    Get user by ID.

    Args:
        user_id: User UUID

    Returns:
        Users object

    Raises:
        ResourceNotFoundException: If user not found
    """
    result = await self.db.execute(
        select(Users).where(Users.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise ResourceNotFoundException(
            resource_type="User",
            resource_id=str(user_id)
        )

    return user
```

---

## Why This Matters (Context & Reasoning)

Individual user retrieval is a fundamental operation in any user management system. The frontend defines this API method as part of its users namespace, establishing a contract that individual users can be fetched by ID. Without the backend endpoint:

1. **Frontend features that need individual user data cannot function.** Components like user profile views, admin user detail pages, and workspace member detail panels need to fetch a single user's data by ID.
2. **The list endpoint is not a substitute.** `GET /users` returns paginated lists, which is inefficient and semantically wrong for fetching a single known user.
3. **The profile endpoint is not a substitute.** `GET /profile` only returns the current authenticated user's data, not arbitrary users.
4. **Silent failure.** The frontend method exists and compiles without errors. Developers may call it assuming it works, only to get 404s at runtime.

The backend already has all the infrastructure needed: the `UserService.get_user_by_id()` method, the `require_permissions` decorator, the `success()` response utility, and the `to_dict()` serialization. Only the route handler is missing.

---

## Impact

- **Severity:** Any frontend component calling `users.get(userId)` receives a 404 error. The API client contract is broken — a defined method has no backend support.
- **Affected Users/Flows:** Currently no active call sites in the frontend, but the method is part of the public API client and could be used by any component. Admin panels and user management flows are the most likely consumers.
- **Blast Radius:** Isolated to the missing `GET /user/{userId}` endpoint. No existing functionality is broken by adding it, but existing functionality that depends on it (or will depend on it) is non-functional.

---

## Recommended Solution

Add a `GET /{user_id}` endpoint to `management.py` at the **bottom** of the file (after the `export_user_data` endpoint). This placement is critical because FastAPI matches routes in declaration order — a `/{user_id}` path pattern could catch requests intended for other routes if placed before them. Since `management.py`'s router has no prefix and is mounted under `/user`, the new route will match `GET /api/v1/user/{user_id}`.

However, there's an important routing consideration: the `management.py` router is mounted at line 32 in `__init__.py`, which means its routes are registered before routes from `roles.py`, `user_status.py`, `admin.py`, etc. A `GET /{user_id}` pattern in `management.py` could intercept `GET /roles`, `GET /sessions`, etc. from other sub-routers.

Looking at the router setup in `__init__.py`, each sub-router is included separately. Since `management.py` uses `router = APIRouter()` (no prefix), and the parent router has `prefix="/user"`, a `GET /{user_id}` in management.py would match `GET /user/<anything>`. However, FastAPI's route resolution is per-router — routes within the same router are matched by declaration order, but routes across different `include_router` calls are matched by the combined path specificity. Static paths (like `/users`, `/profile`) take priority over parameterized paths (like `/{user_id}`).

To be safe, the endpoint should be the **last route added to management.py**, and the `user_id` parameter should be validated as a UUID to prevent it from matching non-UUID path segments.

### Step 1: Add the `GET /{user_id}` endpoint to management.py

```python
# File: src/api/routes/users/management.py
# Add at the very end of the file (after the export_user_data endpoint, after all existing code):

@router.get("/{user_id}")
@require_permissions("user.read")
async def get_user_by_id(
    user_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get a single user by ID.

    Returns user profile data including:
    - Basic info (id, email, full_name, display_name)
    - Status and verification state
    - Preferences (language, timezone)
    - Timestamps (created_at, updated_at)

    Excludes sensitive fields (password_hash, reset_token).

    Requires user.read permission.
    """
    try:
        service = UserService(db)
        user = await service.get_user_by_id(UUID(user_id))

        return success(
            data=user.to_dict(),
            request=request,
            message="User retrieved successfully"
        )
    except ValueError:
        return error(
            message="Invalid user ID format",
            code=ErrorCode.VALIDATION_FAILED,
            status_code=400,
            severity=ErrorSeverity.LOW,
            request=request
        )
    except ResourceNotFoundException:
        raise
```

### Step 2: Verify route ordering

Verify that the new endpoint is the last `@router.get(...)` route in `management.py`. The existing routes are:
1. `GET /users` (line 92) — static path, won't conflict
2. `GET /{user_id}` (new, at bottom) — parameterized path

Since `GET /users` is declared before `GET /{user_id}`, a request to `GET /user/users` will correctly match the list endpoint, not the user-by-id endpoint. All other sub-routers (profile, auth, sessions, etc.) use their own `APIRouter` instances with their own paths, so they won't be affected.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/lib/api-client/users.ts` | 9-23 | The `User` interface defines the expected response type. Note: it includes `username`, `first_name`, `last_name` which don't exist on the backend model — this is addressed by TASK-068. The new endpoint should return the actual backend fields (`full_name`, `display_name`). |
| `src/api/schema/user_schema.py` | 77-88 | `ProfileResponse` schema — could be used as the response model for this endpoint for type safety, but is currently not used by any endpoint (see B3 Finding 28). |
| `src/api/routes/users/__init__.py` | 32 | `management.router` is included at line 32. The order of `include_router` calls determines route priority. |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server locally.
2. Call the missing endpoint:
```bash
curl -X GET http://localhost:8000/api/v1/user/<valid-user-uuid> \
  -H "Authorization: Bearer <valid_token>"
```
3. Observe a 404 Not Found response (or an unexpected match to a different route).

### After Fix (Verify the Solution):
1. Call the endpoint with a valid user ID:
```bash
curl -X GET http://localhost:8000/api/v1/user/<valid-user-uuid> \
  -H "Authorization: Bearer <valid_token>" | python -m json.tool
```
2. Verify the response includes user data: `id`, `email`, `full_name`, `display_name`, `status`, `email_verified`, `avatar_url`, `language`, `timezone`, `created_at`, `updated_at`.
3. Verify `password_hash` and `reset_token` are NOT in the response.

### Edge Cases:
1. **Invalid UUID format:**
```bash
curl -X GET http://localhost:8000/api/v1/user/not-a-uuid \
  -H "Authorization: Bearer <valid_token>"
# Should return 400 with "Invalid user ID format"
```

2. **Non-existent user:**
```bash
curl -X GET http://localhost:8000/api/v1/user/00000000-0000-0000-0000-000000000000 \
  -H "Authorization: Bearer <valid_token>"
# Should return 404 with "User not found"
```

3. **No authentication:**
```bash
curl -X GET http://localhost:8000/api/v1/user/<valid-user-uuid>
# Should return 401 Unauthorized
```

4. **Verify existing routes still work:**
```bash
# These should NOT be intercepted by the new /{user_id} route:
curl -X GET http://localhost:8000/api/v1/user/users -H "Authorization: Bearer <token>"
curl -X GET http://localhost:8000/api/v1/user/profile -H "Authorization: Bearer <token>"
curl -X GET http://localhost:8000/api/v1/user/sessions -H "Authorization: Bearer <token>"
```

### Run Existing Tests:
```bash
cd rext-backend
python -m pytest tests/ -v -k "management or user" --no-header
```

---

## Acceptance Criteria

- [ ] `GET /api/v1/user/{user_id}` endpoint exists and returns user data
- [ ] Endpoint requires authentication (`get_current_user` dependency)
- [ ] Endpoint requires `user.read` permission (`@require_permissions("user.read")`)
- [ ] Response includes all non-sensitive user fields from `Users.to_dict()`
- [ ] Response excludes `password_hash` and `reset_token`
- [ ] Invalid UUID format returns 400 error
- [ ] Non-existent user returns 404 error
- [ ] Existing routes (`/users`, `/profile`, `/sessions`, etc.) are not affected by the new route
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Path Parameters](https://fastapi.tiangolo.com/tutorial/path-params/) — explains path parameter matching and route ordering in FastAPI
- **Official Docs:** [FastAPI Path Operation Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/) — route configuration options
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/) — router organization and prefix patterns

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:**
  - TASK-068 (B3 Finding 8): "Frontend-Backend User Type Mismatch" — the frontend `User` interface expects `username`, `first_name`, `last_name` which don't exist on the backend model. This endpoint should return the correct backend fields (`full_name`, `display_name`). TASK-068 updates the frontend types to match.
  - TASK-062 (B3 Finding 5): "Non-Existent User Model Attributes" — the same model mismatch in `invitations.py` where `first_name`/`last_name`/`username` are incorrectly used.
  - B3 Finding 28 (P3): "ProfileResponse Schema Defined But Never Used" — the `ProfileResponse` schema could potentially be used as the response model for this new endpoint, but this is a separate P3 improvement.
