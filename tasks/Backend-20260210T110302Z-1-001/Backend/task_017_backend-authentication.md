# Task 017: Fix Password Reset Token Using Wrong Token Function (24-Hour Expiry Instead of 30-Minute)

## Metadata
- **Task ID:** TASK-017
- **Source:** Backend Authentication & Authorization Audit (Finding #18 under P2 Medium)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P2 Medium
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `initiate_password_reset()` method in `src/services/auth_service.py:653` calls `create_verification_token()` instead of `create_reset_token()` to generate the password reset token. This is a security bug because `create_verification_token()` creates tokens with a 24-hour expiry (defined at `src/api/security/token_utils.py:138`), while `create_reset_token()` creates tokens with a 30-minute expiry (defined at `token_utils.py:120`). Password reset tokens should have the shortest practical expiry to minimize the attack window if the token is intercepted in transit (email, logs, or network capture).

The OWASP Forgot Password Cheat Sheet recommends password reset tokens expire within 20 minutes, and the OWASP Web Security Testing Guide states it "should rarely be more than an hour." The 30-minute default in `create_reset_token()` is well-aligned with this guidance. The 24-hour expiry from `create_verification_token()` is 48x longer than recommended.

Additionally, the comment on line 652 states `"# Generate reset token (valid 1 hour)"` which is also incorrect — `create_verification_token()` generates a 24-hour token, not 1-hour. This misleading comment compounds the confusion.

The `auth_service.py` import block at lines 42-51 imports `create_verification_token` but does NOT import `create_reset_token`, confirming this was an accidental use of the wrong function rather than a deliberate choice.

There is also a DRY concern: the forgot-password route at `src/api/routes/users/password.py:96-102` creates the reset token directly in the route layer using `create_reset_token(data=reset_data)` (correctly), including `jti` and `email` in the payload. The `initiate_password_reset()` service method is not actually called by any route handler — it is only used in unit tests. However, the service method should still be correct because: (1) it may be called when the code is properly refactored, and (2) the unit tests at `tests/unit/services/test_auth_service.py:570-603` exercise this method and should be testing the correct behavior.

This finding is classified as CWE-640 (Weak Password Recovery Mechanism for Forgotten Password), which has an OWASP risk rating of 8.1 (High).

---

## Current Code

```python
# File: src/services/auth_service.py
# Lines: 42-51 (imports — note create_reset_token is NOT imported)
from src.api.security.token_utils import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    create_verification_token,
    verify_token,
    verify_refresh_token,
    is_token_blacklisted
)
```

```python
# File: src/services/auth_service.py
# Lines: 630-660
    async def initiate_password_reset(self, email: str) -> Tuple[Users, str]:
        """
        Initiate password reset process.

        Args:
            email: User's email address

        Returns:
            Tuple of (user, reset_token)

        Raises:
            ResourceNotFoundException: If user not found
        """
        result = await self.db.execute(select(Users).where(Users.email == email))
        user = result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=email
            )

        # Generate reset token (valid 1 hour)  <-- INCORRECT COMMENT
        reset_token = create_verification_token({"user_id": str(user.id)})  # <-- WRONG FUNCTION

        logger.info(
            f"Password reset initiated for user: {user.id}",
            extra={"email": email}
        )

        return user, reset_token
```

```python
# File: src/api/security/token_utils.py
# Lines: 120-153 (the two token functions for comparison)
def create_reset_token(data: dict, expires_delta: timedelta = timedelta(minutes=30)) -> str:
    """Creates a JWT token for password reset. Defaults to 30 minutes."""
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token

def create_verification_token(data: dict, expires_delta: timedelta = timedelta(hours=24)) -> str:
    """Creates a JWT token for email verification. Defaults to 24 hours."""
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token
```

```python
# File: src/api/routes/users/password.py
# Lines: 96-102 (the CORRECT implementation in the route layer)
        # Generate reset token
        reset_data = {
            "user_id": str(user.id),
            "email": user.email,
            "jti": str(uuid.uuid4())
        }
        reset_token = create_reset_token(data=reset_data)
```

---

## Why This Matters (Context & Reasoning)

Password reset tokens are sensitive one-time credentials sent via email. If an attacker gains access to a user's email (even temporarily), a 24-hour token window gives them ample time to reset the password. With a 30-minute window, the attack must happen almost immediately after the email is sent, significantly reducing the probability of exploitation.

The service method `initiate_password_reset()` is currently not called by any route handler (the route at `password.py:82` handles token creation directly), but it exists in the service layer and is tested in unit tests. If a developer refactors the route to properly delegate to the service (which is the intended architecture), this bug would become active in production.

The risk of NOT fixing this is twofold: (1) any future refactoring that calls this service method will silently introduce a 24-hour token window, and (2) the unit tests are validating incorrect behavior.

---

## Impact

- **Severity:** Password reset tokens would be valid for 24 hours instead of 30 minutes if this service method is called, widening the attack window by 48x. Currently mitigated by the fact that the route layer handles token creation directly.
- **Affected Users/Flows:** Password reset flow — any user who requests a password reset. Currently, the service method is not called from routes, so only unit tests are affected.
- **Blast Radius:** Isolated to the `initiate_password_reset()` service method and its unit tests. The route-level implementation at `password.py` is correct and unaffected.

---

## Recommended Solution

### Step 1: Add `create_reset_token` to imports in auth_service.py

```python
# File: src/services/auth_service.py
# Lines: 42-51
# Replace the import block with:
from src.api.security.token_utils import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    create_reset_token,
    create_verification_token,
    verify_token,
    verify_refresh_token,
    is_token_blacklisted
)
```

### Step 2: Replace `create_verification_token` with `create_reset_token` and fix the comment

```python
# File: src/services/auth_service.py
# Lines: 652-653
# Replace:
#     # Generate reset token (valid 1 hour)
#     reset_token = create_verification_token({"user_id": str(user.id)})
# With:
        # Generate reset token (valid 30 minutes per OWASP recommendation)
        reset_token = create_reset_token(data={
            "user_id": str(user.id),
            "email": user.email,
            "jti": str(uuid.uuid4())
        })
```

Note: The updated payload now includes `email` and `jti` to match the pattern used in the route layer at `password.py:97-101`. The `jti` (JWT ID) enables token revocation and single-use enforcement. You will also need to add `import uuid` at the top of the file if it's not already imported.

### Step 3: Verify the uuid import exists

```python
# File: src/services/auth_service.py
# Check near the top of the file for:
import uuid
# or
from uuid import UUID
# If uuid is not imported, add:
import uuid
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/users/password.py` | 96-102 | Correctly uses `create_reset_token` — this is the currently active code path |
| `src/api/security/token_utils.py` | 120-135, 138-153 | Defines both `create_reset_token` (30min) and `create_verification_token` (24h) |
| `tests/unit/services/test_auth_service.py` | 570-603 | Unit tests for `initiate_password_reset` — may need to be updated if they assert on token expiry |
| `src/services/auth_service.py` | 176 | `register_user` correctly uses `create_verification_token` for email verification (24h is appropriate for verification) |
| `src/services/auth_service.py` | 458 | `resend_verification_email` correctly uses `create_verification_token` (24h is appropriate) |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Call `initiate_password_reset()` directly (e.g., via unit test)
2. Decode the returned JWT token and inspect the `exp` claim
3. Calculate the difference between `exp` and the current time — it should show ~24 hours (the bug)
4. Note that the token payload only contains `user_id` (missing `email` and `jti`)

### After Fix (Verify the Solution):
1. Call `initiate_password_reset()` directly
2. Decode the returned JWT token and inspect the `exp` claim
3. Calculate the difference between `exp` and the current time — it should show ~30 minutes
4. Verify the token payload contains `user_id`, `email`, and `jti`
5. Verify the `jti` is a valid UUID

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/services/test_auth_service.py -v -k "password_reset" --no-header
```

Note: Tests at `test_auth_service.py:570-603` may need to be updated if they mock `create_verification_token` — they should now mock `create_reset_token` instead.

---

## Acceptance Criteria

- [ ] `initiate_password_reset()` calls `create_reset_token()` instead of `create_verification_token()`
- [ ] Reset token expires in 30 minutes (not 24 hours)
- [ ] Reset token payload includes `user_id`, `email`, and `jti` fields
- [ ] Comment on line 652 accurately reflects the token expiry duration
- [ ] `create_reset_token` is properly imported in `auth_service.py`
- [ ] Unit tests for `initiate_password_reset` pass with the updated function call
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) — recommends reset tokens expire within 20 minutes; must be single-use and cryptographically random
- **Security Advisory:** [CWE-640: Weak Password Recovery Mechanism for Forgotten Password](https://cwe.mitre.org/data/definitions/640.html) — CWE classification for password recovery weaknesses including improper token expiry
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP Web Security Testing Guide: Testing for Weak Password Change or Reset Functionalities](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/04-Authentication_Testing/09-Testing_for_Weak_Password_Change_or_Reset_Functionalities) — tokens should rarely be valid for more than 1 hour
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-018 (Reset/Verification Tokens Missing Type Claim — once type claims are added, token confusion between reset and verification tokens becomes impossible), TASK-006 (Forgot-Password Reveals User Existence — related password reset flow security), TASK-004 (Deprecated `datetime.utcnow()` — both `create_reset_token` and `create_verification_token` use deprecated `datetime.utcnow()`)
