# Task 077: Missing `request: Request` Parameter on Email Preferences Endpoints

## Metadata
- **Task ID:** TASK-077
- **Source:** B3 - User Management (Finding #25 under P2 Medium)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P2 Medium
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

All three endpoints in `src/api/routes/users/email_preferences.py` are missing the `request: Request` parameter from `fastapi.Request`. The affected endpoints are `GET /` (`get_preferences`, line 66), `PUT /` (`update_preferences`, line 90), and `POST /unsubscribe` (`unsubscribe`, line 126). Without the `Request` object, these endpoints cannot pass request metadata into the project's standardized `success()` and `error()` response utilities defined in `src/utils/response_utils.py`. The `success()` function accepts an optional `request: Optional[Request]` parameter (line 119 of `response_utils.py`) which it uses to extract a request ID via `get_request_id(request)` and compute `processing_time_ms` from `request.state._start_time`. When `request` is `None`, these metadata fields are omitted from the response envelope, making the email preferences endpoints produce structurally different responses compared to every other authenticated endpoint in the project.

A critical complication is the naming conflict in two of the three endpoints. In `update_preferences`, the parameter `request: UpdatePreferencesRequest` uses the name `request` for the Pydantic body model, which would collide with `request: Request` if added naively. The same collision exists in `unsubscribe`, where `request: UnsubscribeRequest` occupies the `request` name. The established project pattern for resolving this (visible in `password.py` lines 70-72 using `forgot_request: ForgotPasswordRequest`, and `preferences.py` lines 79-81 using `preferences_data: UpdateUserPreferencesRequest`) is to give the Pydantic body model a descriptive name and reserve `request` for the FastAPI `Request` object.

Additionally, all three endpoints currently use `raise HTTPException(status_code=..., detail="...")` for error handling instead of the structured `error()` utility. This produces raw `{"detail": "..."}` JSON responses that lack the standardized error envelope (`error.code`, `error.severity`, `meta.request_id`, `meta.processing_time_ms`) that every other endpoint in the project returns via the `error()` function.

---

## Current Code

```python
# File: src/api/routes/users/email_preferences.py
# Lines 66-87 — GET / (get_preferences)
@router.get("/")
async def get_preferences(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    try:
        user_id = UUID(current_user["identity"])
        service = EmailPreferencesService(db)
        prefs = await service.get_or_create_preferences(user_id, db)

        return success(
            data=prefs.to_dict(),
            message="Email preferences retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Failed to get email preferences: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve email preferences")
```

```python
# File: src/api/routes/users/email_preferences.py
# Lines 90-123 — PUT / (update_preferences)
@router.put("/")
async def update_preferences(
    request: UpdatePreferencesRequest,  # <-- 'request' is Pydantic model, NOT Request
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    try:
        user_id = UUID(current_user["identity"])
        service = EmailPreferencesService(db)
        updates = {k: v for k, v in request.dict().items() if v is not None}
        if not updates:
            return success(data={}, message="No preferences to update")
        prefs = await service.update_preferences(user_id, updates, db)
        return success(data=prefs.to_dict(), message="Email preferences updated successfully")
    except Exception as e:
        logger.error(f"Failed to update email preferences: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update email preferences")
```

```python
# File: src/api/routes/users/email_preferences.py
# Lines 126-160 — POST /unsubscribe (unsubscribe)
@router.post("/unsubscribe")
async def unsubscribe(
    request: UnsubscribeRequest,  # <-- 'request' is Pydantic model, NOT Request
    db: AsyncSession = Depends(get_async_db)
):
    try:
        service = EmailPreferencesService(db)
        success_result = await service.unsubscribe(
            request.token,
            request.email_types or [],
            db
        )
        if not success_result:
            raise HTTPException(status_code=404, detail="Invalid unsubscribe token")
        email_types_str = ", ".join(request.email_types) if request.email_types else "all emails"
        return success(
            data={"unsubscribed_from": email_types_str},
            message=f"Successfully unsubscribed from {email_types_str}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unsubscribe: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process unsubscribe request")
```

---

## Why This Matters (Context & Reasoning)

The project enforces a consistent response envelope across all API endpoints by using the `success()` and `error()` utilities from `src/utils/response_utils.py`. These utilities accept a `request: Optional[Request]` parameter that enables two key behaviors: (1) extracting the request ID via `get_request_id(request)` so every response can be traced back through middleware and logs, and (2) computing `processing_time_ms` from `request.state._start_time` set by the request tracker middleware, giving the frontend and operators visibility into endpoint latency.

Every other user-facing route file in the project follows this pattern. For example, `src/api/routes/users/preferences.py` passes `request=request` to `success()` on lines 68 and 117. `src/api/routes/users/password.py` passes `request=request` to both `success()` and `error()` on lines 93, 123, and throughout. The email preferences file is the sole exception, meaning its responses are structurally incomplete compared to every other endpoint.

The `HTTPException` usage compounds the issue. When other endpoints encounter errors, they return structured JSON via `error()` containing `error.code` (an enum like `INTERNAL_SERVER_ERROR` or `RESOURCE_NOT_FOUND`), `error.severity`, and the full metadata envelope. The email preferences endpoints instead raise `HTTPException`, which FastAPI converts to a minimal `{"detail": "..."}` response. Frontend code that expects the structured error format will fail to parse these responses correctly.

---

## Impact

- **Severity:** Inconsistent response format for all 3 email preferences endpoints. Success responses are missing `meta.request_id` and `meta.processing_time_ms`. Error responses use raw `{"detail": "..."}` format instead of the structured error envelope, breaking frontend error-handling logic that expects `error.code` and `error.severity` fields.
- **Affected Users/Flows:** Any authenticated user managing their email notification preferences (GET and PUT endpoints) and any user clicking an unsubscribe link from an email (POST /unsubscribe endpoint).
- **Blast Radius:** Isolated to the 3 endpoints in `src/api/routes/users/email_preferences.py`. No other files need functional changes, though the imports at the top of this file must be updated.

---

## Recommended Solution

### Step 1: Update imports at the top of the file

```python
# File: src/api/routes/users/email_preferences.py
# Replace existing imports (lines 1-16):
"""
Email Preferences API Routes

Manage user email notification preferences and unsubscribe functionality.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.email_preferences_service import EmailPreferencesService
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.utils.logger import logger
from uuid import UUID
```

Key changes: (a) replaced `HTTPException` with `Request` in the fastapi import, (b) added `error` to the `response_utils` import, (c) added `ErrorCode` and `ErrorSeverity` from `response_schemas`.

### Step 2: Fix `get_preferences` -- add `request: Request` and use `error()` utility

```python
# File: src/api/routes/users/email_preferences.py
# Replace lines 66-87:
@router.get("/")
async def get_preferences(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get user's email preferences.

    Returns the current email notification settings for the authenticated user.
    """
    try:
        user_id = UUID(current_user["identity"])
        service = EmailPreferencesService(db)
        prefs = await service.get_or_create_preferences(user_id, db)

        return success(
            data=prefs.to_dict(),
            request=request,
            message="Email preferences retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Failed to get email preferences: {str(e)}", exc_info=True)
        return error(
            message="Failed to retrieve email preferences",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )
```

### Step 3: Fix `update_preferences` -- add `request: Request`, rename body parameter, use `error()` utility

The body parameter `request: UpdatePreferencesRequest` must be renamed to `preferences_update` to free the `request` name for the FastAPI `Request` object. This follows the same convention used in `preferences.py` (which uses `preferences_data`).

```python
# File: src/api/routes/users/email_preferences.py
# Replace lines 90-123:
@router.put("/")
async def update_preferences(
    request: Request,
    preferences_update: UpdatePreferencesRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update user's email preferences.

    Allows users to control which email notifications they receive.
    Only provided fields will be updated.
    """
    try:
        user_id = UUID(current_user["identity"])
        service = EmailPreferencesService(db)

        # Build update dict from non-None fields
        updates = {k: v for k, v in preferences_update.dict().items() if v is not None}

        if not updates:
            return success(
                data={},
                request=request,
                message="No preferences to update"
            )

        prefs = await service.update_preferences(user_id, updates, db)

        return success(
            data=prefs.to_dict(),
            request=request,
            message="Email preferences updated successfully"
        )
    except Exception as e:
        logger.error(f"Failed to update email preferences: {str(e)}", exc_info=True)
        return error(
            message="Failed to update email preferences",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )
```

Note: The `.dict()` call on `preferences_update` is intentionally left as-is in this task. TASK-080 covers the `.dict()` to `.model_dump()` migration separately.

### Step 4: Fix `unsubscribe` -- add `request: Request`, rename body parameter, use `error()` utility

The body parameter `request: UnsubscribeRequest` must be renamed to `unsubscribe_data` to avoid the naming collision.

```python
# File: src/api/routes/users/email_preferences.py
# Replace lines 126-160:
@router.post("/unsubscribe")
async def unsubscribe(
    request: Request,
    unsubscribe_data: UnsubscribeRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Unsubscribe from emails using token from email link.

    This endpoint does not require authentication - it uses the unique
    unsubscribe token from the email footer link.

    If email_types is empty, unsubscribes from all emails.
    """
    try:
        service = EmailPreferencesService(db)
        success_result = await service.unsubscribe(
            unsubscribe_data.token,
            unsubscribe_data.email_types or [],
            db
        )

        if not success_result:
            return error(
                message="Invalid unsubscribe token",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        email_types_str = ", ".join(unsubscribe_data.email_types) if unsubscribe_data.email_types else "all emails"

        return success(
            data={"unsubscribed_from": email_types_str},
            request=request,
            message=f"Successfully unsubscribed from {email_types_str}"
        )
    except Exception as e:
        logger.error(f"Failed to unsubscribe: {str(e)}", exc_info=True)
        return error(
            message="Failed to process unsubscribe request",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )
```

Key change: The `except HTTPException: raise` block is removed because the endpoint no longer raises `HTTPException`. All error paths now use `return error(...)` which returns a `JSONResponse` rather than raising an exception.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/utils/response_utils.py` | 117-167 | `success()` function that accepts `request` for metadata extraction -- no changes needed |
| `src/utils/response_utils.py` | 170-222 | `error()` function that accepts `request` for metadata extraction -- no changes needed |
| `src/api/schema/response_schemas.py` | 59+ | `ErrorCode` and `ErrorSeverity` enums used for structured errors -- no changes needed |
| `src/api/middleware/request_tracker.py` | Various | `get_request_id()` function called by `success()` and `error()` -- no changes needed |
| `src/api/routes/users/preferences.py` | 46-123 | Sister file that correctly uses `request: Request` alongside a Pydantic body model -- reference implementation |
| `src/api/routes/users/password.py` | 69-76 | Another reference showing `request: Request` + `forgot_request: ForgotPasswordRequest` naming pattern |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server
2. Authenticate and call `GET /api/v1/user/email-preferences/`
3. Observe the response is missing `meta.request_id` and `meta.processing_time_ms` fields that other endpoints include
4. Call `PUT /api/v1/user/email-preferences/` with a valid body and observe the same missing metadata
5. Call `POST /api/v1/user/email-preferences/unsubscribe` with an invalid token and observe the raw `{"detail": "Invalid unsubscribe token"}` response instead of the structured error envelope

### After Fix (Verify the Solution):
1. Call `GET /api/v1/user/email-preferences/` and verify the response includes `meta.request_id` and `meta.processing_time_ms`
2. Call `PUT /api/v1/user/email-preferences/` with a valid body containing at least one preference field (e.g., `{"marketing": false}`) and verify:
   - The update succeeds with updated preferences in the response
   - The response includes `meta.request_id` and `meta.processing_time_ms`
3. Call `PUT /api/v1/user/email-preferences/` with an empty body `{}` and verify the "No preferences to update" response includes metadata
4. Call `POST /api/v1/user/email-preferences/unsubscribe` with an invalid token and verify the response uses the structured error format with `error.code` = `RESOURCE_NOT_FOUND`, `error.severity` = `MEDIUM`, and `meta.request_id`
5. Call `POST /api/v1/user/email-preferences/unsubscribe` with a valid token and verify success response includes metadata
6. Verify the OpenAPI schema (`/docs`) still renders correctly and shows the renamed body parameters

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "email_preferences" -v
```

### Verify No Regressions:
```bash
cd rext-backend && python -m pytest tests/ -v --tb=short
```

---

## Acceptance Criteria

- [ ] All 3 email preferences endpoints accept `request: Request` as a parameter
- [ ] All `success()` calls pass `request=request` for metadata extraction
- [ ] All error handling uses `return error(...)` utility instead of `raise HTTPException(...)`
- [ ] Body parameter in `update_preferences` is renamed from `request` to `preferences_update` to resolve the naming collision
- [ ] Body parameter in `unsubscribe` is renamed from `request` to `unsubscribe_data` to resolve the naming collision
- [ ] All internal references to the renamed body parameters are updated (e.g., `preferences_update.dict()`, `unsubscribe_data.token`, `unsubscribe_data.email_types`)
- [ ] The `HTTPException` import is removed since it is no longer used in the file
- [ ] `error` is added to the `response_utils` import and `ErrorCode`/`ErrorSeverity` are imported from `response_schemas`
- [ ] Response format is consistent with other endpoints (includes `meta.request_id` and `meta.processing_time_ms`)
- [ ] Error responses use structured format with `error.code`, `error.message`, `error.severity`
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI -- Using the Request Directly](https://fastapi.tiangolo.com/advanced/using-request-directly/)
- **Official Docs:** [FastAPI -- Request Body with Multiple Parameters](https://fastapi.tiangolo.com/tutorial/body-multiple-params/)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI -- Handling Errors](https://fastapi.tiangolo.com/tutorial/handling-errors/)
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-080 (same file `email_preferences.py` -- `.dict()` to `.model_dump()` migration; the `.dict()` call on the renamed `preferences_update` body parameter in Step 3 is intentionally left for TASK-080 to address)
