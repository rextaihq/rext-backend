# Task 061: Fix `frontend_url` Referenced Before Assignment in Data Export

## Metadata
- **Task ID:** TASK-061
- **Source:** Backend User Management Audit (Finding #4 under P0 Critical)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P0 Critical
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

In `src/api/routes/users/management.py`, the `export_data` endpoint constructs a billing info block that references the variable `frontend_url` at line 389:

```python
"customer_portal": f"{frontend_url}/settings/subscription"
```

However, `frontend_url` is not assigned until line 409:

```python
frontend_url = settings.FRONTEND_URL
```

The billing block (`if export_request.include_billing:`) appears before the `frontend_url` assignment in the function body. When a user requests a data export with `include_billing=True`, Python encounters `frontend_url` at line 389 before it has been defined, raising `NameError: name 'frontend_url' is not defined`. This crashes the entire export endpoint with a 500 Internal Server Error.

The variable `frontend_url` is later assigned at line 409 and used in the `background_tasks.add_task(send_data_export_email_task, ..., frontend_url=frontend_url, ...)` call at line 419. The assignment was clearly intended to be available for both the billing block and the email task, but was placed too late in the function body.

This is a straightforward Python scoping bug — variables in Python are function-scoped, but they must be assigned before they are referenced. Unlike some languages, Python does not hoist variable declarations.

---

## Current Code

```python
# File: src/api/routes/users/management.py
# Lines: 385-419 (export_data endpoint — billing block through frontend_url assignment)

        export_data["subscriptions"] = subscriptions
        export_data["billing_info"] = {
            "total_subscriptions": len(subscriptions),
            "note": "Complete invoice history can be accessed via the LemonSqueezy customer portal",
            "customer_portal": f"{frontend_url}/settings/subscription"  # Line 389 — NameError!
        }

    # NEW: Export usage metrics
    if export_request.include_usage:
        # Basic usage stats - can be expanded based on your usage tracking
        export_data["usage"] = {
            "workspaces_count": len(db_user.workspace_memberships) if hasattr(db_user, 'workspace_memberships') else 0,
            "roles_count": len(db_user.user_roles) if hasattr(db_user, 'user_roles') else 0,
            "login_count": db_user.login_count if hasattr(db_user, 'login_count') else 0,
            "last_login": db_user.last_login_at.isoformat() if hasattr(db_user, 'last_login_at') and db_user.last_login_at else None,
            "account_age_days": (datetime.utcnow() - db_user.created_at).days if db_user.created_at else 0,
            "note": "Detailed usage metrics available upon request"
        }

    # Convert to JSON for email
    import json
    export_json = json.dumps(export_data, indent=2)

    # Get frontend URL
    frontend_url = settings.FRONTEND_URL  # Line 409 — too late!

    # Send email with data export in background using EmailService
    background_tasks.add_task(
        send_data_export_email_task,
        email=db_user.email,
        name=db_user.full_name or "User",
        export_id=export_id,
        export_json=export_json,
        export_request=export_request,
        frontend_url=frontend_url,
```

---

## Why This Matters (Context & Reasoning)

The data export endpoint (`POST /user/export-data`) is a GDPR/privacy compliance feature that allows users to download all their personal data. The `include_billing` flag lets users include their subscription and billing information in the export. This is a critical user-facing feature — users may request a data export before deleting their account, and billing data is an important part of that export.

When `include_billing=True`, the entire export fails with a 500 error. This means:
1. Users cannot export their billing data.
2. The entire export (including profile, roles, workspaces, activity) also fails because the error occurs before the export email is sent.
3. This could create GDPR compliance issues if users are unable to access their data export.

The fix is trivial — move the assignment before its first use. The `settings.FRONTEND_URL` is a configuration value loaded from environment variables via Pydantic settings, and it's safe to read at any point in the request lifecycle.

---

## Impact

- **Severity:** The entire data export endpoint fails when `include_billing=True`. Users cannot export billing data, and the failure prevents any data from being exported.
- **Affected Users/Flows:** Any user who requests a data export with billing information included. This is typically triggered from a "Download My Data" button in the user settings.
- **Blast Radius:** Isolated to the `export_data` endpoint in `management.py`. The export works correctly when `include_billing=False`.

---

## Recommended Solution

Move the `frontend_url = settings.FRONTEND_URL` assignment to before the billing block. The most logical placement is near the top of the try block, alongside other variable initializations, so that `frontend_url` is available everywhere in the function.

### Step 1: Move `frontend_url` assignment before its first use

```python
# File: src/api/routes/users/management.py
# Move the assignment from line 409 to before the billing block.
# The billing block starts around line 358 (if export_request.include_billing:).
# Place it before that block, after the user and export_id are set up.

# Find this line (around line 409):
    # Get frontend URL
    frontend_url = settings.FRONTEND_URL

# DELETE it from that location.

# ADD it before the billing block. Find the line:
    if export_request.include_billing:

# And add the assignment BEFORE it:
    # Get frontend URL (needed for billing portal link and export email)
    frontend_url = settings.FRONTEND_URL

    if export_request.include_billing:
```

### Step 2: Verify the `settings` import exists

The `settings` object should already be imported in `management.py`. Verify this import exists at the top of the file:

```python
from src.api.config.settings import settings
```

If not present, add it. Based on the codebase pattern, this import is typically already present in route files that use `settings.FRONTEND_URL`.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/users/invitations.py` | 340 | Uses a hardcoded `frontend_url="http://localhost:3000"` instead of `settings.FRONTEND_URL` — this is a separate issue (B3 Finding 13, P1) but related to `frontend_url` usage |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server: `cd rext-backend && uvicorn src.main:app --reload`
2. Authenticate as any user with an active subscription.
3. Request a data export with billing included:
   ```bash
   curl -X POST http://localhost:8000/api/v1/user/export-data \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"include_profile": true, "include_billing": true, "include_roles": false, "include_workspaces": false, "include_activity": false, "include_usage": false}'
   ```
4. Observe a 500 Internal Server Error.
5. Check server logs for `NameError: name 'frontend_url' is not defined`.

### After Fix (Verify the Solution):
1. Repeat the same request.
2. Observe a 200 OK response with an export confirmation (the actual data is sent via email).
3. Verify no `NameError` in server logs.
4. Verify the exported billing data includes the correct `customer_portal` URL (should be the configured `FRONTEND_URL`, not localhost).

### Edge Cases:
5. Request export with `include_billing=False` — should work both before and after the fix (regression check).
6. Request export with all flags set to `True` — should work after the fix.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "export" --tb=short
```

---

## Acceptance Criteria

- [ ] `frontend_url = settings.FRONTEND_URL` is moved before the `if export_request.include_billing:` block
- [ ] Data export with `include_billing=True` returns 200 OK (not 500)
- [ ] The `customer_portal` URL in the exported billing data uses the correct frontend URL from configuration
- [ ] Data export with `include_billing=False` still works correctly (regression check)
- [ ] The export email is sent successfully with all requested data
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python 3.11 — Naming and binding — Scope of names](https://docs.python.org/3.11/reference/executionmodel.html#naming-and-binding)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Settings and Environment Variables](https://fastapi.tiangolo.com/advanced/settings/)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-059 (same file `management.py` — non-existent ErrorCode values at lines 161, 191)
