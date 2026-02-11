# Task 088: Replace `langgraph_sdk.Auth` Type Hint with `dict` in onboarding.py

## Metadata
- **Task ID:** TASK-088
- **Source:** B3 - User Management (Finding #30 under P3 Low)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

In `src/api/routes/users/onboarding.py`, line 8 imports `Auth` from `langgraph_sdk` solely to use the type `Auth.types.MinimalUserDict` as a type hint for the `current_user` parameter across all 6 endpoint functions (lines 28, 66, 108, 133, 163, 192). While this type annotation is technically accurate — `get_current_user()` in `src/api/security/dependencies.py` declares its return type as `Auth.types.MinimalUserDict` — it creates an unnecessary coupling between a route file and the LangGraph SDK.

The `current_user` value is actually a plain Python `dict` containing at minimum an `"identity"` key (and optionally `"is_authenticated"` and `"permissions"`). The `MinimalUserDict` type from `langgraph_sdk` is a TypedDict that describes this shape, but it is not enforced at runtime — FastAPI's dependency injection simply passes the dict returned by `get_current_user()`.

Every other route file in the user management module uses `current_user: dict = Depends(get_current_user)` without importing `langgraph_sdk` at all. For example:
- `preferences.py:50` — `current_user: dict = Depends(get_current_user)`
- `profile.py:32` — `current_user: dict = Depends(get_current_user)`
- `auth.py` — uses `current_user` without `Auth` type hints

The `onboarding.py` file is the only user management route that imports `langgraph_sdk` for this purpose. This inconsistency is confusing: a developer reading `onboarding.py` might think the `langgraph_sdk` Auth system is involved in authentication for these endpoints specifically, when in fact it is not — all endpoints use the same `get_current_user` dependency from `dependencies.py`.

Additionally, `onboarding.py` uses `Annotated[Auth.types.MinimalUserDict, Depends(...)]` syntax while other routes use the simpler `dict = Depends(...)` pattern, adding another style inconsistency.

---

## Current Code

```python
# File: rext-backend/src/api/routes/users/onboarding.py
# Line: 8
from langgraph_sdk import Auth

# Lines 28, 66, 108, 133, 163, 192 — used in all endpoint function signatures:
current_user: Annotated[Auth.types.MinimalUserDict | None, Depends(get_current_user_optional)],
current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
```

---

## Why This Matters (Context & Reasoning)

The onboarding module handles the new-user onboarding flow (get status, update steps, complete, reset, check should-show, update marketing data). It is one of the first modules a new user interacts with after registration. The `langgraph_sdk` package is a LangGraph platform SDK primarily used for AI workflow orchestration — its `Auth` module provides authentication types for the LangGraph deployment platform. Importing it in a standard FastAPI route file for simple type hints creates the false impression that the LangGraph authentication system is somehow involved in the onboarding flow.

The `dependencies.py` file (where `get_current_user` is defined) does legitimately use `Auth.types.MinimalUserDict` as its return type annotation, and that is appropriate since the authentication layer integrates with the LangGraph platform. However, route files that simply consume the dependency do not need to know about the LangGraph type system — they should use the standard `dict` type that the value actually conforms to.

If `langgraph_sdk` is ever removed or the Auth type changes, all 6 endpoint signatures in `onboarding.py` would break unnecessarily.

---

## Impact

- **Severity:** No runtime impact. Code quality and dependency coupling issue.
- **Affected Users/Flows:** None directly. Affects developer comprehension and reduces unnecessary dependency coupling.
- **Blast Radius:** Isolated to `onboarding.py` — 1 import line and 6 type annotations across 6 endpoint functions.

---

## Recommended Solution

### Step 1: Remove the `langgraph_sdk` import

```python
# File: rext-backend/src/api/routes/users/onboarding.py
# Delete line 8:
# from langgraph_sdk import Auth  <-- remove this line
```

### Step 2: Replace `Auth.types.MinimalUserDict` with `dict` in all endpoint signatures

Replace all 6 occurrences. The `Annotated` syntax can be preserved for consistency with the existing style in this file, or simplified to match the style used in other route files. The recommended approach is to match the simpler pattern used throughout the rest of the project:

```python
# File: rext-backend/src/api/routes/users/onboarding.py

# Line 28 (get_onboarding_status) — replace:
#   current_user: Annotated[Auth.types.MinimalUserDict | None, Depends(get_current_user_optional)],
# with:
    current_user: Annotated[dict | None, Depends(get_current_user_optional)],

# Line 66 (update_onboarding_step) — replace:
#   current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
# with:
    current_user: Annotated[dict, Depends(get_current_user)],

# Line 108 (complete_onboarding) — replace:
#   current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
# with:
    current_user: Annotated[dict, Depends(get_current_user)],

# Line 133 (reset_onboarding) — replace:
#   current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
# with:
    current_user: Annotated[dict, Depends(get_current_user)],

# Line 163 (should_show_onboarding) — replace:
#   current_user: Annotated[Auth.types.MinimalUserDict | None, Depends(get_current_user_optional)],
# with:
    current_user: Annotated[dict | None, Depends(get_current_user_optional)],

# Line 192 (update_marketing_data) — replace:
#   current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
# with:
    current_user: Annotated[dict, Depends(get_current_user)],
```

### Step 3: Verify the `Annotated` import is still needed

After the change, `Annotated` (from `typing`) is still used in every endpoint signature, so the import on line 3 (`from typing import Annotated`) should remain.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/security/dependencies.py` | `10, 28, 112, 132` | Also imports `Auth` from `langgraph_sdk` and uses `Auth.types.MinimalUserDict` as return type for `get_current_user()` — this is the appropriate place for this type since it is the auth layer. No change needed. |
| `rext-backend/src/api/security/auth.py` | `1` | Imports `Auth` from `langgraph_sdk` — likely used for the actual auth implementation. No change needed. |
| `rext-backend/src/api/routes/workspaces/workspace_permissions.py` | `13` | Also imports `Auth` from `langgraph_sdk` for type hints — same pattern as onboarding.py. Consider applying the same fix in a future task. |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Confirm the import exists:
   ```bash
   cd rext-backend && grep -n "langgraph_sdk" src/api/routes/users/onboarding.py
   ```
   Expected: line 8 shows the import.
2. Confirm `Auth.types.MinimalUserDict` is used in 6 endpoint signatures:
   ```bash
   cd rext-backend && grep -c "Auth.types.MinimalUserDict" src/api/routes/users/onboarding.py
   ```
   Expected: 6.

### After Fix (Verify the Solution):
1. Confirm the `langgraph_sdk` import is removed:
   ```bash
   cd rext-backend && grep "langgraph_sdk" src/api/routes/users/onboarding.py
   ```
   Expected: no output.
2. Confirm `dict` is used instead:
   ```bash
   cd rext-backend && grep "current_user.*dict" src/api/routes/users/onboarding.py
   ```
   Expected: 6 matches.
3. Verify the file compiles:
   ```bash
   cd rext-backend && python -m py_compile src/api/routes/users/onboarding.py
   ```
4. Test onboarding endpoints:
   ```bash
   # Check onboarding status
   curl -H "Authorization: Bearer <token>" http://localhost:8000/api/users/onboarding
   # Check should-show
   curl -H "Authorization: Bearer <token>" http://localhost:8000/api/users/onboarding/should-show
   ```

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "onboarding" -v
```

---

## Acceptance Criteria

- [ ] `from langgraph_sdk import Auth` removed from `onboarding.py`
- [ ] All 6 endpoint signatures use `dict` (or `dict | None`) instead of `Auth.types.MinimalUserDict`
- [ ] `Annotated` import from `typing` is preserved (still used)
- [ ] File compiles without errors
- [ ] Onboarding endpoints function identically to before
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [LangGraph Auth Documentation](https://langchain-ai.github.io/langgraph/tutorials/auth/getting_started/) — documents `Auth.types.MinimalUserDict` as part of LangGraph Platform's authentication system. The type requires only `identity` (str) and optionally `is_authenticated` (bool).
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/) — FastAPI dependency injection does not require route files to know the internal type of injected dependencies; `dict` is sufficient when the consumer only accesses dict keys.
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-073 (No `@require_permissions` on Onboarding Endpoints — also in onboarding.py); workspace_permissions.py has the same unnecessary `Auth` import pattern (not yet tracked as a separate task)
