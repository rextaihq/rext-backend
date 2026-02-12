# Task 172: Add Missing `__table_args__` UniqueConstraint Declaration to ContentMedia Model

## Metadata
- **Task ID:** TASK-172
- **Source:** Backend Content Management Audit (Finding #25 under P2 Medium)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `ContentMedia` model in `src/api/models/content_models/content_media.py` is a junction table linking content to media files. The audit report flagged that there is "no constraint preventing duplicate (content_id, media_id) pairs." However, upon investigation, the database migration `alembic/versions/f0102d372d26_add_media_relationships_to_content.py` at line 98 already creates a composite unique constraint named `uq_content_media` on the `(content_id, media_id)` columns. This means the constraint **does exist at the database level** but is **not declared in the SQLAlchemy model**.

This model-database mismatch is problematic because SQLAlchemy uses model definitions to generate new Alembic autogenerate migrations. Without `__table_args__` declaring the constraint, a future `alembic revision --autogenerate` could mistakenly generate a migration that drops the existing constraint (since Alembic sees it in the database but not in the model). Additionally, developers reading the model have no indication that uniqueness is enforced, which can lead to confusion or redundant application-level validation.

The Content model also currently inserts media items in a loop in `ContentService.create_content()` at `src/services/content_service.py:100-107` without any application-level duplicate check. While the database constraint will prevent duplicates with an `IntegrityError`, the application does not handle this scenario gracefully. The fix should both align the model definition with the database and optionally add application-level validation to provide a better error message.

According to SQLAlchemy 2.0 documentation, `__table_args__` with `UniqueConstraint` is the recommended approach for declaring composite unique constraints. On PostgreSQL, a `UniqueConstraint` automatically creates a backing unique index, so no separate index is needed for the constrained columns.

---

## Current Code

```python
# File: rext-backend/src/api/models/content_models/content_media.py
# Lines: 17-28
class ContentMedia(Base, SerializableMixin):
    """
    Junction table linking content to media.

    Tracks all media files used within content body (not just featured image).
    Useful for:
    - Finding all content that uses a specific media file
    - Listing all media used in a piece of content
    - Preventing deletion of media that's in use
    - Identifying orphaned media files
    """
    __tablename__ = "content_media"
```

Note: No `__table_args__` is defined despite the database having constraint `uq_content_media`.

```sql
-- Already exists in database via migration f0102d372d26:
-- sa.UniqueConstraint('content_id', 'media_id', name='uq_content_media')
```

---

## Why This Matters (Context & Reasoning)

The `ContentMedia` junction table tracks which media files are used in which content items. This is essential for features like preventing deletion of in-use media, listing all media in a content piece, and identifying orphaned files. Without the model declaring the unique constraint, the codebase is fragile: Alembic autogenerate may drop the constraint in a future migration, and developers working on the model have no visibility into the database-level invariant. The project already follows the pattern of declaring `__table_args__` with `UniqueConstraint` in other models (e.g., `OAuthAccounts` at `oauth_accounts.py:57`, `AdminInvitations` at `admin_invitations.py:177`, `Invitations` at `invitations.py:24`), so this model should be consistent.

---

## Impact

- **Severity:** Future Alembic autogenerate could silently drop the `uq_content_media` constraint, allowing duplicate media attachments to content. Application-level code doesn't protect against this.
- **Affected Users/Flows:** Content creation and update flows that attach media items; media deletion protection logic.
- **Blast Radius:** Isolated to the `content_media` table, but downstream effects include broken media usage tracking and potential orphaned media detection failures.

---

## Recommended Solution

### Step 1: Add `__table_args__` to the ContentMedia model

```python
# File: rext-backend/src/api/models/content_models/content_media.py
# Replace the class definition (lines 17-28) with:

from sqlalchemy import Column, String, Integer, ForeignKey, TIMESTAMP, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from datetime import datetime, timezone
import uuid


class ContentMedia(Base, SerializableMixin):
    """
    Junction table linking content to media.

    Tracks all media files used within content body (not just featured image).
    Useful for:
    - Finding all content that uses a specific media file
    - Listing all media used in a piece of content
    - Preventing deletion of media that's in use
    - Identifying orphaned media files
    """
    __tablename__ = "content_media"
    __table_args__ = (
        UniqueConstraint('content_id', 'media_id', name='uq_content_media'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)

    content_id = Column(
        UUID(as_uuid=True),
        ForeignKey("content.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    media_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    usage_type = Column(
        String(50),
        nullable=True,
        comment="How media is used: inline, gallery, attachment, embed, etc."
    )

    position = Column(
        Integer,
        nullable=True,
        comment="Position/order in content (for sorting)"
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relationships
    content = relationship("Content", backref="media_items")
    media = relationship("Media", backref="used_in_content")

    def __repr__(self) -> str:
        return f"<ContentMedia(content_id={self.content_id}, media_id={self.media_id})>"
```

Note: This also fixes the deprecated `datetime.utcnow` in the `created_at` default (line 60 of the original file) — replacing it with `lambda: datetime.now(timezone.utc)` and adding the `timezone` import.

### Step 2: Verify Alembic detects no changes

After updating the model, run Alembic autogenerate to confirm it produces an empty migration (since the constraint already exists in the database):

```bash
cd rext-backend
alembic revision --autogenerate -m "verify_content_media_model_sync"
```

If the generated migration is empty (no `upgrade()` or `downgrade()` operations), delete it. This confirms the model now matches the database schema.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/services/content_service.py` | `100-107` | Inserts `ContentMedia` records in a loop without checking for duplicates — relies on DB constraint |
| `rext-backend/src/services/content_service.py` | `160-168` | Deletes and re-inserts media links on update — bypasses duplicate issue but is inefficient |
| `rext-backend/src/services/media_service.py` | `742` | Imports `ContentMedia` for media usage tracking |
| `rext-backend/alembic/versions/f0102d372d26_add_media_relationships_to_content.py` | `98` | Original migration that creates the `uq_content_media` constraint |
| `rext-backend/alembic/versions/2d09d2bad33e_restore_content_seo_and_integrations.py` | `582` | Migration that also references this constraint |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open `rext-backend/src/api/models/content_models/content_media.py` and confirm no `__table_args__` is defined.
2. Run `alembic revision --autogenerate -m "test_drift"` and observe whether it attempts to drop the `uq_content_media` constraint (indicating model-database drift).

### After Fix (Verify the Solution):
1. Apply the model changes from Step 1.
2. Run `alembic revision --autogenerate -m "verify_no_drift"`.
3. Inspect the generated migration — it should be empty (no operations).
4. Delete the empty migration file.
5. Verify the application starts without errors.

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/unit/services/test_content_service.py -v
```

---

## Acceptance Criteria

- [ ] `ContentMedia` model declares `__table_args__` with `UniqueConstraint('content_id', 'media_id', name='uq_content_media')`
- [ ] `UniqueConstraint` is imported from `sqlalchemy` at the top of the file
- [ ] `datetime.utcnow` replaced with `lambda: datetime.now(timezone.utc)` in `created_at` default
- [ ] `timezone` is imported from `datetime` module
- [ ] Alembic autogenerate produces an empty migration (no drift between model and database)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 — Defining Constraints and Indexes](https://docs.sqlalchemy.org/en/20/core/constraints.html#unique-constraint)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Alembic Discussion — UniqueConstraint vs Index(unique=True) on PostgreSQL](https://github.com/sqlalchemy/alembic/discussions/1512) — UniqueConstraint is preferred for data integrity rules; PostgreSQL automatically creates a backing index
- **Related Issues/PRs:** [Alembic Discussion #1316 — Autogenerate may not detect new UniqueConstraint additions](https://github.com/sqlalchemy/alembic/discussions/1316)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-033 (Missing Unique Constraints on Join Tables — B2), TASK-045 (Deprecated datetime.utcnow in model files — B2)
