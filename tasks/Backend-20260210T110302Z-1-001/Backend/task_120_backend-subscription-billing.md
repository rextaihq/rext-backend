# Task 120: Add Missing Super Admin Authorization to Invoice Export and License Revoke Endpoints

## Metadata
- **Task ID:** TASK-120
- **Source:** Backend Subscription & Billing Audit (Finding #5 under P0 Critical)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P0 Critical
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

Two admin-level endpoints in the subscription and billing system are missing the `require_super_admin()` authorization check that is consistently applied to all other admin endpoints in the same module. This is a Broken Access Control vulnerability (OWASP A01:2021), the #1 risk in the OWASP Top 10.

**First endpoint:** The invoice export endpoint at `src/api/routes/subscriptions/admin/export_routes.py:159-189` (`GET /export/invoices`) does not call `require_super_admin(db, admin_user_id)` anywhere in its function body. Every other export endpoint in the same file — `export_subscriptions_csv` (line 61), `export_revenue_summary_csv` (line 215), and `export_trial_conversions_csv` (line 353) — all call `require_super_admin()`. The invoice export was likely omitted because the function body immediately raises `NotImplementedError`, but the endpoint is still registered in the router and accessible to any authenticated user with `subscription.read` permission. This exposes the existence of the unimplemented feature and could become a real data leak if someone implements the function body without adding the auth check.

**Second endpoint:** The license revoke endpoint at `src/api/routes/subscriptions/license_routes.py:454-502` (`POST /admin/{license_id}/revoke`) has `@require_permissions("license.revoke", workspace_scoped=False)` and `Depends(get_current_user)`, but does **not** call `require_super_admin()`. Despite the `/admin/` path prefix and the docstring explicitly stating "admin only", any user with the `license.revoke` permission can revoke any license in the system. This is a destructive action that disables a license and deactivates all instances — it should require super admin role verification, matching the pattern used by all other admin subscription endpoints (refund routes, analytics, management, webhook monitoring).

Note: The audit report references `src/api/routes/admin/license_routes.py` and `src/api/routes/admin/export_routes.py`, but the actual file locations differ. The export routes for subscriptions are at `src/api/routes/subscriptions/admin/export_routes.py`, and the license revoke endpoint is embedded in `src/api/routes/subscriptions/license_routes.py` (not a separate admin file).

---

## Current Code

```python
# File: src/api/routes/subscriptions/admin/export_routes.py
# Lines: 159-189
@router.get("/export/invoices", response_class=StreamingResponse)
@require_permissions("subscription.read")
@db_transaction_handler("export invoices", auto_commit=False)
async def export_invoices_csv(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status (paid, pending, refunded)"),
    start_date: Optional[datetime] = Query(None, description="Filter by invoice date (from)"),
    end_date: Optional[datetime] = Query(None, description="Filter by invoice date (to)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    # TODO: Implement invoice export when Invoice model is created
    raise NotImplementedError(
        "Invoice export is not available. The Invoice database model has not been implemented yet."
    )
```

```python
# File: src/api/routes/subscriptions/license_routes.py
# Lines: 454-502
@router.post("/admin/{license_id}/revoke", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("revoke license")
@require_permissions("license.revoke", workspace_scoped=False)
async def revoke_license_endpoint(
    request: Request,
    license_id: str,
    revoke_data: LicenseRevokeRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    admin_user_id = current_user.get("identity")
    service = LicenseService(db)

    # Revoke license
    license_obj = await service.revoke_license(
        license_id=UUID(license_id),
        revoked_by_user_id=admin_user_id
    )
    # ... response construction ...
```

---

## Why This Matters (Context & Reasoning)

The subscription and billing system manages financial data and license keys — two of the most sensitive areas in the application. Admin endpoints in this system consistently use a two-layer authorization pattern: (1) `@require_permissions()` decorator for permission-based access control, and (2) `require_super_admin()` call in the function body for role-based verification. This defense-in-depth approach ensures that even if a permission is incorrectly assigned to a non-admin user, the super admin check prevents unauthorized access.

The two endpoints missing this check break the pattern. The license revoke endpoint is particularly dangerous because revoking a license is a destructive, potentially irreversible action that affects a paying customer's access to the product. If a regular user somehow obtains the `license.revoke` permission (through a misconfigured role, a bug in permission assignment, or privilege escalation), they could revoke licenses belonging to other users.

---

## Impact

- **Severity:** Any authenticated user with `subscription.read` or `license.revoke` permissions can access admin-only functionality. The revoke endpoint allows destructive actions (disabling licenses, deactivating all instances) without super admin verification.
- **Affected Users/Flows:** Admin export workflows, license management. Any user with LTD licenses could have their license revoked by a non-admin user.
- **Blast Radius:** Isolated to two endpoints, but the license revoke has high impact per incident. Fixing is trivial (2 lines of code) but the vulnerability is severe if exploited.

---

## Recommended Solution

### Step 1: Add `require_super_admin()` to the invoice export endpoint

```python
# File: src/api/routes/subscriptions/admin/export_routes.py
# Replace lines 183-189 with:

    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    # TODO: Implement invoice export when Invoice model is created
    # The Invoice database model does not exist in the codebase.
    # This functionality requires creating the Invoice model and migration first.
    raise NotImplementedError(
        "Invoice export is not available. The Invoice database model has not been implemented yet."
    )
```

### Step 2: Add `require_super_admin()` to the license revoke endpoint

```python
# File: src/api/routes/subscriptions/license_routes.py
# Add import at the top of the file (after existing imports, around line 28):
from src.api.routes.subscriptions.admin.shared.auth import require_super_admin

# Replace lines 483-484 (inside revoke_license_endpoint function body) with:
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = LicenseService(db)
```

### Step 3: Verify all other admin endpoints have consistent authorization

Run the following grep to confirm no other admin endpoints are missing `require_super_admin`:

```bash
# Find all admin route functions that have get_current_user but don't call require_super_admin
grep -rn "def.*admin\|/admin/" src/api/routes/ --include="*.py" | grep -v "__pycache__"
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/admin/export_routes.py` | 83-128 | Duplicate export_routes file in `/admin/` directory — has `require_super_admin` but is a separate copy of similar functionality. May need consolidation. |
| `src/api/routes/subscriptions/admin/refund_routes.py` | 93, 132, 173 | Refund routes — correctly use `require_super_admin`. Pattern to follow. |
| `src/api/routes/subscriptions/admin/admin_subscription_management.py` | 43, 72, 99 | Admin management — correctly use `require_super_admin`. Pattern to follow. |
| `src/api/routes/subscriptions/admin/webhook_monitoring_routes.py` | 62, 173, 276, 335 | Webhook monitoring — correctly use `require_super_admin`. Pattern to follow. |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a non-admin user with `subscription.read` and `license.revoke` permissions.
2. Authenticate as this non-admin user and obtain a JWT token.
3. Call `GET /api/v1/subscriptions/admin/export/invoices` with the token — expect to receive the `NotImplementedError` response (no 403).
4. Call `POST /api/v1/licenses/admin/{license_id}/revoke` with a valid license ID — expect the license to be revoked (no 403).

### After Fix (Verify the Solution):
1. Using the same non-admin user token, call `GET /api/v1/subscriptions/admin/export/invoices` — expect HTTP 403 "Super admin role required for this operation".
2. Call `POST /api/v1/licenses/admin/{license_id}/revoke` — expect HTTP 403 "Super admin role required for this operation".
3. Authenticate as a super admin user and verify both endpoints work normally (invoice export returns NotImplementedError, revoke succeeds).

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "export or license or revoke or admin" --no-header
```

---

## Acceptance Criteria

- [ ] `export_invoices_csv` endpoint calls `require_super_admin(db, admin_user_id)` before any processing
- [ ] `revoke_license_endpoint` calls `require_super_admin(db, admin_user_id)` before any processing
- [ ] Non-admin users receive HTTP 403 when calling either endpoint
- [ ] Super admin users can still access both endpoints normally
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Security - First Steps](https://fastapi.tiangolo.com/tutorial/security/first-steps/) — FastAPI's dependency injection security pattern
- **Security Advisory:** [OWASP A01:2021 - Broken Access Control](https://owasp.org/Top10/2021/A01_2021-Broken_Access_Control/) — #1 risk in OWASP Top 10, covering missing authorization checks on API endpoints
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP A01:2025 - Broken Access Control](https://owasp.org/Top10/A01_2021-Broken_Access_Control/) — Updated guidance on access control enforcement
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-121 (License validate missing auth — same file), TASK-089 (B4: Integration credentials exposed — related admin security pattern)
