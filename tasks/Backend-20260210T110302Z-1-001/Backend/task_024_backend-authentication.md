# Task 024: Document and Deprecate Duplicate revoke_all_sessions_post Endpoint

## Metadata
- **Task ID:** TASK-024
- **Source:** B1 - Authentication & Authorization (Finding #25 under P3 Low)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `sessions.py` file contains two endpoints that perform the exact same operation—revoking all user sessions except the current one:

1. **`DELETE /sessions`** (lines 87-132) — The RESTful endpoint
2. **`POST /sessions/revoke-all`** (lines 135-146) — A duplicate added "for frontend compatibility"

The POST endpoint simply delegates to the DELETE endpoint:

```python
async def revoke_all_sessions_post(...) -> dict:
    """Revoke all sessions except the current one (POST version for frontend)."""
    return await revoke_all_sessions(request, current_user, authorization, db)
```

This creates several issues:

1. **Increased API surface area:** Two endpoints doing the same thing means more code to maintain and test.
2. **Documentation confusion:** API consumers must understand both endpoints are equivalent.
3. **Inconsistent REST semantics:** `DELETE /sessions` is the correct RESTful approach for removing resources.
4. **No deprecation notice:** The POST endpoint has no indication it should be phased out.

The comment "for frontend compatibility" suggests this was added as a workaround, but without documentation of which frontend component requires it or a plan to migrate away from it.

---

## Current Code

```python
# File: rext-backend/src/api/routes/users/sessions.py
# Lines: 87-132 - The primary DELETE endpoint
@router.delete("/sessions")
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("revoke all user sessions", auto_commit=True)
async def revoke_all_sessions(
    request: Request,
    current_user: dict = Depends(get_current_user),
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """Revoke all sessions except the current one."""
    user_uuid = UUID(str(current_user.get("identity")))

    try:
        _, token = authorization.split()
    except ValueError as exc:
        raise RextValidationException(
            message="Invalid authorization header",
            validation_errors={"authorization": "Expected 'Bearer <token>' format"}
        ) from exc

    current_payload = verify_token(token)
    current_jti = current_payload.get("jti")

    service = SessionService(db)
    exclude_session_id = None
    if current_payload.get("session_id"):
        try:
            exclude_session_id = UUID(str(current_payload.get("session_id")))
        except (ValueError, TypeError):
            exclude_session_id = None

    revoked_count = await service.revoke_all_sessions(
        user_uuid,
        exclude_session_id=exclude_session_id,
        exclude_session_jti=current_jti,
    )

    logger.info(
        "Revoked other sessions",
        extra={"user_id": str(user_uuid), "revoked_count": revoked_count},
    )

    return {
        "revoked_count": revoked_count,
        "current_session_preserved": True,
    }


# Lines: 135-146 - The duplicate POST endpoint
@router.post("/sessions/revoke-all")
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("revoke all user sessions (POST)", auto_commit=True)
async def revoke_all_sessions_post(
    request: Request,
    current_user: dict = Depends(get_current_user),
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """Revoke all sessions except the current one (POST version for frontend)."""
    # Reuse the same logic as DELETE /sessions
    return await revoke_all_sessions(request, current_user, authorization, db)
```

---

## Why This Matters (Context & Reasoning)

Having duplicate endpoints is a form of technical debt:

1. **Maintenance burden:** Any change to session revocation logic must be verified against both endpoints.
2. **Testing overhead:** Both endpoints should be tested, even though they're functionally identical.
3. **OpenAPI/Swagger bloat:** The API documentation shows two ways to do the same thing, confusing consumers.
4. **No clear migration path:** Without deprecation warnings, the duplicate may persist indefinitely.

The "for frontend compatibility" comment suggests the frontend was originally calling a POST endpoint for this action. Modern best practice is to use the appropriate HTTP method (`DELETE` for removing resources), but the migration should be planned and tracked.

---

## Impact

- **Severity:** Low. Both endpoints work correctly; this is a code quality issue.
- **Affected Users/Flows:** Frontend code that calls `POST /sessions/revoke-all` instead of `DELETE /sessions`.
- **Blast Radius:** Limited to session management functionality.

---

## Recommended Solution

Since removing the endpoint could break the frontend, the recommended approach is:

1. **Document the deprecation** in code and API docs
2. **Add a deprecation header** to the response
3. **Track frontend usage** to plan eventual removal
4. **Create a ticket** to update the frontend to use the DELETE endpoint

### Step 1: Add Deprecation Header and Warning

```python
# File: rext-backend/src/api/routes/users/sessions.py
# Replace lines 135-146 with:

import warnings
from fastapi import Response

@router.post("/sessions/revoke-all", deprecated=True)
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("revoke all user sessions (POST)", auto_commit=True)
async def revoke_all_sessions_post(
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user),
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """
    Revoke all sessions except the current one.

    .. deprecated::
        This endpoint is deprecated. Use DELETE /sessions instead.
        This endpoint exists for legacy frontend compatibility and will be
        removed in a future version.
    """
    # Add deprecation header for API consumers
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"  # Plan removal date
    response.headers["Link"] = '</api/user/sessions>; rel="successor-version"'

    # Log deprecation warning for monitoring
    logger.warning(
        "Deprecated endpoint called: POST /sessions/revoke-all",
        extra={
            "user_id": str(current_user.get("identity")),
            "deprecated_endpoint": "POST /sessions/revoke-all",
            "replacement_endpoint": "DELETE /sessions"
        }
    )

    return await revoke_all_sessions(request, current_user, authorization, db)
```

### Step 2: Add Response Import (if needed)

```python
# File: rext-backend/src/api/routes/users/sessions.py
# Line 5 - Update import:
from fastapi import APIRouter, Depends, Header, Request, Response
```

### Step 3: Document in API Comments

Add a comment block at the top of the file explaining the situation:

```python
# File: rext-backend/src/api/routes/users/sessions.py
# Add after the module docstring (line 1-2):

"""User session management routes.

Note: The POST /sessions/revoke-all endpoint is deprecated.
It was added for frontend compatibility but DELETE /sessions
should be used for new integrations. The POST endpoint is
scheduled for removal after the frontend is migrated.

See: [Frontend Migration Ticket URL]
"""
```

### Step 4: Update OpenAPI Tags (Optional Enhancement)

The `deprecated=True` parameter in `@router.post()` automatically marks the endpoint as deprecated in the OpenAPI schema, which will show in Swagger UI with a strikethrough.

### Step 5: Create Follow-up Task for Frontend Migration

Create a separate task (or Jira ticket) to:
1. Identify all frontend code calling `POST /sessions/revoke-all`
2. Update frontend to call `DELETE /sessions`
3. Remove the deprecated POST endpoint after migration is complete

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| Frontend code | Unknown | Likely calling POST /sessions/revoke-all |
| API documentation | N/A | Should note the deprecation |

---

## Testing Instructions

### Before Fix (Current State):
1. Call `POST /sessions/revoke-all` with valid auth
2. Observe it works and returns session revocation count
3. Note there's no indication this is deprecated

### After Fix (Verify Deprecation):
1. Call `POST /sessions/revoke-all` with valid auth:
   ```bash
   curl -X POST http://localhost:8000/api/user/sessions/revoke-all \
     -H "Authorization: Bearer $TOKEN" \
     -v
   ```
2. Verify response includes deprecation headers:
   ```
   < Deprecation: true
   < Sunset: 2026-06-01
   < Link: </api/user/sessions>; rel="successor-version"
   ```
3. Verify the endpoint still works (returns revoked count)
4. Check server logs for deprecation warning

5. Verify OpenAPI shows endpoint as deprecated:
   - Open `http://localhost:8000/docs`
   - Find `POST /sessions/revoke-all`
   - Should display with strikethrough or "deprecated" label

### Verify DELETE Endpoint Still Works:
```bash
curl -X DELETE http://localhost:8000/api/user/sessions \
  -H "Authorization: Bearer $TOKEN"
```

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "session"
```

---

## Acceptance Criteria

- [ ] POST endpoint marked as `deprecated=True` in decorator
- [ ] Deprecation headers added to POST endpoint response
- [ ] Deprecation logged when POST endpoint is called
- [ ] Docstring updated to document deprecation
- [ ] OpenAPI/Swagger shows endpoint as deprecated
- [ ] DELETE endpoint continues to work unchanged
- [ ] Follow-up ticket created for frontend migration
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Deprecating Path Operations](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/#deprecate-a-path-operation)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [HTTP Deprecation Header RFC](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-deprecation-header)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** Frontend migration to DELETE endpoint (to be created)
- **Related:** None
