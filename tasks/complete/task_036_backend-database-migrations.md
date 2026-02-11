# Task 036: Fix Misleading get_async_db_context() Docstring

## Metadata
- **Task ID:** TASK-036
- **Source:** Backend Database & Migrations Audit (Finding #10 under P1 High)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P1 High
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `get_async_db_context()` function in `async_database.py` has a docstring that makes promises the implementation doesn't fulfill. The docstring states:

> "Returns an async context manager that provides a database session with automatic transaction handling (commit on success, rollback on error)."

However, the actual implementation on line 72 simply returns:

```python
return AsyncSessionLocal()
```

This returns a raw `AsyncSession` instance directly from the session factory. There is:

1. **No async context manager wrapping** - The function returns a session directly, not a context manager
2. **No automatic commit on success** - The session will not commit unless the caller explicitly calls `await session.commit()`
3. **No automatic rollback on error** - Exceptions will not trigger a rollback unless the caller handles this

The docstring even provides a misleading usage example:

```python
async with get_async_db_context() as db:
    await db.execute(...)
    # Automatically commits on exit if no exception
```

This example WILL work syntactically because `AsyncSession` can be used as an async context manager (it has `__aenter__` and `__aexit__` methods). However, the default `AsyncSession.__aexit__` behavior does NOT commit the transaction - it only closes the session. Data written through sessions obtained from this function will be lost unless the caller manually commits.

According to SQLAlchemy 2.x documentation, the recommended pattern for automatic transaction handling is to use `session.begin()` as a context manager, which provides the commit-on-success, rollback-on-error behavior. Alternatively, the existing `@transactional` decorator in the codebase (in `transactional_decorator.py`) provides this functionality and should be referenced.

This is a P1 issue because developers relying on this documented behavior will experience silent data loss - their writes will appear to succeed but won't be persisted to the database.

---

## Current Code

```python
# File: src/api/database/async_database.py
# Lines: 55-72

# Context manager for background tasks
def get_async_db_context():
    """
    Async context manager for background tasks and standalone operations.

    Returns an async context manager that provides a database session with
    automatic transaction handling (commit on success, rollback on error).

    Usage:
        async with get_async_db_context() as db:
            # Use db session
            await db.execute(...)
            # Automatically commits on exit if no exception

    This is specifically designed for FastAPI background tasks which need
    their own database session independent of the request lifecycle.
    """
    return AsyncSessionLocal()  # <-- Just returns raw session, NO transaction handling
```

**For comparison - the @transactional decorator that DOES provide transaction handling:**

```python
# File: src/utils/transactional_decorator.py
# Lines: 27-93

def transactional(func: Callable) -> Callable:
    """
    Decorator for automatic transaction management.

    Wraps async functions to:
    1. Commit transaction on successful completion
    2. Rollback transaction on exception
    3. Ensure proper error propagation
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        # ... extracts db_session ...
        try:
            result = await func(*args, **kwargs)
            await db_session.commit()  # <-- Actual commit
            return result
        except Exception as e:
            await db_session.rollback()  # <-- Actual rollback
            raise
    return wrapper
```

---

## Why This Matters (Context & Reasoning)

The `get_async_db_context()` function is specifically designed for "FastAPI background tasks which need their own database session independent of the request lifecycle." Background tasks are a critical pattern in FastAPI applications for:

1. **Email sending after user registration**
2. **Webhook processing**
3. **Async job processing**
4. **Scheduled tasks (subscription renewals, cleanup, etc.)**

If developers trust the docstring and use this function in background tasks without manual commits, their database operations will silently fail to persist. This is particularly insidious because:

- No exception is raised
- The code appears to work correctly during development/testing
- Data loss only becomes apparent when checking the database
- Debug sessions may show the data (it's in the session), but it's not committed

The codebase already has the `@transactional` decorator that provides the documented behavior. The fix should either:
1. Implement the function as documented (provide a context manager with transaction handling)
2. Fix the docstring to accurately describe what the function does and reference the `@transactional` decorator

---

## Impact

- **Severity:** Silent data loss in background tasks. Developers trusting the docstring will write code that appears to work but doesn't persist data.
- **Affected Users/Flows:** Any background task or standalone operation that uses this function for database access
- **Blast Radius:** Any code using `get_async_db_context()` without manual transaction management

---

## Recommended Solution

There are two valid approaches. Choose based on codebase conventions:

### Option A: Fix the Docstring (Minimal Change)

Update the docstring to accurately describe the function's behavior and reference existing transaction management tools.

```python
# File: src/api/database/async_database.py
# Replace lines 55-72 with:

def get_async_db_context() -> AsyncSession:
    """
    Get an AsyncSession for background tasks and standalone operations.

    Returns a raw AsyncSession from the session factory. The caller is
    responsible for transaction management (commit/rollback).

    IMPORTANT: This function does NOT provide automatic transaction handling.
    You must either:
    1. Manually call `await db.commit()` after write operations
    2. Use the `@transactional` decorator from `src.utils.transactional_decorator`
    3. Use `async with db.begin():` context manager for atomic operations

    Usage with manual commit:
        db = get_async_db_context()
        try:
            await db.execute(...)
            await db.commit()  # Required for persistence!
        except Exception:
            await db.rollback()
            raise
        finally:
            await db.close()

    Usage with @transactional decorator (recommended for service methods):
        from src.utils.transactional_decorator import transactional

        class MyBackgroundService:
            def __init__(self):
                self.db = get_async_db_context()

            @transactional
            async def process_item(self, item_id):
                # Transaction handled by decorator
                await self.db.execute(...)

    This is specifically designed for FastAPI background tasks which need
    their own database session independent of the request lifecycle.
    """
    return AsyncSessionLocal()
```

### Option B: Implement as Documented (Full Fix)

Create a proper async context manager that provides the documented behavior.

```python
# File: src/api/database/async_database.py
# Replace lines 55-72 with:

from contextlib import asynccontextmanager

@asynccontextmanager
async def get_async_db_context():
    """
    Async context manager for background tasks and standalone operations.

    Provides a database session with automatic transaction handling:
    - Commits on successful exit (no exception)
    - Rolls back on exception
    - Always closes the session

    Usage:
        async with get_async_db_context() as db:
            await db.execute(...)
            # Automatically commits on exit if no exception

    This is specifically designed for FastAPI background tasks which need
    their own database session independent of the request lifecycle.
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
```

**Note:** Option B changes the function signature (from returning `AsyncSession` to returning `AsyncContextManager[AsyncSession]`). If there are existing callers that don't use `async with`, they will break. Run a codebase search first:

```bash
grep -r "get_async_db_context" --include="*.py" | grep -v "async with"
```

### Step 2: Update Any Callers (if using Option B)

If Option B is chosen, update any callers that don't use `async with`:

```python
# Before:
db = get_async_db_context()
await db.execute(...)

# After:
async with get_async_db_context() as db:
    await db.execute(...)
```

### Step 3: Add Tests

Add a test to verify the behavior matches the documentation:

```python
# File: tests/unit/test_async_database.py

import pytest
from src.api.database.async_database import get_async_db_context

@pytest.mark.asyncio
async def test_get_async_db_context_commits_on_success():
    """Verify session commits on successful exit from context manager."""
    async with get_async_db_context() as db:
        # Create a test record
        result = await db.execute(
            text("INSERT INTO test_table (name) VALUES ('test') RETURNING id")
        )
        test_id = result.scalar()

    # After context exit, verify commit happened
    async with get_async_db_context() as db:
        result = await db.execute(
            text("SELECT name FROM test_table WHERE id = :id"),
            {"id": test_id}
        )
        assert result.scalar() == 'test'


@pytest.mark.asyncio
async def test_get_async_db_context_rollbacks_on_error():
    """Verify session rolls back on exception."""
    try:
        async with get_async_db_context() as db:
            await db.execute(
                text("INSERT INTO test_table (name) VALUES ('rollback_test')")
            )
            raise ValueError("Intentional error")
    except ValueError:
        pass

    # Verify rollback happened - record should not exist
    async with get_async_db_context() as db:
        result = await db.execute(
            text("SELECT COUNT(*) FROM test_table WHERE name = 'rollback_test'")
        )
        assert result.scalar() == 0
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/database/deps.py` | 27 | Docstring mentions "automatic transaction handling" - should be reviewed |
| Any file using `get_async_db_context()` | Various | Search for callers that may rely on documented (but non-existent) auto-commit |

Search for all callers:
```bash
grep -rn "get_async_db_context" --include="*.py" src/
```

---

## Testing Instructions

### Before Fix (Demonstrate the Bug):
1. Create a test script that uses `get_async_db_context()` as documented:
   ```python
   from src.api.database.async_database import get_async_db_context
   from sqlalchemy import text
   import asyncio

   async def test_false_commit():
       async with get_async_db_context() as db:
           await db.execute(text("INSERT INTO audit_logs (action) VALUES ('test')"))
           print("Insert executed - docstring says this will auto-commit")

       # Check if it was actually committed
       async with get_async_db_context() as db:
           result = await db.execute(text("SELECT COUNT(*) FROM audit_logs WHERE action = 'test'"))
           count = result.scalar()
           print(f"Records found: {count}")  # Will be 0 - not committed!

   asyncio.run(test_false_commit())
   ```
2. **Expected (based on docstring):** Insert should be committed automatically
3. **Actual:** Insert is NOT committed, count will be 0

### After Fix (Verify Correct Behavior):

**If Option A (docstring fix):**
1. Verify docstring accurately describes manual commit requirement
2. Verify callers have been updated to manually commit or use `@transactional`

**If Option B (implementation fix):**
1. Run the same test script
2. **Expected:** Insert IS committed automatically, count will be 1
3. Verify rollback works by raising an exception inside the context

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "database" --tb=short
pytest tests/ -v -k "async" --tb=short
```

---

## Acceptance Criteria

- [ ] Docstring accurately describes the function's behavior
- [ ] If implementing Option B: `get_async_db_context()` provides automatic commit/rollback
- [ ] If implementing Option A: All callers have been updated for manual transaction management
- [ ] `deps.py` docstring reviewed and corrected if needed
- [ ] No existing callers are broken by the change
- [ ] Tests verify the documented behavior matches implementation
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.1 - Transactions and Connection Management](https://docs.sqlalchemy.org/en/21/orm/session_transaction.html) - Session transaction patterns
- **Security Advisory:** N/A (code quality issue)
- **Migration Guide:** N/A
- **Best Practice Reference:** [Mastering Transaction Boundaries in Python with SQLAlchemy](https://cevheri.medium.com/mastering-transaction-boundaries-in-python-with-sqlalchemy-and-clean-architecture-principles-10361aaf715e) - Clean architecture patterns
- **Related Issues/PRs:** [Transactional Decorator Implementation in FastAPI](https://dev.to/uponthesky/python-post-reviewhow-to-implement-a-transactional-decorator-in-fastapi-sqlalchemy-ein) - Alternative approaches

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** None (isolated documentation/implementation issue)
