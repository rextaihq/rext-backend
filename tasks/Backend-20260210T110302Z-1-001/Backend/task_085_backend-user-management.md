# Task 085: Remove Unused `LoginWithInvitation` Import from auth.py

## Metadata
- **Task ID:** TASK-085
- **Source:** B3 - User Management (Finding #27 under P3 Low)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

In `src/api/routes/users/auth.py` at line 4, the `LoginWithInvitation` schema is imported from `src.api.schema.user_schema` alongside `LoginUser`, `RegisterUser`, and `RegisterWithInvitation`. However, `LoginWithInvitation` is never referenced anywhere in the file — it is not used as a request body type annotation, a response model, or in any other capacity within `auth.py`.

A codebase-wide search confirms that `LoginWithInvitation` is defined in `src/api/schema/user_schema.py` (lines 25-38) and only appears in two places: its definition and this unused import in `auth.py`. No other file in the entire backend codebase imports or references `LoginWithInvitation`.

This is dead code. The `LoginWithInvitation` schema itself defines a request model for logging in while accepting a workspace invitation (email, password, invitation_token), but no endpoint in `auth.py` (or anywhere else) uses it as a parameter type. The schema definition in `user_schema.py` may itself be dead code, but that is a separate concern — this task focuses on removing the unused import from `auth.py`.

Unused imports increase cognitive load for developers reading the file, can cause confusion about whether the symbol is actually used somewhere (perhaps dynamically), and may trigger linter warnings.

---

## Current Code

```python
# File: rext-backend/src/api/routes/users/auth.py
# Line: 4
from src.api.schema.user_schema import LoginUser, RegisterUser, RegisterWithInvitation, LoginWithInvitation
```

---

## Why This Matters (Context & Reasoning)

The `auth.py` route file is the largest route file in the user management module (1,046 lines) and handles all authentication endpoints — login, registration, registration with invitation, OAuth, password reset, etc. Having an unused import at the top of such a critical file creates unnecessary noise. While this has no runtime impact, it violates clean code principles and the project's own pattern of importing only what is needed.

The `LoginWithInvitation` schema appears to have been created anticipating a "login with invitation acceptance" flow, but that flow was either never implemented or was implemented differently (the existing `RegisterWithInvitation` schema handles new user registration with invitation tokens, while existing users accepting invitations likely go through a different flow).

---

## Impact

- **Severity:** No runtime impact. Code quality issue — unused import creates noise and potential confusion.
- **Affected Users/Flows:** None directly. Affects developer experience when reading/maintaining `auth.py`.
- **Blast Radius:** Isolated to a single import line in `auth.py`.

---

## Recommended Solution

### Step 1: Remove `LoginWithInvitation` from the import statement

```python
# File: rext-backend/src/api/routes/users/auth.py
# Replace line 4:
from src.api.schema.user_schema import LoginUser, RegisterUser, RegisterWithInvitation
```

This removes only `LoginWithInvitation` from the import while keeping the other three schemas that are actively used in the file.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/schema/user_schema.py` | `25-38` | The `LoginWithInvitation` class definition itself — may be dead code if no endpoint uses it. Consider removing in a separate task. |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open `rext-backend/src/api/routes/users/auth.py` and confirm `LoginWithInvitation` is imported on line 4.
2. Search the file for any usage of `LoginWithInvitation` beyond the import — confirm none exists.
3. Run a linter to confirm it flags the unused import:
   ```bash
   cd rext-backend && python -m py_compile src/api/routes/users/auth.py
   ```

### After Fix (Verify the Solution):
1. Confirm `LoginWithInvitation` is no longer imported in `auth.py`.
2. Confirm `LoginUser`, `RegisterUser`, and `RegisterWithInvitation` are still imported.
3. Start the application and verify auth endpoints still work:
   ```bash
   # Test login
   curl -X POST -H "Content-Type: application/json" \
     -d '{"email": "test@example.com", "password": "testpass123"}' \
     http://localhost:8000/api/auth/login
   ```

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "auth" -v
```

---

## Acceptance Criteria

- [ ] `LoginWithInvitation` is removed from the import on line 4 of `auth.py`
- [ ] `LoginUser`, `RegisterUser`, and `RegisterWithInvitation` remain imported
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python Import System](https://docs.python.org/3/reference/import.html) — standard reference for Python imports
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [PEP 8 - Imports](https://peps.python.org/pep-0008/#imports) — Python style guide recommends removing unused imports
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-026 (Unused Import `os` in Auth Routes — also in B1, same file `auth.py`); B1 Finding 24 also identified dead code in auth.py
