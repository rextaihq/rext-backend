# Task 057: Migrate Legacy db.query() API to Modern select() Pattern in Sync Utilities

## Metadata
- **Task ID:** TASK-057
- **Source:** Backend Database & Migrations Audit (Finding #31 under P3 Low)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The sync utility modules `src/utils/token_cleanup.py` and `src/utils/account_cleanup.py` use SQLAlchemy's legacy `Session.query()` API (the 1.x-style query interface) instead of the modern `Session.execute(select(Model).where(...))` pattern introduced in SQLAlchemy 2.0. While `Session.query()` is still functional and [will not be removed](https://github.com/sqlalchemy/sqlalchemy/discussions/9619), it is explicitly labeled as ["Legacy"](https://docs.sqlalchemy.org/en/21/orm/queryguide/query.html) in the SQLAlchemy 2.0+ documentation.

The project uses SQLAlchemy 2.x (confirmed by the use of `asyncpg>=0.30.0` and `psycopg[binary]>=3.2.0` async/sync drivers, `async_sessionmaker`, and the `select()` pattern throughout async code). The `workspace_utils.py` file clearly demonstrates the inconsistency: its sync functions at lines 48 and 53 use `db.query(WorkspaceModel).filter(...)` while the identical async functions at lines 88-96 use `select(WorkspaceModel).where(...)`. This dual pattern within the same file creates confusion for developers about which API to use.

A codebase-wide search reveals **22 occurrences** of `db.query()` across 6 utility files. The finding specifically references `token_cleanup.py` (1 occurrence) and `account_cleanup.py` (3 occurrences), but the same pattern appears in `invitation_utils.py` (5), `workspace_utils.py` (2), `slug_utils.py` (1), and `trial_manager.py` (10). The internal documentation in `async_database.py:114` even perpetuates the pattern by showing `db.query(...)` as the expected usage in its sync session docstring.

According to the [SQLAlchemy 2.0 Migration Guide](https://docs.sqlalchemy.org/en/21/changelog/migration_20.html), the recommended transformations are: `session.query(Model).filter(...)` becomes `session.execute(select(Model).where(...)).scalars()`, and `session.query(Model).filter(...).delete()` becomes `session.execute(delete(Model).where(...))`.

---

## Current Code

```python
# File: rext-backend/src/utils/token_cleanup.py
# Lines: 46-52
    try:
        # Delete tokens that expired before current time
        cutoff_time = datetime.utcnow()

        deleted_count = db.query(TokenBlacklist).filter(
            TokenBlacklist.expires_at < cutoff_time
        ).delete(synchronize_session=False)
```

```python
# File: rext-backend/src/utils/account_cleanup.py
# Lines: 42-47
        # Find all inactive users deactivated 14+ days ago
        deactivated_users = db.query(Users).filter(
            Users.status == "inactive",
            Users.deactivated_at.isnot(None),
            Users.deactivated_at <= cutoff_date,
            Users.deleted_at.is_(None)  # Not already deleted
        ).all()
```

```python
# File: rext-backend/src/utils/account_cleanup.py
# Lines: 99-103
        deactivated_users = db.query(Users).filter(
            Users.status == "inactive",
            Users.deactivated_at.isnot(None),
            Users.deleted_at.is_(None)
        ).all()
```

```python
# File: rext-backend/src/utils/account_cleanup.py
# Line: 145
        user = db.query(Users).filter(Users.id == user_id).first()
```

---

## Why This Matters (Context & Reasoning)

These sync utility modules provide background task functionality for the Rext backend: `token_cleanup.py` removes expired tokens from the blacklist to prevent unbounded table growth, and `account_cleanup.py` handles the 14-day account deletion grace period (soft-delete deactivated accounts, list pending deletions, cancel deactivation).

The utilities are used by scheduled tasks and background jobs. They use synchronous database sessions via `SyncSessionLocal` (defined in `async_database.py:96-100`) because they run in thread pool executors for LangGraph nodes.

Standardizing on the `select()` pattern matters because:

1. **Consistency:** The async codebase already uses `select()` exclusively. Having sync utilities use `db.query()` while async code uses `select()` means developers must context-switch between two query APIs.
2. **Portability:** Code written with `select()` can be more easily converted to async (the query construction is identical; only the execution differs between `db.execute()` and `await db.execute()`).
3. **Future-proofing:** While `Session.query()` will not be removed, all new SQLAlchemy features, documentation, and tutorials exclusively use the `select()` pattern. New team members learning from docs will encounter `select()` as the standard.

---

## Impact

- **Severity:** No runtime errors or data corruption. This is a code consistency and maintainability issue. The legacy API functions identically to the modern API.
- **Affected Users/Flows:** No user-facing impact. Affects developer experience and codebase maintainability.
- **Blast Radius:** 4 `db.query()` calls in 2 files (finding scope). 22 total occurrences across 6 utility files (codebase-wide).

---

## Recommended Solution

Migrate all `db.query()` calls in `token_cleanup.py` and `account_cleanup.py` to the modern `select()`/`delete()` pattern. Also update the `async_database.py` docstring to show the modern pattern.

### Step 1: Update `token_cleanup.py` — Replace `db.query().filter().delete()` with `db.execute(delete().where())`

```python
# File: rext-backend/src/utils/token_cleanup.py
# Replace the entire file content:

"""
Token Cleanup Utility

Provides functions to clean up expired tokens from the blacklist table.
Expired tokens can be safely removed since they would be rejected anyway.

Usage:
    from src.utils.token_cleanup import cleanup_expired_tokens
    from src.api.database.database import SessionLocal

    db = SessionLocal()
    deleted_count = cleanup_expired_tokens(db)
    db.close()
"""

from datetime import datetime
from sqlalchemy import delete
from sqlalchemy.orm import Session
from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.utils.logger import logger


def cleanup_expired_tokens(db: Session) -> int:
    """
    Remove expired tokens from blacklist.

    Tokens that have expired can be safely removed from the blacklist
    since they would be rejected anyway due to expiration. This prevents
    the blacklist table from growing indefinitely and improves query performance.

    Args:
        db: Database session

    Returns:
        Number of tokens deleted

    Raises:
        Exception: If database operation fails (logged and returns 0)

    Example:
        >>> from src.api.database.database import SessionLocal
        >>> db = SessionLocal()
        >>> deleted = cleanup_expired_tokens(db)
        >>> logger.info(f"Deleted {deleted} tokens")
        >>> db.close()
    """
    try:
        # Delete tokens that expired before current time
        cutoff_time = datetime.utcnow()

        result = db.execute(
            delete(TokenBlacklist).where(
                TokenBlacklist.expires_at < cutoff_time
            )
        )
        deleted_count = result.rowcount

        db.commit()

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired tokens from blacklist")
        else:
            logger.debug("No expired tokens to clean up")

        return deleted_count

    except Exception as e:
        logger.error(f"Token cleanup failed: {str(e)}")
        db.rollback()
        return 0
```

### Step 2: Update `account_cleanup.py` — Replace all 3 `db.query()` calls

```python
# File: rext-backend/src/utils/account_cleanup.py
# Replace the entire file content:

"""
Account cleanup utilities for handling deactivated account deletion.

This module provides functions to automatically delete accounts that have been
deactivated for 14 days or more.
"""

from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.api.models.user_models.users import Users
from src.utils.logger import logger


def delete_deactivated_accounts(db: Session) -> int:
    """
    Permanently delete accounts that have been deactivated for 14 days or more.

    This function:
    1. Finds all users with status='inactive' and deactivated_at >= 14 days ago
    2. Sets deleted_at timestamp for soft deletion
    3. Returns count of deleted accounts

    Args:
        db: SQLAlchemy database session

    Returns:
        int: Number of accounts deleted

    Example:
        >>> from src.api.database.async_database import get_async_db as get_db
        >>> db = next(get_db())
        >>> deleted_count = delete_deactivated_accounts(db)
        >>> logger.info(f"Deleted {deleted_count} accounts")
    """
    try:
        # Calculate cutoff date (14 days ago)
        cutoff_date = datetime.utcnow() - timedelta(days=14)

        logger.info(f"Starting deactivated account cleanup. Cutoff date: {cutoff_date.isoformat()}")

        # Find all inactive users deactivated 14+ days ago
        result = db.execute(
            select(Users).where(
                Users.status == "inactive",
                Users.deactivated_at.isnot(None),
                Users.deactivated_at <= cutoff_date,
                Users.deleted_at.is_(None)
            )
        )
        deactivated_users = result.scalars().all()

        deleted_count = 0

        for user in deactivated_users:
            try:
                # Soft delete the user
                user.deleted_at = datetime.utcnow()
                logger.info(
                    f"Deleting deactivated account: {user.email} (ID: {user.id}), "
                    f"deactivated on {user.deactivated_at.isoformat()}"
                )
                deleted_count += 1

            except Exception as e:
                logger.error(f"Error deleting user {user.id}: {str(e)}")
                continue

        # Commit all deletions
        if deleted_count > 0:
            db.commit()
            logger.info(f"Successfully deleted {deleted_count} deactivated account(s)")
        else:
            logger.info("No deactivated accounts found for deletion")

        return deleted_count

    except Exception as e:
        logger.error(f"Error during deactivated account cleanup: {str(e)}")
        db.rollback()
        raise


def get_pending_deletions(db: Session) -> list:
    """
    Get list of accounts scheduled for deletion with their deletion dates.

    Returns accounts that are deactivated but not yet deleted, along with
    their scheduled deletion date.

    Args:
        db: SQLAlchemy database session

    Returns:
        list: List of dicts containing user info and scheduled deletion date

    Example:
        >>> pending = get_pending_deletions(db)
        >>> for account in pending:
        ...     logger.info(f"{account['email']} - deletes on {account['scheduled_deletion']}")
    """
    try:
        result = db.execute(
            select(Users).where(
                Users.status == "inactive",
                Users.deactivated_at.isnot(None),
                Users.deleted_at.is_(None)
            )
        )
        deactivated_users = result.scalars().all()

        pending_deletions = []
        for user in deactivated_users:
            scheduled_deletion = user.deactivated_at + timedelta(days=14)
            days_remaining = (scheduled_deletion - datetime.utcnow()).days

            pending_deletions.append({
                "user_id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "deactivated_at": user.deactivated_at.isoformat(),
                "scheduled_deletion": scheduled_deletion.isoformat(),
                "days_remaining": max(0, days_remaining)
            })

        return pending_deletions

    except Exception as e:
        logger.error(f"Error getting pending deletions: {str(e)}")
        raise


def cancel_account_deactivation(user_id: str, db: Session) -> bool:
    """
    Cancel account deactivation and reactivate the account.

    Allows users to reactivate their account before the 14-day deletion window expires.

    Args:
        user_id: UUID of the user
        db: SQLAlchemy database session

    Returns:
        bool: True if reactivation successful, False otherwise

    Example:
        >>> success = cancel_account_deactivation("user-uuid", db)
        >>> if success:
        ...     logger.info("Account reactivated successfully")
    """
    try:
        result = db.execute(
            select(Users).where(Users.id == user_id)
        )
        user = result.scalars().first()

        if not user:
            logger.warning(f"User not found: {user_id}")
            return False

        if user.status != "inactive":
            logger.warning(f"User {user_id} is not deactivated (status: {user.status})")
            return False

        # Reactivate account
        user.status = "active"
        user.deactivated_at = None
        user.updated_at = datetime.utcnow()

        db.commit()
        logger.info(f"Account reactivated: {user.email} (ID: {user_id})")

        return True

    except Exception as e:
        logger.error(f"Error reactivating account {user_id}: {str(e)}")
        db.rollback()
        return False
```

### Step 3: Update `async_database.py` docstring to show modern pattern

```python
# File: rext-backend/src/api/database/async_database.py
# Replace the docstring in get_sync_db() (lines 103-122):
# Change line 114 from:
#            db.query(...)
# To:
#            db.execute(select(...).where(...))
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/utils/invitation_utils.py` | 46, 84, 92, 96, 100 | 5 `db.query()` calls: queries `UserInvitations`, `WorkspaceModel`, `Role`, `Users` in `cleanup_expired_invitations()` and `get_invitation_with_details()` |
| `rext-backend/src/utils/workspace_utils.py` | 48, 53 | 2 `db.query()` calls in sync `resolve_workspace()`. The async version at lines 88-96 already uses `select()` — a clear example of the inconsistency |
| `rext-backend/src/utils/slug_utils.py` | 66 | 1 `db.query()` call in `generate_unique_slug()` checking for slug existence |
| `rext-backend/src/utils/trial_manager.py` | 81, 102, 158, 206, 256, 295, 300, 306, 312, 318 | 10 `db.query()` calls across all trial management functions — the largest concentration of legacy API usage |
| `rext-backend/src/api/database/async_database.py` | 114 | Docstring for `get_sync_db()` shows `db.query(...)` as the expected usage pattern, perpetuating the legacy API |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Search the codebase for legacy query usage: `grep -rn "db.query(" rext-backend/src/utils/token_cleanup.py rext-backend/src/utils/account_cleanup.py`
2. Confirm 4 occurrences exist in the two files

### After Fix (Verify the Solution):
1. Verify no `db.query()` calls remain in `token_cleanup.py` or `account_cleanup.py`: `grep -rn "db.query(" rext-backend/src/utils/token_cleanup.py rext-backend/src/utils/account_cleanup.py` should return no results
2. Verify the new imports are correct: `from sqlalchemy import select` in `account_cleanup.py` and `from sqlalchemy import delete` in `token_cleanup.py`
3. Run the token cleanup function in a test environment to verify expired tokens are still deleted correctly
4. Run the account cleanup functions to verify deactivated accounts are still processed correctly

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v --no-header -k "token_cleanup or account_cleanup or cleanup"
```

If no specific tests exist for these utilities:
```bash
cd rext-backend && python -m pytest tests/ -v --no-header
```

---

## Acceptance Criteria

- [ ] `token_cleanup.py` uses `db.execute(delete(TokenBlacklist).where(...))` instead of `db.query(TokenBlacklist).filter(...).delete()`
- [ ] `account_cleanup.py` uses `db.execute(select(Users).where(...)).scalars()` instead of `db.query(Users).filter(...)`
- [ ] All 3 functions in `account_cleanup.py` (`delete_deactivated_accounts`, `get_pending_deletions`, `cancel_account_deactivation`) are updated
- [ ] `token_cleanup.py` imports `delete` from `sqlalchemy` instead of using `Session.query()`
- [ ] `account_cleanup.py` imports `select` from `sqlalchemy` instead of using `Session.query()`
- [ ] `async_database.py` docstring shows the modern `db.execute(select(...).where(...))` pattern
- [ ] Token cleanup still correctly deletes expired tokens
- [ ] Account cleanup still correctly identifies and soft-deletes deactivated accounts
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Legacy Query API — SQLAlchemy 2.1 Documentation](https://docs.sqlalchemy.org/en/21/orm/queryguide/query.html) — The `Session.query()` API is explicitly labeled "Legacy" and documented separately from the modern query API
- **Security Advisory:** N/A
- **Migration Guide:** [SQLAlchemy 2.0 Major Migration Guide](https://docs.sqlalchemy.org/en/21/changelog/migration_20.html) — Provides side-by-side examples of migrating from `Session.query()` to `Session.execute(select())`
- **Best Practice Reference:** [Writing SELECT statements for ORM Mapped Classes — SQLAlchemy 2.1](https://docs.sqlalchemy.org/en/21/orm/queryguide/select.html) — The recommended modern query API documentation
- **Related Issues/PRs:** [GitHub Discussion #9619 — Will session.query() ever be deprecated/removed?](https://github.com/sqlalchemy/sqlalchemy/discussions/9619) — Maintainer confirmation that `Session.query()` will remain but is legacy

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-011 (`token_cleanup.py` uses synchronous ORM — if TASK-011 converts the file to async, the `db.query()` migration will be done as part of that conversion), TASK-045 (Deprecated `datetime.utcnow()` — both `token_cleanup.py:48` and `account_cleanup.py:37,54,108,158` also use `datetime.utcnow()`, which should be addressed alongside or after this task)
