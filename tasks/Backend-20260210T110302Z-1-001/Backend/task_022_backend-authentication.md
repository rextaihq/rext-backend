# Task 022: Refactor verify_token to Separate Dependency and Direct Call Functions

## Metadata
- **Task ID:** TASK-022
- **Source:** B1 - Authentication & Authorization (Finding #14 under P2 Medium)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `verify_token` function in `src/api/security/token_utils.py` (line 176) is defined with a dual-purpose signature that serves both as a FastAPI dependency and as a directly callable function. The current signature is:

```python
def verify_token(token: str = Depends(oauth2_scheme)) -> dict:
```

This design creates confusion because the `Depends(oauth2_scheme)` default parameter is only meaningful when the function is used as a FastAPI dependency injected into route handlers. When called directly (as it is in `auth_service.py:339` and `sessions.py:40,107`), the `Depends()` wrapper is completely ignored, and a raw token string must be passed explicitly.

The problem is not that the code doesn't work—it does. The issue is maintainability and clarity:

1. **Misleading signature:** A developer seeing `Depends(oauth2_scheme)` as a default might incorrectly assume the function automatically extracts tokens when called directly.
2. **Inconsistent usage patterns:** Some code uses it as a dependency (via `Depends(verify_token)`), while other code calls it directly with `verify_token(token)`.
3. **Testing complexity:** Mocking the function requires understanding both usage contexts.
4. **Violation of Single Responsibility:** The function tries to be two things—a pure utility function and a FastAPI dependency.

The modern FastAPI best practice is to use `Annotated` types for dependencies and keep utility functions separate from dependency injection concerns.

---

## Current Code

```python
# File: rext-backend/src/api/security/token_utils.py
# Lines: 175-204
# verify password
def verify_token(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Verifies the JWT token and decodes the payload.

    Args:
        token (str): JWT token passed via the Authorization header.

    Raises:
        HTTPException: If token is invalid or expired.

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
        return payload
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )
```

### Current Usage Patterns

**As direct function call:**
```python
# File: rext-backend/src/services/auth_service.py
# Line: 339
access_payload = verify_token(access_token)

# File: rext-backend/src/api/routes/users/sessions.py
# Lines: 40, 107
current_payload = verify_token(token)
```

**As dependency (implied via get_current_user):**
```python
# File: rext-backend/src/api/security/dependencies.py
# The verify_token function is not directly used as Depends() in routes,
# but get_current_user uses oauth2_scheme directly
```

---

## Why This Matters (Context & Reasoning)

The JWT verification logic is security-critical code that is called on every authenticated request. Having a confusing API increases the risk of misuse:

1. **Future developers** might call `verify_token()` without arguments, expecting the `Depends()` to work, leading to unexpected errors.
2. **Code reviews** become harder when the function's purpose is ambiguous.
3. **Testing** requires understanding the dual behavior, complicating unit test setup.
4. **Dependency injection** best practices recommend using `Annotated` types (FastAPI 0.95+) to make dependencies explicit and type-safe.

The codebase also has a similar comment issue—line 175 says `# verify password` but the function is `verify_token`. This suggests copy-paste errors that further reduce code clarity.

---

## Impact

- **Severity:** Low immediate impact (code works), but medium maintenance burden and potential for future bugs.
- **Affected Users/Flows:** All authenticated API endpoints rely on token verification.
- **Blast Radius:** Changes to this function affect the entire authentication system, requiring careful testing.

---

## Recommended Solution

Refactor into two separate, single-purpose functions:

1. **`decode_and_verify_token(token: str) -> dict`** — Pure utility function for direct calls
2. **`VerifiedToken` (Annotated type)** — FastAPI dependency for route injection

### Step 1: Create the Pure Utility Function

```python
# File: rext-backend/src/api/security/token_utils.py
# Add after line 204 (after current verify_token)

def decode_and_verify_token(token: str) -> dict:
    """
    Decode and verify a JWT token.

    This is a pure utility function for direct calls. For FastAPI route
    dependencies, use the VerifiedToken annotated type instead.

    Args:
        token: The JWT token string to verify.

    Returns:
        dict: The decoded token payload.

    Raises:
        HTTPException: If token is invalid, expired, or malformed.
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
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )
```

### Step 2: Create the Annotated Type for Dependencies

```python
# File: rext-backend/src/api/security/token_utils.py
# Add at the top after imports (around line 31)

from typing import Annotated

# ... existing code ...

# Add after oauth2_scheme definition (around line 41)

def _get_verified_token(token: str = Depends(oauth2_scheme)) -> dict:
    """
    FastAPI dependency that extracts and verifies the JWT token from the
    Authorization header.

    This is an internal function. Use VerifiedToken type annotation in routes.
    """
    return decode_and_verify_token(token)


# Type alias for use in route function signatures
VerifiedToken = Annotated[dict, Depends(_get_verified_token)]
```

### Step 3: Keep Original Function for Backward Compatibility (Deprecate)

```python
# File: rext-backend/src/api/security/token_utils.py
# Replace lines 175-204

import warnings

def verify_token(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Verifies the JWT token and decodes the payload.

    .. deprecated::
        This function has a confusing dual-purpose signature.
        - For direct calls, use decode_and_verify_token(token) instead.
        - For FastAPI dependencies, use VerifiedToken type annotation.

    Args:
        token (str): JWT token passed via the Authorization header.

    Raises:
        HTTPException: If token is invalid or expired.

    Returns:
        dict: The decoded payload.
    """
    warnings.warn(
        "verify_token() is deprecated. Use decode_and_verify_token() for direct calls "
        "or VerifiedToken for FastAPI dependencies.",
        DeprecationWarning,
        stacklevel=2
    )
    return decode_and_verify_token(token)
```

### Step 4: Update Direct Call Sites

```python
# File: rext-backend/src/services/auth_service.py
# Line 339 - Replace:
access_payload = verify_token(access_token)
# With:
access_payload = decode_and_verify_token(access_token)

# File: rext-backend/src/api/routes/users/sessions.py
# Line 40 - Replace:
current_payload = verify_token(token)
# With:
current_payload = decode_and_verify_token(token)

# Line 107 - Replace:
current_payload = verify_token(token)
# With:
current_payload = decode_and_verify_token(token)
```

### Step 5: Update Import Statements

```python
# File: rext-backend/src/services/auth_service.py
# Update import (around line 42-50):
from src.api.security.token_utils import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    create_verification_token,
    decode_and_verify_token,  # Changed from verify_token
    verify_refresh_token,
    is_token_blacklisted
)

# File: rext-backend/src/api/routes/users/sessions.py
# Update import (around line 11):
from src.api.security.token_utils import decode_and_verify_token  # Changed from verify_token
```

### Step 6: Fix the Misleading Comment

```python
# File: rext-backend/src/api/security/token_utils.py
# Line 175 - Remove or fix the comment "# verify password"
# It should be removed entirely since the function name is self-documenting
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/services/auth_service.py` | 42-50, 339 | Import and direct call to verify_token |
| `rext-backend/src/api/routes/users/sessions.py` | 11, 40, 107 | Import and direct calls to verify_token |
| `rext-backend/src/api/security/dependencies.py` | 55-84 | get_current_user uses similar pattern |

---

## Testing Instructions

### Before Fix (Demonstrate the Issue):
1. Review the function signature:
   ```python
   def verify_token(token: str = Depends(oauth2_scheme)) -> dict:
   ```
2. Note that `Depends()` in the default is confusing for direct calls
3. Observe the same function used both as dependency and direct call

### After Fix (Verify the Solution):
1. Verify new function exists:
   ```python
   from src.api.security.token_utils import decode_and_verify_token, VerifiedToken
   ```
2. Test direct call:
   ```python
   payload = decode_and_verify_token("valid.jwt.token")
   assert "id" in payload
   ```
3. Test that deprecation warning is raised for old function:
   ```python
   import warnings
   with warnings.catch_warnings(record=True) as w:
       warnings.simplefilter("always")
       verify_token("valid.jwt.token")
       assert len(w) == 1
       assert "deprecated" in str(w[0].message).lower()
   ```

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "token or auth or session"
```

---

## Acceptance Criteria

- [ ] New `decode_and_verify_token(token: str)` function created for direct calls
- [ ] New `VerifiedToken` Annotated type created for FastAPI dependencies
- [ ] Original `verify_token` marked as deprecated with warning
- [ ] All direct call sites updated to use `decode_and_verify_token`
- [ ] Misleading `# verify password` comment removed
- [ ] Import statements updated in affected files
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Dependencies Tutorial](https://fastapi.tiangolo.com/tutorial/dependencies/)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Classes as Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/classes-as-dependencies/)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-004 (datetime.utcnow deprecation used in verify_token - lines 192, 198)
