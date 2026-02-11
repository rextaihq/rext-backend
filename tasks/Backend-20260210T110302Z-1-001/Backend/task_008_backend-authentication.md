# Task 008: Restore Commented-Out Workspace Validation in Permission Decorator

## Metadata
- **Task ID:** TASK-008
- **Source:** Backend Authentication & Authorization Audit (Finding #12 under P1 High)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P1 High
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `require_permissions` decorator in `src/utils/route_decorators.py` (lines 362-365) contains a critical validation check that has been commented out. When `workspace_scoped=True` is specified (the default), the decorator should verify that a `workspace_id` parameter exists in the route's function signature. Without this validation, a route that is mistakenly decorated with `@require_permissions("some.permission", workspace_scoped=True)` but lacks a `workspace_id` parameter will silently proceed with `workspace_id_param = None`.

When `workspace_id_param` is `None`, line 369 executes `UUID(str(None))` which is `UUID("None")`, raising a `ValueError`. This causes the code to fall through to line 371 where `async_get_workspace_id_from_identifier(db, None)` is called, which will either return `None` or raise an exception depending on its implementation. If it returns `None`, `workspace_uuid` remains `None`, and the permission check at line 388 (`check_func(db, user_id, list(permissions), workspace_uuid)`) runs with `workspace_uuid=None` — effectively checking global permissions instead of workspace-scoped permissions. This means a user without workspace-level access could pass a permission check that was intended to be workspace-scoped.

Currently, 68 routes across the codebase use `workspace_scoped=True`, and they all correctly include `workspace_id` in their function signatures. However, the commented-out validation exists as a safety net to catch future misconfigurations. Without it, a developer adding a new workspace-scoped route could accidentally omit `workspace_id` and the permission check would silently degrade to a global check instead of failing loudly.

The commented-out code was likely disabled during development to work around a temporary issue, but it was never re-enabled. This is a defense-in-depth concern — the validation should be active to prevent silent permission check bypasses.

---

## Current Code

```python
# File: src/utils/route_decorators.py
# Lines: 359-371
            # Resolve workspace if scoped
            if workspace_scoped:
                workspace_id_param = kwargs.get('workspace_id')
                # if not workspace_id_param:
                    # raise ValueError(
                    #     "require_permissions with workspace_scoped=True requires 'workspace_id' parameter in route signature"
                    # )

                # Resolve workspace ID (handles both UUID and slug)
                try:
                    workspace_uuid = UUID(str(workspace_id_param))
                except ValueError:
                    workspace_uuid = await async_get_workspace_id_from_identifier(db, workspace_id_param)
```

---

## Why This Matters (Context & Reasoning)

The `require_permissions` decorator is the primary authorization mechanism in the Rext backend. It is used on 131 routes (68 workspace-scoped, 63 global). Workspace-scoped permissions are fundamental to multi-tenant isolation — they ensure that a user can only perform actions within workspaces they belong to and have the appropriate role in.

If a workspace-scoped permission check runs without a workspace context (because `workspace_id` was not provided), it falls back to checking global permissions. This means a user with a global `content.read` permission but no membership in a specific workspace could pass a check intended to verify they have `content.read` in that workspace. This violates the principle of workspace isolation that is central to Rext AI's multi-tenant architecture.

The risk of not fixing this is that any future route added with `workspace_scoped=True` but without `workspace_id` in its parameters will silently have its authorization check degraded. This kind of bug is extremely difficult to catch in code review because the decorator does not produce any error — it just silently checks the wrong scope.

---

## Impact

- **Severity:** Future routes could silently bypass workspace-scoped authorization, allowing cross-tenant access. Currently no routes are affected because all 68 workspace-scoped routes correctly include `workspace_id`, but this is a latent vulnerability.
- **Affected Users/Flows:** Any workspace-scoped operation (content CRUD, member management, knowledge base operations, email templates, personas, invitations, brand voice, permissions)
- **Blast Radius:** Potentially system-wide for any future misconfigured routes. Currently isolated because all existing routes are correctly configured.

---

## Recommended Solution

### Step 1: Uncomment and improve the workspace_id validation

```python
# File: src/utils/route_decorators.py
# Replace lines 359-371 with:
            # Resolve workspace if scoped
            if workspace_scoped:
                workspace_id_param = kwargs.get('workspace_id')
                if not workspace_id_param:
                    logger.error(
                        f"require_permissions with workspace_scoped=True requires 'workspace_id' parameter "
                        f"in route signature for {func.__name__}",
                        extra={"operation": func.__name__, "permissions": list(permissions)}
                    )
                    raise ValueError(
                        f"require_permissions with workspace_scoped=True requires 'workspace_id' parameter "
                        f"in route signature. Route: {func.__name__}"
                    )

                # Resolve workspace ID (handles both UUID and slug)
                try:
                    workspace_uuid = UUID(str(workspace_id_param))
                except ValueError:
                    workspace_uuid = await async_get_workspace_id_from_identifier(db, workspace_id_param)
```

### Step 2: Verify no existing routes break

Run the full test suite to confirm that all 68 workspace-scoped routes correctly provide `workspace_id`. If any route breaks, it means that route was silently running without workspace-scoped permission checks — which is itself a bug that needs to be fixed.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/workspaces/workspace_personas.py` | `22, 57, 92, 135, 183` | 5 routes using `workspace_scoped=True` — all correctly include `workspace_id` |
| `src/api/routes/workspaces/workspace_members.py` | `151, 185, 233, 335` | 4 routes using `workspace_scoped=True` — all correctly include `workspace_id` |
| `src/api/routes/workspaces/workspace_knowledge.py` | Multiple | 15 routes using `workspace_scoped=True` — all correctly include `workspace_id` |
| `src/api/routes/content/` | Multiple | Content routes using `workspace_scoped=True` — all correctly include `workspace_id` |
| `src/api/routes/workspaces/workspace_invitations.py` | `117, 170, 315, 471, 590` | 5 routes using `workspace_scoped=True` — all correctly include `workspace_id` |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a test route with `@require_permissions("content.read", workspace_scoped=True)` but without `workspace_id` in the function parameters
2. Call the route — observe that no validation error is raised
3. The permission check runs with `workspace_uuid=None`, checking global permissions instead of workspace-scoped

### After Fix (Verify the Solution):
1. Create the same test route without `workspace_id`
2. Call the route — observe that a `ValueError` is raised with a clear message identifying the misconfigured route
3. Verify all existing workspace-scoped routes continue to work correctly

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v
```

If any tests fail after this change, it means those tests were calling workspace-scoped routes without providing `workspace_id`, which indicates a test or route configuration issue that should be fixed.

---

## Acceptance Criteria

- [ ] The commented-out validation at lines 362-365 of `route_decorators.py` is restored and active
- [ ] A `ValueError` is raised with a descriptive message when `workspace_scoped=True` but `workspace_id` is not in the route parameters
- [ ] The error message includes the route function name for easy identification
- [ ] A log entry at error level is written before raising the exception
- [ ] All existing workspace-scoped routes continue to work correctly (no false positives)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Dependencies — Security](https://fastapi.tiangolo.com/tutorial/security/) — describes the dependency injection pattern used for auth
- **Security Advisory:** N/A (defense-in-depth measure, not a direct vulnerability)
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — recommends fail-closed authorization (deny by default, require explicit access)
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-009 (Test Stub Bypasses Permission Checks — both affect the `require_permissions` decorator in the same file)
