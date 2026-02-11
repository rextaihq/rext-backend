# Task 009: Remove Test Stub That Bypasses Permission Checks in Production Code

## Metadata
- **Task ID:** TASK-009
- **Source:** Backend Authentication & Authorization Audit (Finding #13 under P1 High)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P1 High
- **Category:** security
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `require_permissions` decorator in `src/utils/route_decorators.py` (lines 375-399) contains two production code paths that skip permission checks entirely — both are accommodations for test infrastructure that should never exist in production code.

**Bypass 1 — `_executed` attribute check (lines 375-385):**
The decorator checks `hasattr(db, "_executed")` on the database session object. If this attribute exists, it sets `has_permission = True` without performing any permission check. This was added to accommodate a mock database class (`_MembersDB`) used in `tests/unit/routes/test_workspace_members_routes.py` (lines 118-126) that sets `self._executed = False` in its constructor.

**Bypass 2 — `AssertionError` catch (lines 389-399):**
If the permission check function (`check_all_permissions` or `check_any_permission`) raises an `AssertionError` (which happens when the mock DB's `execute()` is called more than once), the decorator catches it and sets `has_permission = True`. This means any `AssertionError` during a permission check — including legitimate assertion failures in production — results in a silent permission bypass.

Both bypasses are problematic because they exist in production code paths. While the `_executed` attribute is currently only set in a test mock class, this is not enforced — if any database session object in production ever acquires an `_executed` attribute (e.g., from SQLAlchemy internals, connection pooling behavior, or a third-party middleware), all permission checks would be silently bypassed for that request.

The correct approach for testing, per FastAPI's official documentation, is to use `app.dependency_overrides` to replace the permission-checking dependency in test fixtures. The test file at `test_workspace_members_routes.py:147-148` already uses `app.dependency_overrides` for `get_async_db` and `get_current_user` — the same pattern should be used for permission checks instead of embedding test-specific logic in the production decorator.

---

## Current Code

```python
# File: src/utils/route_decorators.py
# Lines: 373-399
            # Check permissions using appropriate logic (AND or OR)
            check_func = check_all_permissions if require_all else check_any_permission
            if hasattr(db, "_executed"):
                logger.debug(
                    "Skipping permission check for stubbed database session",
                    extra={
                        "operation": func.__name__,
                        "user_id": str(user_id),
                        "workspace_id": str(workspace_uuid) if workspace_uuid else None,
                        "permissions": list(permissions),
                    },
                )
                has_permission = True
            else:
                try:
                    has_permission = await check_func(db, user_id, list(permissions), workspace_uuid)
                except AssertionError:
                    logger.debug(
                        "Permission check skipped due to test stub assertion",
                        extra={
                            "operation": func.__name__,
                            "user_id": str(user_id),
                            "workspace_id": str(workspace_uuid) if workspace_uuid else None,
                            "permissions": list(permissions),
                        },
                    )
                    has_permission = True
```

**Test code that relies on this bypass:**

```python
# File: tests/unit/routes/test_workspace_members_routes.py
# Lines: 118-126
    class _MembersDB:
        def __init__(self) -> None:
            self._executed = False

        async def execute(self, *_args: Any, **_kwargs: Any) -> _ResultWithScalar:
            if self._executed:
                raise AssertionError("execute called more times than expected")
            self._executed = True
            return _ResultWithScalar(invited_user)
```

---

## Why This Matters (Context & Reasoning)

The `require_permissions` decorator protects 131 routes in the Rext backend. It is the primary authorization enforcement point for the entire application. Having any code path in this decorator that silently bypasses permission checks is a significant security concern, regardless of whether it is currently exploitable.

The `_executed` attribute check is particularly dangerous because:
1. **It relies on a naming convention, not a type check.** Any object with an `_executed` attribute triggers the bypass — not just the specific test mock class.
2. **SQLAlchemy sessions are complex objects.** Database session objects from the connection pool may have unexpected attributes from middleware, plugins, or internal state tracking.
3. **It provides a blueprint for exploitation.** If an attacker can influence the database session object (e.g., through a custom middleware vulnerability or connection pool poisoning), they can bypass all permission checks by setting `_executed` on the session.

The `AssertionError` catch is equally problematic because `AssertionError` is a general Python exception that can occur in many contexts, not just tests. Catching it and granting permission means that any assertion failure in the RBAC utility functions (e.g., due to an internal invariant being violated) results in full permission bypass rather than a denied request.

Defense-in-depth requires that authorization code fail closed — if anything unexpected happens during a permission check, the request should be denied, not approved.

---

## Impact

- **Severity:** Any database session with an `_executed` attribute causes complete permission bypass on all 131 protected routes. Any `AssertionError` during permission checks also causes complete permission bypass.
- **Affected Users/Flows:** All authenticated users on all protected endpoints. An exploited bypass would grant any user full access to any resource regardless of their actual permissions.
- **Blast Radius:** System-wide — the decorator is the central authorization enforcement point.

---

## Recommended Solution

### Step 1: Remove the test bypass logic from the production decorator

```python
# File: src/utils/route_decorators.py
# Replace lines 373-399 with:
            # Check permissions using appropriate logic (AND or OR)
            check_func = check_all_permissions if require_all else check_any_permission
            has_permission = await check_func(db, user_id, list(permissions), workspace_uuid)
```

This is the entire replacement — just a single line. The `_executed` check, the `AssertionError` catch, and all associated debug logging are removed. The permission check is now straightforward: call the check function, get a boolean result.

### Step 2: Update the test to use FastAPI's `dependency_overrides` for permission bypass

The test at `tests/unit/routes/test_workspace_members_routes.py` needs to be updated to bypass permissions using FastAPI's recommended pattern instead of relying on the `_executed` attribute.

```python
# File: tests/unit/routes/test_workspace_members_routes.py
# Add this import at the top:
from src.utils.rbac_utils import check_all_permissions, check_any_permission

# In the test function, after the existing dependency_overrides (around line 147), add:
# Mock the RBAC check functions to always return True in tests
monkeypatch.setattr(
    "src.utils.route_decorators.check_all_permissions",
    AsyncMock(return_value=True),
)
monkeypatch.setattr(
    "src.utils.route_decorators.check_any_permission",
    AsyncMock(return_value=True),
)
```

Alternatively, if the RBAC functions are imported inside the decorator (which they are — line 341), use `monkeypatch.setattr` on the import path used inside the decorator:

```python
# File: tests/unit/routes/test_workspace_members_routes.py
# In the test function, add:
monkeypatch.setattr(
    "src.utils.rbac_utils.check_all_permissions",
    AsyncMock(return_value=True),
)
monkeypatch.setattr(
    "src.utils.rbac_utils.check_any_permission",
    AsyncMock(return_value=True),
)
```

### Step 3: Remove the `_executed` attribute from the mock DB class

```python
# File: tests/unit/routes/test_workspace_members_routes.py
# Update the _MembersDB class (lines 118-126) — remove _executed if no longer needed:
    class _MembersDB:
        async def execute(self, *_args: Any, **_kwargs: Any) -> _ResultWithScalar:
            return _ResultWithScalar(invited_user)

        async def commit(self) -> None:
            pass

        async def rollback(self) -> None:
            pass
```

Note: The `_executed` attribute was only used to prevent double-execution and to signal the permission bypass. With the `monkeypatch` approach for permission bypassing, you can simplify the mock DB class. If you still want the double-execution guard, keep it but name it something that doesn't trigger the (now-removed) production bypass.

### Step 4: Check for other test files that might rely on the bypass

Search the test suite for any other mock DB classes with `_executed`:

```bash
cd rext-backend
grep -rn "_executed" tests/
```

Update any other test files found using the same `monkeypatch.setattr` pattern from Step 2.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `tests/unit/routes/test_workspace_members_routes.py` | `118-126` | Mock DB class with `_executed` attribute that triggers the production bypass |
| `src/utils/rbac_utils.py` | `237-267` | `check_all_permissions` and `check_any_permission` — the functions whose exceptions are caught and swallowed |
| All 131 route files using `@require_permissions` | Various | All protected routes are affected by this bypass vulnerability |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. In a Python shell or test, create a mock database session with `_executed` attribute:
   ```python
   class MockDB:
       _executed = True
   ```
2. Pass this as the `db` parameter to a route protected by `@require_permissions`
3. Observe that permission checks are completely skipped — any user gets full access

### After Fix (Verify the Solution):
1. Run the same test with the mock DB — observe that permission checks are now enforced
2. The mock DB will cause the permission check to fail (since it can't actually query the database)
3. Verify that the test suite uses `monkeypatch.setattr` to bypass permissions instead

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/unit/routes/test_workspace_members_routes.py -v
pytest tests/ -v
```

After applying the fix, some tests may fail because they relied on the `_executed` bypass. These tests need to be updated to use `monkeypatch.setattr` (Step 2). Each failing test confirms a location where the production bypass was being used.

---

## Acceptance Criteria

- [ ] The `hasattr(db, "_executed")` check is removed from `route_decorators.py`
- [ ] The `except AssertionError` catch-and-bypass is removed from `route_decorators.py`
- [ ] The permission check is a single line: `has_permission = await check_func(db, user_id, list(permissions), workspace_uuid)`
- [ ] Test files are updated to use `monkeypatch.setattr` for RBAC function mocking instead of the `_executed` pattern
- [ ] All existing tests pass after the update
- [ ] No production code path can bypass permission checks without proper authorization
- [ ] No new warnings or errors introduced
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Testing Dependencies with Overrides](https://fastapi.tiangolo.com/advanced/testing-dependencies/) — the official pattern for replacing dependencies in tests
- **Security Advisory:** N/A (defense-in-depth, not a CVE)
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — "Ensure that authorization checks are fail-closed — if anything unexpected happens, deny access"
- **Related Issues/PRs:** [FastAPI Dependency Injection in Testing — TestDriven.io](https://testdriven.io/tips/b1b6489d-6538-4734-b148-6c03f8100096/)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-008 (Commented-Out Workspace Validation — both modify the `require_permissions` decorator in `route_decorators.py` and should ideally be done together to minimize code churn)
