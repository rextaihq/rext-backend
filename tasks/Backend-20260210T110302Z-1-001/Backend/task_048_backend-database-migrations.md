# Task 048: Standardize 4 Different Soft Delete Patterns into a Single SoftDeleteMixin

## Metadata
- **Task ID:** TASK-048
- **Source:** Backend Database & Migrations Audit (Finding #19 under P2 Medium)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P2 Medium
- **Category:** refactoring
- **Effort Estimate:** large (4+ hours)

---

## Description

The codebase implements soft deletion using four distinct and incompatible patterns across different models, creating inconsistency in how "deleted" records are represented, queried, and restored. This lack of standardization means every service that queries a soft-deletable model must know which specific pattern that model uses, and there is no shared filtering mechanism to ensure deleted records are excluded from normal queries.

**Pattern 1** — `deleted_at` column only (with `DateTime(timezone=True)`): Used by `WorkspaceModel` (line 23), `Content` (line 45), and `WorkspaceIntegration` (line 36). `WorkspaceModel` additionally has a `deleted_by` FK column (line 24) to track who performed the deletion, which the others lack.

**Pattern 2** — `deleted_at` + `deactivated_at` dual columns: Used only by `Users` (lines 40-41), where `deactivated_at` represents a reversible account suspension and `deleted_at` represents permanent deletion. Both use `TIMESTAMP` without timezone.

**Pattern 3** — `is_deleted` Boolean + `deleted_at` with helper methods: Used only by `Notification` (lines 109-110), which provides `soft_delete()`, `restore()`, `archive()`, and `unarchive()` methods (lines 216-224). This is the most complete implementation but is not shared with any other model.

**Pattern 4** — No soft delete: All remaining ~25 models hard-delete records when removed.

**Pattern 1** itself is internally inconsistent: `Media` (line 102) uses `TIMESTAMP` without timezone for `deleted_at`, while `WorkspaceModel`, `Content`, and `WorkspaceIntegration` use `DateTime(timezone=True)`. This means timezone-aware and naive timestamps coexist in soft delete columns across the codebase, creating potential comparison bugs.

The absence of a shared mixin means there are no automatic query filters to exclude soft-deleted records. Every `SELECT` query against a soft-deletable table must manually include `WHERE deleted_at IS NULL` (or `WHERE is_deleted = False` for Notification), and forgetting this filter results in deleted records appearing in API responses — a data leakage risk.

---

## Current Code

```python
# File: rext-backend/src/api/models/workspace_models/workspace_model.py
# Lines: 23-24 (Pattern 1: deleted_at with deleted_by)
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # Soft delete timestamp
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # User who deleted
```

```python
# File: rext-backend/src/api/models/content_models/content.py
# Line: 45 (Pattern 1: deleted_at only)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
```

```python
# File: rext-backend/src/api/models/media_models/media.py
# Line: 102 (Pattern 1 variant: TIMESTAMP without timezone!)
    deleted_at = Column(TIMESTAMP, comment="Soft delete timestamp")
```

```python
# File: rext-backend/src/api/models/user_models/users.py
# Lines: 40-41 (Pattern 2: dual columns)
    deactivated_at = Column(TIMESTAMP)
    deleted_at = Column(TIMESTAMP)
```

```python
# File: rext-backend/src/api/models/notification/notification_model.py
# Lines: 109-110, 216-224 (Pattern 3: Boolean + timestamp + helper methods)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(TIMESTAMP, nullable=True)

    def soft_delete(self):
        """Soft delete notification."""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()

    def restore(self):
        """Restore soft-deleted notification."""
        self.is_deleted = False
        self.deleted_at = None
```

---

## Why This Matters (Context & Reasoning)

Soft deletion is a foundational data management pattern in multi-tenant SaaS applications. When users delete workspaces, content, or media, the data must be retained for audit trails, undo functionality, and compliance requirements. The inconsistency across four patterns means:

1. **Query correctness is fragile.** A developer writing `select(WorkspaceModel).where(WorkspaceModel.deleted_at.is_(None))` must remember to use a completely different filter for Notification: `select(Notification).where(Notification.is_deleted == False)`. Missing this creates data leakage bugs.

2. **No automated protection.** Libraries like `sqlalchemy-easy-softdelete` can intercept all ORM queries and automatically append soft-delete filters using SQLAlchemy's `do_orm_execute` event. The current per-model approach cannot leverage this.

3. **The `deleted_by` tracking is inconsistently available.** Only `WorkspaceModel` tracks who deleted a record. This audit information is valuable for all soft-deletable models but is currently a one-off implementation.

4. **Timezone inconsistency in soft delete columns** (TASK-042 related) means comparing `deleted_at` values across models can produce incorrect results.

---

## Impact

- **Severity:** Deleted records may appear in normal queries if a developer forgets the model-specific filter pattern. The `is_deleted` Boolean on Notification adds an additional indexed column that is redundant with `deleted_at IS NOT NULL`.
- **Affected Users/Flows:** Any flow that queries soft-deletable models — workspace listing, content browsing, media galleries, notification feeds.
- **Blast Radius:** Moderate. The mixin change touches 6 model files directly, but the query filter changes may affect many service files that query these models.

---

## Recommended Solution

Create a `SoftDeleteMixin` that standardizes soft deletion across all models, using `deleted_at` as the canonical column and providing helper methods and a class-level filter.

### Step 1: Create the SoftDeleteMixin

```python
# File: rext-backend/src/api/models/base.py
# Add at the end of the file, after SerializableMixin:

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, event
from sqlalchemy.ext.hybrid import hybrid_property


class SoftDeleteMixin:
    """
    Mixin for soft-delete support on SQLAlchemy models.

    Adds a `deleted_at` column and provides:
    - `soft_delete()` / `restore()` instance methods
    - `is_deleted` hybrid property (works in Python and SQL)
    - `active()` class method for filtering queries

    Usage:
        class MyModel(Base, SerializableMixin, SoftDeleteMixin):
            __tablename__ = "my_table"

        # Query only active records:
        stmt = select(MyModel).where(MyModel.is_deleted == False)
        # Or use the helper:
        stmt = select(MyModel).where(MyModel.active())
    """

    deleted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Soft delete timestamp. NULL = active, non-NULL = deleted."
    )

    @hybrid_property
    def is_deleted(self) -> bool:
        """Python-side check: is this record soft-deleted?"""
        return self.deleted_at is not None

    @is_deleted.expression
    def is_deleted(cls):
        """SQL-side expression: generates `deleted_at IS NOT NULL`."""
        return cls.deleted_at.isnot(None)

    def soft_delete(self) -> None:
        """Mark this record as soft-deleted."""
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.deleted_at = None

    @classmethod
    def active(cls):
        """Return a filter expression for non-deleted records.

        Usage: select(Model).where(Model.active())
        """
        return cls.deleted_at.is_(None)
```

### Step 2: Apply SoftDeleteMixin to Existing Models

For each model, replace the manual `deleted_at` column with the mixin. Remove any duplicate `is_deleted` Boolean columns and manual `soft_delete()`/`restore()` methods.

**WorkspaceModel:**
```python
# File: rext-backend/src/api/models/workspace_models/workspace_model.py
# Change class declaration on line 12:
class WorkspaceModel(Base, SerializableMixin, SoftDeleteMixin):
    # ...
    # Remove line 23: deleted_at = Column(DateTime(timezone=True), nullable=True)
    # Keep line 24: deleted_by is workspace-specific, not part of the mixin
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
```

**Content:**
```python
# File: rext-backend/src/api/models/content_models/content.py
# Change class declaration on line 10:
class Content(Base, SerializableMixin, SoftDeleteMixin):
    # ...
    # Remove line 45: deleted_at = Column(DateTime(timezone=True), nullable=True)
```

**Media:**
```python
# File: rext-backend/src/api/models/media_models/media.py
# Change class declaration on line 18:
class Media(Base, SerializableMixin, SoftDeleteMixin):
    # ...
    # Remove line 102: deleted_at = Column(TIMESTAMP, comment="Soft delete timestamp")
    # The mixin provides deleted_at with DateTime(timezone=True) — fixes the timezone issue
```

**WorkspaceIntegration:**
```python
# File: rext-backend/src/api/models/workspace_models/workspace_integration.py
# Change class declaration on line 10:
class WorkspaceIntegration(Base, SerializableMixin, SoftDeleteMixin):
    # ...
    # Remove line 36: deleted_at = Column(DateTime(timezone=True), nullable=True)
```

**Notification:**
```python
# File: rext-backend/src/api/models/notification/notification_model.py
# Change class declaration on line 12:
class Notification(Base, SerializableMixin, SoftDeleteMixin):
    # ...
    # Remove line 109: is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    # Remove line 110: deleted_at = Column(TIMESTAMP, nullable=True)
    # Remove lines 216-224: soft_delete() and restore() methods (now provided by mixin)
    # Keep archive()/unarchive() as they are Notification-specific
```

### Step 3: Handle the Users Model Separately

The `Users` model has a `deactivated_at` column that represents a different concept (reversible account suspension) from `deleted_at` (permanent deletion). Apply `SoftDeleteMixin` for the `deleted_at` column but keep `deactivated_at` as a separate User-specific field.

```python
# File: rext-backend/src/api/models/user_models/users.py
# Change class declaration on line 16:
class Users(Base, SerializableMixin, SoftDeleteMixin):
    # ...
    # Remove line 41: deleted_at = Column(TIMESTAMP) — provided by mixin now
    # Keep line 40: deactivated_at = Column(TIMESTAMP) — User-specific concept
```

### Step 4: Create Alembic Migration for Schema Changes

```python
# The main schema changes are:
# 1. Media.deleted_at changes from TIMESTAMP to DateTime(timezone=True) — type change
# 2. Users.deleted_at changes from TIMESTAMP to DateTime(timezone=True) — type change
# 3. Notification.is_deleted Boolean column can be dropped (replaced by hybrid property)
#
# Generate with: alembic revision --autogenerate -m "standardize_soft_delete_columns"
# Then review and adjust the generated migration manually.
```

### Step 5: Update Notification Composite Index

The `Notification` model's composite index `idx_user_read_deleted` (line 172) references `is_deleted`. After removing the physical column, update the index to use `deleted_at`:

```python
# File: rext-backend/src/api/models/notification/notification_model.py
# Update __table_args__ (line 170-176):
    __table_args__ = (
        Index('idx_user_read_deleted', 'user_id', 'is_read', 'deleted_at'),
        Index('idx_user_created', 'user_id', 'created_at'),
        Index('idx_user_type_created', 'user_id', 'type', 'created_at'),
        Index('idx_workspace_created', 'workspace_id', 'created_at'),
    )
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/services/` (multiple) | Various | Any service querying soft-deletable models with manual `WHERE deleted_at IS NULL` filters — can now use `Model.active()` |
| `rext-backend/src/services/notifications_services.py` | Various | Queries Notification with `is_deleted == False` — must change to `Notification.active()` or `Notification.deleted_at.is_(None)` |
| `rext-backend/src/api/routes/` (multiple) | Various | Route handlers that filter by `deleted_at` or `is_deleted` |
| `rext-backend/src/utils/account_cleanup.py` | Various | Account deletion utility that sets `deleted_at` on Users |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Inspect the model files and confirm four distinct soft-delete patterns exist
2. Query `Notification` with `WHERE deleted_at IS NOT NULL` — compare results to `WHERE is_deleted = True` — they should match (if not, the redundant column is out of sync)
3. Compare `Media.deleted_at` column type (TIMESTAMP) with `Content.deleted_at` type (DateTime with timezone) — confirm they differ

### After Fix (Verify the Solution):
1. Verify all models using `SoftDeleteMixin` have a `deleted_at` column of type `DateTime(timezone=True)`
2. Call `workspace.soft_delete()` — verify `workspace.deleted_at` is set and `workspace.is_deleted` returns `True`
3. Call `workspace.restore()` — verify `workspace.deleted_at` is `None` and `workspace.is_deleted` returns `False`
4. Query `select(WorkspaceModel).where(WorkspaceModel.active())` — verify soft-deleted workspaces are excluded
5. Verify `Notification.is_deleted` hybrid property works in both Python (`notification.is_deleted`) and SQL (`where(Notification.is_deleted == False)`) contexts
6. Run migration — verify `Media.deleted_at` column type changed to timezone-aware

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v --no-header
```

---

## Acceptance Criteria

- [ ] `SoftDeleteMixin` exists in `src/api/models/base.py` with `deleted_at`, `is_deleted` hybrid property, `soft_delete()`, `restore()`, and `active()` class method
- [ ] `WorkspaceModel`, `Content`, `Media`, `WorkspaceIntegration`, `Notification`, and `Users` all use `SoftDeleteMixin`
- [ ] No model has a manual `deleted_at` column definition (all come from the mixin)
- [ ] `Notification.is_deleted` physical Boolean column is removed and replaced by the hybrid property
- [ ] All `deleted_at` columns use `DateTime(timezone=True)` consistently
- [ ] Alembic migration successfully updates column types and drops `Notification.is_deleted`
- [ ] Composite index on Notification is updated to reference `deleted_at` instead of `is_deleted`
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy Hybrid Properties](https://docs.sqlalchemy.org/en/20/orm/extensions/hybrid.html) — Documentation for `hybrid_property` used in the `is_deleted` expression
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [sqlalchemy-easy-softdelete library](https://github.com/flipbit03/sqlalchemy-easy-softdelete) — Reference implementation for automatic soft-delete query filtering using `do_orm_execute` event; the `SoftDeleteMixin` in this task provides the foundation needed to adopt this library later
- **Best Practice Reference:** [Implementing Soft Delete with Flask and SQLAlchemy](https://blog.miguelgrinberg.com/post/implementing-the-soft-delete-pattern-with-flask-and-sqlalchemy) — Miguel Grinberg's reference implementation of the soft-delete mixin pattern
- **Related Issues/PRs:** [SQLAlchemy Discussion #10517: Soft Deletable Tables](https://github.com/sqlalchemy/sqlalchemy/discussions/10517)

---

## Dependencies & Related Tasks

- **Depends on:** None directly, but implementing alongside TASK-042 (Inconsistent Timestamp Column Types) would be efficient since both standardize on `DateTime(timezone=True)`
- **Blocks:** None
- **Related:** TASK-042 (timestamp type standardization), TASK-045 (deprecated `datetime.utcnow()` — the mixin uses `datetime.now(timezone.utc)` which is the correct replacement)
