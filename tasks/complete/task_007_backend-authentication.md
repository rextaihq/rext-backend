# Task 007: Reduce Excessive 24-Hour Access Token Lifetime

## Metadata
- **Task ID:** TASK-007
- **Source:** Backend Authentication & Authorization Audit (Finding #6 under P1 High)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P1 High
- **Category:** security
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The access token lifetime is configured to 1440 minutes (24 hours) in `src/api/config.py` at line 29 via `ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440)`. This value is used in `src/api/security/token_utils.py:83` when creating access tokens: `expires_delta = timedelta(minutes=_settings.ACCESS_TOKEN_EXPIRE_MINUTES)`.

According to OWASP and industry best practices, JWT access tokens should have a lifetime of 5-15 minutes for high-security applications, and no more than 30 minutes for general web applications. The OWASP JWT Cheat Sheet recommends 15-30 minutes as an idle timeout for tokens stored client-side. Curity's JWT best practices guide states: "Set JWT expiration to minutes or hours at maximum — avoid issuing access tokens valid for days or months," because JWTs are self-contained by-value tokens that are very hard to revoke once issued.

A 24-hour access token means that if a token is stolen (via XSS, MITM, log exposure, or the SSE query parameter leakage identified in Finding 22), the attacker has full unrestricted access for an entire day. The token cannot be effectively revoked because JWTs are validated locally without a server roundtrip — the token blacklist check (`is_token_blacklisted` in `token_utils.py:257`) only runs when the token is presented to the server, not when it's used by an attacker against other services.

The refresh token mechanism (7-day expiry, configured at `src/api/config.py:30`) already supports longer sessions. The frontend at `rext-admin/auth.config.ts:345-360` already implements automatic token refresh via the NextAuth JWT callback — when `accessTokenExpires` is past, it calls `/api/v1/user/refresh` with the refresh token to get a new access token. This means reducing the access token lifetime will not break user sessions; the refresh flow will simply trigger more frequently.

However, the frontend hardcodes the access token expiry duration at `auth.config.ts:214-218` as `24 * 60 * 60 * 1000` (24 hours). This hardcoded value must be updated to match the new backend setting, or ideally, the backend should return the token expiry timestamp in the login response so the frontend does not need to guess.

---

## Current Code

```python
# File: src/api/config.py
# Line: 29
ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440, description="Access token expiration (minutes)")
```

```python
# File: src/api/security/token_utils.py
# Lines: 70-92
def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    if expires_delta is None:
        expires_delta = timedelta(minutes=_settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.utcnow() + expires_delta
    jti = str(uuid.uuid4())
    to_encode.update({
        "exp": expire,
        "jti": jti,
        "type": "access"
    })
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token
```

```typescript
// File: rext-admin/auth.config.ts
// Lines: 214-218
const expiryDuration = user.rememberMe
  ? 30 * 24 * 60 * 60 * 1000 // 30 days
  : 24 * 60 * 60 * 1000; // 24 hours
token.accessTokenExpires = Date.now() + expiryDuration;
```

---

## Why This Matters (Context & Reasoning)

Access tokens are the primary authentication credential for every API request in Rext AI. They are sent in the Authorization header on every request and are also used in SSE query parameters (Finding 22). A stolen access token grants the attacker the same privileges as the legitimate user — they can read content, modify workspaces, access billing information, and perform any action the user is authorized for.

The 24-hour window is particularly dangerous because:
1. **No IP binding:** The token is not bound to a specific IP or device, so a stolen token works from anywhere.
2. **Token in query parameters:** The SSE endpoint accepts tokens via query parameters, which appear in server logs, proxy caches, and browser history.
3. **localStorage storage:** The frontend also stores tokens in localStorage (via `auth-store.ts`), which is accessible to any JavaScript running on the same origin (XSS risk).
4. **No real-time revocation:** While a token blacklist exists, it only checks during token verification on the server. An attacker using the token against cached/CDN endpoints or third-party integrations would not be checked.

The refresh token mechanism is already fully functional, making this change low-risk. Users will not notice any difference — the token refresh happens transparently in the background via the NextAuth JWT callback.

---

## Impact

- **Severity:** A stolen access token provides 24 hours of unrestricted access. Reducing to 30 minutes shrinks the attack window by 48x.
- **Affected Users/Flows:** All authenticated users and all API endpoints. The change is transparent — users will not see any difference in their experience.
- **Blast Radius:** System-wide configuration change, but the existing refresh token mechanism handles it seamlessly.

---

## Recommended Solution

### Step 1: Reduce the default access token lifetime in backend config

```python
# File: src/api/config.py
# Replace line 29:
ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="Access token expiration (minutes)")
```

### Step 2: Update the frontend access token expiry calculation

```typescript
// File: rext-admin/auth.config.ts
// Replace lines 214-218 with:
const expiryDuration = user.rememberMe
  ? 30 * 24 * 60 * 60 * 1000 // 30 days (uses refresh token for session persistence)
  : 30 * 60 * 1000; // 30 minutes (matches backend ACCESS_TOKEN_EXPIRE_MINUTES)
token.accessTokenExpires = Date.now() + expiryDuration;
```

### Step 3: Update the refreshed token expiry in the refresh callback

```typescript
// File: rext-admin/auth.config.ts
// In the refreshAccessToken function, find the line that sets accessTokenExpires
// (approximately line 57) and replace:
//   accessTokenExpires: Date.now() + 24 * 60 * 60 * 1000, // 24 hours from now
// with:
accessTokenExpires: Date.now() + 30 * 60 * 1000, // 30 minutes from now (matches backend)
```

### Step 4: Verify the refresh token flow works with shorter access tokens

After making the changes, manually test the full authentication lifecycle:
1. Log in and verify you receive a valid access token
2. Wait for the access token to expire (or temporarily set it to 1 minute for testing)
3. Make an API request and verify the frontend automatically refreshes the token
4. Verify the new access token works for subsequent requests

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/auth.config.ts` | `57` | `refreshAccessToken()` hardcodes `24 * 60 * 60 * 1000` for refreshed token expiry |
| `rext-admin/auth.config.ts` | `214-218` | Login callback hardcodes `24 * 60 * 60 * 1000` for initial token expiry |
| `rext-admin/auth.config.ts` | `409-414` | Session `maxAge` set to 30 days — this controls the NextAuth session cookie, not the JWT access token, so no change needed |
| `rext-admin/stores/auth-store.ts` | Various | Stores tokens in localStorage — no expiry logic here, just storage |
| `src/api/security/token_utils.py` | `83` | Uses `ACCESS_TOKEN_EXPIRE_MINUTES` — automatically picks up the new value |
| `.env` | N/A | If `ACCESS_TOKEN_EXPIRE_MINUTES` is set in `.env`, it will override the default. Check and update if present. |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Decode a valid JWT access token (e.g., using jwt.io or `python -c "import jwt; print(jwt.decode(token, options={'verify_signature': False}))"`)
2. Check the `exp` claim — it should be approximately 24 hours from the current time
3. This confirms the excessive token lifetime

### After Fix (Verify the Solution):
1. Log in to the application
2. Decode the new access token — the `exp` claim should be approximately 30 minutes from the current time
3. Wait for the token to approach expiry (or set `ACCESS_TOKEN_EXPIRE_MINUTES=1` temporarily in `.env` for fast testing)
4. Make an API request in the frontend — the NextAuth JWT callback should automatically call `/api/v1/user/refresh`
5. Verify the application continues working without the user being logged out
6. Check that the new access token also has a 30-minute expiry
7. Test the "Remember Me" flow: log in with remember me checked, verify the session persists across browser restarts (this uses the refresh token, not the access token)

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -k "token or auth or login or refresh" -v
```

---

## Acceptance Criteria

- [ ] Backend `ACCESS_TOKEN_EXPIRE_MINUTES` defaults to 30 instead of 1440
- [ ] Frontend access token expiry calculation uses 30 minutes instead of 24 hours for non-rememberMe users
- [ ] Frontend `refreshAccessToken()` sets expiry to 30 minutes for refreshed tokens
- [ ] Automatic token refresh works correctly — users are not logged out when the access token expires
- [ ] The "Remember Me" flow continues to work (long-lived sessions via refresh tokens)
- [ ] If `ACCESS_TOKEN_EXPIRE_MINUTES` is overridden in `.env`, the override still works
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [OWASP JWT for Java Cheat Sheet — Token Lifetime](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html) — recommends 15-30 minute idle timeout for client-stored tokens
- **Security Advisory:** [OWASP Top 10:2025 A07 — Authentication Failures](https://owasp.org/Top10/2025/A07_2025-Authentication_Failures/)
- **Migration Guide:** N/A
- **Best Practice Reference:** [Curity JWT Best Practices](https://curity.io/resources/learn/jwt-best-practices/) — "Set JWT expiration to minutes or hours at maximum"
- **Related Issues/PRs:** [Token Expiry Best Practices — Zuplo](https://zuplo.com/blog/2025/03/01/token-expiry-best-practices) — documents the 5-15 minute industry standard

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-004 (Deprecated `datetime.utcnow()` in token creation — both modify `token_utils.py`), TASK-001 (Timing attack on API key — both are auth security hardening)
