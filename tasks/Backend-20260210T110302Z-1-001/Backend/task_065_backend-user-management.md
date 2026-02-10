# Task 065: Add Rate Limiting to OAuth Login and Link Endpoints

## Metadata
- **Task ID:** TASK-065
- **Source:** Backend User Management Audit (Finding #11 under P1 High)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P1 High
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `auth.py` route file in user management has rate limiting applied inconsistently across authentication endpoints. The login endpoint (`POST /auth/login` at line 479) uses `Depends(login_rate_limit())`, the registration endpoints (`POST /auth/register` at line 114, `POST /auth/register-with-invitation` at line 209) use `Depends(registration_rate_limit())`, and the resend verification endpoint (`POST /auth/resend-verification` at line 725) also uses `Depends(registration_rate_limit())`. However, the two OAuth endpoints — `POST /oauth/login` (line 787) and `POST /oauth/link` (line 926) — have **no rate limiting at all**.

The `EndpointRateLimiter` class in `src/api/middleware/rate_limiter.py` implements a sliding-window rate limiter using Redis (with an in-memory fallback). It identifies clients by user ID if authenticated, or by IP address otherwise. Factory functions at lines 472-508 provide preconfigured rate limiters for different endpoints.

The OAuth login endpoint is particularly dangerous without rate limiting because it handles both login and automatic account creation. An attacker can enumerate valid email addresses by repeatedly submitting OAuth callback data with different `provider_email` values — the response will differ between "new account created" and "existing account found." Without rate limiting, this enumeration can happen at machine speed.

The OAuth link endpoint (`POST /oauth/link`) is authenticated (requires `get_current_user`), but still lacks rate limiting. An attacker with a valid session could brute-force OAuth provider account IDs to attempt account linking attacks.

Per OWASP API Security Top 10 (API2:2023 Broken Authentication), authentication endpoints without rate limiting are classified as having broken authentication. The OWASP Credential Stuffing Prevention Cheat Sheet specifically recommends rate limiting as a layered defense mechanism for all authentication-related endpoints, including OAuth flows.

---

## Current Code

```python
# File: src/api/routes/users/auth.py
# Lines: 786-790 (oauth_login — NO rate limiting)
@router.post("/oauth/login")
async def oauth_login(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
```

```python
# File: src/api/routes/users/auth.py
# Lines: 926-931 (link_oauth — NO rate limiting)
@router.post("/oauth/link")
async def link_oauth(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
```

For comparison, the login endpoint HAS rate limiting:

```python
# File: src/api/routes/users/auth.py
# Lines: 473-479 (login — HAS rate limiting)
@router.post("/login")
async def login(
    user: LoginUser,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(login_rate_limit())
):
```

The existing factory functions in `rate_limiter.py`:

```python
# File: src/api/middleware/rate_limiter.py
# Lines: 472-508
def login_rate_limit():
    """Rate limiter for login endpoint. Limit: 5 attempts per minute per IP."""
    return EndpointRateLimiter(requests=5, window_minutes=1, description="login")

def password_reset_rate_limit():
    """Rate limiter for password reset endpoint. Limit: 3 attempts per 5 minutes per IP."""
    return EndpointRateLimiter(requests=3, window_minutes=5, description="password reset")

def registration_rate_limit():
    """Rate limiter for registration endpoint. Limit: 1000 registrations per hour per IP."""
    return EndpointRateLimiter(requests=1000, window_minutes=60, description="registration")
```

---

## Why This Matters (Context & Reasoning)

OAuth endpoints are high-value targets because they bypass the normal password-based authentication flow. The OAuth login endpoint in particular is a dual-purpose endpoint — it both authenticates existing users and auto-registers new users. This makes it useful for:

1. **Account enumeration:** Different response structures for new vs. existing users allow attackers to build a list of registered email addresses.
2. **Credential stuffing via provider tokens:** If an attacker obtains leaked OAuth tokens from another breach, they can rapidly test them against this endpoint.
3. **Automated account creation:** Without rate limiting, an attacker can create thousands of fake accounts by submitting fabricated OAuth provider data.

The OAuth link endpoint, while authenticated, can be abused for:
1. **OAuth account ID brute-forcing:** Testing provider account IDs to find linkable accounts.
2. **Account hijacking preparation:** Linking attacker-controlled OAuth accounts to victim users in rapid succession.

Every other authentication endpoint in `auth.py` has rate limiting. The OAuth endpoints were likely added later and the rate limiting was missed. The infrastructure is already in place — only a factory function and two `Depends()` additions are needed.

---

## Impact

- **Severity:** OAuth login and link endpoints can be abused at machine speed for account enumeration, credential stuffing, and automated account creation. No throttling exists to slow down or block automated attacks.
- **Affected Users/Flows:** All users who authenticate via OAuth (Google, GitHub). Also affects the system integrity through potential mass fake account creation.
- **Blast Radius:** Two endpoints (`POST /oauth/login`, `POST /oauth/link`). The vulnerability is isolated to these endpoints, but its exploitation could affect the entire user base through enumeration and mass account creation.

---

## Recommended Solution

Add a new `oauth_rate_limit()` factory function to the rate limiter module and apply it to both OAuth endpoints. The rate limit should be slightly more generous than the login rate limit (since OAuth flows may involve legitimate retries from the frontend) but strict enough to prevent brute-force attacks.

### Step 1: Add `oauth_rate_limit()` factory function to rate_limiter.py

```python
# File: src/api/middleware/rate_limiter.py
# Add after the existing factory functions (after line 508):

def oauth_rate_limit():
    """
    Rate limiter for OAuth login/link endpoints.

    Limit: 10 attempts per 5 minutes per IP.
    Slightly more generous than login (5/min) because OAuth flows
    may involve legitimate retries from frontend callback handling.
    """
    return EndpointRateLimiter(
        requests=10,
        window_minutes=5,
        description="OAuth"
    )
```

### Step 2: Import `oauth_rate_limit` in auth.py

```python
# File: src/api/routes/users/auth.py
# Lines: 23-26 — update the import:
from src.api.middleware.rate_limiter import (
    login_rate_limit,
    registration_rate_limit,
    oauth_rate_limit
)
```

### Step 3: Add rate limiting to `oauth_login` endpoint

```python
# File: src/api/routes/users/auth.py
# Lines: 786-790 — add _rate_limit parameter:
@router.post("/oauth/login")
async def oauth_login(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(oauth_rate_limit())
):
```

### Step 4: Add rate limiting to `link_oauth` endpoint

```python
# File: src/api/routes/users/auth.py
# Lines: 926-931 — add _rate_limit parameter:
@router.post("/oauth/link")
async def link_oauth(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(oauth_rate_limit())
):
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/users/auth.py` | 1007-1011 | `DELETE /oauth/{provider}` (`unlink_oauth`) — also has no rate limiting. Consider adding `oauth_rate_limit()` here as well for consistency, though the risk is lower since it's authenticated and destructive. |
| `src/api/routes/users/password.py` | All endpoints | Password change/reset endpoints — verify they all have `password_reset_rate_limit()` applied. |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server locally.
2. Send 20 rapid `POST /api/v1/user/oauth/login` requests within 10 seconds:
```bash
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/v1/user/oauth/login \
    -H "Content-Type: application/json" \
    -d '{"provider": "google", "provider_account_id": "test'$i'", "provider_email": "test'$i'@example.com", "provider_name": "Test"}'
done
```
3. Observe that all 20 requests are processed without any 429 responses. All return either 200 (success) or 400/500 (application errors) but never 429 (rate limited).

### After Fix (Verify the Solution):
1. Send the same 20 rapid requests.
2. The first 10 should succeed (or return application errors), but requests 11-20 should return HTTP 429 (Too Many Requests) with a `Retry-After` header.
3. Wait 5 minutes and verify requests are accepted again.

### Verify rate limiting with authentication:
```bash
# Get a valid auth token first, then test link_oauth:
for i in $(seq 1 15); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/v1/user/oauth/link \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer <valid_token>" \
    -d '{"provider": "github", "provider_account_id": "test'$i'", "provider_email": "test@example.com"}'
done
# Requests 11+ should return 429
```

### Run Existing Tests:
```bash
cd rext-backend
python -m pytest tests/ -v -k "auth or oauth or rate_limit" --no-header
```

---

## Acceptance Criteria

- [ ] `oauth_rate_limit()` factory function exists in `src/api/middleware/rate_limiter.py`
- [ ] `POST /oauth/login` endpoint has `_rate_limit: None = Depends(oauth_rate_limit())` in its signature
- [ ] `POST /oauth/link` endpoint has `_rate_limit: None = Depends(oauth_rate_limit())` in its signature
- [ ] Sending more than 10 requests within 5 minutes from the same IP returns HTTP 429 for both endpoints
- [ ] The 429 response includes a `Retry-After` header
- [ ] Rate limiting uses Redis when available and falls back to in-memory storage
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Dependencies documentation](https://fastapi.tiangolo.com/tutorial/dependencies/) — explains the `Depends()` pattern used for rate limiting injection
- **Security Advisory:** [OWASP API Security Top 10 - API2:2023 Broken Authentication](https://owasp.org/API-Security/editions/2023/en/0xa2-broken-authentication/) — classifies authentication endpoints without rate limiting as broken authentication
- **Best Practice Reference:** [OWASP Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html) — recommends multi-layered defense including rate limiting for all authentication endpoints
- **Best Practice Reference:** [OWASP Blocking Brute Force Attacks](https://owasp.org/www-community/controls/Blocking_Brute_Force_Attacks) — guidelines for implementing brute force protections
- **Migration Guide:** N/A
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None (rate limiting infrastructure already exists)
- **Blocks:** None
- **Related:**
  - TASK-005 (B1 Finding 5): "No Password Strength Validation" — related authentication hardening
  - TASK-007 (B1 Finding 6): "24-Hour Access Token Lifetime" — related authentication security
  - B5 Finding 15: "No Rate Limiting on License Endpoints" — same pattern in a different module (queued, not yet extracted)
