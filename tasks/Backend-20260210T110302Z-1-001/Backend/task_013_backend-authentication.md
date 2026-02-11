# Task 013: Remove Dead passlib[bcrypt] Dependency and Add Explicit bcrypt

## Metadata
- **Task ID:** TASK-013
- **Source:** Backend Authentication & Authorization Audit (Finding #10 under P1 High)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P1 High
- **Category:** dependency
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `pyproject.toml` file lists `passlib[bcrypt]>=1.7.4` as a dependency (line 30), but `passlib` is never imported or used anywhere in the codebase. The code exclusively uses `bcrypt` directly via `import bcrypt` in five files: `src/api/security/token_utils.py` (line 28), `src/services/user_service.py` (line 22), `tests/unit/services/test_user_service.py` (line 17), `scripts/generate_test_password_hash.py` (line 5), and `alembic/versions/6a35a3742a53_seed_super_admin_from_env.py` (line 29).

Critically, `bcrypt` is **not** listed as an explicit dependency in `pyproject.toml`. It is only available as a transitive dependency installed by the `passlib[bcrypt]` extra. This means removing `passlib[bcrypt]` without adding `bcrypt` as an explicit dependency would cause an `ImportError` at application startup.

Furthermore, `passlib` has been unmaintained since 2020 (last release: version 1.7.4). It is known to be incompatible with `bcrypt>=4.1` due to the removal of `bcrypt.__about__`, which causes `AttributeError: module 'bcrypt' has no attribute '__about__'`. With the release of `bcrypt` 5.0.0, further breaking changes occurred. FastAPI's own documentation discussions have acknowledged that passlib is no longer maintained and should not be recommended. Keeping `passlib` as a dependency adds unnecessary attack surface and risks breakage if its transitive dependency resolution pulls in an incompatible bcrypt version.

The `PyJWT[crypto]` extra (line 34 in `pyproject.toml`) installs the `cryptography` package, **not** `bcrypt`. So `bcrypt` is only available through the `passlib[bcrypt]` extra.

---

## Current Code

```toml
# File: pyproject.toml
# Line: 30
    "passlib[bcrypt]>=1.7.4",
```

```python
# File: src/api/security/token_utils.py
# Line: 28
import bcrypt
```

```python
# File: src/services/user_service.py
# Line: 22
import bcrypt
```

---

## Why This Matters (Context & Reasoning)

Password hashing is the most critical security function in the authentication system. The `bcrypt` library is used to hash passwords on registration (`hash_password()` in `token_utils.py`) and verify passwords on login (`verify_password()` in `token_utils.py`). It is also used in `user_service.py` for password change operations and in a migration script that seeds the super admin account.

Having `bcrypt` as only a transitive dependency (through the unmaintained `passlib`) creates a fragile dependency chain. If a developer runs `pip install` in a clean environment and passlib's dependency resolution changes, or if passlib is removed from PyPI, bcrypt could disappear from the environment, breaking all authentication. Making `bcrypt` an explicit dependency ensures it is always installed regardless of other package changes.

---

## Impact

- **Severity:** If `passlib` is accidentally imported or if its dependency resolution changes, the application could crash on startup or produce incorrect password hashes. The unmaintained dependency also adds unnecessary attack surface.
- **Affected Users/Flows:** All users — registration, login, password changes, and admin seeding all depend on the `bcrypt` package.
- **Blast Radius:** Application-wide. Password hashing is a foundational security function.

---

## Recommended Solution

### Step 1: Remove `passlib[bcrypt]` from dependencies

```toml
# File: pyproject.toml
# Remove line 30: "passlib[bcrypt]>=1.7.4",
```

### Step 2: Add `bcrypt` as an explicit dependency

```toml
# File: pyproject.toml
# Add to the dependencies list (in alphabetical position, after "asyncpg"):
    "bcrypt>=4.0.0",
```

The constraint `>=4.0.0` is recommended because:
- bcrypt 4.0.0+ uses a Rust-based backend which is faster and more secure
- bcrypt 4.0.0+ dropped the `__about__` attribute that caused passlib incompatibility
- bcrypt 5.0.0 raises `ValueError` for passwords longer than 72 bytes instead of silently truncating — this is a security improvement
- The project already uses `bcrypt.hashpw()` and `bcrypt.checkpw()` directly, which are stable APIs across all 4.x and 5.x versions

### Step 3: Reinstall dependencies

```bash
cd rext-backend && pip install -e ".[dev]"
```

### Step 4: Verify no passlib imports exist

```bash
cd rext-backend && grep -r "passlib\|from passlib" src/ tests/ scripts/ alembic/
```

This should return zero results (confirmed during research).

### Step 5: Uninstall passlib from the environment

```bash
pip uninstall passlib -y
```

### Step 6: Verify the application starts correctly

```bash
cd rext-backend && python -c "import bcrypt; print(f'bcrypt version: {bcrypt.__version__}')"
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/security/token_utils.py` | 28, 43-53, 56-67 | Uses `import bcrypt` — `hash_password()` and `verify_password()` functions |
| `src/services/user_service.py` | 22 | Uses `import bcrypt` — password change operations |
| `tests/unit/services/test_user_service.py` | 17 | Uses `import bcrypt` — test password hashing |
| `scripts/generate_test_password_hash.py` | 5 | Uses `import bcrypt` — utility script |
| `alembic/versions/6a35a3742a53_seed_super_admin_from_env.py` | 29 | Uses `import bcrypt` — migration script for admin seeding |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Confirm `passlib` is listed in `pyproject.toml` but never imported: `grep -r "passlib" rext-backend/src/ rext-backend/tests/` — should return no results
2. Confirm `bcrypt` is NOT listed as explicit dependency: `grep "\"bcrypt" rext-backend/pyproject.toml` — should only show the passlib line
3. Check which package provides bcrypt: `pip show bcrypt` — note "Required-by" shows passlib

### After Fix (Verify the Solution):
1. Confirm `passlib` is removed from `pyproject.toml`: `grep "passlib" rext-backend/pyproject.toml` — should return no results
2. Confirm `bcrypt` is explicitly listed: `grep "\"bcrypt" rext-backend/pyproject.toml` — should show `"bcrypt>=4.0.0"`
3. Verify bcrypt still works after passlib removal:
   ```bash
   cd rext-backend
   pip uninstall passlib -y
   pip install -e .
   python -c "import bcrypt; print(bcrypt.hashpw(b'test', bcrypt.gensalt()))"
   ```
4. Start the application and verify login works

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "password or auth or login" --no-header
```

---

## Acceptance Criteria

- [ ] `passlib[bcrypt]>=1.7.4` removed from `pyproject.toml` dependencies
- [ ] `bcrypt>=4.0.0` added as explicit dependency in `pyproject.toml`
- [ ] No `passlib` imports exist anywhere in the codebase
- [ ] `pip install -e .` succeeds in a clean environment without passlib
- [ ] All password hashing and verification functions work correctly
- [ ] Application starts without import errors
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [bcrypt on PyPI](https://pypi.org/project/bcrypt/) — latest version documentation and changelog
- **Security Advisory:** [GitHub Issue #684: passlib incompatible with bcrypt 4.1.1](https://github.com/pyca/bcrypt/issues/684) — documents the `__about__` AttributeError
- **Migration Guide:** N/A (no migration needed — the code already uses bcrypt directly)
- **Best Practice Reference:** [FastAPI Discussion #11773: passlib unmaintained](https://github.com/fastapi/fastapi/discussions/11773) — FastAPI community acknowledges passlib should be replaced
- **Related Issues/PRs:** [Radicale Issue #1405: passlib unmaintained and needs replacement](https://github.com/Kozea/Radicale/issues/1405) — another project documenting the same problem

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** None — this is a standalone dependency cleanup task
