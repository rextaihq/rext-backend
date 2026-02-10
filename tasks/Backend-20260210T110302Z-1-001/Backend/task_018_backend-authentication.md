# Task 018: Add Type and JTI Claims to Reset and Verification Tokens to Prevent Token Confusion

## Metadata
- **Task ID:** TASK-018
- **Source:** Backend Authentication & Authorization Audit (Finding #19 under P2 Medium)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P2 Medium
- **Category:** security
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `create_reset_token()` and `create_verification_token()` functions in `src/api/security/token_utils.py:120-153` do not include `type` or `jti` (JWT ID) claims in their token payloads. In contrast, `create_access_token()` (line 86-89) includes `"type": "access"` and a `jti`, and `create_refresh_token()` (line 111-114) includes `"type": "refresh"` and a `jti`. This inconsistency creates a token type confusion vulnerability.

Because `verify_token()` at `token_utils.py:176-204` does not validate the `type` claim, any token type can be used interchangeably wherever `verify_token()` is called. Specifically:
- An **access token** could be used as a password reset token (at `auth_service.py:677`)
- An **access token** could be used as an email verification token (at `auth_service.py:387`)
- A **verification token** could be used as a reset token (and vice versa)
- Only `verify_refresh_token()` at `token_utils.py:208` validates the type claim (line 234: `if payload.get("type") != "refresh"`)

This violates RFC 8725 (JSON Web Token Best Current Practices, which updates RFC 7519), which states: "As JWTs are being used by more different protocols in diverse application areas, it becomes increasingly important to prevent cases of JWT tokens that have been issued for one purpose being subverted and used for another." RFC 8725 recommends explicit JWT typing to prevent substitution attacks.

Additionally, without `jti` claims, reset and verification tokens cannot be revoked or blacklisted. The `is_token_blacklisted()` function at `token_utils.py:256` checks the `jti` claim for blacklist status, but since reset/verification tokens have no `jti`, they cannot be individually revoked even if a user reports their email as compromised.

The `verify_token()` function is called in 11 locations across the codebase (`dependencies.py:57,163`, `password.py:145`, `auth.py:643`, `sessions.py:40,107`, `sentry_middleware.py:48`, `auth_service.py:339,387,677`). None of these callers validate the `type` claim of the received token.

---

## Current Code

```python
# File: src/api/security/token_utils.py
# Lines: 70-92 (access token — HAS type and jti)
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

```python
# File: src/api/security/token_utils.py
# Lines: 120-153 (reset and verification tokens — MISSING type and jti)
def create_reset_token(data: dict, expires_delta: timedelta = timedelta(minutes=30)) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})  # <-- Only adds exp, no type or jti
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token

def create_verification_token(data: dict, expires_delta: timedelta = timedelta(hours=24)) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})  # <-- Only adds exp, no type or jti
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token
```

```python
# File: src/api/security/token_utils.py
# Lines: 176-204 (verify_token — does NOT check type)
def verify_token(token: str = Depends(oauth2_scheme)) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        exp = payload.get("exp")
        if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload  # <-- Returns payload without checking type
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )
```

```python
# File: src/services/auth_service.py
# Lines: 387 (verify_email — no type validation)
        payload = verify_token(token)  # <-- Any token type accepted
        user_id = payload.get("user_id")
```

```python
# File: src/services/auth_service.py
# Lines: 677 (complete_password_reset — no type validation)
        payload = verify_token(token)  # <-- Any token type accepted
        user_id = payload.get("user_id")
