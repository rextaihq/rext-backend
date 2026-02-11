# Task 035: Add Missing ForeignKey Constraint to TokenBlacklist.user_id

## Metadata
- **Task ID:** TASK-035
- **Source:** Backend Database & Migrations Audit (Finding #9 under P1 High)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P1 High
- **Category:** data-integrity
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `TokenBlacklist.user_id` column is defined without a `ForeignKey` constraint referencing the `users` table. The column is declared as:

```python
user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
```

This is inconsistent with every other model in the codebase that references a user. For comparison, the `UserSession` model (which serves a similar purpose - tracking user authentication state) correctly declares:

```python
user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
```

Without the ForeignKey constraint, PostgreSQL has no knowledge that `token_blacklist.user_id` should reference `users.id`. This creates several problems:

1. **No referential integrity:** The `user_id` column can contain UUID values that don't correspond to any user in the database. There's nothing preventing insertion of blacklisted tokens for non-existent users.

2. **Orphaned records accumulate:** When a user is deleted, their blacklisted tokens remain in the `token_blacklist` table indefinitely. The table will grow with stale data that serves no purpose.

3. **Inconsistent behavior:** The `UserSession` model uses `ondelete="CASCADE"` which automatically cleans up sessions when a user is deleted. The `TokenBlacklist` model should have the same behavior - when a user is deleted, their blacklisted tokens become meaningless and should be automatically removed.

4. **Query planner disadvantage:** PostgreSQL's query planner can use FK relationships to optimize joins. Without the FK, the optimizer has less information to work with.

According to PostgreSQL and SQLAlchemy best practices, foreign key constraints should always be declared to enforce referential integrity at the database level. This is especially important for security-sensitive tables like `token_blacklist` where data integrity affects authentication security.

---

## Current Code

```python
# File: src/api/models/user_models/token_blacklist.py
# Line: 28

user_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # User who owned the token
```

**For comparison - correct pattern in user_sessions.py:**

```python
# File: src/api/models/user_models/user_sessions.py
# Line: 22

user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
```

**Users model shows proper FK relationship setup:**

```python
# File: src/api/models/user_models/users.py
# Lines: 49-50

sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
# Note: No relationship defined for TokenBlacklist because there's no FK
```

---

## Why This Matters (Context & Reasoning)

The `token_blacklist` table is a critical security component that stores revoked JWT tokens to prevent their reuse. Its purpose is:

1. **Logout:** When a user logs out, their access token is blacklisted to prevent reuse
2. **Token refresh:** Old refresh tokens are blacklisted after rotation
3. **Forced logout:** Admins can revoke all tokens for a user
4. **Password change:** All existing tokens are blacklisted when password changes

The table is checked on every authenticated API request to verify the token hasn't been revoked. This makes data integrity critical:

- **Security implication:** Orphaned records (tokens for deleted users) consume resources during lookup operations but serve no security purpose
- **Storage growth:** Without cascade delete, the table grows indefinitely with useless records
- **Inconsistency:** The application assumes `user_id` references a valid user, but the database doesn't enforce this

The `UserSession` model already demonstrates the correct pattern for user-related authentication tables. The `TokenBlacklist` model should follow the same pattern for consistency and correctness.

---

## Impact

- **Severity:** Data integrity violation. Orphaned token records accumulate indefinitely when users are deleted. No referential integrity enforcement on a security-critical table.
- **Affected Users/Flows:** User deletion, token cleanup jobs, any database maintenance operations
- **Blast Radius:** Isolated to `token_blacklist` table, but affects all authentication flows that check token status

---

## Recommended Solution

Add a `ForeignKey` constraint to the `user_id` column with `ondelete="CASCADE"` to automatically clean up blacklisted tokens when users are deleted.

### Step 1: Check for Orphaned Records

Before adding the FK constraint, check if any orphaned records exist:

```sql
SELECT tb.*
FROM token_blacklist tb
LEFT JOIN users u ON tb.user_id = u.id
WHERE u.id IS NULL;
```

If orphaned records exist, delete them:

```sql
DELETE FROM token_blacklist tb
WHERE NOT EXISTS (
    SELECT 1 FROM users u WHERE u.id = tb.user_id
);
```

### Step 2: Update token_blacklist.py

```python
# File: src/api/models/user_models/token_blacklist.py
# Add ForeignKey import at the top (line 15):
from sqlalchemy import Column, String, TIMESTAMP, Index, ForeignKey

# Replace line 28:
# OLD:
# user_id = Column(UUID(as_uuid=True), nullable=False, index=True)

# NEW:
user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id", ondelete="CASCADE"),
    nullable=False,
    index=True
)  # User who owned the token - cascade delete when user is removed
```

### Step 3: Add Relationship in Users Model (Optional but Recommended)

```python
# File: src/api/models/user_models/users.py
# Add after line 50 (sessions relationship):

blacklisted_tokens = relationship("TokenBlacklist", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
```

```python
# File: src/api/models/user_models/token_blacklist.py
# Add after __table_args__ (around line 39):
from sqlalchemy.orm import relationship

# Add inside the class:
user = relationship("Users", back_populates="blacklisted_tokens")
```

### Step 4: Generate and Apply Migration

```bash
cd rext-backend
alembic revision --autogenerate -m "add_fk_to_token_blacklist_user_id"
```

Review the generated migration. It should look like:

```python
def upgrade():
    # First, delete orphaned records (if migration includes this)
    op.execute("""
        DELETE FROM token_blacklist tb
        WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.id = tb.user_id)
    """)

    # Add the foreign key constraint
    op.create_foreign_key(
        'fk_token_blacklist_user_id',
        'token_blacklist', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )

def downgrade():
    op.drop_constraint('fk_token_blacklist_user_id', 'token_blacklist', type_='foreignkey')
```

Apply the migration:

```bash
alembic upgrade head
```

### Step 5: Verify FK Constraint Exists

```sql
SELECT conname, contype, confdeltype
FROM pg_constraint
WHERE conrelid = 'token_blacklist'::regclass AND contype = 'f';

-- Should show:
-- conname: fk_token_blacklist_user_id
-- contype: f (foreign key)
-- confdeltype: c (cascade)
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/models/user_models/users.py` | ~50 | Add `blacklisted_tokens` relationship (optional) |
| `src/services/auth_service.py` | Various | May use relationship for cleaner queries (optional) |
| `src/utils/token_cleanup.py` | Various | Token cleanup may be simplified since FK cascade handles user deletion |

---

## Testing Instructions

### Before Fix (Verify Missing Constraint):
1. Check that no FK constraint exists:
   ```sql
   SELECT conname FROM pg_constraint
   WHERE conrelid = 'token_blacklist'::regclass AND contype = 'f';
   -- Should return empty result
   ```

2. Create an orphaned record (requires a non-existent user UUID):
   ```sql
   INSERT INTO token_blacklist (id, jti, token_type, user_id, revoked_at, expires_at, reason)
   VALUES (
       gen_random_uuid(),
       'test-orphan-jti',
       'access',
       '00000000-0000-0000-0000-000000000000',  -- Non-existent user
       NOW(),
       NOW() + INTERVAL '1 hour',
       'test'
   );
   -- Should succeed (no FK check)
   ```

### After Fix (Verify Constraint Works):
1. Apply the migration: `alembic upgrade head`

2. Verify FK constraint exists:
   ```sql
   SELECT conname, confdeltype FROM pg_constraint
   WHERE conrelid = 'token_blacklist'::regclass AND contype = 'f';
   -- Should show fk_token_blacklist_user_id with confdeltype = 'c'
   ```

3. Try to insert with non-existent user:
   ```sql
   INSERT INTO token_blacklist (id, jti, token_type, user_id, revoked_at, expires_at, reason)
   VALUES (
       gen_random_uuid(),
       'test-orphan-jti-2',
       'access',
       '00000000-0000-0000-0000-000000000000',
       NOW(),
       NOW() + INTERVAL '1 hour',
       'test'
   );
   -- Should fail: violates foreign key constraint
   ```

4. Test cascade delete:
   - Create a test user
   - Blacklist a token for that user
   - Delete the user
   - Verify the blacklisted token is also deleted

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "token" --tb=short
pytest tests/ -v -k "blacklist" --tb=short
pytest tests/ -v -k "auth" --tb=short
```

---

## Acceptance Criteria

- [ ] `TokenBlacklist.user_id` has `ForeignKey("users.id", ondelete="CASCADE")`
- [ ] Any existing orphaned records have been cleaned up
- [ ] Alembic migration generated and applies successfully
- [ ] FK constraint exists in PostgreSQL (`pg_constraint`)
- [ ] Inserting with non-existent user_id fails with constraint violation
- [ ] Deleting a user cascades to delete their blacklisted tokens
- [ ] Token blacklist functionality still works correctly
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.1 - Special Relationship Persistence Patterns](https://docs.sqlalchemy.org/en/21/orm/relationship_persistence.html) - Cascade and orphan handling
- **Security Advisory:** N/A (data integrity issue)
- **Migration Guide:** N/A
- **Best Practice Reference:** [Understanding PostgreSQL Foreign Keys and Relationships](https://moldstud.com/articles/p-understanding-postgresql-foreign-keys-and-relationships-a-comprehensive-guide) - Comprehensive FK guide
- **Related Issues/PRs:** [PostgreSQL Referential Integrity Tutorial](https://wiki.postgresql.org/wiki/Referential_Integrity_Tutorial_&_Hacking_the_Referential_Integrity_tables)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-032 (Missing ondelete specifications - related FK issue), TASK-034 (Duplicate indexes in TokenBlacklist - same file)
