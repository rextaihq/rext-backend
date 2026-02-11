# Task 002: Fix OAuth Users Getting Invalid Password Hash Placeholder

## Metadata
- **Task ID:** TASK-002
- **Source:** Authentication & Authorization Audit (Finding #3 under P0 Critical)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P0 Critical
- **Category:** security
- **Effort Estimate:** medium (1-4 hours)

---

## Description

When a new user is created via OAuth (Google, GitHub, etc.) in `src/services/oauth_service.py:183`, the `password_hash` field is set to the string literal `"oauth_no_password"`. This string is not a valid bcrypt hash — bcrypt hashes must match the format `$2b$<cost>$<22-char-salt><31-char-hash>`. The `Users` model (`src/api/models/user_models/users.py:22`) defines `password_hash = Column(String(255), nullable=False)`, so `None` cannot be stored without a schema change.

This creates two distinct problems:

1. **Runtime crash:** If an OAuth-only user triggers any code path that calls `verify_password()` (defined in `src/api/security/token_utils.py:56-67`), the function calls `bcrypt.checkpw(password.encode('utf-8'), "oauth_no_password".encode('utf-8'))`, which raises `ValueError: Invalid salt` (or in bcrypt 4.2.0, a `pyo3_runtime.PanicException` per [pyca/bcrypt#917](https://github.com/pyca/bcrypt/issues/917)). This affects the `/verify-password` endpoint (`src/api/routes/users/password.py:284-348`) which is used for confirming sensitive operations like workspace deletion. It also affects the login flow (`src/services/auth_service.py:238`) if an OAuth user tries to log in with email/password.

2. **Security concern:** The placeholder string `"oauth_no_password"` could theoretically be confused with an actual (weak) password hash by code that doesn't understand the convention. There is no standard sentinel for "no password" — the correct approach is to make the column nullable and use `None`.

The `verify_password` function at `token_utils.py:56-67` has no guard for invalid hash formats. It passes the hash directly to `bcrypt.checkpw` without checking if it's a valid bcrypt hash first. Both call sites (`auth_service.py:238` for login, `user_service.py:566` for password verification) also lack null/invalid hash guards.

---

## Current Code

```python
# File: src/services/oauth_service.py
# Lines: 180-188
                # Create user (no password needed for OAuth-only users)
                user = Users(
                    full_name=full_name,
                    email=provider_email,
                    password_hash="oauth_no_password",  # Placeholder - OAuth users don't need password
                    email_verified=True,  # OAuth email is pre-verified
                    email_verified_at=datetime.utcnow(),
                    avatar_url=provider_avatar_url,
                    created_at=datetime.utcnow()
                )
```

```python
# File: src/api/models/user_models/users.py
# Line: 22
    password_hash = Column(String(255), nullable=False)
```

```python
# File: src/api/security/token_utils.py
# Lines: 56-67
def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verifies that a plain text password matches the hashed password.

    Args:
        password (str): The plain text password.
        hashed_password (str): The hashed password from the database.

    Returns:
        bool: True if the password matches, False otherwise.
    """
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
```

---

## Why This Matters (Context & Reasoning)

The OAuth flow is a primary authentication path for the application. When users sign up via Google or GitHub, they never set a password. However, the current architecture requires a non-null `password_hash`, so a placeholder is used. This placeholder creates a ticking time bomb: any feature that requires password verification (confirming account deletion, changing email, deactivating account) will crash for OAuth-only users.

The `/verify-password` endpoint is specifically designed for confirming sensitive operations. If an OAuth user tries to delete their workspace (which requires password confirmation), the backend will crash with an unhandled `ValueError` rather than returning a helpful error message like "Please set a password first" or "Use OAuth to verify your identity."

Additionally, if an OAuth user attempts to log in via email/password (perhaps not remembering they used OAuth), the `verify_password` call at `auth_service.py:238` will also crash rather than returning "Invalid email or password."

---

## Impact

- **Severity:** `ValueError: Invalid salt` runtime crash whenever an OAuth-only user triggers password verification. This is an unhandled exception that will result in a 500 Internal Server Error.
- **Affected Users/Flows:** All OAuth-registered users who attempt: password verification for sensitive operations, email/password login, password change
- **Blast Radius:** Affects multiple endpoints: `/verify-password`, `/login` (email/password path for OAuth users), `/change-password`

---

## Recommended Solution

This fix requires three coordinated changes: make the column nullable, store `None` for OAuth users, and add guards before password verification.

### Step 1: Make `password_hash` column nullable in the Users model

```python
# File: src/api/models/user_models/users.py
# Change line 22 from:
#   password_hash = Column(String(255), nullable=False)
# To:
    password_hash = Column(String(255), nullable=True)
```

### Step 2: Create an Alembic migration for the schema change

```bash
cd rext-backend
alembic revision --autogenerate -m "make_password_hash_nullable_for_oauth_users"
```

Verify the generated migration contains:

```python
# File: rext-backend/alembic/versions/<generated>_make_password_hash_nullable_for_oauth_users.py
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.alter_column('users', 'password_hash',
                    existing_type=sa.String(255),
                    nullable=True)
    # Update existing OAuth-only users who have the placeholder
    op.execute("UPDATE users SET password_hash = NULL WHERE password_hash = 'oauth_no_password'")

def downgrade():
    # Set a placeholder back for any NULL password_hash before making non-nullable
    op.execute("UPDATE users SET password_hash = 'oauth_no_password' WHERE password_hash IS NULL")
    op.alter_column('users', 'password_hash',
                    existing_type=sa.String(255),
                    nullable=False)
```

### Step 3: Update OAuth service to use `None` instead of placeholder

```python
# File: src/services/oauth_service.py
# Change line 183 from:
#   password_hash="oauth_no_password",  # Placeholder - OAuth users don't need password
# To:
                    password_hash=None,
```

### Step 4: Add null guard in `verify_password` function

```python
# File: src/api/security/token_utils.py
# Replace lines 56-67 with:
def verify_password(password: str, hashed_password: str | None) -> bool:
    """
    Verifies that a plain text password matches the hashed password.

    Args:
        password (str): The plain text password.
        hashed_password (str | None): The hashed password from the database.
            Returns False if None (OAuth-only users without a password).

    Returns:
        bool: True if the password matches, False otherwise.
    """
    if hashed_password is None:
        return False
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
```

### Step 5: Add null guard in `UserService.verify_user_password`

```python
# File: src/services/user_service.py
# Replace lines 562-569 with:
        from src.api.security.token_utils import verify_password

        user = await self.get_user_by_id(user_id)

        if user.password_hash is None:
            return False

        is_valid = verify_password(password, user.password_hash)
        logger.debug(f"Password verification for user {user_id}: {is_valid}")

        return is_valid
```

### Step 6: Run the migration

```bash
cd rext-backend
alembic upgrade head
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/auth_service.py` | `238` | Login flow calls `verify_password(password=password, hashed_password=db_user.password_hash)` — will now safely return `False` for OAuth users instead of crashing |
| `src/services/user_service.py` | `562-569` | `verify_user_password` method — needs null guard added (Step 5) |
| `src/api/routes/users/password.py` | `284-348` | `/verify-password` endpoint — calls `service.verify_user_password()`, now protected by the null guard |
| `src/api/routes/users/password.py` | `230-278` | `/change-password` endpoint — should check if user has a password before allowing change |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a user via OAuth (e.g., Google login)
2. Check the database: `SELECT password_hash FROM users WHERE email = '<oauth-user-email>'` — should show `"oauth_no_password"`
3. Call `POST /api/v1/user/verify-password` with the OAuth user's JWT and any password in the body
4. Observe: 500 Internal Server Error with `ValueError: Invalid salt` in server logs

### After Fix (Verify the Solution):
1. Create a new user via OAuth
2. Check the database: `SELECT password_hash FROM users WHERE email = '<new-oauth-user-email>'` — should show `NULL`
3. Call `POST /api/v1/user/verify-password` with the OAuth user's JWT and any password — should return `401` with "Invalid password" (not a 500 crash)
4. Attempt email/password login with an OAuth-only user — should return "Invalid email or password" (not a 500 crash)
5. Verify that existing email/password users can still log in and verify passwords normally

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "auth or oauth or password" -v
```

---

## Acceptance Criteria

- [ ] `password_hash` column in `Users` model is `nullable=True`
- [ ] Alembic migration created and applied to make column nullable
- [ ] Existing `"oauth_no_password"` placeholder values migrated to `NULL`
- [ ] `oauth_service.py` sets `password_hash=None` for new OAuth users
- [ ] `verify_password()` in `token_utils.py` returns `False` when `hashed_password` is `None`
- [ ] `verify_user_password()` in `user_service.py` has null guard for `password_hash`
- [ ] OAuth users hitting `/verify-password` get a proper error response (not a 500 crash)
- [ ] OAuth users attempting email/password login get "Invalid email or password" (not a crash)
- [ ] Existing email/password users unaffected — login and password verification still work
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [pyca/bcrypt documentation — checkpw](https://github.com/pyca/bcrypt#usage)
- **Security Advisory:** [pyca/bcrypt#917 — PanicException instead of ValueError with invalid salt](https://github.com/pyca/bcrypt/issues/917)
- **Migration Guide:** [Alembic — Auto Generating Migrations](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
- **Best Practice Reference:** [OWASP Authentication Cheat Sheet — Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- **Related Issues/PRs:** [pyca/bcrypt#63 — ValueError: Invalid salt](https://github.com/pyca/bcrypt/issues/63)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-005 (No Password Strength Validation — both touch password handling code paths)
