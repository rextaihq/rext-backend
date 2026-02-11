# Task 011: Convert token_cleanup.py from Synchronous to Async ORM

## Metadata
- **Task ID:** TASK-011
- **Source:** Backend Authentication & Authorization Audit (Finding #8 under P1 High)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `src/utils/token_cleanup.py` module is written using SQLAlchemy's synchronous ORM (`sqlalchemy.orm.Session` and `db.query()`), while the entire rest of the Rext backend uses asynchronous database access via `sqlalchemy.ext.asyncio.AsyncSession` and `await db.execute()`. This function cannot be called correctly in the async FastAPI application context. The `UserService.cleanup_expired_tokens()` method at `src/services/user_service.py:277-279` wraps it by calling `cleanup_expired_tokens(self.db.sync_session)`, which accesses a `sync_session` attribute — this is a fragile workaround that couples async service code to a synchronous database session.

Additionally, the function uses `datetime.utcnow()` at line 48, which is deprecated since Python 3.12 (PEP 587) and should use `datetime.now(timezone.utc)` instead. The companion script `scripts/cleanup_tokens.py` imports from `src.api.database.database.SessionLocal`, which may not even exist (the project uses `async_database.py` with `AsyncSessionLocal` and `SyncSessionLocal`).

The `DataCleanupService` in `src/services/data_cleanup_service.py` already provides an async cleanup pattern for other tables (audit logs, email logs, user sessions, webhook events) using `sqlalchemy.delete()` with `AsyncSession`, but does not include token blacklist cleanup. The `ScheduledTaskManager` in `src/tasks/scheduled_tasks.py` already runs `DataCleanupService.cleanup_all()` on a cron schedule but never calls token cleanup. This means expired tokens in the `token_blacklist` table accumulate indefinitely, degrading query performance over time as every token verification checks this table.

---

## Current Code

```python
# File: src/utils/token_cleanup.py
# Lines: 1-67
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
from sqlalchemy.orm import Session
from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.utils.logger import logger


def cleanup_expired_tokens(db: Session) -> int:
    """
    Remove expired tokens from blacklist.
    ...
    """
    try:
        # Delete tokens that expired before current time
        cutoff_time = datetime.utcnow()

        deleted_count = db.query(TokenBlacklist).filter(
            TokenBlacklist.expires_at < cutoff_time
        ).delete(synchronize_session=False)

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

```python
# File: src/services/user_service.py
# Lines: 277-279
    async def cleanup_expired_tokens(self) -> int:
        """Remove expired tokens from the blacklist."""
        return cleanup_expired_tokens(self.db.sync_session)
```

---

## Why This Matters (Context & Reasoning)

The token blacklist table (`token_blacklist`) is a critical security component — every JWT token verification checks this table to ensure the token hasn't been revoked. As tokens are blacklisted on logout, refresh rotation, forced logout, and password changes, the table grows continuously. Without periodic cleanup, query performance degrades as the table accumulates expired entries that would be rejected anyway.

The existing cleanup function cannot be used reliably because it requires a synchronous database session in an async application. The `UserService` workaround using `self.db.sync_session` is fragile — it depends on an undocumented attribute and blocks the async event loop during execution. The scheduled task system (`ScheduledTaskManager`) does not include token cleanup, meaning no automated cleanup runs in production.

---

## Impact

- **Severity:** The `token_blacklist` table grows unbounded in production. Over time, this degrades performance of every authenticated API request (each checks the blacklist). The admin endpoint at `src/api/routes/users/admin.py:77` that triggers manual cleanup calls the sync function through the async wrapper, potentially blocking the event loop.
- **Affected Users/Flows:** All authenticated users — every request that verifies a JWT token queries the blacklist table. Admin users who trigger manual cleanup via the admin endpoint.
- **Blast Radius:** System-wide performance degradation. The blacklist is checked on every authenticated request via `verify_token()` in `src/api/security/token_utils.py`.

---

## Recommended Solution

### Step 1: Rewrite `token_cleanup.py` as an async function using SQLAlchemy 2.0 `delete()` construct

```python
# File: src/utils/token_cleanup.py
# Replace entire file contents with:
"""
Token Cleanup Utility

Provides async functions to clean up expired tokens from the blacklist table.
Expired tokens can be safely removed since they would be rejected anyway.

Usage:
    from src.utils.token_cleanup import cleanup_expired_tokens
    from src.api.database.async_database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        deleted_count = await cleanup_expired_tokens(db)
"""

from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.utils.logger import logger


async def cleanup_expired_tokens(db: AsyncSession) -> int:
    """
    Remove expired tokens from blacklist.

    Tokens that have expired can be safely removed from the blacklist
    since they would be rejected anyway due to expiration. This prevents
    the blacklist table from growing indefinitely and improves query performance.

    Args:
        db: Async database session

    Returns:
        Number of tokens deleted

    Raises:
        Exception: If database operation fails (logged and returns 0)
    """
    try:
        cutoff_time = datetime.now(timezone.utc)

        stmt = delete(TokenBlacklist).where(
            TokenBlacklist.expires_at < cutoff_time
        )
        result = await db.execute(stmt)
        await db.commit()

        deleted_count = result.rowcount

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired tokens from blacklist")
        else:
            logger.debug("No expired tokens to clean up")

        return deleted_count

    except Exception as e:
        logger.error(f"Token cleanup failed: {str(e)}")
        await db.rollback()
        return 0
```

### Step 2: Update `UserService.cleanup_expired_tokens()` to use async version

```python
# File: src/services/user_service.py
# Replace lines 277-279 with:
    async def cleanup_expired_tokens(self) -> int:
        """Remove expired tokens from the blacklist."""
        return await cleanup_expired_tokens(self.db)
```

Note: The `self.db` in `UserService` is already an `AsyncSession` — the previous code was incorrectly accessing `self.db.sync_session`.

### Step 3: Add token cleanup to `DataCleanupService`

```python
# File: src/services/data_cleanup_service.py
# Add import at top of file (after existing imports):
from src.api.models.user_models.token_blacklist import TokenBlacklist

# Add this method to the DataCleanupService class (after the last cleanup method):
    async def cleanup_expired_tokens(self) -> int:
        """
        Clean up expired tokens from the blacklist.

        Expired tokens can be safely removed since they would be
        rejected anyway due to expiration.

        Returns:
            Number of records deleted (or would be deleted in dry-run mode)
        """
        cutoff_date = datetime.now(timezone.utc)

        if self.dry_run:
            count_stmt = select(func.count()).select_from(TokenBlacklist).where(
                TokenBlacklist.expires_at < cutoff_date
            )
            result = await self.db.execute(count_stmt)
            count = result.scalar() or 0
            logger.info(f"[DRY RUN] Would delete {count} expired tokens from blacklist")
            return count

        stmt = delete(TokenBlacklist).where(
            TokenBlacklist.expires_at < cutoff_date
        )
        result = await self.db.execute(stmt)
        deleted = result.rowcount
        await self.db.commit()

        logger.info(f"Cleaned up {deleted} expired tokens from blacklist")
        return deleted
```

Also add a call to `cleanup_expired_tokens` inside the `cleanup_all()` method of `DataCleanupService` so it runs as part of the scheduled daily cleanup.

### Step 4: Update `scripts/cleanup_tokens.py` to use async

```python
# File: scripts/cleanup_tokens.py
# Replace entire file contents with:
#!/usr/bin/env python3
"""
Script to clean up expired tokens from blacklist.

Usage:
    Manual run:
        python3 scripts/cleanup_tokens.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.api.database.async_database import AsyncSessionLocal
from src.utils.token_cleanup import cleanup_expired_tokens
from src.utils.logger import logger


async def main():
    """Main cleanup function."""
    logger.info("Starting token cleanup job")

    try:
        async with AsyncSessionLocal() as db:
            deleted_count = await cleanup_expired_tokens(db)
            logger.info(f"Token cleanup completed. Deleted {deleted_count} tokens.")

            if deleted_count > 0:
                print(f"Cleaned up {deleted_count} expired tokens")
            else:
                print("No expired tokens to clean up")

            return 0
    except Exception as e:
        logger.error(f"Token cleanup job failed: {str(e)}")
        print(f"Token cleanup failed: {str(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/utils/trial_manager.py` | 10 | Same sync ORM pattern — uses `from sqlalchemy.orm import Session` |
| `src/utils/account_cleanup.py` | 9 | Same sync ORM pattern — uses `from sqlalchemy.orm import Session` |
| `src/utils/invitation_utils.py` | 4 | Same sync ORM pattern — uses `from sqlalchemy.orm import Session` |
| `src/utils/workspace_utils.py` | 6 | Same sync ORM pattern — uses `from sqlalchemy.orm import Session` |
| `src/utils/slug_utils.py` | 6 | Same sync ORM pattern — uses `from sqlalchemy.orm import Session` |
| `src/utils/audit_helper.py` | 3 | Same sync ORM pattern — uses `from sqlalchemy.orm import Session` |
| `src/api/tasks/knowledge_task.py` | 3 | Same sync ORM pattern — uses `from sqlalchemy.orm import Session` |
| `src/services/user_service.py` | 268-279 | Callers of sync cleanup functions via `self.db.sync_session` workaround |
| `src/api/routes/users/admin.py` | 77 | Calls `service.cleanup_expired_tokens()` — the admin cleanup endpoint |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Confirm `token_cleanup.py` uses synchronous `Session` and `db.query()` API
2. Attempt to call `cleanup_expired_tokens()` with an `AsyncSession` — it will fail with a `TypeError` because `db.query()` does not exist on `AsyncSession`
3. Check the `token_blacklist` table for expired tokens: `SELECT COUNT(*) FROM token_blacklist WHERE expires_at < NOW();` — these accumulate without cleanup

### After Fix (Verify the Solution):
1. Verify the function now accepts `AsyncSession` and uses `await db.execute(delete(...))`
2. Manually trigger cleanup via the admin endpoint: `POST /admin/cleanup-tokens` (or equivalent)
3. Confirm expired tokens are removed: `SELECT COUNT(*) FROM token_blacklist WHERE expires_at < NOW();` should return 0
4. Verify the scheduled task system runs cleanup as part of `DataCleanupService.cleanup_all()`

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "token" --no-header
```

---

## Acceptance Criteria

- [ ] `token_cleanup.py` uses `AsyncSession` and `sqlalchemy.delete()` instead of sync `Session` and `db.query()`
- [ ] `datetime.utcnow()` replaced with `datetime.now(timezone.utc)`
- [ ] `UserService.cleanup_expired_tokens()` calls the async version with `await` and `self.db`
- [ ] `DataCleanupService` includes token blacklist cleanup in its `cleanup_all()` method
- [ ] `scripts/cleanup_tokens.py` uses async database session
- [ ] Admin cleanup endpoint at `admin.py:77` works correctly
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 ORM-Enabled DELETE Statements](https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html) — documents the `delete()` construct with `session.execute()`
- **Security Advisory:** N/A
- **Migration Guide:** [SQLAlchemy 2.0 Migration — ORM Query Unified with Core Select](https://docs.sqlalchemy.org/en/20/changelog/migration_20.html#migration-orm-usage) — explains migration from `session.query()` to `session.execute(select(...))`
- **Best Practice Reference:** [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) — periodic task patterns for FastAPI applications
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-004 (deprecated `datetime.utcnow()` — this file also uses it), B5 Finding 29 (`trial_manager.py` uses same synchronous Session pattern)
