# Task 014: Add CSRF Mitigation for SSE and Cookie-Adjacent Authentication

## Metadata
- **Task ID:** TASK-014
- **Source:** Backend Authentication & Authorization Audit (Finding #16 under P2 Medium)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P2 Medium
- **Category:** security
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The Rext backend has no CSRF protection mechanisms implemented. A search for `csrf` or `CSRF` across the entire backend codebase returns zero results. While the API primarily uses JWT Bearer tokens sent via the `Authorization` header — which is inherently resistant to CSRF because browsers do not automatically attach custom headers on cross-origin requests — there are specific attack surfaces that remain vulnerable.

The primary risk is the SSE (Server-Sent Events) authentication endpoint at `src/api/security/dependencies.py:128-211`. The `get_current_user_sse()` function accepts authentication tokens via the `token` query parameter (`?token=...`) because the browser's `EventSource` API does not support custom headers. Query parameters are automatically included by the browser in cross-origin requests, making this endpoint potentially vulnerable to CSRF attacks where a malicious page could open an EventSource connection to the API using the victim's session.

The CORS middleware is configured in `src/api/server.py:164-172` with `allow_credentials=True` and origin restrictions via `settings.allowed_origins_list`. This provides partial CSRF defense by rejecting cross-origin requests from unauthorized origins. However, CORS is enforced by the browser and can be bypassed by non-browser clients, and it does not protect against same-site attacks from compromised subdomains.

Per the OWASP CSRF Prevention Cheat Sheet, for APIs using JWT Bearer tokens in the `Authorization` header, CSRF protection is generally not needed. However, the SSE query parameter token mechanism is an exception that warrants additional mitigation. The recommended approach is defense-in-depth: add `SameSite` attributes to any response cookies, verify the `Origin`/`Referer` headers for SSE connections, and consider short-lived tokens for SSE.

---

## Current Code

```python
# File: src/api/middleware/security.py
# Lines: 1-39 (entire file)
"""
Security Headers Middleware

Adds security-related HTTP headers to all responses.
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Enable XSS filter
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # HSTS (only for HTTPS)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response
```

```python
# File: src/api/security/dependencies.py
# Lines: 128-136
async def get_current_user_sse(
    authorization: str = Header(None),
    token: str = Query(None),
    db: AsyncSession = Depends(get_async_db)
) -> Auth.types.MinimalUserDict:
    """
    Authentication dependency for SSE that supports both Header and Query param.
    EventSource API does not support custom headers, so we allow passing token via query param.
    """
```

```python
# File: src/api/server.py
# Lines: 164-172
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600,
)
```

---

## Why This Matters (Context & Reasoning)

CSRF attacks exploit the browser's automatic inclusion of cookies and credentials in cross-origin requests. While the Rext API's primary authentication via `Authorization: Bearer <token>` header is not vulnerable to CSRF (browsers do not auto-attach custom headers), the SSE endpoint's query parameter token acceptance creates a different risk profile. An attacker on a malicious website could construct an `EventSource` URL pointing to the Rext API with a stolen or session-embedded token, potentially receiving real-time data streams belonging to the victim.

The frontend uses NextAuth (v5.0.0-beta.29) which manages its own session cookies with built-in CSRF token handling. The backend does not set any authentication cookies directly. However, defense-in-depth principles recommend adding CSRF mitigations regardless, especially as the application evolves and new features may introduce cookie-based flows.

---

## Impact

- **Severity:** Low-to-medium. The primary API is protected by JWT Bearer tokens (CSRF-resistant). The SSE endpoint via query parameter is the main attack vector, but exploitation requires the attacker to obtain a valid JWT token first, which limits the practical risk.
- **Affected Users/Flows:** Users connected to real-time SSE streams (notifications, live updates). The SSE token in the query parameter could appear in server access logs and browser history.
- **Blast Radius:** Limited to SSE connections. All non-SSE endpoints use `Authorization` header and are not affected by CSRF.

---

## Recommended Solution

### Step 1: Add Origin/Referer validation for SSE endpoints

```python
# File: src/api/security/dependencies.py
# Add the following imports at the top of the file:
from urllib.parse import urlparse

from src.api.config import get_settings

# Add this helper function before get_current_user_sse:
def _validate_request_origin(request: Request) -> bool:
    """
    Validate that the request originates from an allowed origin.
    Checks the Origin header first, falls back to Referer.
    Returns True if the origin is allowed, False otherwise.
    """
    settings = get_settings()
    allowed_origins = settings.allowed_origins_list

    origin = request.headers.get("origin")
    if origin:
        return origin in allowed_origins

    referer = request.headers.get("referer")
    if referer:
        parsed = urlparse(referer)
        referer_origin = f"{parsed.scheme}://{parsed.netloc}"
        return referer_origin in allowed_origins

    # No Origin or Referer header — this could be a same-origin request
    # or a direct API call. Allow it since the token is still validated.
    return True
```

### Step 2: Add origin check to `get_current_user_sse`

```python
# File: src/api/security/dependencies.py
# Update the get_current_user_sse function signature to include Request:
async def get_current_user_sse(
    request: Request,
    authorization: str = Header(None),
    token: str = Query(None),
    db: AsyncSession = Depends(get_async_db)
) -> Auth.types.MinimalUserDict:
    """
    Authentication dependency for SSE that supports both Header and Query param.
    EventSource API does not support custom headers, so we allow passing token via query param.
    """
    from src.api.middleware.exceptions import (
        RextAuthenticationException,
        TokenExpiredException,
    )

    # Validate request origin for CSRF protection on SSE connections
    if token and not _validate_request_origin(request):
        raise RextAuthenticationException(
            message="Cross-origin SSE request rejected",
            context={"reason": "Origin validation failed"}
        )

    # ... rest of existing function unchanged
```

### Step 3: Add missing security headers to SecurityHeadersMiddleware

```python
# File: src/api/middleware/security.py
# Replace the entire dispatch method:
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Content Security Policy — restrict resource loading
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"

        # Referrer Policy — limit information sent in Referer header
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions Policy — disable unnecessary browser features
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        # HSTS (only for HTTPS)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Remove deprecated X-XSS-Protection header (no longer supported by modern browsers)
        # Previously: response.headers["X-XSS-Protection"] = "1; mode=block"

        return response
```

Note: The `X-XSS-Protection: 1; mode=block` header is deprecated and no longer supported by modern browsers (Chrome removed it in 2019). It should be removed in favor of `Content-Security-Policy`. This aligns with Finding 21 (Missing Security Headers, extraction order 19) from the same audit report.

### Step 4: Ensure CORS origin list is restrictive

Verify that `settings.allowed_origins_list` contains only the specific frontend origins (not wildcards). The current configuration at `src/api/server.py:166` uses `settings.allowed_origins_list` which is good — just ensure the environment variable does not contain `*`.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/server.py` | 164-172 | CORS middleware configuration — `allow_credentials=True` means CORS relies on origin whitelist |
| `src/api/config.py` | 53-58 | `FRONTEND_URL` and `CORS_ALLOWED_ORIGINS` settings — controls which origins are allowed |
| `src/api/routes/events/sse_test_route.py` | 73 | SSE test route — also uses query parameter tokens |
| `src/api/middleware/security.py` | 32 | `X-XSS-Protection` header is deprecated — related to Finding 21 (extraction order 19) |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server
2. From a different origin (e.g., `http://evil.com`), attempt to create an EventSource connection: `new EventSource('https://your-api.com/api/events/stream?token=<valid-token>')` — this should succeed (no CSRF protection)
3. Verify no `Content-Security-Policy` or `Referrer-Policy` headers are present in API responses

### After Fix (Verify the Solution):
1. Verify the Origin/Referer validation rejects SSE connections from unauthorized origins
2. From the legitimate frontend origin, verify SSE connections still work normally
3. From a different origin without `Origin`/`Referer` headers (e.g., curl), verify direct API calls still work (they provide their own token)
4. Check response headers include `Content-Security-Policy`, `Referrer-Policy`, and `Permissions-Policy`
5. Verify `X-XSS-Protection` header is no longer present
6. Test CORS preflight requests still work correctly for the configured origins

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "sse or security or middleware or cors" --no-header
```

---

## Acceptance Criteria

- [ ] SSE endpoint validates Origin/Referer header when token is provided via query parameter
- [ ] Unauthorized cross-origin SSE requests are rejected with appropriate error
- [ ] Legitimate frontend SSE connections continue to work
- [ ] `Content-Security-Policy` header added to all responses
- [ ] `Referrer-Policy` header added to all responses
- [ ] `Permissions-Policy` header added to all responses
- [ ] Deprecated `X-XSS-Protection` header removed
- [ ] CORS configuration verified to use explicit origin list (no wildcards)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) — comprehensive CSRF prevention guidance including SameSite cookies, token patterns, and custom headers
- **Security Advisory:** [OWASP Cross-Site Request Forgery](https://owasp.org/www-community/attacks/csrf) — CSRF attack description and classification
- **Migration Guide:** N/A
- **Best Practice Reference:** [MDN: Cross-site request forgery (CSRF)](https://developer.mozilla.org/en-US/docs/Web/Security/Attacks/CSRF) — browser-level CSRF explanation and SameSite cookie guidance (updated Oct 2025)
- **Related Issues/PRs:** [fastapi-csrf-protect on PyPI](https://pypi.org/project/fastapi-csrf-protect/) — FastAPI CSRF middleware library for cookie-based auth (not needed for pure JWT Bearer, but useful reference)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** B1 Finding 21 (Missing Security Headers, extraction order 19) — overlaps with security headers changes in this task; B1 Finding 22 (SSE Token in Query Parameter, extraction order 16) — related SSE security concern
