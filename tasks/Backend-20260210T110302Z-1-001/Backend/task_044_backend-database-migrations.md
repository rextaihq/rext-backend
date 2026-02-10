# Task 044: Remove Redundant Index on UserPreferences.user_id

## Metadata
- **Task ID:** TASK-044
- **Source:** Backend Database & Migrations Audit (Finding #26 under P2 Medium)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P2 Medium
- **Category:** performance
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `UserPreferences` model in `src/api/models/user_models/user_preferences.py` has a `user_id` column with `unique=True` (line 22), which in PostgreSQL automatically creates a unique B-tree index on that column. Additionally, the model's `__table_args__` (lines 39-41) declares an explicit non-unique `Index("ix_user_preferences_user_id", "user_id")` on the same column. This results in two indexes on the `user_id` column:

1. A **unique index** automatically created by PostgreSQL to enforce the `UNIQUE` constraint (named something like `user_preferences_user_id_key`)
2. A **non-unique index** explicitly created by SQLAlchemy via `__table_args__` (named `ix_user_preferences_user_id`)

The non-unique index is completely redundant because the unique index already serves all lookup queries on `user_id`. PostgreSQL uses the unique index for both uniqueness enforcement and query optimization (it is a full B-tree index). Maintaining a second index doubles the write overhead for INSERT and UPDATE operations on this table and wastes disk space.

This is the same class of issue identified in TASK-034 (duplicate indexes in TokenBlacklist and UserSession), where columns had both `index=True` and explicit `Index()` declarations. In this case, the duplication is between `unique=True` and an explicit `Index()`.

---

## Current Code

```python
# File: rext-backend/src/api/models/user_models/user_preferences.py
# Lines: 16-41

class UserPreferences(Base):
    """User preferences for UI and behavior customization"""

    __tablename__ = "user_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Display preferences
    theme = Column(String(20), nullable=True, default="system")
    date_format = Column(String(20), nullable=True, default="iso")
    time_format = Column(String(20), nullable=True, default="24h")
    items_per_page = Column(Integer, nullable=True, default=25)
    sidebar_collapsed = Column(Boolean, nullable=True, default=False)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("Users", back_populates="preferences")

    # Indexes
    __table_args__ = (
        Index("ix_user_preferences_user_id", "user_id"),  # REDUNDANT — unique=True already creates an index
    )
```

---

## Why This Matters (Context & Reasoning)

Every INSERT and UPDATE to the `user_preferences` table must update both indexes on `user_id`. Since every user has preferences (created during registration or first use), and preferences can be updated frequently (theme changes, pagination settings), this doubles the index maintenance cost for the most common column.

While the performance impact on a single table is small, this represents a pattern that should be corrected to prevent it from being copied to new models. The codebase already had this exact issue in `TokenBlacklist` and `UserSession` (addressed in TASK-034), and this is a third instance of the same anti-pattern.

---

## Impact

- **Severity:** Minor performance overhead — doubled index maintenance on INSERT/UPDATE for user_preferences table. Wasted disk space for the redundant index.
- **Affected Users/Flows:** Any operation that creates or updates user preferences (registration, profile settings changes).
- **Blast Radius:** Isolated to the `user_preferences` table.

---

## Recommended Solution

### Step 1: Remove the Redundant Index from `__table_args__`

```python
# File: rext-backend/src/api/models/user_models/user_preferences.py
# Remove lines 39-41 entirely (the __table_args__ tuple)

# BEFORE (lines 38-41):
    # Indexes
    __table_args__ = (
        Index("ix_user_preferences_user_id", "user_id"),
    )

# AFTER: Remove the __table_args__ entirely, or if other entries exist, keep them
# (In this case, there are no other entries, so remove the entire block)
```

The complete updated model should have the `__table_args__` block and the comment above it removed.

### Step 2: Generate Alembic Migration to Drop the Redundant Index

```bash
cd rext-backend && alembic revision --autogenerate -m "drop_redundant_user_preferences_user_id_index"
```

Verify the generated migration drops the `ix_user_preferences_user_id` index. It should look like:

```python
# File: rext-backend/alembic/versions/<auto>_drop_redundant_user_preferences_user_id_index.py
from alembic import op

def upgrade() -> None:
    op.drop_index('ix_user_preferences_user_id', table_name='user_preferences')

def downgrade() -> None:
    op.create_index('ix_user_preferences_user_id', 'user_preferences', ['user_id'], unique=False)
```

### Step 3: Verify the Unique Index Remains

After running the migration, confirm that the unique constraint index still exists:

```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'user_preferences' AND indexdef LIKE '%user_id%';
```

You should see one remaining index — the unique constraint index on `user_id`.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/models/user_models/token_blacklist.py` | `33-38` | Similar pattern — `index=True` on columns plus explicit `Index()` in `__table_args__` (addressed in TASK-034) |
| `src/api/models/user_models/user_sessions.py` | `50-54` | Similar pattern — `index=True` on columns plus explicit `Index()` (addressed in TASK-034) |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Connect to PostgreSQL and list indexes on `user_preferences`:
   ```sql
   SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'user_preferences';
   ```
2. Observe two indexes on `user_id`: one from the unique constraint and one named `ix_user_preferences_user_id`.

### After Fix (Verify the Solution):
1. Run the migration: `cd rext-backend && alembic upgrade head`
2. List indexes again — only the unique constraint index should remain on `user_id`.
3. Test that user preference CRUD operations still work correctly.
4. Verify that the unique constraint still prevents duplicate `user_id` values: attempt to INSERT two rows with the same `user_id` — should fail with a unique violation error.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v
```

---

## Acceptance Criteria

- [ ] The explicit `Index("ix_user_preferences_user_id", "user_id")` is removed from the model's `__table_args__`
- [ ] Alembic migration drops the redundant `ix_user_preferences_user_id` index
- [ ] The unique constraint on `user_id` remains intact
- [ ] Queries on `user_id` still use an index (the unique constraint index)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [PostgreSQL — Unique Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-UNIQUE-CONSTRAINTS) — "PostgreSQL automatically creates a unique index when a unique constraint or primary key is defined for a table"
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [SQLAlchemy — Column.unique](https://docs.sqlalchemy.org/en/20/core/metadata.html#sqlalchemy.schema.Column.params.unique) — documents that `unique=True` creates a UNIQUE constraint (which implies an index)
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-034 (Duplicate Index Declarations in TokenBlacklist and UserSession — same class of issue)
