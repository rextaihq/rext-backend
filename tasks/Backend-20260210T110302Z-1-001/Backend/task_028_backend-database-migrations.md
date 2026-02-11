# Task 028: Fix Module-level __table_args__ in DiscountUsage - Named Indexes Silently Ignored

## Metadata
- **Task ID:** TASK-028
- **Source:** Database & Migrations Audit (Finding #2 under P0 Critical)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P0 Critical
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `DiscountUsage` model in `src/api/models/subscription_models/discount_usage.py` has the same bug as LicenseActivation (TASK-027): the `__table_args__` tuple is defined at **module level** (line 135) instead of inside the class body (which ends at line 131). SQLAlchemy's declarative system only recognizes `__table_args__` when defined as a class-level attribute.

According to the [SQLAlchemy 2.0 documentation](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html), `__table_args__` must be placed inside the class body alongside `__tablename__` and column definitions. The current module-level placement means four named indexes are silently ignored:

1. `idx_discount_usage_user_id` - index on `user_id`
2. `idx_discount_usage_code` - index on `discount_code`
3. `idx_discount_usage_applied_at` - index on `applied_at`
4. `idx_discount_usage_subscription_id` - index on `subscription_id`

**Important Mitigation:** Unlike TASK-027, the columns in this model already have `index=True` on their column definitions (lines 43, 50, 57, 90), so PostgreSQL will create auto-named indexes. The impact is that the **explicitly named indexes** defined in `__table_args__` are not created, but functionally equivalent auto-named indexes do exist. The primary issue is inconsistency - the code declares named indexes but they don't exist, which could cause confusion during debugging or index maintenance.

---

## Current Code

```python
# File: rext-backend/src/api/models/subscription_models/discount_usage.py
# Lines: 112-140

    def __repr__(self) -> str:
        return (
            f"<DiscountUsage(id={self.id}, user_id={self.user_id}, "
            f"code={self.discount_code}, amount={self.discount_amount})>"
        )

    def to_dict(self) -> dict:
        """Convert model to dictionary."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "subscription_id": str(self.subscription_id) if self.subscription_id else None,
            "discount_code": self.discount_code,
            "discount_amount": float(self.discount_amount) if self.discount_amount else None,
            "discount_amount_type": self.discount_amount_type,
            "order_id": self.order_id,
            "lemonsqueezy_discount_id": self.lemonsqueezy_discount_id,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "metadata": self.usage_metadata
        }


# Indexes are created in the migration file  <-- THIS IS OUTSIDE THE CLASS (MODULE LEVEL)
__table_args__ = (
    Index('idx_discount_usage_user_id', 'user_id'),
    Index('idx_discount_usage_code', 'discount_code'),
    Index('idx_discount_usage_applied_at', 'applied_at'),
    Index('idx_discount_usage_subscription_id', 'subscription_id'),
)
```

The misleading comment "Indexes are created in the migration file" compounds the confusion - it suggests these indexes exist somewhere, but the module-level placement means SQLAlchemy never sees them.

---

## Why This Matters (Context & Reasoning)

The `DiscountUsage` model tracks when users apply discount codes during checkout for analytics and fraud prevention. While the immediate performance impact is mitigated (columns have `index=True`), this bug matters because:

1. **Code-Reality Mismatch:** The codebase explicitly declares named indexes that don't exist. Developers maintaining this code may assume these indexes exist when debugging query performance or writing index maintenance scripts.

2. **Duplicate Index Risk:** If someone notices the missing named indexes and adds them via migration without realizing auto-named indexes already exist, the table will have duplicate indexes on the same columns.

3. **Consistency with LicenseActivation:** Both models have the same bug. Fixing one but not the other creates inconsistent patterns in the codebase.

4. **Future Refactoring Risk:** If someone removes `index=True` from the columns assuming `__table_args__` will handle it, the indexes will disappear entirely.

---

## Impact

- **Severity:** Lower than TASK-027 because column-level `index=True` provides equivalent functionality. Primary issue is code clarity and consistency.
- **Affected Users/Flows:** Discount code analytics, fraud detection queries, admin reporting on discount usage.
- **Blast Radius:** Isolated to discount_usage table. Functional impact is minimal due to existing auto-indexes.

---

## Recommended Solution

### Step 1: Move __table_args__ Inside the Class Body and Remove Redundant Indexes

Since the columns already have `index=True`, the explicit `Index()` objects in `__table_args__` are redundant and should be removed to avoid duplicate indexes. However, if you want to keep the named indexes for clarity, choose one approach:

**Option A (Recommended): Remove redundant __table_args__ entirely**

```python
# File: rext-backend/src/api/models/subscription_models/discount_usage.py
# Remove lines 134-140 completely (the module-level __table_args__)

# The columns already have index=True:
# - user_id (line 43): index=True
# - subscription_id (line 50): index=True
# - discount_code (line 57): index=True
# - applied_at (line 90): index=True

# No __table_args__ needed - indexes are handled by column definitions
```

**Option B: Move inside class but remove index=True from columns to avoid duplicates**

```python
# File: rext-backend/src/api/models/subscription_models/discount_usage.py

class DiscountUsage(Base, SerializableMixin):
    # ... (column definitions) ...

    # Remove index=True from these columns:
    # user_id: remove index=True from line 43
    # subscription_id: remove index=True from line 50
    # discount_code: remove index=True from line 57
    # applied_at: remove index=True from line 90

    # Table arguments with named indexes
    __table_args__ = (
        Index('idx_discount_usage_user_id', 'user_id'),
        Index('idx_discount_usage_code', 'discount_code'),
        Index('idx_discount_usage_applied_at', 'applied_at'),
        Index('idx_discount_usage_subscription_id', 'subscription_id'),
    )

    def __repr__(self) -> str:
        # ...
```

### Step 2: Delete the Module-level __table_args__

Regardless of which option you choose, delete lines 134-140:

```python
# DELETE THESE LINES (134-140):
# Indexes are created in the migration file
__table_args__ = (
    Index('idx_discount_usage_user_id', 'user_id'),
    Index('idx_discount_usage_code', 'discount_code'),
    Index('idx_discount_usage_applied_at', 'applied_at'),
    Index('idx_discount_usage_subscription_id', 'subscription_id'),
)
```

### Step 3: Verify No Migration Needed (Option A)

If using Option A (removing redundant `__table_args__`):

```bash
cd rext-backend
alembic revision --autogenerate -m "cleanup_discount_usage_model"
```

The generated migration should be empty (no changes) since indexes already exist via `index=True`.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/models/subscription_models/license_activations.py` | `126-131` | Same bug - but composite indexes ARE needed there (see TASK-027) |

---

## Testing Instructions

### Before Fix (Verify Current State):
1. Connect to PostgreSQL database
2. Run: `SELECT indexname FROM pg_indexes WHERE tablename = 'discount_usage';`
3. Note: You should see auto-named indexes like `ix_discount_usage_user_id` (from `index=True`) but NOT `idx_discount_usage_user_id` (the named index from `__table_args__`)

### After Fix (Verify the Solution):
1. Apply the code change (Option A: delete module-level `__table_args__`)
2. Run: `alembic revision --autogenerate -m "cleanup_discount_usage"`
3. Verify the generated migration is empty or only contains comment cleanup
4. Run the model file in Python to verify no syntax errors:
   ```bash
   python -c "from src.api.models.subscription_models.discount_usage import DiscountUsage; print('OK')"
   ```

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "discount"
```

---

## Acceptance Criteria

- [ ] Module-level `__table_args__` (lines 134-140) is deleted
- [ ] If keeping named indexes (Option B): `__table_args__` moved inside class AND `index=True` removed from columns
- [ ] If removing redundant indexes (Option A): No `__table_args__` needed, column-level `index=True` remains
- [ ] No duplicate indexes created in database
- [ ] Alembic autogenerate shows no unexpected changes
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 - Table Configuration with Declarative](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html) - Documents that `__table_args__` must be a class-level attribute
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [SQLAlchemy - Column-level vs Table-level Indexes](https://docs.sqlalchemy.org/en/20/core/constraints.html#indexes) - Guidance on when to use `index=True` vs explicit `Index()` objects

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-027 (same bug in LicenseActivation - but that one has composite indexes that ARE needed)
