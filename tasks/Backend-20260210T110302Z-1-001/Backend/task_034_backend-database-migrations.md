# Task 034: Remove Duplicate Index Declarations in TokenBlacklist and UserSession

## Metadata
- **Task ID:** TASK-034
- **Source:** Backend Database & Migrations Audit (Finding #8 under P1 High)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P1 High
- **Category:** performance
- **Effort Estimate:** small (< 1 hour)

---

## Description

Two models (`TokenBlacklist` and `UserSession`) have duplicate index declarations where the same column has both `index=True` on the Column definition AND an explicit `Index()` object in `__table_args__`. This creates two separate indexes on the same column in PostgreSQL, which doubles storage overhead and write latency for those columns without providing any query performance benefit.

In SQLAlchemy, `index=True` is shorthand for creating an `Index(None, column)` where the name is auto-generated (typically `ix_tablename_columnname`). When you also define an explicit `Index('custom_name', 'column')` in `__table_args__`, SQLAlchemy creates both indexes. PostgreSQL accepts this without error, but it results in:

1. **Doubled storage:** Each index requires disk space proportional to the table size
2. **Doubled write overhead:** Every INSERT, UPDATE (on indexed column), and DELETE must update both indexes
3. **No query benefit:** The query planner will use one index and ignore the other

The affected columns are:

**In `token_blacklist.py`:**
- `jti`: `index=True` (line 26) + `Index('idx_token_blacklist_jti', 'jti')` (line 35)
- `user_id`: `index=True` (line 28) + `Index('idx_token_blacklist_user_id', 'user_id')` (line 36)
- `expires_at`: `index=True` (line 30) + `Index('idx_token_blacklist_expires_at', 'expires_at')` (line 37)

**In `user_sessions.py`:**
- `jti`: `index=True` (line 23) + `Index('idx_user_sessions_jti', 'jti')` (line 52)
- `last_activity_at`: `index=True` (line 40) + `Index('idx_user_sessions_last_activity', 'last_activity_at')` (line 53)

This is a total of 5 duplicate indexes across 2 tables.

---

## Current Code

```python
# File: src/api/models/user_models/token_blacklist.py
# Lines: 26, 28, 30, 33-38

class TokenBlacklist(Base, SerializableMixin):
    """Store revoked/blacklisted tokens."""
    __tablename__ = "token_blacklist"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jti = Column(String(255), unique=True, nullable=False, index=True)  # <-- index=True
    token_type = Column(String(20), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # <-- index=True
    revoked_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    expires_at = Column(TIMESTAMP, nullable=False, index=True)  # <-- index=True
    reason = Column(String(100))

    __table_args__ = (
        Index('idx_token_blacklist_jti', 'jti'),  # <-- DUPLICATE of jti index=True
        Index('idx_token_blacklist_user_id', 'user_id'),  # <-- DUPLICATE of user_id index=True
        Index('idx_token_blacklist_expires_at', 'expires_at'),  # <-- DUPLICATE of expires_at index=True
    )
```

```python
# File: src/api/models/user_models/user_sessions.py
# Lines: 22-23, 36, 40, 50-54

class UserSession(Base, SerializableMixin):
    """Store active user login sessions with device and location metadata."""
    __tablename__ = "user_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    jti = Column(String(255), unique=True, nullable=False, index=True)  # <-- index=True
    # ... other columns ...
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    # ...
    last_activity_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False, index=True)  # <-- index=True
    # ...

    __table_args__ = (
        Index('idx_user_sessions_user_active', 'user_id', 'is_active'),  # Composite - NOT duplicate
        Index('idx_user_sessions_jti', 'jti'),  # <-- DUPLICATE of jti index=True
        Index('idx_user_sessions_last_activity', 'last_activity_at'),  # <-- DUPLICATE of last_activity_at index=True
    )
```

---

## Why This Matters (Context & Reasoning)

The `token_blacklist` and `user_sessions` tables are authentication-critical tables that are accessed on every API request:

1. **TokenBlacklist:** Checked on every authenticated request to verify the token hasn't been revoked. The table grows with every logout, refresh, and forced logout operation.

2. **UserSession:** Updated on every authenticated request to track `last_activity_at`. This table grows with each new login session.

Both tables are write-heavy and read-heavy. Having duplicate indexes means:
- Every token blacklist entry requires updating 6 indexes (3 real + 3 duplicates) instead of 3
- Every session activity update requires updating 4+ indexes instead of 2+
- Disk space is wasted storing redundant B-tree structures
- Database maintenance operations (VACUUM, REINDEX) take longer

While the performance impact per-operation is small (milliseconds), it compounds:
- Token blacklist grows indefinitely until cleaned up
- User sessions accumulate across all active users
- High-traffic authentication endpoints hit these tables frequently

---

## Impact

- **Severity:** Unnecessary database overhead. Doubled index storage and write latency on authentication-critical tables.
- **Affected Users/Flows:** All authenticated API requests (token validation), all login/logout operations, session cleanup jobs
- **Blast Radius:** Affects 2 tables (`token_blacklist`, `user_sessions`) with 5 duplicate indexes total

---

## Recommended Solution

Remove the `index=True` attribute from columns that have explicit `Index()` declarations in `__table_args__`. Keep the explicit `Index()` declarations because they provide meaningful names that appear in PostgreSQL's `pg_indexes` view and error messages.

### Step 1: Update token_blacklist.py

```python
# File: src/api/models/user_models/token_blacklist.py
# Remove index=True from lines 26, 28, 30

class TokenBlacklist(Base, SerializableMixin):
    """Store revoked/blacklisted tokens."""
    __tablename__ = "token_blacklist"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jti = Column(String(255), unique=True, nullable=False)  # Removed index=True
    token_type = Column(String(20), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)  # Removed index=True
    revoked_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    expires_at = Column(TIMESTAMP, nullable=False)  # Removed index=True
    reason = Column(String(100))

    __table_args__ = (
        # Keep explicit indexes with meaningful names
        Index('idx_token_blacklist_jti', 'jti'),
        Index('idx_token_blacklist_user_id', 'user_id'),
        Index('idx_token_blacklist_expires_at', 'expires_at'),
    )
```

### Step 2: Update user_sessions.py

```python
# File: src/api/models/user_models/user_sessions.py
# Remove index=True from jti (line 23) and last_activity_at (line 40)
# Keep index=True on user_id and is_active as they have different use cases

class UserSession(Base, SerializableMixin):
    """Store active user login sessions with device and location metadata."""
    __tablename__ = "user_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)  # Keep - no duplicate in __table_args__
    jti = Column(String(255), unique=True, nullable=False)  # Removed index=True - has explicit Index

    # ... other columns ...

    is_active = Column(Boolean, default=True, nullable=False, index=True)  # Keep - composite index serves different purpose

    # Timestamps
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    last_activity_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)  # Removed index=True - has explicit Index
    expires_at = Column(TIMESTAMP, nullable=False)
    revoked_at = Column(TIMESTAMP)

    # ... rest of the model ...

    __table_args__ = (
        Index('idx_user_sessions_user_active', 'user_id', 'is_active'),  # Composite index
        Index('idx_user_sessions_jti', 'jti'),
        Index('idx_user_sessions_last_activity', 'last_activity_at'),
    )
```

### Step 3: Generate Migration to Drop Duplicate Indexes

```bash
cd rext-backend
alembic revision --autogenerate -m "remove_duplicate_indexes"
```

Review the generated migration. It should contain `drop_index` operations for the auto-generated indexes. The migration should look something like:

```python
def upgrade():
    # Drop the auto-generated indexes (ix_tablename_column format)
    op.drop_index('ix_token_blacklist_jti', table_name='token_blacklist')
    op.drop_index('ix_token_blacklist_user_id', table_name='token_blacklist')
    op.drop_index('ix_token_blacklist_expires_at', table_name='token_blacklist')
    op.drop_index('ix_user_sessions_jti', table_name='user_sessions')
    op.drop_index('ix_user_sessions_last_activity_at', table_name='user_sessions')

def downgrade():
    # Recreate the indexes if needed
    op.create_index('ix_token_blacklist_jti', 'token_blacklist', ['jti'])
    # ... etc
```

### Step 4: Verify and Apply Migration

First, check current indexes in the database:

```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename IN ('token_blacklist', 'user_sessions')
ORDER BY tablename, indexname;
```

Apply the migration:

```bash
alembic upgrade head
```

### Step 5: Verify Indexes After Migration

```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'token_blacklist';

-- Should show:
-- idx_token_blacklist_jti
-- idx_token_blacklist_user_id
-- idx_token_blacklist_expires_at
-- token_blacklist_pkey
-- (unique constraint on jti creates its own index)

SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'user_sessions';

-- Should show:
-- idx_user_sessions_user_active
-- idx_user_sessions_jti
-- idx_user_sessions_last_activity
-- user_sessions_pkey
-- (unique constraint on jti creates its own index)
-- ix_user_sessions_user_id (kept - no duplicate)
-- ix_user_sessions_is_active (kept - no duplicate)
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| None | N/A | This issue is isolated to these two model files |

---

## Testing Instructions

### Before Fix (Verify Duplicates Exist):
1. Connect to the database and list indexes:
   ```sql
   SELECT indexname, indexdef
   FROM pg_indexes
   WHERE tablename = 'token_blacklist'
   ORDER BY indexname;
   ```
2. **Expected:** Multiple indexes on the same columns, e.g.:
   - `idx_token_blacklist_jti` and `ix_token_blacklist_jti` both on `jti`
   - Similar duplicates for `user_id` and `expires_at`

### After Fix (Verify Duplicates Removed):
1. Apply the migration: `alembic upgrade head`
2. Re-run the index query:
   ```sql
   SELECT indexname, indexdef
   FROM pg_indexes
   WHERE tablename = 'token_blacklist'
   ORDER BY indexname;
   ```
3. **Expected:** Only one index per column (the explicitly named one from `__table_args__`)
4. Verify authentication still works:
   - Log in and verify session is created
   - Log out and verify token is blacklisted
   - Attempt to use the blacklisted token (should fail)

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "token" --tb=short
pytest tests/ -v -k "session" --tb=short
pytest tests/ -v -k "auth" --tb=short
```

---

## Acceptance Criteria

- [ ] `token_blacklist.py` columns `jti`, `user_id`, `expires_at` no longer have `index=True`
- [ ] `user_sessions.py` columns `jti`, `last_activity_at` no longer have `index=True`
- [ ] Explicit `Index()` declarations in `__table_args__` are preserved
- [ ] Alembic migration drops the duplicate auto-generated indexes
- [ ] After migration, each column has only one index
- [ ] Token blacklist lookup still works correctly
- [ ] Session management still works correctly
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.1 - Defining Constraints and Indexes](https://docs.sqlalchemy.org/en/21/core/constraints.html) - Index definition options
- **Security Advisory:** N/A (performance issue, not security)
- **Migration Guide:** N/A
- **Best Practice Reference:** [PostgreSQL Indexing with SQLAlchemy Guide](https://www.opcito.com/blogs/a-guide-to-postgresql-indexing-with-sqlalchemy) - Comprehensive indexing guide
- **Related Issues/PRs:** [SQLAlchemy Discussion #7597](https://github.com/sqlalchemy/sqlalchemy/discussions/7597) - Discussion on Index declaration patterns

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-035 (TokenBlacklist.user_id Missing FK - same file)
