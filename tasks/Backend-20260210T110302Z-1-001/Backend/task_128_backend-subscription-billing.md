# Task 128: No Rate Limiting on License Endpoints — Brute-Force License Key Discovery

## Metadata
- **Task ID:** TASK-128
- **Source:** B5 - Subscription & Billing (Finding #15 under P1 High)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P1 High
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The license management endpoints in `rext-backend/src/api/routes/subscriptions/license_routes.py` lack endpoint-specific rate limiting, unlike other sensitive billing endpoints which have dedicated rate limiters. The affected endpoints are:

1. **`POST /licenses/validate`** (line 37) — License key validation. While this endpoint has `@require_permissions("license.read")`, it accepts a license key in the request body and validates it against the payment provider. Without rate limiting, an attacker with any valid authentication token can make unlimited validation requests to probe for valid license keys.

2. **`POST /licenses/{license_id}/activate`** (line 148) — License activation. Accepts a license ID and instance data. Without rate limiting, an attacker can rapidly activate and deactivate licenses to exhaust activation slots.

3. **`POST /licenses/{license_id}/deactivate`** (line 235) — License deactivation. Similar abuse potential as activate.

For comparison, other billing endpoints in the same codebase already have endpoint-specific rate limiters:
- `subscription_routes.py` uses `checkout_rate_limit()` (5/min), `subscription_update_rate_limit()` (10/min), `subscription_cancel_rate_limit()` (3/min)
- `checkout_routes.py` uses `customer_portal_rate_limit()` (10/min)

The project already has a comprehensive rate limiting infrastructure in `src/api/middleware/rate_limiter.py` with both a global `RateLimiterMiddleware` (applied to all endpoints) and an `EndpointRateLimiter` class for per-endpoint limits via FastAPI dependency injection. The global rate limiter uses configurable limits (`RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_PER_HOUR`, `RATE_LIMIT_PER_DAY` from settings), but these are too permissive for sensitive license operations.

License keys for Lifetime Deal (LTD) purchases represent real monetary value. If an attacker can discover valid license keys through brute-force validation, they can potentially activate them on their own devices, stealing access that was paid for by legitimate customers.

According to OWASP's Brute Force Protection guidelines, endpoints that accept secrets or keys as input must have strict rate limiting to prevent enumeration attacks.

---

## Current Code

```python
# File: rext-backend/src/api/routes/subscriptions/license_routes.py
# Lines: 37-43 — No rate limiting dependency
@router.post("/validate", response_model=dict, status_code=status.HTTP_200_OK)
@require_permissions("license.read", workspace_scoped=False)
@db_transaction_handler("validate license key", auto_commit=False)
async def validate_license(
    request: Request,
    license_data: LicenseValidateRequest,
    db: AsyncSession = Depends(get_async_db)
):
```

```python
# File: rext-backend/src/api/routes/subscriptions/license_routes.py
# Lines: 148-157 — No rate limiting dependency
@router.post("/{license_id}/activate", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("activate license")
@require_permissions("license.activate", workspace_scoped=False)
async def activate_license_endpoint(
    request: Request,
    license_id: str,
    activation_data: LicenseActivateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
```

```python
# File: rext-backend/src/api/routes/subscriptions/license_routes.py
# Lines: 235-244 — No rate limiting dependency
@router.post("/{license_id}/deactivate", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("deactivate license")
@require_permissions("license.deactivate", workspace_scoped=False)
async def deactivate_license_endpoint(
    request: Request,
    license_id: str,
    deactivation_data: LicenseDeactivateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
```

---

## Why This Matters (Context & Reasoning)

License keys are the authentication mechanism for Lifetime Deal (LTD) and one-time purchase products. They have direct monetary value — each license represents a purchase. The validate endpoint is particularly dangerous because it confirms whether a given license key exists and is valid, providing a boolean oracle that enables brute-force enumeration.

LemonSqueezy license keys follow known formats, and without rate limiting, an attacker can systematically probe all possible keys. Even at a modest 100 requests/second (well within the global rate limit), an attacker could test 360,000 keys per hour.

The project already has the infrastructure to add per-endpoint rate limiting — the `EndpointRateLimiter` class in `rate_limiter.py` provides a FastAPI dependency that can be added to any endpoint with a single `Depends()` call. Factory functions already exist for similar use cases (e.g., `checkout_rate_limit()`, `login_rate_limit()`).

---

## Impact

- **Severity:** Brute-force license key discovery is possible. An authenticated attacker can enumerate valid license keys at high speed. Activation endpoints can be abused to exhaust activation slots on others' licenses.
- **Affected Users/Flows:** All license holders (LTD and one-time purchase customers). License validation, activation, and deactivation flows.
- **Blast Radius:** Moderate — limited to license endpoints, but financial impact is direct (stolen license access).

---

## Recommended Solution

Add endpoint-specific rate limiters to all three license endpoints using the existing `EndpointRateLimiter` infrastructure. Create factory functions following the established pattern.

### Step 1: Add license rate limiter factory functions to rate_limiter.py

```python
# File: rext-backend/src/api/middleware/rate_limiter.py
# Add after the existing checkout/subscription rate limiter factory functions (after line 805):

def license_validate_rate_limit():
    """
    Rate limiter for license validation endpoint.

    Limit: 10 attempts per minute per user.
    Prevents brute-force license key discovery.
    """
    return EndpointRateLimiter(
        requests=10,
        window_minutes=1,
        description="license validation"
    )


def license_activate_rate_limit():
    """
    Rate limiter for license activation endpoint.

    Limit: 5 attempts per minute per user.
    Prevents activation slot exhaustion.
    """
    return EndpointRateLimiter(
        requests=5,
        window_minutes=1,
        description="license activation"
    )


def license_deactivate_rate_limit():
    """
    Rate limiter for license deactivation endpoint.

    Limit: 5 attempts per minute per user.
    Prevents rapid deactivation abuse.
    """
    return EndpointRateLimiter(
        requests=5,
        window_minutes=1,
        description="license deactivation"
    )
```

### Step 2: Import rate limiters in license_routes.py

```python
# File: rext-backend/src/api/routes/subscriptions/license_routes.py
# Add to imports (after line 28):
from src.api.middleware.rate_limiter import (
    license_validate_rate_limit,
    license_activate_rate_limit,
    license_deactivate_rate_limit
)
```

### Step 3: Add rate limiting to validate endpoint

```python
# File: rext-backend/src/api/routes/subscriptions/license_routes.py
# Add rate limit dependency to validate_license function signature (line 40-43):
async def validate_license(
    request: Request,
    license_data: LicenseValidateRequest,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(license_validate_rate_limit())
):
```

### Step 4: Add rate limiting to activate endpoint

```python
# File: rext-backend/src/api/routes/subscriptions/license_routes.py
# Add rate limit dependency to activate_license_endpoint function signature (line 153-157):
async def activate_license_endpoint(
    request: Request,
    license_id: str,
    activation_data: LicenseActivateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(license_activate_rate_limit())
):
```

### Step 5: Add rate limiting to deactivate endpoint

```python
# File: rext-backend/src/api/routes/subscriptions/license_routes.py
# Add rate limit dependency to deactivate_license_endpoint function signature (line 238-244):
async def deactivate_license_endpoint(
    request: Request,
    license_id: str,
    deactivation_data: LicenseDeactivateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(license_deactivate_rate_limit())
):
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/routes/subscriptions/license_routes.py` | `287-293` | `list_licenses_endpoint` — read-only, lower priority but could add rate limiting for consistency |
| `rext-backend/src/api/routes/subscriptions/license_routes.py` | `335-343` | `get_license_endpoint` — read-only, lower priority |
| `rext-backend/src/api/routes/subscriptions/license_routes.py` | `396-404` | `list_license_activations_endpoint` — read-only, lower priority |
| `rext-backend/src/api/routes/subscriptions/license_routes.py` | `454-462` | `revoke_license_endpoint` — admin endpoint, should also have rate limiting |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Obtain a valid auth token
2. Send 50 rapid license validation requests:
   ```bash
   for i in $(seq 1 50); do
     curl -s -o /dev/null -w "%{http_code}\n" \
       -X POST http://localhost:2024/api/v1/licenses/validate \
       -H "Authorization: Bearer <token>" \
       -H "Content-Type: application/json" \
       -d '{"license_key": "TEST-KEY-'$i'"}' &
   done
   wait
   ```
3. Observe that all 50 requests succeed (no 429 responses)

### After Fix (Verify the Solution):
1. Send the same 50 rapid requests
2. Observe that after the first 10, subsequent requests receive HTTP 429 (Too Many Requests)
3. Verify the `Retry-After` header is present in 429 responses
4. Wait 1 minute and verify requests succeed again

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "license" -v
```

---

## Acceptance Criteria

- [ ] `POST /licenses/validate` has rate limiting of 10 requests/minute/user
- [ ] `POST /licenses/{id}/activate` has rate limiting of 5 requests/minute/user
- [ ] `POST /licenses/{id}/deactivate` has rate limiting of 5 requests/minute/user
- [ ] Rate limit responses include `Retry-After` header
- [ ] Rate limiting uses the existing `EndpointRateLimiter` infrastructure (Redis with in-memory fallback)
- [ ] Factory functions follow the established naming convention
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Dependencies for Rate Limiting](https://fastapi.tiangolo.com/tutorial/dependencies/) — FastAPI dependency injection pattern used for per-endpoint rate limiting
- **Security Advisory:** [OWASP Brute Force Attack](https://owasp.org/www-community/attacks/Brute_force_attack) — OWASP guidance on brute-force prevention
- **Best Practice Reference:** [OWASP Rate Limiting Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html) — OWASP recommendations for API rate limiting
- **Migration Guide:** N/A
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-065 (No Rate Limiting on OAuth Endpoints from B3), TASK-125 (X-Forwarded-For Spoofable — rate limiter IP extraction is also affected)
