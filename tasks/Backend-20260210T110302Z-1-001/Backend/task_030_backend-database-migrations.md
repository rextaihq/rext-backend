# Task 030: Fix Content.title Global unique=True Constraint Breaking Multi-Tenant Isolation

## Metadata
- **Task ID:** TASK-030
- **Source:** Database & Migrations Audit (Finding #4 under P0 Critical)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P0 Critical
- **Category:** bug
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `Content` model in `src/api/models/content_models/content.py` has a critical multi-tenancy bug. Line 19 defines the title column with a global unique constraint:

```python
title = Column(Text, nullable=False,unique=True)
```

This enforces uniqueness of `title` across the **entire table** - meaning across ALL workspaces. In a multi-tenant SaaS application like Rext AI, this is fundamentally broken: two different workspaces cannot create content with the same title (e.g., "Welcome Blog Post", "About Us", "Product Launch").

When Workspace A creates content titled "Getting Started Guide", Workspace B will receive a database constraint violation error if they try to create content with the same title. This:
1. Breaks workspace isolation - workspaces should be completely independent
2. Creates unpredictable failures - users have no way to know what titles are "taken" by other workspaces
3. Violates the principle that each workspace is a separate tenant with its own content namespace

The correct approach is a **composite unique constraint** on `(workspace_id, title)`, ensuring titles are unique only within each workspace. This pattern is already used elsewhere in the codebase - for example, `src/api/models/user_models/invitations.py:24` uses `UniqueConstraint('email', 'workspace_id', name='uq_email_workspace')`.

---

## Current Code

```python
# File: rext-backend/src/api/models/content_models/content.py
# Lines: 10-54

class Content(Base, SerializableMixin):
    """Main content table - stores core content and metadata"""
    __tablename__ = "content"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True)

    # Core content fields
    title = Column(Text, nullable=False,unique=True)  # BUG: Global uniqueness breaks multi-tenancy
    slug = Column(Text, unique=True, nullable=False, index=True)  # NOTE: slug also has same issue!
    # ...
```

**Note:** The `slug` column on line 20 has the same problem - `unique=True` enforces global uniqueness. This should likely also be a per-workspace unique constraint.

---

## Why This Matters (Context & Reasoning)

Rext AI is a multi-tenant content management platform where each workspace represents a separate customer/organization. The content table stores blog posts, articles, and other content items created by workspace users.

**Business Impact:**
1. **Common titles are blocked globally:** Titles like "Welcome", "About", "FAQ", "Contact Us", "Blog" can only exist in ONE workspace across the entire platform
2. **First-mover advantage:** Whichever workspace creates a common title first "owns" it forever
3. **Unpredictable errors:** Users get cryptic database errors when creating content with titles that happen to exist in another workspace
4. **Support burden:** Users will file tickets saying "I can't create content" without understanding why

**Technical Context:**
- The `workspace_id` column exists and is already indexed (line 15)
- The relationship to workspace is properly defined (line 48)
- The per-workspace uniqueness pattern exists in `invitations.py` as a reference

---

## Impact

- **Severity:** Users in separate workspaces receive database constraint violation errors when creating content with titles already used by ANY other workspace. This is a data integrity violation that breaks the core multi-tenant isolation model.
- **Affected Users/Flows:** Every content creation operation across all workspaces. More workspaces = more title collisions.
- **Blast Radius:** All workspaces. As the platform grows, this will cause exponentially more conflicts.

---

## Recommended Solution

### Step 1: Update the Content Model

Edit `rext-backend/src/api/models/content_models/content.py`:

```python
# File: rext-backend/src/api/models/content_models/content.py

from sqlalchemy import Column, String, Text, Integer, Float, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from datetime import datetime
import uuid


class Content(Base, SerializableMixin):
    """Main content table - stores core content and metadata"""
    __tablename__ = "content"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True)

    # Core content fields
    title = Column(Text, nullable=False)  # CHANGED: Removed unique=True
    slug = Column(Text, nullable=False, index=True)  # CHANGED: Removed unique=True
    introduction = Column(Text, nullable=True)
    body_markdown = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)

    # ... (rest of columns unchanged) ...

    # Per-workspace uniqueness constraints
    __table_args__ = (
        UniqueConstraint('workspace_id', 'title', name='uq_content_workspace_title'),
        UniqueConstraint('workspace_id', 'slug', name='uq_content_workspace_slug'),
    )

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="content_items")
    created_by = relationship("Users", foreign_keys=[created_by_user_id])
    seo_data = relationship("ContentSEOData", back_populates="content", uselist=False, cascade="all, delete-orphan")

    def to_dict(self, **kwargs):
        return super().to_dict(**kwargs)
```

### Step 2: Generate Alembic Migration

```bash
cd rext-backend
alembic revision --autogenerate -m "fix_content_title_slug_per_workspace_uniqueness"
```

### Step 3: Review and Modify the Generated Migration

The autogenerated migration may need adjustment. Ensure it:
1. Drops the global unique constraints on `title` and `slug`
2. Creates the composite unique constraints

```python
# File: alembic/versions/xxx_fix_content_title_slug_per_workspace_uniqueness.py

from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    # Drop global unique constraints
    op.drop_constraint('content_title_key', 'content', type_='unique')
    op.drop_constraint('content_slug_key', 'content', type_='unique')

    # Create per-workspace unique constraints
    op.create_unique_constraint('uq_content_workspace_title', 'content', ['workspace_id', 'title'])
    op.create_unique_constraint('uq_content_workspace_slug', 'content', ['workspace_id', 'slug'])


def downgrade() -> None:
    # Remove per-workspace constraints
    op.drop_constraint('uq_content_workspace_slug', 'content', type_='unique')
    op.drop_constraint('uq_content_workspace_title', 'content', type_='unique')

    # Restore global constraints (NOTE: May fail if duplicate titles/slugs exist across workspaces)
    op.create_unique_constraint('content_title_key', 'content', ['title'])
    op.create_unique_constraint('content_slug_key', 'content', ['slug'])
```

### Step 4: Check for Existing Duplicates Before Migration

Before running the migration, check if any duplicate titles/slugs exist across workspaces:

```sql
-- Check for duplicate titles across workspaces (OK - these will be allowed after fix)
SELECT title, COUNT(*), array_agg(workspace_id)
FROM content
WHERE deleted_at IS NULL
GROUP BY title
HAVING COUNT(*) > 1;

-- Check for duplicate titles WITHIN the same workspace (NOT OK - would violate new constraint)
SELECT workspace_id, title, COUNT(*)
FROM content
WHERE deleted_at IS NULL
GROUP BY workspace_id, title
HAVING COUNT(*) > 1;
```

If the second query returns results, you need to resolve those duplicates before the migration can succeed.

### Step 5: Run the Migration

```bash
alembic upgrade head
```

### Step 6: Verify Constraints in Database

```sql
SELECT conname, contype, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'content'::regclass
AND contype = 'u';
```

Should show `uq_content_workspace_title` and `uq_content_workspace_slug`.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/models/content_models/content.py` | `20` | `slug` column also has global `unique=True` - same fix needed |
| `src/services/content_service.py` | Various | May have validation logic assuming global uniqueness - review |
| `src/api/routes/content/` | Various | Error handling for uniqueness violations may need updates |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create Workspace A with a content item titled "Test Article"
2. Create Workspace B (different workspace)
3. Try to create content in Workspace B with title "Test Article"
4. **BUG:** Receive database constraint violation error (IntegrityError)

### After Fix (Verify the Solution):
1. Apply the migration
2. Create Workspace A with content titled "Test Article"
3. Create Workspace B
4. Create content in Workspace B with the SAME title "Test Article"
5. **FIXED:** Both succeed - each workspace has its own "Test Article"
6. Try to create a SECOND "Test Article" in Workspace A
7. **CORRECT:** This should fail (per-workspace uniqueness enforced)

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "content"
```

---

## Acceptance Criteria

- [ ] `unique=True` removed from `title` column definition
- [ ] `unique=True` removed from `slug` column definition
- [ ] `__table_args__` added with `UniqueConstraint('workspace_id', 'title', name='uq_content_workspace_title')`
- [ ] `__table_args__` includes `UniqueConstraint('workspace_id', 'slug', name='uq_content_workspace_slug')`
- [ ] Import statement includes `UniqueConstraint` from `sqlalchemy`
- [ ] Alembic migration drops global constraints and creates composite constraints
- [ ] Different workspaces can create content with the same title
- [ ] Same workspace cannot create duplicate titles
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass

---

## References & Resources

- **Official Docs:** [SQLAlchemy - UniqueConstraint](https://docs.sqlalchemy.org/en/20/core/constraints.html#unique-constraint) - Documentation on composite unique constraints
- **Security Advisory:** N/A (this is a data integrity/multi-tenancy bug, not a security vulnerability)
- **Migration Guide:** N/A
- **Best Practice Reference:** [Multi-tenant Database Design Patterns](https://docs.microsoft.com/en-us/azure/architecture/patterns/sharding) - General guidance on tenant isolation in SaaS applications

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** The same pattern should be audited for other workspace-scoped models (media, knowledge base, etc.)
