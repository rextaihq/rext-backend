# Task 043: Add Missing Timestamp Columns to Website, KnowledgeFiles, Permission, and TokenBlacklist Models

## Metadata
- **Task ID:** TASK-043
- **Source:** Backend Database & Migrations Audit (Finding #23 under P2 Medium)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P2 Medium
- **Category:** refactoring
- **Effort Estimate:** medium (1-4 hours)

---

## Description

Four models in the Rext backend are missing standard timestamp columns (`created_at` and/or `updated_at`) that are present on virtually every other model in the codebase. The affected models are:

1. **`Website`** (`src/api/models/knowledge_models/knowledge_model.py`, lines 91-104) — Missing both `created_at` and `updated_at`. This model represents web knowledge sources that are crawled and indexed. There is no way to determine when a website was added to a knowledge base or when it was last modified. Other knowledge models in the same file (`KnowledgeBase`, `BrandVoice`, `KnowledgeFiles`, `TextKnowledge`) all have both timestamp columns.

2. **`KnowledgeFiles`** (`src/api/models/knowledge_models/knowledge_model.py`, lines 119-141) — Has `created_at` (line 133) but is missing `updated_at`. When a file is re-processed (e.g., status changes from "processing" to "completed", or chunk_count is updated), there is no record of when the update occurred.

3. **`Permission`** (`src/api/models/user_models/permissions.py`, lines 13-27) — Has `created_at` (line 22) but is missing `updated_at`. When permission metadata is updated (display_name, description), the modification is untracked. While permissions may change infrequently, audit requirements and data synchronization depend on knowing when records were last modified.

4. **`TokenBlacklist`** (`src/api/models/user_models/token_blacklist.py`, lines 21-38) — Has `revoked_at` as a creation timestamp but is missing a proper `updated_at`. If a blacklisted token record is ever modified (e.g., reason updated), the change is untracked.

The SQLAlchemy best practice, as demonstrated by the existing `KnowledgeBase`, `BrandVoice`, and `TextKnowledge` models in the same knowledge_model.py file, is to include both `created_at` and `updated_at` columns with timezone-aware datetime types and proper defaults.

---

## Current Code

```python
# File: rext-backend/src/api/models/knowledge_models/knowledge_model.py
# Lines: 91-104 (Website class — NO timestamp columns at all)
class Website(Base, SerializableMixin):
    __tablename__ = "website"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    knowledge_base_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False)

    url = Column(String, nullable=False)
    status = Column(String, nullable=False, default="process")
    char_count = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=True)

    workspace = relationship("WorkspaceModel", back_populates="websites")
    knowledge_base = relationship("KnowledgeBase", back_populates="websites")
```

```python
# File: rext-backend/src/api/models/knowledge_models/knowledge_model.py
# Lines: 119-141 (KnowledgeFiles class — has created_at but NO updated_at)
class KnowledgeFiles(Base, SerializableMixin):
    __tablename__ = "knowledge_files"
    # ... columns ...
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    # No updated_at column
```

```python
# File: rext-backend/src/api/models/user_models/permissions.py
# Lines: 13-27 (Permission class — has created_at but NO updated_at)
class Permission(Base, SerializableMixin):
    __tablename__ = "permissions"
    # ... columns ...
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    # No updated_at column
```

```python
# File: rext-backend/src/api/models/user_models/token_blacklist.py
# Lines: 21-38 (TokenBlacklist class — NO updated_at)
class TokenBlacklist(Base, SerializableMixin):
    __tablename__ = "token_blacklist"
    # ... columns ...
    revoked_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    expires_at = Column(TIMESTAMP, nullable=False, index=True)
    # No created_at (revoked_at serves this purpose) and no updated_at
```

---

## Why This Matters (Context & Reasoning)

Timestamps are essential for:
- **Audit trails:** Knowing when records were created and last modified supports compliance and debugging.
- **Data synchronization:** Cache invalidation and incremental sync strategies depend on `updated_at` to detect changes.
- **Debugging:** When investigating issues, knowing the timeline of record changes is critical.
- **Query optimization:** Time-based queries (e.g., "recently updated websites") require timestamp columns.

The `Website` model is particularly impactful because website crawling is an asynchronous process — knowing when a website was added and when it was last updated (re-crawled) is essential for managing stale content and triggering re-crawls.

---

## Impact

- **Severity:** Cannot track creation/modification times for Website knowledge sources, KnowledgeFiles updates, Permission changes, or TokenBlacklist modifications. Limits debugging, auditing, and data synchronization.
- **Affected Users/Flows:** Knowledge base management (adding/updating websites and files), permission administration, token management.
- **Blast Radius:** Localized to 4 models, but affects the ability to audit and debug operations involving these models.

---

## Recommended Solution

### Step 1: Add Timestamps to Website Model

```python
# File: rext-backend/src/api/models/knowledge_models/knowledge_model.py
# Add after the word_count column (line ~101), before the relationships:
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=True)
```

### Step 2: Add updated_at to KnowledgeFiles Model

```python
# File: rext-backend/src/api/models/knowledge_models/knowledge_model.py
# Add after the created_at column in KnowledgeFiles (after line 133):
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=True)
```

### Step 3: Add updated_at to Permission Model

```python
# File: rext-backend/src/api/models/user_models/permissions.py
# Add after created_at (after line 22):
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=True)
```

Note: Also update `created_at` to use `DateTime(timezone=True)` (per TASK-042).

### Step 4: Add updated_at to TokenBlacklist Model

```python
# File: rext-backend/src/api/models/user_models/token_blacklist.py
# Add after the reason column (after line 31):
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=True)
```

### Step 5: Generate Alembic Migration

```bash
cd rext-backend && alembic revision --autogenerate -m "add_missing_timestamp_columns"
```

Review the generated migration to ensure it:
- Adds `created_at` and `updated_at` to the `website` table
- Adds `updated_at` to the `knowledge_files` table
- Adds `updated_at` to the `permissions` table
- Adds `updated_at` to the `token_blacklist` table

For existing rows, the `created_at` column on `website` needs a default value. Add a server_default to the migration:

```python
# In the generated migration, modify the website.created_at addition:
op.add_column('website', sa.Column(
    'created_at',
    sa.DateTime(timezone=True),
    nullable=False,
    server_default=sa.func.now()  # Default for existing rows
))
# Then remove the server_default after migration if desired:
# op.alter_column('website', 'created_at', server_default=None)
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/models/knowledge_models/knowledge_model.py` | `91-116` | Website class — add both created_at and updated_at |
| `src/api/models/knowledge_models/knowledge_model.py` | `119-141` | KnowledgeFiles class — add updated_at |
| `src/api/models/user_models/permissions.py` | `13-27` | Permission class — add updated_at |
| `src/api/models/user_models/token_blacklist.py` | `21-38` | TokenBlacklist class — add updated_at |
| `src/services/knowledge_service.py` | Various | May need to set updated_at when updating Website/KnowledgeFiles records |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open a Python shell: `cd rext-backend && python -c "from src.api.models.knowledge_models.knowledge_model import Website; print([c.name for c in Website.__table__.columns])"`
2. Verify that `created_at` and `updated_at` are NOT in the column list for Website.

### After Fix (Verify the Solution):
1. Repeat the same command — both `created_at` and `updated_at` should appear.
2. Run the migration: `cd rext-backend && alembic upgrade head`
3. Verify in PostgreSQL: `SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'website' AND column_name IN ('created_at', 'updated_at');` — should show both columns with `timestamp with time zone`.
4. Create a new Website record via the API — verify `created_at` is populated automatically.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v
```

---

## Acceptance Criteria

- [ ] Website model has both `created_at` and `updated_at` columns with `DateTime(timezone=True)`
- [ ] KnowledgeFiles model has `updated_at` column with `DateTime(timezone=True)`
- [ ] Permission model has `updated_at` column with `DateTime(timezone=True)`
- [ ] TokenBlacklist model has `updated_at` column with `DateTime(timezone=True)`
- [ ] Alembic migration successfully adds all missing columns
- [ ] Existing rows have sensible default values for new columns
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 — Column and Data Types: DateTime](https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.DateTime) — documents `DateTime(timezone=True)` for timezone-aware timestamps
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Alembic — Auto Generating Migrations](https://alembic.sqlalchemy.org/en/latest/autogenerate.html) — how to use `--autogenerate` for schema changes
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None (but should ideally be done alongside TASK-042 for consistent timestamp types)
- **Blocks:** None
- **Related:** TASK-042 (Inconsistent Timestamp Column Types — new columns should use the standardized `DateTime(timezone=True)` type), TASK-045 (datetime.utcnow deprecation — new column defaults should use `lambda: datetime.now(timezone.utc)`)
