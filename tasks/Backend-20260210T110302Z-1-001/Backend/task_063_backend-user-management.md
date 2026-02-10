# Task 063: Fix `return HTTPException` Instead of `raise HTTPException` in Avatar Delete

## Metadata
- **Task ID:** TASK-063
- **Source:** Backend User Management Audit (Finding #2 under P0 Critical)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P0 Critical
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

In `src/api/routes/users/profile.py` at line 471, the `delete_avatar` endpoint's catch-all exception handler uses `return HTTPException(...)` instead of `raise HTTPException(...)`. In FastAPI, `HTTPException` is an exception class that must be **raised** to trigger FastAPI's error handling mechanism. When it is **returned** instead of raised, FastAPI treats the `HTTPException` object as a regular response value and serializes it as a JSON response with HTTP 200 OK status.

The result is that when avatar deletion fails due to an unexpected error, the client receives:
- **HTTP Status:** `200 OK` (incorrect — should be 500)
- **Response Body:** `{"status_code": 500, "detail": "Failed to delete avatar"}` (a serialized Python object, not a proper error response)

The client has no way to detect the failure because the HTTP status code indicates success. Any client-side error handling that checks `response.ok` or `response.status` will treat this as a successful response.

This is a common Python/FastAPI mistake — `HTTPException` looks like a regular class instantiation when used with `return`, but it must be used with `raise` to actually produce an HTTP error response. FastAPI's `HTTPException` handler only intercepts raised exceptions, not returned objects.

The catch-all `except Exception as e:` block at line 459 is supposed to handle unexpected errors gracefully by returning a 500 error. Instead, it returns a 200 with an exception object serialized as JSON.

---

## Current Code

```python
# File: src/api/routes/users/profile.py
# Lines: 459-474 (delete_avatar — catch-all exception handler)
    except Exception as e:
        logger.error(f"Error deleting avatar: {str(e)}")
        # Schedule notification
        await schedule_if_allowed(
            db=db,
            user_id=str(user_id),
            background_tasks=background_tasks,
            pref_flag="in_app_notifications",
            message="failed to delete avatar",
            payload={"user_id": str(user_id), "error": str(e)},
            workspace_id=None
        )
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete avatar"
        )
```

---

## Why This Matters (Context & Reasoning)

The avatar delete endpoint (`DELETE /user/profile/avatar`) removes a user's profile picture. When this operation fails (e.g., file system error, database error, external storage service error), the catch-all handler is supposed to return a 500 error so the client can display an appropriate error message and potentially retry.

With the current `return` instead of `raise`:
1. The client receives a 200 OK status, so client-side error handling doesn't trigger.
2. The response body contains a serialized `HTTPException` object which doesn't match the application's standard error response format.
3. The user sees a "success" state in the UI even though their avatar was not actually deleted.
4. Any retry logic on the client side doesn't activate because the response appears successful.

The preferred fix is to use the project's standard `error()` response utility instead of `HTTPException`, which ensures consistent error response formatting and proper HTTP status codes. However, simply changing `return` to `raise` is also correct and is the minimal fix.

---

## Impact

- **Severity:** Avatar deletion failures are silently swallowed — clients see 200 OK when the operation actually failed. The avatar is not deleted but the UI may show it as deleted.
- **Affected Users/Flows:** Any user deleting their profile avatar when an unexpected server-side error occurs (file I/O failure, database error, etc.).
- **Blast Radius:** Isolated to the catch-all exception handler in the `delete_avatar` endpoint. A codebase-wide search confirmed this is the only instance of `return HTTPException` in the entire backend — all other locations correctly use `raise HTTPException`.

---

## Recommended Solution

Replace `return HTTPException(...)` with the project's standard `error()` response utility for consistency with other error handlers in the same file. The `error()` utility is already imported and used elsewhere in `profile.py`.

### Step 1: Replace `return HTTPException` with `error()` utility

```python
# File: src/api/routes/users/profile.py
# Replace lines 471-474:
# OLD:
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete avatar"
        )
# NEW:
        return error(
            message="Failed to delete avatar",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )
```

This approach is preferred over simply changing `return` to `raise` because:
1. It uses the same `error()` utility pattern as the `ResourceNotFoundException` handler above it (lines 452-458).
2. It returns a structured error response matching the application's standard `ErrorResponse` schema.
3. It includes the request metadata for audit/tracing purposes.
4. `ErrorCode.INTERNAL_SERVER_ERROR` exists in the enum (verified) and is the correct error code for this scenario.

The `error()` function, `ErrorCode`, and `ErrorSeverity` are already imported at the top of `profile.py` (lines 11-12):
```python
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
```

No new imports needed.

### Alternative (minimal fix):

If the team prefers a minimal change, simply change `return` to `raise`:

```python
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete avatar"
        )
```

This is correct but produces FastAPI's default error format (`{"detail": "Failed to delete avatar"}`) instead of the project's standardized error response format. The `error()` utility approach is recommended for consistency.

---

## Other Affected Locations

A codebase-wide search for `return HTTPException` confirmed this is the **only** instance in the entire backend. No other files have this issue.

| File | Line(s) | Description |
|------|---------|-------------|
| None identified | — | This is the only instance of `return HTTPException` in the codebase |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server: `cd rext-backend && uvicorn src.main:app --reload`
2. Authenticate and upload an avatar for a test user.
3. Temporarily make the avatar file unreadable/undeletable to simulate a file system error:
   ```bash
   chmod 000 media/avatars/<avatar-filename>
   ```
4. Attempt to delete the avatar:
   ```bash
   curl -v -X DELETE http://localhost:8000/api/v1/user/profile/avatar \
     -H "Authorization: Bearer <token>"
   ```
5. Observe the response:
   - **HTTP Status:** `200 OK` (incorrect)
   - **Body:** `{"status_code": 500, "detail": "Failed to delete avatar"}` (serialized exception object)
6. Note: The `-v` flag shows the HTTP status code in the curl output.

### After Fix (Verify the Solution):
1. Repeat the same steps to trigger a file system error.
2. Observe the response:
   - **HTTP Status:** `500 Internal Server Error` (correct)
   - **Body:** A properly structured error response:
     ```json
     {
       "status": "error",
       "error": {
         "code": "internal_server_error",
         "message": "Failed to delete avatar",
         "severity": "high"
       }
     }
     ```
3. Restore file permissions:
   ```bash
   chmod 644 media/avatars/<avatar-filename>
   ```
4. Verify normal avatar deletion works correctly (returns 200 with success response).

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "avatar or profile" --tb=short
```

---

## Acceptance Criteria

- [ ] `return HTTPException(...)` at line 471 is replaced with `return error(...)` using the project's standard error utility
- [ ] Avatar deletion failures return HTTP 500 (not 200)
- [ ] The error response follows the project's standard `ErrorResponse` format
- [ ] The error response includes `code: "internal_server_error"` and `severity: "high"`
- [ ] Normal avatar deletion (no error) still works correctly and returns 200
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI — Handling Errors — HTTPException](https://fastapi.tiangolo.com/tutorial/handling-errors/#raise-an-httpexception-in-your-code) — explicitly states "raise" is required: "To return HTTP responses with errors to the client you use `raise` with `HTTPException`"
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Starlette HTTPException Source](https://github.com/encode/starlette/blob/master/starlette/exceptions.py) — `HTTPException` inherits from `Exception`, confirming it must be raised to trigger exception handlers
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-060 (same file `profile.py`, same `delete_avatar` endpoint — unbound variable `e` in the `ResourceNotFoundException` handler just above this code)
