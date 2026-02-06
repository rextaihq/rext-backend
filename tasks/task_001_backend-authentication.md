# Task 001: Fix Timing-Attack-Vulnerable API Key Comparison

## Metadata
- **Task ID:** TASK-001
- **Source:** Authentication & Authorization Audit (Finding #2 under P0 Critical)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P0 Critical
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `get_api_key` function in `src/api/security/auth.py` uses Python's standard `!=` operator (line 34) to compare the client-supplied API key header against the server-side secret `API_KEY`. Python's `!=` operator performs a byte-by-byte comparison and short-circuits on the first mismatch, meaning the comparison returns faster when the first character is wrong than when the last character is wrong. This timing difference, while measured in nanoseconds, is exploitable by an attacker making repeated requests and statistically analyzing response times to incrementally determine the correct API key one character at a time.

This is a well-documented class of vulnerability known as a timing side-channel attack, catalogued by OWASP under "Timing Attack" and demonstrated in CVE-2022-48566 (which affected Python's own `hmac.compare_digest` implementation in versions prior to 3.9.2). The correct mitigation is to use `hmac.compare_digest()` from Python's standard library, which performs constant-time comparison regardless of where the strings differ. This function has been available since Python 3.3 and was further hardened after CVE-2022-48566.

Notably, the same codebase already uses `hmac.compare_digest` correctly in `src/utils/lemonsqueezy_webhook.py:84` and `src/providers/payment/providers/lemonsqueezy.py:755` for webhook signature verification, making this an inconsistency rather than a missing pattern. The API key authentication path is the only place where a non-constant-time comparison is used for a secret.

The function `get_api_key` is used as a FastAPI `Security` dependency, meaning every endpoint that requires API key authentication passes through this vulnerable comparison.

---

## Current Code

```python
# File: src/api/security/auth.py
# Lines: 28-39
def get_api_key(api_key_header: str = Security(api_key_header)):
    if not api_key_header:
        raise InvalidAPIKeyException(
            message="API key is required"
        )

    if api_key_header != API_KEY:
        raise InvalidAPIKeyException(
            message="Invalid API key provided"
        )

    return api_key_header
```

---

## Why This Matters (Context & Reasoning)

The `get_api_key` function is a FastAPI security dependency that gates access to service-level API endpoints. The API key provides machine-to-machine authentication for internal services or administrative tooling. If an attacker can determine the API key through a timing attack, they gain full access to all API-key-protected endpoints without needing user credentials.

The risk is amplified because API keys are typically long-lived (unlike JWTs) and not rotated frequently. A compromised API key could provide persistent unauthorized access until discovered and rotated. The attack is feasible over a network, especially if the attacker can make many requests (no rate limiting was identified on this endpoint).

---

## Impact

- **Severity:** An attacker could incrementally determine the API key character-by-character through statistical timing analysis, gaining unauthorized access to all API-key-protected endpoints.
- **Affected Users/Flows:** All endpoints that use `get_api_key` as a dependency. This includes any service-to-service authentication flows.
- **Blast Radius:** Isolated to API key authentication. JWT-based user authentication is not affected by this specific issue.

---

## Recommended Solution

### Step 1: Add `hmac` import and use `compare_digest` for API key comparison

```python
# File: src/api/security/auth.py
# Replace the entire file content with:

import hmac

from langgraph_sdk import Auth
from fastapi import Security
from fastapi.security.api_key import APIKeyHeader
from src.api.middleware.exceptions import InvalidAPIKeyException
from src.api.config import get_settings

# Get settings instance
settings = get_settings()

auth = Auth()
API_KEY = settings.API_KEY
API_KEY_NAME = settings.API_KEY_NAME
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


@auth.on
async def add_owner(
    ctx: Auth.types.AuthContext,
    value: dict,
):
    filters = {"owner": ctx.user.identity}
    metadata = value.setdefault("metadata", {})
    metadata.update(filters)

    # Only let users see their own resources
    return filters

def get_api_key(api_key_header: str = Security(api_key_header)):
    if not api_key_header:
        raise InvalidAPIKeyException(
            message="API key is required"
        )

    if not API_KEY or not hmac.compare_digest(api_key_header, API_KEY):
        raise InvalidAPIKeyException(
            message="Invalid API key provided"
        )

    return api_key_header
```

**Key changes:**
1. Added `import hmac` at the top of the file
2. Replaced `api_key_header != API_KEY` with `not hmac.compare_digest(api_key_header, API_KEY)`
3. Added a guard `not API_KEY` to handle the case where `API_KEY` is `None` (since `hmac.compare_digest` requires both arguments to be strings or bytes, passing `None` would raise `TypeError`)

**Why `hmac.compare_digest`:** This function compares two strings in constant time by computing an XOR of all bytes and returning the result, preventing timing leakage. It is the same approach used in `src/utils/lemonsqueezy_webhook.py:84` for webhook signature verification, maintaining consistency within the codebase.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/utils/lemonsqueezy_webhook.py` | `84` | Already uses `hmac.compare_digest` correctly for webhook signatures |
| `src/providers/payment/providers/lemonsqueezy.py` | `755` | Already uses `hmac.compare_digest` correctly for webhook signatures |

No other API key or secret comparisons using `!=`/`==` were found in the codebase.

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Read `src/api/security/auth.py:34` and confirm it uses `api_key_header != API_KEY` (non-constant-time comparison)
2. Optionally, use a timing analysis tool to measure response time variance when sending API keys with correct vs incorrect prefixes

### After Fix (Verify the Solution):
1. Confirm `src/api/security/auth.py` now uses `hmac.compare_digest()` for comparison
2. Test with a valid API key — should return successfully
3. Test with an invalid API key — should return `InvalidAPIKeyException`
4. Test with no API key header — should return "API key is required" error
5. Test with `API_KEY` unset in environment (None) — should return error without crashing

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "api_key or auth" -v
```

---

## Acceptance Criteria

- [ ] `hmac.compare_digest()` is used for API key comparison in `src/api/security/auth.py`
- [ ] `import hmac` is added to the file
- [ ] A guard clause handles the case where `API_KEY` is `None`
- [ ] All endpoints using `get_api_key` dependency continue to function correctly
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python hmac.compare_digest documentation](https://docs.python.org/3/library/hmac.html#hmac.compare_digest)
- **Security Advisory:** [CVE-2022-48566 — Python hmac.compare_digest timing flaw (fixed in 3.9.2+)](https://www.cve.news/cve-2022-48566/)
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP Timing Attack Prevention](https://owasp.org/www-community/attacks/Timing_attack)
- **Related Issues/PRs:** [Sqreen Developer Security Best Practices — Timing Attack in Python](https://sqreen.github.io/DevelopersSecurityBestPractices/timing-attack/python)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** None
