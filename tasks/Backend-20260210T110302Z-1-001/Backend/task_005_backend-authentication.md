# Task 005: Add Server-Side Password Strength Validation

## Metadata
- **Task ID:** TASK-005
- **Source:** Authentication & Authorization Audit (Finding #5 under P1 High)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P1 High
- **Category:** security
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The backend has zero password strength validation. Any single-character password is accepted and stored. There are three entry points where passwords are set or changed, and none of them validate password strength:

1. **`AuthService.register_user()`** (`src/services/auth_service.py:78-120`) — New user registration. The password is passed directly to `hash_password()` at line 120 with no validation.

2. **`AuthService.complete_password_reset()`** (`src/services/auth_service.py:685-707`) — Password reset completion. The new password is passed directly to `hash_password()` at line 698 with no validation.

3. **`UserService.change_password()`** (`src/services/user_service.py:152-201`) — Password change for existing users. Checks that the current password is correct and the new password is different, but does not validate the new password's strength.

4. **`UserService.reset_user_password()`** (`src/services/user_service.py:520-542`) — Another password reset path. Passes the new password directly to `hash_password()` at line 537 with no validation.

The frontend does enforce password validation via Zod schemas in `rext-admin/schemas/auth-schemas.ts` and `rext-admin/schemas/profile-schemas.ts`:
- **Signup/Reset:** min 8 chars, at least one uppercase, one lowercase, one number
- **Change Password:** same as above plus at least one special character

However, frontend validation is easily bypassed by calling the API directly (via curl, Postman, or any HTTP client). The backend must enforce its own validation rules as a defense-in-depth measure.

**NIST SP 800-63B Revision 4 (August 2024) considerations:** The latest NIST guidelines have shifted away from mandatory complexity rules (uppercase, lowercase, digit, special character), instead recommending: minimum 15 characters (when password is the sole authenticator), no forced rotation, and screening against known breached passwords. However, since this application uses JWTs (not password-only auth), and the frontend already enforces composition rules, the recommendation here is to match the frontend's existing rules for consistency while noting the NIST guidance for future consideration.

---

## Current Code

```python
# File: src/services/auth_service.py
# Lines: 78-120 (register_user — no password validation)
    async def register_user(
        self,
        email: str,
        password: str,
        full_name: str
    ) -> Tuple[Users, str]:
        # ... email uniqueness check ...

        # Hash password — NO validation before hashing
        hashed_pwd = hash_password(password)
```

```python
# File: src/services/auth_service.py
# Lines: 697-698 (complete_password_reset — no password validation)
        # Hash and update password — NO validation before hashing
        hashed_pwd = hash_password(new_password)
        user.password_hash = hashed_pwd
```

```python
# File: src/services/user_service.py
# Lines: 194-196 (change_password — validates old password, but NOT new password strength)
        # Hash new password — NO strength validation
        new_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        user.password_hash = new_hash.decode('utf-8')
```

```python
# File: src/services/user_service.py
# Lines: 536-537 (reset_user_password — no password validation)
        # Update password — NO validation before hashing
        user.password_hash = hash_password(new_password)
```

---

## Why This Matters (Context & Reasoning)

Password validation on the frontend provides a good user experience but offers no security guarantee. Any API endpoint that accepts a password can be called directly without going through the frontend. An attacker could:

1. Call `POST /api/v1/user/register` with `{"password": "a"}` — account created with a 1-character password
2. Call `POST /api/v1/user/change-password` with `{"new_password": "1"}` — existing user's password changed to a single digit
3. Call `POST /api/v1/user/complete-reset` with a weak password — password reset to something trivially guessable

Weak passwords are the most common vector for account takeover attacks. The backend is the system boundary and must enforce password policy regardless of what the client does. This is a fundamental principle of input validation: never trust the client.

Additionally, bcrypt 5.0+ raises a `ValueError` for passwords longer than 72 bytes (previously silently truncated). Adding server-side validation provides an opportunity to also enforce a maximum length to prevent this error.

---

## Impact

- **Severity:** Any user can set an arbitrarily weak password (including a single character) by bypassing frontend validation. This makes accounts vulnerable to brute-force and credential-stuffing attacks.
- **Affected Users/Flows:** User registration, password change, and password reset flows
- **Blast Radius:** All user accounts. If a user sets a weak password via direct API call, their account and all associated workspaces/content are at risk.

---

## Recommended Solution

Create a reusable password validation utility and call it from all four password-setting entry points. Match the frontend's existing rules for consistency, with an awareness of NIST SP 800-63B recommendations for future evolution.

### Step 1: Create password validation utility

```python
# File: src/utils/password_utils.py (new file)
import re
from src.api.middleware.exceptions import RextValidationException


# Password policy constants
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 72  # bcrypt truncates at 72 bytes


def validate_password_strength(password: str) -> None:
    """
    Validate password meets minimum strength requirements.

    Requirements (matching frontend validation):
    - Minimum 8 characters
    - Maximum 72 characters (bcrypt limit)
    - At least one uppercase letter (A-Z)
    - At least one lowercase letter (a-z)
    - At least one digit (0-9)

    Args:
        password: Plain text password to validate

    Raises:
        RextValidationException: If password does not meet requirements
    """
    errors = []

    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")

    if len(password) > MAX_PASSWORD_LENGTH:
        errors.append(f"Password must be at most {MAX_PASSWORD_LENGTH} characters")

    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")

    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")

    if not re.search(r'\d', password):
        errors.append("Password must contain at least one number")

    if errors:
        raise RextValidationException(
            message="Password does not meet strength requirements",
            field_errors={"password": errors}
        )
```

### Step 2: Add validation to `AuthService.register_user()`

```python
# File: src/services/auth_service.py
# Add import at top of file (near other utility imports):
from src.utils.password_utils import validate_password_strength

# Add validation before hashing in register_user() (before line 120):
        # Validate password strength
        validate_password_strength(password)

        # Hash password
        hashed_pwd = hash_password(password)
```

### Step 3: Add validation to `AuthService.complete_password_reset()`

```python
# File: src/services/auth_service.py
# Add validation before hashing in complete_password_reset() (before line 698):
        # Validate new password strength
        validate_password_strength(new_password)

        # Hash and update password
        hashed_pwd = hash_password(new_password)
```

### Step 4: Add validation to `UserService.change_password()`

```python
# File: src/services/user_service.py
# Add import at top of file:
from src.utils.password_utils import validate_password_strength

# Add validation after the "new password must be different" check (after line 192):
        # Validate new password strength
        validate_password_strength(new_password)

        # Hash new password
        new_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
```

### Step 5: Add validation to `UserService.reset_user_password()`

```python
# File: src/services/user_service.py
# Add validation before hashing in reset_user_password() (before line 537):
        # Validate new password strength
        validate_password_strength(new_password)

        # Update password
        user.password_hash = hash_password(new_password)
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/schemas/auth-schemas.ts` | `10-16` | Frontend Zod schema with password rules — backend should match these rules |
| `rext-admin/schemas/profile-schemas.ts` | `23-41` | Frontend change-password schema — adds special character requirement (backend does not enforce this for consistency with signup rules) |
| `src/api/routes/users/auth.py` | `78-130` | Registration route handler — calls `register_user()`, will now receive `RextValidationException` for weak passwords |
| `src/api/routes/users/password.py` | `160-278` | Password change/reset route handlers — will now receive validation exceptions |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Call `POST /api/v1/user/register` with body:
   ```json
   {"email": "test@example.com", "password": "a", "full_name": "Test"}
   ```
2. Observe: Registration succeeds with a 1-character password (no validation error)

### After Fix (Verify the Solution):
1. Call `POST /api/v1/user/register` with a weak password (`"a"`) — should return 400 with "Password does not meet strength requirements" and list of violations
2. Call `POST /api/v1/user/register` with `"password"` (no uppercase, no digit) — should return 400
3. Call `POST /api/v1/user/register` with `"Password1"` (valid: 8+ chars, uppercase, lowercase, digit) — should succeed
4. Call `POST /api/v1/user/change-password` with new password `"weak"` — should return 400
5. Call `POST /api/v1/user/complete-reset` with new password `"abc"` — should return 400
6. Call with a password longer than 72 characters — should return 400 with max length error
7. Verify existing registration with strong passwords still works

### Edge Cases:
1. Password of exactly 8 characters with all required character types — should succeed
2. Password of exactly 72 characters — should succeed
3. Password of 73 characters — should fail with max length error
4. Password with only spaces — should fail (no uppercase, no lowercase letter if all spaces, no digit)
5. Unicode passwords (e.g., with accented characters) — should work if they contain ASCII uppercase, lowercase, and digits

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "register or password or auth" -v
```

---

## Acceptance Criteria

- [ ] New file `src/utils/password_utils.py` created with `validate_password_strength()` function
- [ ] `validate_password_strength()` enforces: min 8 chars, max 72 chars, at least one uppercase, one lowercase, one digit
- [ ] `AuthService.register_user()` calls `validate_password_strength()` before hashing
- [ ] `AuthService.complete_password_reset()` calls `validate_password_strength()` before hashing
- [ ] `UserService.change_password()` calls `validate_password_strength()` before hashing
- [ ] `UserService.reset_user_password()` calls `validate_password_strength()` before hashing
- [ ] Weak passwords are rejected with clear error messages listing all violations
- [ ] Strong passwords (matching frontend rules) are accepted
- [ ] `RextValidationException` is raised (not `HTTPException`) for consistency with the service layer
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [OWASP Authentication Cheat Sheet — Password Strength Controls](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#implement-proper-password-strength-controls)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [NIST SP 800-63B — Digital Identity Guidelines](https://pages.nist.gov/800-63-3/sp800-63b.html)
- **Related Issues/PRs:** [NIST SP 800-63B Revision 4 — Updated Password Guidelines (2024)](https://www.enzoic.com/blog/nist-sp-800-63b-rev4/)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-002 (OAuth password hash placeholder — both touch password handling code. After TASK-002 is implemented, OAuth users won't have passwords, so password validation won't apply to them)
