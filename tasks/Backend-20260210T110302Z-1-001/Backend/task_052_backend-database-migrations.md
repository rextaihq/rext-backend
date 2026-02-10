# Task 052: Create Reusable Model Mixins to Eliminate Repetitive Column Definitions

## Metadata
- **Task ID:** TASK-052
- **Source:** Backend Database & Migrations Audit (Finding #24 under P2 Medium)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P2 Medium
- **Category:** refactoring
- **Effort Estimate:** large (4+ hours)

---

## Description

All 33+ SQLAlchemy models in the Rext backend repeat the same boilerplate column definitions: a UUID primary key, `created_at`/`updated_at` timestamps, soft delete columns, and a `workspace_id` foreign key. There are no shared mixins to consolidate these patterns, meaning every model independently defines identical columns with minor variations.

For example, the UUID primary key pattern `id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)` is copied verbatim in every model file — see `roles.py:16`, `permissions.py:16`, `user_roles.py:16`, `invitations.py:11`, `users.py:19`, `workspace_model.py:15`, `content.py:14`, `notification_model.py:37-43`, and ~25 others.

Timestamp columns are repeated in ~30 models with four different type variations (`TIMESTAMP`, `DateTime(timezone=True)`, `DateTime`, `TIMESTAMP(timezone=True)`), and some use the deprecated `datetime.utcnow` while others use the correct `lambda: datetime.now(timezone.utc)`. Soft delete is implemented with `deleted_at` columns in 5+ models using three different patterns (see Finding 19 / TASK-048). The `workspace_id` FK is repeated in ~15 models, most without `index=True` (see Finding 5 / TASK-031).

This lack of shared mixins means that fixing the `datetime.utcnow` deprecation (Finding 21 / TASK-045) requires changing ~30 files individually, and standardizing timestamp types (Finding 20 / TASK-042) requires editing every model. A single `TimestampMixin` with the correct `DateTime(timezone=True)` and `lambda: datetime.now(timezone.utc)` would fix both issues across all models that adopt it. According to the [SQLAlchemy 2.0 documentation on declarative mixins](https://docs.sqlalchemy.org/en/20/orm/declarative_mixins.html), `Column` objects and `mapped_column()` constructs can be used directly in mixins without `declared_attr()`, making this refactoring straightforward.

---

## Current Code

```python
# File: rext-backend/src/api/models/user_models/roles.py
# Lines: 16, 28-29
# UUID PK + timestamps repeated in every model
id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
created_at = Column(TIMESTAMP, default=datetime.utcnow)
updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
```

```python
# File: rext-backend/src/api/models/user_models/users.py
# Lines: 19, 38-41
# Same pattern, different timestamp type, plus soft delete
id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
deactivated_at = Column(TIMESTAMP)
deleted_at = Column(TIMESTAMP)
```

```python
# File: rext-backend/src/api/models/workspace_models/workspace_model.py
# Lines: 15-16, 21-24
# Same pattern, yet another timestamp type
id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)
deleted_at = Column(DateTime(timezone=True), nullable=True)
deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
```

```python
# File: rext-backend/src/api/models/knowledge_models/persona_model.py
# Lines: 14-15, 35-36
# workspace_id FK repeated in ~15 models
id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=True)
```

---

## Why This Matters (Context & Reasoning)

The Rext backend has 33+ models spread across 15 subdirectories (`user_models/`, `workspace_models/`, `content_models/`, `subscription_models/`, `knowledge_models/`, `media_models/`, `audit_models/`, `admin_models/`, `email_models/`, `notification/`). Each model independently defines its primary key, timestamps, and — where applicable — soft delete and workspace scoping columns.

This creates a high maintenance burden: any change to the primary key pattern, timestamp handling, or soft delete logic requires updating every model file individually. For example, the deprecated `datetime.utcnow` is used in ~30 models (TASK-045), and fixing it one file at a time is error-prone. Similarly, the inconsistent timestamp types across four different variants (TASK-042) exist because each model was written independently.

Creating shared mixins is a foundational refactoring that makes many other tasks (TASK-042, TASK-043, TASK-045, TASK-048) easier and less error-prone to implement. It also prevents the same inconsistencies from recurring when new models are added.

---

## Impact

- **Severity:** Not a runtime bug, but the lack of mixins multiplies the effort of every schema-level fix by 30x. Without this, TASK-042 (timestamp types), TASK-045 (utcnow deprecation), and TASK-048 (soft delete patterns) each require touching 30+ files independently.
- **Affected Users/Flows:** All models and API responses. Adopting mixins standardizes timestamp behavior, which indirectly affects every endpoint that returns timestamps.
- **Blast Radius:** High — this touches every model file in the codebase. Should be coordinated with an Alembic migration to ensure no schema changes are accidentally introduced.

---

## Recommended Solution

Create four reusable mixins in a new file `src/api/models/mixins.py`, then incrementally adopt them across models. This is a large refactoring that should be done in phases to minimize risk.

### Step 1: Create the mixins file

```python
# File: rext-backend/src/api/models/mixins.py
"""
Reusable SQLAlchemy model mixins for the Rext backend.

These mixins provide standardized column definitions for common patterns:
- UUIDPrimaryKeyMixin: UUID primary key
- TimestampMixin: created_at / updated_at columns
- SoftDeleteMixin: deleted_at column with filtering helpers
- WorkspaceScopedMixin: workspace_id FK with index

Usage:
    from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin
    from src.api.database.base import Base
    from src.api.models.base import SerializableMixin

    class MyModel(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin):
        __tablename__ = "my_table"
        name = Column(String, nullable=False)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID


class UUIDPrimaryKeyMixin:
    """Standardized UUID primary key for all models."""
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False,
    )


class TimestampMixin:
    """Standardized created_at/updated_at timestamps with timezone awareness."""
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class SoftDeleteMixin:
    """Standardized soft delete support with deleted_at timestamp."""
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    @classmethod
    def active_filter(cls):
        """Return a filter expression for non-deleted records.

        Usage in queries:
            query = select(MyModel).where(MyModel.active_filter())
        """
        return cls.deleted_at.is_(None)

    @property
    def is_deleted(self) -> bool:
        """Check if the record has been soft-deleted."""
        return self.deleted_at is not None

    def soft_delete(self):
        """Mark the record as deleted."""
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self):
        """Restore a soft-deleted record."""
        self.deleted_at = None


class WorkspaceScopedMixin:
    """Standardized workspace_id FK with index for workspace-scoped models."""
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
```

### Step 2: Adopt mixins in a model (example with Persona)

```python
# File: rext-backend/src/api/models/knowledge_models/persona_model.py
# Replace individual column definitions with mixins

from sqlalchemy import Column, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin


class Persona(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin):
    """Persona model - Stores extracted user personas for workspaces."""
    __tablename__ = "persona"

    # workspace_id provided by WorkspaceScopedMixin
    # id provided by UUIDPrimaryKeyMixin
    # created_at, updated_at provided by TimestampMixin

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    full_name = Column(String(255), nullable=True)
    professional_title = Column(String(255), nullable=True)
    areas_of_expertise = Column(Text, nullable=True)
    tone_of_voice = Column(String(255), nullable=True)
    bio = Column(Text, nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    demographics = Column(Text, nullable=True)
    pain_points = Column(Text, nullable=True)
    goals = Column(Text, nullable=True)
    behaviors = Column(Text, nullable=True)
    custom_metadata = Column(JSONB, nullable=True)

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="personas")

    # to_dict() inherited from SerializableMixin — remove the manual override
```

### Step 3: Adopt mixins in remaining models (phased approach)

Apply mixins to models in this order to minimize risk:

**Phase A — Simple models (no soft delete, no extra columns):**
- `roles.py`, `permissions.py`, `user_roles.py`, `role_permissions.py`
- `invitations.py`, `onboarding.py`, `token_blacklist.py`
- `audit_logs.py`, `email_log.py`, `email_event.py`
- `customer_note.py`, `error_log.py`

**Phase B — Workspace-scoped models:**
- `persona_model.py`, `knowledge_model.py` (KnowledgeBase, BrandVoice, Website, KnowledgeFiles, TextKnowledge)
- `email_template.py`, `content.py`, `content_seo_data.py`, `content_media.py`
- `media.py`, `notification_model.py`

**Phase C — Models with soft delete:**
- `workspace_model.py` (has extra `deleted_by` column — use SoftDeleteMixin + extra column)
- `content.py`, `media.py`, `workspace_integration.py`

**Phase D — Complex models:**
- `users.py` (has `deactivated_at` + `deleted_at` — may need custom handling)
- `subscriptions.py`, `plans.py`, `license_activations.py`, `discount_usage.py`, `trial_conversions.py`, `refunds.py`

### Step 4: Verify no schema changes

After adopting mixins, run Alembic autogenerate to confirm no unintended schema changes:

```bash
cd rext-backend && alembic revision --autogenerate -m "verify_mixin_adoption_no_changes"
```

The generated migration should be empty (no operations). If it contains changes, the mixin column types differ from the existing columns and must be reconciled.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/models/user_models/users.py` | 19, 38-41 | UUID PK + timestamps + soft delete — candidate for all four mixins |
| `rext-backend/src/api/models/workspace_models/workspace_model.py` | 15-24 | UUID PK + timestamps + soft delete + extra `deleted_by` column |
| `rext-backend/src/api/models/content_models/content.py` | 14, 43-45 | UUID PK + timestamps + soft delete + workspace scoped |
| `rext-backend/src/api/models/media_models/media.py` | (various) | UUID PK + timestamps + soft delete + workspace scoped |
| `rext-backend/src/api/models/notification/notification_model.py` | 37-43, 153-159 | UUID PK + timestamps |
| `rext-backend/src/api/models/subscription_models/refunds.py` | 58, 94-96 | UUID PK + timestamps |
| All 33+ model files | Various | Every model repeats the UUID PK pattern |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open any two model files (e.g., `roles.py` and `permissions.py`) and observe that the UUID PK and timestamp columns are copy-pasted verbatim
2. Run `grep -r "default=datetime.utcnow" rext-backend/src/api/models/` to see ~30 occurrences of the deprecated pattern
3. Run `grep -r "primary_key=True, default=uuid.uuid4" rext-backend/src/api/models/` to see 33+ occurrences

### After Fix (Verify the Solution):
1. Verify `rext-backend/src/api/models/mixins.py` exists and contains all four mixins
2. For each model that adopts a mixin, verify the individual column definitions have been removed
3. Run Alembic autogenerate and confirm no schema changes: `cd rext-backend && alembic revision --autogenerate -m "verify_no_changes"` — the migration should have empty `upgrade()` and `downgrade()` functions
4. Run the application and verify API responses still contain `id`, `created_at`, `updated_at` fields as expected
5. Test serialization: models using mixins should still produce correct JSON output via `to_dict()`

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v --no-header
```

---

## Acceptance Criteria

- [ ] `src/api/models/mixins.py` exists with `UUIDPrimaryKeyMixin`, `TimestampMixin`, `SoftDeleteMixin`, and `WorkspaceScopedMixin`
- [ ] All mixins use `DateTime(timezone=True)` and `lambda: datetime.now(timezone.utc)` (not deprecated `datetime.utcnow`)
- [ ] At least Phase A models (simple models) have adopted the mixins
- [ ] Alembic autogenerate produces an empty migration (no schema changes introduced)
- [ ] All model `to_dict()` output remains unchanged after mixin adoption
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 — Composing Mapped Hierarchies with Mixins](https://docs.sqlalchemy.org/en/20/orm/declarative_mixins.html) — Official guide for creating mixins with Column objects and mapped_column constructs
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Modularizing SQLAlchemy Models with Mixins and Annotations](https://dev.to/atanusaha143/modularizing-sqlalchemy-models-with-mixins-and-annotations-3kp1) — Community guide demonstrating UUIDPrimaryKeyMixin and TimestampMixin patterns
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None (but ideally complete TASK-041 first to migrate to `DeclarativeBase`, as the mixin patterns work best with the modern declarative API)
- **Blocks:** None (but makes TASK-042, TASK-043, TASK-045, TASK-048 significantly easier)
- **Related:** TASK-042 (Inconsistent Timestamp Column Types — mixins standardize this), TASK-043 (Missing Timestamps on Models — TimestampMixin adds them), TASK-045 (Deprecated datetime.utcnow — mixins use the correct replacement), TASK-048 (4 Different Soft Delete Patterns — SoftDeleteMixin standardizes this), TASK-031 (Missing FK Indexes — WorkspaceScopedMixin includes `index=True`)
