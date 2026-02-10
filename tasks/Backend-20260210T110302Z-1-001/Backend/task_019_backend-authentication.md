# Task 019: Add Missing Security Headers and Remove Deprecated X-XSS-Protection

## Metadata
- **Task ID:** TASK-019
- **Source:** Backend Authentication & Authorization Audit (Finding #21 under P2 Medium)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P2 Medium
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `SecurityHeadersMiddleware` in `src/api/middleware/security.py` adds four security headers to all API responses, but it is missing several important headers recommended by the OWASP Secure Headers Project (OSHP), and it includes a deprecated header that can actually introduce vulnerabilities.

**Currently present:**
- `X-Content-Type-Options: nosniff` — Correct and recommended
- `X-Frame-Options: DENY` — Correct, though `frame-ancestors 'none'` in CSP is the modern replacement
- `X-XSS-Protection: 1; mode=block` — **Deprecated and potentially harmful**
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` — Correct (HTTPS only)

**Missing (recommended by OWASP):**
- `Content-Security-Policy` — The most critical missing header. Even for a REST API that only returns JSON, a CSP of `default-src 'none'; frame-ancestors 'none'` prevents response content from being interpreted as HTML/JS if a browser somehow renders the API response directly.
- `Referrer-Policy` — Controls how much referrer information is sent with requests originating from the page. Without this, the browser uses its default policy, which may leak full URLs (including query parameters containing tokens — related to TASK-016).
- `Permissions-Policy` — Restricts which browser features (camera, microphone, geolocation) can be used. While less relevant for a pure API, it is a defense-in-depth measure if the API response is ever rendered in a browser context.

**Deprecated header to remove:**
- `X-XSS-Protection: 1; mode=block` — This header was deprecated by all major browsers. Chrome removed its XSS Auditor in 2019 (Chrome 78). The OWASP Secure Headers Project recommends setting this to `0` or removing it entirely, because the XSS Auditor has known bypasses and can actually create XSS vulnerabilities in otherwise safe pages. The replacement is `Content-Security-Policy` with appropriate directives.

**Note:** TASK-014 (CSRF Mitigation, already extracted) included these same security header changes in its "Step 3: Add missing security headers to SecurityHeadersMiddleware." If TASK-014 has already been implemented, this task may be partially or fully resolved. However, TASK-019 is the canonical task for this finding and provides more detailed guidance, including API-specific CSP configuration and the rationale for each header choice. Verify whether TASK-014's Step 3 was implemented before starting this task.

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
    """
    Middleware to add security headers to all responses.

    Headers added:
    - X-Content-Type-Options: Prevents MIME type sniffing
    - X-Frame-Options: Prevents clickjacking
    - X-XSS-Protection: Enables XSS filter in browsers
    - Strict-Transport-Security: Forces HTTPS (only on HTTPS requests)
    """

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

---

## Why This Matters (Context & Reasoning)

Security headers are a defense-in-depth mechanism. While the Rext backend is primarily a REST API serving JSON responses, there are scenarios where these headers provide meaningful protection:

1. **Content-Security-Policy:** If an API endpoint ever returns HTML content (error pages, documentation endpoints, or if a browser navigates directly to an API URL), CSP prevents the browser from executing any scripts or loading external resources. The `frame-ancestors 'none'` directive also replaces the older `X-Frame-Options: DENY` approach with the modern standard.

2. **Referrer-Policy:** Without this header, browsers may send the full URL (including query parameters) in the `Referer` header when making subsequent requests. This is directly related to TASK-016's finding about SSE tokens in query parameters — if a page loaded via the API makes a request to another origin, the full URL (including `?token=...`) could leak via the Referer header.

3. **X-XSS-Protection removal:** The XSS Auditor was designed to detect reflected XSS attacks, but it has known bypasses and can actually be weaponized to selectively block parts of a page's content, potentially creating new vulnerabilities. All major browsers have removed support, and the OWASP recommendation is `X-XSS-Protection: 0` or simply omitting the header.

The OWASP Secure Headers Project confirms these headers are applicable to both web applications and web APIs: "The headers proposed can be applied both in the context of a classic web application and in that of a web API."

---

## Impact

- **Severity:** Missing defense-in-depth headers. The `X-XSS-Protection: 1; mode=block` header could potentially create XSS vulnerabilities in edge cases where API responses are rendered by older browsers.
- **Affected Users/Flows:** All API responses are missing CSP, Referrer-Policy, and Permissions-Policy headers. All API responses include the deprecated X-XSS-Protection header.
- **Blast Radius:** Global — the `SecurityHeadersMiddleware` is applied to every API response via `src/api/server.py:151`.

---

## Recommended Solution

### Step 1: Replace the entire `dispatch` method in `SecurityHeadersMiddleware`

```python
# File: src/api/middleware/security.py
# Replace the entire file contents with:
"""
Security Headers Middleware

Adds security-related HTTP headers to all responses.
Based on OWASP Secure Headers Project recommendations.
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.

    Headers added:
    - X-Content-Type-Options: Prevents MIME type sniffing
    - X-Frame-Options: Prevents clickjacking (legacy, superseded by CSP frame-ancestors)
    - Content-Security-Policy: Restricts resource loading and framing
    - Referrer-Policy: Controls Referer header leakage
    - Permissions-Policy: Restricts browser feature access
    - Strict-Transport-Security: Forces HTTPS (only on HTTPS requests)

    Headers removed (deprecated):
    - X-XSS-Protection: Removed per OWASP recommendation (can cause vulnerabilities)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking (legacy header, kept for older browsers)
        response.headers["X-Frame-Options"] = "DENY"

        # Content Security Policy — restrict all resource loading for API responses
        # default-src 'none' blocks all resource loading (appropriate for JSON API)
        # frame-ancestors 'none' prevents framing (modern replacement for X-Frame-Options)
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )

        # Referrer Policy — prevent leaking full URLs (including query params) in Referer header
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions Policy — disable unnecessary browser features
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        # HSTS (only for HTTPS)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # Note: X-XSS-Protection is intentionally NOT set.
        # The XSS Auditor is deprecated (Chrome removed it in v78, 2019) and can
        # create XSS vulnerabilities in otherwise safe pages. CSP is the replacement.
        # See: https://owasp.org/www-project-secure-headers/

        return response
```

### Step 2: Verify the middleware is registered in server.py

```python
# File: src/api/server.py
# Line ~151 — should already have:
app.add_middleware(SecurityHeadersMiddleware)
# No changes needed here — the middleware registration is already correct.
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/server.py` | ~151 | Registers `SecurityHeadersMiddleware` — no changes needed |
| `src/api/routes/events/sse_routes.py` | 68-80 | SSE responses set their own `Cache-Control` headers — verify CSP doesn't interfere with `text/event-stream` media type |
| TASK-014 | Step 3 | Already included these same header changes — verify if already implemented to avoid duplicate work |
| `src/api/middleware/request_tracker.py` | - | Logs requests — verify it doesn't log response headers containing sensitive values |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server
2. Make any API request: `curl -v http://localhost:2024/api/v1/health`
3. Inspect the response headers:
   - Verify `X-XSS-Protection: 1; mode=block` IS present (deprecated, should be removed)
   - Verify `Content-Security-Policy` is NOT present
   - Verify `Referrer-Policy` is NOT present
   - Verify `Permissions-Policy` is NOT present

### After Fix (Verify the Solution):
1. Make the same API request: `curl -v http://localhost:2024/api/v1/health`
2. Inspect the response headers:
   - `X-Content-Type-Options: nosniff` — should be present
   - `X-Frame-Options: DENY` — should be present
   - `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` — should be present
   - `Referrer-Policy: strict-origin-when-cross-origin` — should be present
   - `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()` — should be present
   - `X-XSS-Protection` — should NOT be present
3. Verify SSE connections still work correctly (CSP should not interfere with `text/event-stream` responses)
4. Verify the frontend application can still make API calls without CORS issues (CSP does not affect CORS)
5. Check HTTPS requests include `Strict-Transport-Security`

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "middleware or security or headers" --no-header
```

---

## Acceptance Criteria

- [ ] `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` header added to all responses
- [ ] `Referrer-Policy: strict-origin-when-cross-origin` header added to all responses
- [ ] `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()` header added to all responses
- [ ] `X-XSS-Protection` header is no longer set on any response
- [ ] `X-Content-Type-Options: nosniff` remains present
- [ ] `X-Frame-Options: DENY` remains present
- [ ] `Strict-Transport-Security` remains present on HTTPS responses
- [ ] SSE streams continue to work correctly with the new headers
- [ ] Frontend application functions normally (no CORS or CSP conflicts)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [OWASP Secure Headers Project](https://owasp.org/www-project-secure-headers/) — the authoritative reference for HTTP security headers, including recommended values and headers to remove
- **Security Advisory:** [OWASP HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html) — comprehensive guidance on security headers with rationale for each recommendation
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html) — CSP configuration guidance including API-specific recommendations
- **Related Issues/PRs:** [VulnAPI Security Headers Documentation](https://vulnapi.cerberauth.com/docs/best-practices/security-headers) — API-specific security header recommendations including `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` for REST APIs

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-014 (CSRF Mitigation — Step 3 of TASK-014 already recommended these same header changes; if TASK-014 was fully implemented, this task may be resolved. Check before starting.), TASK-016 (SSE Token in Query Parameter — the `Referrer-Policy` header helps prevent token leakage via the Referer header for SSE connections using query parameter tokens)
