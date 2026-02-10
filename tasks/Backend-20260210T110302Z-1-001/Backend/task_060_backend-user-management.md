# Task 060: Fix Unbound Variable `e` in Avatar Exception Handlers

## Metadata
- **Task ID:** TASK-060
- **Source:** Backend User Management Audit (Finding #3 under P0 Critical)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P0 Critical
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

In `src/api/routes/users/profile.py`, both the avatar upload endpoint (`upload_avatar`) and the avatar delete endpoint (`delete_avatar`) have exception handling blocks that reference the variable `e` inside `except ResourceNotFoundException:` clauses where `e` is never bound.

Python exception variables are scoped to their specific `except` clause per PEP 3110. When an `except` clause uses the form `except SomeException:` (without `as e`), no variable is bound. The variable `e` used in `str(e)` at lines 334 and 449 refers to... nothing. It is not available from the subsequent `except Exception as e:` block because that block has not executed yet — Python evaluates `except` clauses sequentially and only enters the first matching one.

At line 334 (avatar upload) and line 449 (avatar delete), the code attempts to include `str(e)` in a notification payload:
```python
except ResourceNotFoundException:  # ← no 'as e' binding
    await schedule_if_allowed(
        ...
        payload={"user_id": str(user_id), "error": str(e)},  # ← NameError
        ...
    )
```

When a `ResourceNotFoundException` is raised (i.e., the user is not found in the database during avatar upload or delete), Python enters this `except` block and hits `str(e)`. Since `e` is not defined in this scope, Python raises `NameError: name 'e' is not defined`. This `NameError` is unhandled, causing the request to fail with a 500 Internal Server Error instead of the intended 404 response that is constructed just below the `schedule_if_allowed` call.

The `except Exception as e:` block that appears after the `except ResourceNotFoundException:` block DOES bind `e`, but this is irrelevant — it's a separate exception handler that only executes if no earlier handler matches. The `e` from one `except` clause is not accessible in another.

---

## Current Code

```python
# File: src/api/routes/users/profile.py
# Lines: 326-343 (avatar upload — ResourceNotFoundException handler)
    except ResourceNotFoundException:
        # Schedule notification
        await schedule_if_allowed(
            db=db,
            user_id=str(user_id),
            background_tasks=background_tasks,
            pref_flag="in_app_notifications",
            message="failed to upload avatar",
            payload={"user_id": str(user_id), "error": str(e)},
            workspace_id=None
        )
        return error(
            message="User not found",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        logger.error(f"Error uploading avatar: {str(e)}")
```

```python
# File: src/api/routes/users/profile.py
# Lines: 441-474 (avatar delete — ResourceNotFoundException handler)
    except ResourceNotFoundException:
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
        return error(
            message="User not found",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        logger.error(f"Error deleting avatar: {str(e)}")
```

---

## Why This Matters (Context & Reasoning)

Avatar upload and deletion are common user profile operations. When a user's account is deleted or not found (e.g., due to a stale session token pointing to a deleted user), the system should return a clear 404 "User not found" response. Instead, the `NameError` crash causes a 500 error with no useful information.

The `schedule_if_allowed` function is a notification helper that queues in-app notifications for the user. Including the error details in the notification payload is reasonable, but the implementation incorrectly references an unbound variable. Since the exception type is already known (`ResourceNotFoundException`), the error message can be a static string — there's no dynamic exception message to capture.

This bug also has a secondary effect: the `schedule_if_allowed` call itself crashes, which means the subsequent `return error(...)` line never executes, and the user never receives the intended 404 error response.

---

## Impact

- **Severity:** Avatar upload and delete operations crash with `NameError` (500) instead of returning 404 when the user is not found. The intended error response and in-app notification are both lost.
- **Affected Users/Flows:** Any user whose session references a deleted/non-existent user ID attempting to upload or delete their avatar. Also affects admin impersonation scenarios where the impersonated user has been deleted.
- **Blast Radius:** Isolated to two exception handlers in `profile.py`. No other files exhibit this pattern (verified via codebase-wide search).

---

## Recommended Solution

Replace `str(e)` with a static string `"User not found"` in both locations. This is the preferred approach because:
1. The exception type is already known (`ResourceNotFoundException`), so the error message is deterministic.
2. Using `as e` would work but is unnecessary since we don't need the specific exception message for a simple "user not found" case.
3. The static string matches the error message returned to the client in the `return error(...)` call below.

### Step 1: Fix avatar upload handler (line 334)

```python
# File: src/api/routes/users/profile.py
# Replace line 334:
# OLD: payload={"user_id": str(user_id), "error": str(e)},
# NEW:
            payload={"user_id": str(user_id), "error": "User not found"},
```

### Step 2: Fix avatar delete handler (line 449)

```python
# File: src/api/routes/users/profile.py
# Replace line 449:
# OLD: payload={"user_id": str(user_id), "error": str(e)},
# NEW:
            payload={"user_id": str(user_id), "error": "User not found"},
```

No new imports needed. No other files affected.

---

## Other Affected Locations

A codebase-wide search for `except` clauses without `as e` that reference `str(e)` found no other instances of this pattern. The bug is isolated to these two locations in `profile.py`.

| File | Line(s) | Description |
|------|---------|-------------|
| None identified | — | — |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server: `cd rext-backend && uvicorn src.main:app --reload`
2. Obtain an authentication token for a valid user.
3. Delete that user directly from the database (to simulate a stale session):
   ```sql
   UPDATE users SET deleted_at = NOW() WHERE id = '<user-id>';
   ```
4. Using the stale token, attempt to upload an avatar:
   ```bash
   curl -X POST http://localhost:8000/api/v1/user/profile/avatar \
     -H "Authorization: Bearer <stale-token>" \
     -F "file=@test_image.jpg"
   ```
5. Observe a 500 Internal Server Error. Check server logs for `NameError: name 'e' is not defined`.

### After Fix (Verify the Solution):
1. Repeat the same steps as above.
2. Observe a 404 response with `{"status": "error", "error": {"code": "resource_not_found", "message": "User not found"}}`.
3. Verify no `NameError` in server logs.
4. Repeat for the avatar delete endpoint:
   ```bash
   curl -X DELETE http://localhost:8000/api/v1/user/profile/avatar \
     -H "Authorization: Bearer <stale-token>"
   ```
5. Confirm the same 404 response.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "avatar or profile" --tb=short
```

---

## Acceptance Criteria

- [ ] `str(e)` replaced with `"User not found"` at line 334 of `profile.py` (avatar upload handler)
- [ ] `str(e)` replaced with `"User not found"` at line 449 of `profile.py` (avatar delete handler)
- [ ] Avatar upload returns 404 (not 500) when user is not found
- [ ] Avatar delete returns 404 (not 500) when user is not found
- [ ] No `NameError` in server logs when these error paths are triggered
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python 3.11 — The try statement — except clause variable scoping](https://docs.python.org/3.11/reference/compound_stmts.html#the-try-statement)
- **Security Advisory:** N/A
- **Migration Guide:** [PEP 3110 — Catching Exceptions in Python 3000](https://peps.python.org/pep-3110/) — established the `as` keyword for exception binding and clarified that exception variables are deleted after the `except` block exits
- **Best Practice Reference:** [Python Exception Handling Best Practices](https://docs.python.org/3.11/tutorial/errors.html#handling-exceptions)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-063 (same file `profile.py`, different bug in avatar delete handler — `return HTTPException` instead of `raise`)
