# Task 121: Add Missing Authentication Dependency to License Validate Endpoint

## Metadata
- **Task ID:** TASK-121
- **Source:** Backend Subscription & Billing Audit (Finding #6 under P0 Critical)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P0 Critical
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `validate_license` endpoint at `src/api/routes/subscriptions/license_routes.py:37-141` is missing the `current_user: dict = Depends(get_current_user)` dependency in its function signature. While the endpoint has a `@require_permissions("license.read", workspace_scoped=False)` decorator, this decorator relies on extracting the `user` or `current_user` parameter from the function's kwargs (see `src/utils/route_decorators.py:348`). Since `current_user` is not declared as a parameter, FastAPI never injects the authenticated user, and the `require_permissions` wrapper receives `None` for the user — causing it to raise a `ValueError` at runtime (`route_decorators.py:351-353`).

The net effect is that the endpoint always crashes with a `ValueError: "require_permissions decorator requires 'user' (or 'current_user') and 'db' parameters in route signature"`, which propagates as an HTTP 500 Internal Server Error. This means:

1. **The endpoint is non-functional.** Every call results in a 500 error regardless of whether the user is authenticated, making the license validation feature completely broken.
2. **No proper authentication challenge.** Unauthenticated requests receive a 500 error instead of a 401 Unauthorized response, violating HTTP semantics and preventing clients from handling auth failures correctly.
3. **Information leakage.** Depending on error handling configuration (debug mode, Sentry, etc.), the ValueError message may leak internal implementation details about the permission system.
4. **Latent vulnerability.** If someone removes the `@require_permissions` decorator to "fix" the 500 error (thinking the decorator is the problem), the endpoint becomes completely unauthenticated — allowing anyone to probe for valid license keys without authentication.

Every other endpoint in the same file (`activate_license_endpoint`, `deactivate_license_endpoint`, `list_licenses_endpoint`, `get_license_endpoint`, `list_license_activations_endpoint`, `revoke_license_endpoint`) correctly includes `current_user: dict = Depends(get_current_user)` in its signature. The `validate_license` endpoint is the only one missing it.

Combined with Finding 15 (no rate limiting on license endpoints), this creates a situation where fixing just the auth dependency — without also adding rate limiting — still leaves the validation endpoint vulnerable to brute-force license key discovery by authenticated users.

---

## Current Code

```python
# File: src/api/routes/subscriptions/license_routes.py
# Lines: 37-44
@router.post("/validate", response_model=dict, status_code=status.HTTP_200_OK)
@require_permissions("license.read", workspace_scoped=False)
@db_transaction_handler("validate license key", auto_commit=False)
async def validate_license(
    request: Request,
    license_data: LicenseValidateRequest,
    db: AsyncSession = Depends(get_async_db)
    # NOTE: Missing current_user: dict = Depends(get_current_user)
):
```

Compare with a correctly implemented endpoint in the same file:

```python
# File: src/api/routes/subscriptions/license_routes.py
# Lines: 148-156
@router.post("/activate", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("activate license")
@require_permissions("license.activate", workspace_scoped=False)
async def activate_license_endpoint(
    request: Request,
    activation_data: LicenseActivateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)  # ← Present here
):
```

---

## Why This Matters (Context & Reasoning)

License validation is a critical security boundary. License keys represent paid access to the product (Lifetime Deals). The validation endpoint checks if a license key is valid, what its activation limits are, and what product it unlocks. Without authentication, this endpoint could be used to:

1. **Enumerate valid license keys** — An attacker could probe thousands of keys to find valid ones.
2. **Gather customer intelligence** — Valid responses include `customer_email`, `customer_name`, `product_name`, and activation usage data.
3. **Map activation limits** — Knowing a license's activation limit and current usage reveals how many more devices can be activated.

FastAPI's dependency injection system requires that security dependencies like `get_current_user` be explicitly declared in the endpoint function signature. Unlike middleware-based auth in other frameworks, FastAPI does not automatically inject dependencies that aren't listed. The `@require_permissions` decorator is not a substitute for the dependency — it depends on the dependency being injected first.

---

## Impact

- **Severity:** The license validation endpoint is completely non-functional (500 error on every request). Once fixed, it must also have proper auth to prevent unauthenticated access.
- **Affected Users/Flows:** Any user or system attempting to validate a license key. LTD purchasers cannot validate their licenses through the API.
- **Blast Radius:** Isolated to the `/licenses/validate` endpoint, but affects all license validation workflows. Frontend components calling this endpoint silently fail.

---

## Recommended Solution

### Step 1: Add `current_user` dependency to the `validate_license` endpoint

```python
# File: src/api/routes/subscriptions/license_routes.py
# Replace the function signature at lines 40-44 with:

async def validate_license(
    request: Request,
    license_data: LicenseValidateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
```

### Step 2: (Optional but recommended) Add user context to the license validation logging

```python
# File: src/api/routes/subscriptions/license_routes.py
# Replace lines 82-88 with:

    user_id = current_user.get("identity")
    logger.info(
        f"License validation request for key: {license_data.license_key[:8]}...",
        extra={
            "user_id": user_id,
            "license_key_prefix": license_data.license_key[:8],
            "has_instance_id": bool(license_data.instance_id)
        }
    )
```

### Step 3: Verify the fix handles unauthenticated requests correctly

After the fix, unauthenticated requests should receive a 401 Unauthorized response (from the `get_current_user` dependency), and authenticated requests without `license.read` permission should receive a 403 Forbidden response (from the `@require_permissions` decorator).

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/subscriptions/license_routes.py` | 454-502 | The revoke endpoint — related auth issue (TASK-120), missing `require_super_admin()` |
| `src/utils/route_decorators.py` | 348-354 | The `require_permissions` decorator that crashes when `user`/`current_user` is missing from kwargs |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server.
2. Obtain a valid JWT token for an authenticated user.
3. Send `POST /api/v1/licenses/validate` with a valid token and license key body `{"license_key": "test-key"}`.
4. Observe HTTP 500 Internal Server Error (due to ValueError in require_permissions).
5. Send the same request without a token — also observe HTTP 500 (same error, because the failure happens before auth is checked).

### After Fix (Verify the Solution):
1. Send `POST /api/v1/licenses/validate` without a token — expect HTTP 401 Unauthorized.
2. Send with a token for a user WITHOUT `license.read` permission — expect HTTP 403 Forbidden.
3. Send with a token for a user WITH `license.read` permission and a valid license key — expect HTTP 200 with validation result.
4. Send with a token for a user WITH `license.read` permission and an invalid key — expect HTTP 400 with error message.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "license" --no-header
```

---

## Acceptance Criteria

- [ ] `validate_license` endpoint includes `current_user: dict = Depends(get_current_user)` in its function signature
- [ ] Unauthenticated requests to `/licenses/validate` return HTTP 401 (not 500)
- [ ] Authenticated requests without `license.read` permission return HTTP 403
- [ ] Authenticated requests with `license.read` permission and valid license key return HTTP 200 with validation data
- [ ] The endpoint no longer raises ValueError at runtime
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Security Dependencies](https://fastapi.tiangolo.com/tutorial/security/first-steps/) — How FastAPI dependency injection works for security, specifically the `Depends()` pattern for `get_current_user`
- **Security Advisory:** [OWASP A01:2021 - Broken Access Control](https://owasp.org/Top10/2021/A01_2021-Broken_Access_Control/) — Missing authentication on API endpoints is a core example of broken access control
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Best Practices for Production 2026](https://fastlaunchapi.dev/blog/fastapi-best-practices-production-2026) — Production security patterns including auth dependency injection
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-120 (Missing super admin auth on revoke endpoint — same file), TASK-005 (B1: No password strength validation — auth security pattern), TASK-065 (B3: No rate limiting on OAuth endpoints — similar rate limiting concern for license endpoints)