```

---

## Why This Matters (Context & Reasoning)

Token type confusion is a well-documented JWT vulnerability class. In the Rext application, the password reset and email verification flows both accept any valid JWT as authentication. This means:

1. **Access token as reset token:** If an attacker obtains a user's access token (e.g., from a compromised client, log file, or XSS attack), they could use it to reset the user's password without needing access to the user's email — bypassing the entire "forgot password" flow.

2. **Cross-flow confusion:** A verification token (24-hour expiry) could be used as a reset token, giving the attacker 48x more time than intended (24h vs 30min) to complete a password reset.

3. **No revocation capability:** Without `jti` claims, there is no way to blacklist a specific reset or verification token. If a user reports their email as compromised, the only option is to wait for the token to expire naturally.

The `verify_refresh_token()` function already validates the type claim correctly (line 234), proving the pattern exists in the codebase. The fix simply extends this pattern to `verify_token()` and adds the missing claims to the token creation functions.

---

## Impact

- **Severity:** Token confusion allows an access token to be used as a password reset token, enabling password takeover without email access. Also prevents individual token revocation for reset and verification tokens.
- **Affected Users/Flows:** Password reset flow (`complete_password_reset`), email verification flow (`verify_email`), and any flow that uses `verify_token()` without type validation.
- **Blast Radius:** Affects all 11 callers of `verify_token()` across the codebase. The fix adds optional type validation that can be incrementally enabled per caller.

---

## Recommended Solution

### Step 1: Add `type` and `jti` claims to `create_reset_token`

```python
# File: src/api/security/token_utils.py
# Replace lines 120-135 with:
def create_reset_token(data: dict, expires_delta: timedelta = timedelta(minutes=30)) -> str:
    """
    Creates a JWT token for password reset.

    Args:
        data (dict): The payload to include in the token.
        expires_delta (timedelta, optional): Token expiration time. Defaults to 30 minutes.

    Returns:
        str: The JWT token.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    jti = str(uuid.uuid4())
    to_encode.update({
        "exp": expire,
        "jti": jti,
        "type": "reset"
    })
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token
```

### Step 2: Add `type` and `jti` claims to `create_verification_token`

```python
# File: src/api/security/token_utils.py
# Replace lines 138-153 with:
def create_verification_token(data: dict, expires_delta: timedelta = timedelta(hours=24)) -> str:
    """
    Creates a JWT token for email verification.

    Args:
        data (dict): The payload to include in the token.
        expires_delta (timedelta, optional): Token expiration time. Defaults to 24 hours.

    Returns:
        str: The JWT token.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    jti = str(uuid.uuid4())
    to_encode.update({
        "exp": expire,
        "jti": jti,
        "type": "verification"
    })
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token
```

### Step 3: Add optional `expected_type` parameter to `verify_token`

```python
# File: src/api/security/token_utils.py
# Replace lines 176-204 with:
def verify_token(token: str = Depends(oauth2_scheme), expected_type: str = None) -> dict:
    """
    Verifies the JWT token and decodes the payload.

    Args:
        token (str): JWT token passed via the Authorization header or directly.
        expected_type (str, optional): If provided, validates the token's "type" claim
            matches this value. Use "access", "reset", or "verification".

    Raises:
        HTTPException: If token is invalid, expired, or has wrong type.

    Returns:
        dict: The decoded payload.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        exp = payload.get("exp")
        if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Validate token type if expected_type is specified
        if expected_type is not None:
            token_type = payload.get("type")
            if token_type != expected_type:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid token type: expected '{expected_type}'",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        return payload
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )
```

**Important note on backward compatibility:** The `expected_type` parameter defaults to `None`, which means existing callers that don't pass this parameter will continue to work without type validation. This allows incremental adoption — critical callers (reset, verification) are updated immediately, while other callers can be updated in follow-up tasks.

**Note on FastAPI Depends:** When `verify_token` is used as a FastAPI dependency via `Depends(verify_token)`, only the `token` parameter is injected by FastAPI (via `oauth2_scheme`). The `expected_type` parameter cannot be passed via `Depends()` in this usage pattern. For callers that need type validation, call `verify_token(token, expected_type="reset")` directly instead of using `Depends(verify_token)`. The existing direct callers in `auth_service.py` already call it directly, so this is not a concern for the immediate fix.

### Step 4: Update `verify_email` to validate token type

```python
# File: src/services/auth_service.py
# Line 387
# Replace:
#     payload = verify_token(token)
# With:
        payload = verify_token(token, expected_type="verification")
```

### Step 5: Update `complete_password_reset` to validate token type

```python
# File: src/services/auth_service.py
# Line 677
# Replace:
#     payload = verify_token(token)
# With:
        payload = verify_token(token, expected_type="reset")
```

### Step 6: Update `password.py` reset token verification to validate type

```python
# File: src/api/routes/users/password.py
# Line 145
# Replace:
#     verify_token(payload.token)
# With:
            verify_token(payload.token, expected_type="reset")
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/security/dependencies.py` | 57 | `get_current_user` — calls `verify_token(token)` for access tokens. Future improvement: pass `expected_type="access"` |
| `src/api/security/dependencies.py` | 163 | `get_current_user_sse` — calls `verify_token(auth_token)` for SSE access tokens. Future improvement: pass `expected_type="access"` |
| `src/api/routes/users/auth.py` | 643 | Token refresh flow — calls `verify_token(token)` to verify existing access token |
| `src/api/routes/users/sessions.py` | 40, 107 | Session management — calls `verify_token(token)` for access tokens |
| `src/api/middleware/sentry_middleware.py` | 48 | Sentry context — calls `verify_token(token)` for logging context |
| `src/services/auth_service.py` | 339 | `refresh_access_token` — calls `verify_token(access_token)` to verify existing access token |
| `src/api/security/token_utils.py` | 208-253 | `verify_refresh_token` — already validates `type == "refresh"` (line 234). This is the pattern to follow |
| `tests/unit/services/test_auth_service.py` | - | Unit tests for verify_email and complete_password_reset may need updates to include type claims in mock tokens |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Generate an access token using `create_access_token({"user_id": "test-user-id"})`
2. Call `verify_email(access_token)` — it should succeed (BUG: an access token should not work as a verification token)
3. Call `complete_password_reset(access_token, "NewPassword123")` — it should succeed (BUG: an access token should not work as a reset token)
4. Generate a verification token using `create_verification_token({"user_id": "test-user-id"})`
5. Call `complete_password_reset(verification_token, "NewPassword123")` — it should succeed (BUG: cross-type confusion)

### After Fix (Verify the Solution):
1. Generate an access token using `create_access_token({"user_id": "test-user-id"})`
2. Call `verify_email(access_token)` — it should FAIL with "Invalid token type: expected 'verification'"
3. Call `complete_password_reset(access_token, "NewPassword123")` — it should FAIL with "Invalid token type: expected 'reset'"
4. Generate a verification token using `create_verification_token({"user_id": "test-user-id"})`
5. Call `verify_email(verification_token)` — it should SUCCEED
6. Call `complete_password_reset(verification_token, "NewPassword123")` — it should FAIL with "Invalid token type: expected 'reset'"
7. Generate a reset token using `create_reset_token({"user_id": "test-user-id"})`
8. Call `complete_password_reset(reset_token, "NewPassword123")` — it should SUCCEED
9. Verify the reset token payload contains `type: "reset"` and a valid `jti` UUID
10. Verify the verification token payload contains `type: "verification"` and a valid `jti` UUID
11. Verify existing login/authentication flows still work (access tokens don't break)

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "token or verify or reset or verification or auth" --no-header
```

---

## Acceptance Criteria

- [ ] `create_reset_token` includes `"type": "reset"` and `"jti"` claims in the token payload
- [ ] `create_verification_token` includes `"type": "verification"` and `"jti"` claims in the token payload
- [ ] `verify_token` accepts an optional `expected_type` parameter and validates the `type` claim when provided
- [ ] `verify_email` passes `expected_type="verification"` to `verify_token`
- [ ] `complete_password_reset` passes `expected_type="reset"` to `verify_token`
- [ ] `password.py` reset token verification passes `expected_type="reset"`
- [ ] An access token cannot be used as a reset or verification token
- [ ] A verification token cannot be used as a reset token (and vice versa)
- [ ] Existing authentication flows (login, session management) continue to work unchanged
- [ ] Reset and verification tokens can now be blacklisted via their `jti` claim
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [RFC 8725: JSON Web Token Best Current Practices](https://datatracker.ietf.org/doc/html/rfc8725) — Section 3.11 recommends explicit JWT typing to prevent substitution attacks: "If the JWT could be used in an application context in which it could be confused with other kinds of JWTs, then mitigations MUST be employed to prevent these substitution attacks"
- **Security Advisory:** [RFC 7519: JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519) — Section 4.1.7 defines the `jti` claim for unique token identification and replay prevention
- **Migration Guide:** N/A
- **Best Practice Reference:** [JWT Security Best Practices - Curity](https://curity.io/resources/learn/jwt-best-practices/) — comprehensive checklist including token type validation, JTI for replay prevention, and claim validation
- **Related Issues/PRs:** [RFC 9068: JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html) — mandates explicit typing for OAuth2 access tokens, establishing the pattern for all token types

---

## Dependencies & Related Tasks

- **Depends on:** None (but implementing TASK-017 first ensures `initiate_password_reset` uses the correct token function)
- **Blocks:** None
- **Related:** TASK-017 (Password Reset Uses Wrong Token Function — once type claims are added, using the wrong function would also produce the wrong type claim, making the error detectable), TASK-007 (24-Hour Token Lifetime — complementary security hardening), TASK-011 (token_cleanup.py — reset/verification tokens with `jti` can now be blacklisted via the same mechanism used for access/refresh tokens), TASK-004 (Deprecated `datetime.utcnow()` — the token creation functions also use `datetime.utcnow()` which will be addressed separately)
