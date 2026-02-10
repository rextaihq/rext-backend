# Task 016: Mitigate SSE Token Exposure via Query Parameter Logging and Caching

## Metadata
- **Task ID:** TASK-016
- **Source:** Backend Authentication & Authorization Audit (Finding #22 under P2 Medium)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P2 Medium
- **Category:** security
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `get_current_user_sse()` function in `src/api/security/dependencies.py:128-211` accepts JWT authentication tokens via query parameter (`?token=...`) as a fallback for the browser's native `EventSource` API, which does not support custom HTTP headers. While this is a well-known limitation of the EventSource specification (WHATWG HTML issue #2177 has 178+ upvotes requesting header support), the current implementation creates multiple token exposure vectors.

The most critical exposure is in the request tracking middleware at `src/api/middleware/request_tracker.py:198`. The `_log_request_start()` method logs `"query_params": dict(request.query_params)`, which means every SSE connection made with `?token=<jwt>` has the full JWT written to server logs in plaintext. This violates OWASP's guidance on sensitive data exposure (CWE-598: Use of GET Request Method With Sensitive Query Strings) and the OWASP ASVS requirement 9.3 that sensitive data must not be sent via URL parameters.

Additional exposure vectors include: (1) the full URL with token appearing in reverse proxy access logs (nginx, Cloudflare, etc.), (2) browser history if the URL is navigated directly, and (3) CDN or proxy caches that may cache the URL including query parameters.

Notably, the Rext frontend at `rext-admin/providers/sse-provider.tsx` already uses `@microsoft/fetch-event-source` (line 2) which sends authentication via proper `Authorization` headers (lines 194-198). The frontend does not use the native `EventSource` API and therefore does not need the query parameter token fallback. The `get_current_user_sse` function already supports both `Authorization` header and query parameter (header takes priority at lines 144-153), so the frontend path is already secure. The query parameter path exists as a fallback for clients that cannot set headers.

Per OWASP ASVS 9.3: "All sensitive data is sent to the server in the HTTP message body or headers (i.e., URL parameters are never used to send sensitive data)." The current implementation violates this requirement for any client using the query parameter path.

---

## Current Code

```python
# File: src/api/security/dependencies.py
# Lines: 128-153
async def get_current_user_sse(
    authorization: str = Header(None),
    token: str = Query(None),
    db: AsyncSession = Depends(get_async_db)
) -> Auth.types.MinimalUserDict:
    """
    Authentication dependency for SSE that supports both Header and Query param.
    EventSource API does not support custom headers, so we allow passing token via query param.
    """
    # Import exceptions at runtime to avoid circular dependency
    from src.api.middleware.exceptions import (
        RextAuthenticationException,
        TokenExpiredException,
    )

    auth_token = None
    if authorization:
        try:
            scheme, param = authorization.split()
            if scheme.lower() == "bearer":
                auth_token = param
        except ValueError:
            pass

    if not auth_token and token:
        auth_token = token

    if not auth_token:
        raise RextAuthenticationException(
            message="Authentication required",
            context={"expected_sources": ["Authorization header", "token query param"]}
        )
```

```python
# File: src/api/middleware/request_tracker.py
# Lines: 192-203
logger.info(
    f"Request started: {request.method} {request.url.path}",
    extra={
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "query_params": dict(request.query_params),  # <-- Logs full JWT in plaintext
        "client_ip": self._get_client_ip(request),
        "user_agent": request.headers.get("User-Agent", "unknown"),
        "event_type": "request_start"
    }
)
```

```python
# File: src/api/routes/events/sse_routes.py
# Lines: 68-80 (SSE responses set Cache-Control: no-cache but not no-store)
return EventSourceResponse(
    event_stream_manager.subscribe(operation_id, user_id),
    media_type="text/event-stream",
    headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    },
)
```

---

## Why This Matters (Context & Reasoning)

The SSE (Server-Sent Events) system powers real-time updates in Rext, including content generation progress, pipeline status, and live notifications. The `get_current_user_sse` dependency authenticates these real-time connections. Because the browser's native `EventSource` API cannot send custom headers, the backend accepts tokens via query parameters as a fallback.

However, tokens in URLs are fundamentally less secure than tokens in headers. Server access logs, reverse proxy logs, and CDN logs routinely capture full URLs including query parameters. A single log breach could expose all JWT tokens used for SSE connections, giving attackers access to user sessions. Even with HTTPS, the URL (including query string) is visible to any intermediary that terminates TLS (load balancers, WAFs, CDN edge nodes).

The risk of NOT fixing this is that a log aggregation breach or misconfigured log retention policy could expose active JWT tokens. Given that the current access token lifetime is 24 hours (TASK-007 addresses reducing this), a leaked token provides a substantial attack window.

---

## Impact

- **Severity:** JWT tokens logged in plaintext in server logs via the request tracker middleware. Any log access (authorized or unauthorized) exposes authentication credentials.
- **Affected Users/Flows:** All users with active SSE connections where the token was passed via query parameter. The frontend already uses header-based auth, so the primary risk is from third-party clients or testing tools using the query parameter path.
- **Blast Radius:** Limited to SSE connections using query parameter tokens. Standard API endpoints use `Authorization` header via `get_current_user` and are not affected.

---

## Recommended Solution

### Step 1: Redact sensitive query parameters in the request tracker middleware

```python
# File: src/api/middleware/request_tracker.py
# Add this constant near the top of the file, after imports:

SENSITIVE_QUERY_PARAMS = {"token", "api_key", "password", "secret", "code", "access_token"}


# Then update the _log_request_start method to redact sensitive params:
# Replace the line:
#     "query_params": dict(request.query_params),
# With:

    def _sanitize_query_params(self, query_params: dict) -> dict:
        """Redact sensitive query parameter values before logging."""
        return {
            k: "[REDACTED]" if k.lower() in SENSITIVE_QUERY_PARAMS else v
            for k, v in query_params.items()
        }
```

```python
# File: src/api/middleware/request_tracker.py
# In the _log_request_start method, replace:
#     "query_params": dict(request.query_params),
# With:
        "query_params": self._sanitize_query_params(dict(request.query_params)),
```

Also check and apply the same redaction in `_log_request_success` and `_log_request_error` if they also log query parameters.

### Step 2: Strengthen Cache-Control headers on SSE responses

```python
# File: src/api/routes/events/sse_routes.py
# Replace Cache-Control headers in both EventSourceResponse calls (lines 68-71 and 77-80):
# Change:
#     "Cache-Control": "no-cache",
# To:
        "Cache-Control": "no-cache, no-store, must-revalidate, private",
        "Pragma": "no-cache",
        "X-Accel-Buffering": "no",
```

The `no-store` directive prevents caching of the response entirely (including the URL with token). The `private` directive ensures no shared cache (CDN, proxy) stores the response. `Pragma: no-cache` provides backward compatibility with HTTP/1.0 proxies.

### Step 3: Add a deprecation warning for query parameter token usage

```python
# File: src/api/security/dependencies.py
# After line 152 (if not auth_token and token: auth_token = token), add a warning log:

    if not auth_token and token:
        auth_token = token
        logger.warning(
            "SSE authentication via query parameter is deprecated. "
            "Use Authorization header with @microsoft/fetch-event-source instead.",
            extra={"path": "sse_auth", "method": "query_param"}
        )
```

This creates visibility into which clients still use the query parameter path, enabling a future migration to header-only authentication.

### Step 4: Document the security consideration in the SSE dependency docstring

```python
# File: src/api/security/dependencies.py
# Update the docstring for get_current_user_sse:

async def get_current_user_sse(
    authorization: str = Header(None),
    token: str = Query(None),
    db: AsyncSession = Depends(get_async_db)
) -> Auth.types.MinimalUserDict:
    """
    Authentication dependency for SSE that supports both Header and Query param.

    SECURITY NOTE: Token via query parameter is deprecated due to exposure risks
    (server logs, proxy logs, browser history). The Rext frontend uses
    @microsoft/fetch-event-source which sends tokens via Authorization header.
    Query parameter support is maintained for backward compatibility only.

    Clients should use: Authorization: Bearer <token> header.
    """
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/middleware/request_tracker.py` | 198 | Primary exposure: logs `dict(request.query_params)` including JWT tokens |
| `src/api/routes/events/sse_routes.py` | 68-80 | SSE response headers use `no-cache` but not `no-store` |
| `rext-admin/providers/sse-provider.tsx` | 194-198 | Frontend already sends auth via headers (not affected, but confirms query param is unused by frontend) |
| `src/api/routes/events/sse_test_route.py` | - | SSE test route — verify it doesn't log tokens either |
| `src/api/security/dependencies.py` | 188 | Error handler also logs `str(e)` which could contain token fragments in context |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server with logging enabled
2. Make an SSE connection using the query parameter token: `curl -N "http://localhost:2024/api/v1/events/test-op?token=eyJhbGciOiJIUzI1NiIs..."`
3. Check the server logs — the full JWT token should appear in the `query_params` field of the request log entry
4. Verify the `Cache-Control` header on SSE responses is only `no-cache` (missing `no-store`)

### After Fix (Verify the Solution):
1. Make the same SSE connection with query parameter token
2. Check server logs — the `query_params` field should show `{"token": "[REDACTED]"}` instead of the actual JWT
3. Verify a deprecation warning is logged when query parameter token is used
4. Verify SSE connections via `Authorization` header still work without deprecation warning
5. Verify the `Cache-Control` header on SSE responses includes `no-cache, no-store, must-revalidate, private`
6. Verify the `Pragma: no-cache` header is present on SSE responses

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "sse or events or middleware or request_tracker" --no-header
```

---

## Acceptance Criteria

- [ ] Request tracker middleware redacts `token` (and other sensitive params) from logged query parameters
- [ ] SSE responses include `Cache-Control: no-cache, no-store, must-revalidate, private` and `Pragma: no-cache`
- [ ] Deprecation warning is logged when SSE authentication uses query parameter instead of header
- [ ] SSE authentication via `Authorization` header continues to work without warnings
- [ ] SSE authentication via query parameter continues to work (backward compatibility) with deprecation log
- [ ] No JWT tokens appear in server logs from SSE requests
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [OWASP Information Exposure Through Query Strings in URL](https://owasp.org/www-community/vulnerabilities/Information_exposure_through_query_strings_in_url) — classification of sensitive data in URL query parameters as a vulnerability
- **Security Advisory:** [CWE-598: Use of GET Request Method With Sensitive Query Strings](https://cwe.mitre.org/data/definitions/598.html) — CWE classification for sensitive data in GET query strings
- **Migration Guide:** [@microsoft/fetch-event-source](https://github.com/Azure/fetch-event-source) — fetch-based EventSource alternative that supports custom headers (already used by the Rext frontend)
- **Best Practice Reference:** [OWASP ASVS 9.3: Sensitive Data Not Sent in URL](https://owasp-aasvs.readthedocs.io/en/latest/requirement-9.3.html) — ASVS requirement that sensitive data must be sent in HTTP body or headers, never in URL parameters
- **Related Issues/PRs:** [WHATWG HTML Issue #2177: Setting headers for EventSource](https://github.com/whatwg/html/issues/2177) — the long-standing browser specification issue that prevents native EventSource from supporting custom headers

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-014 (CSRF Mitigation — added origin validation to `get_current_user_sse` and security headers to `SecurityHeadersMiddleware`), TASK-007 (24-Hour Token Lifetime — reducing token lifetime also reduces exposure window for leaked SSE tokens), TASK-018 (Token Type Claims — a dedicated SSE token type would benefit from having a `type: "sse"` claim)
