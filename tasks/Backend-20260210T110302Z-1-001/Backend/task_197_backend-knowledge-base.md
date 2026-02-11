# Task 197: Fix Model Attribute Errors in knowledge_service.py

## Metadata
- **Task ID:** TASK-197
- **Source:** Backend Knowledge Base (Finding #8 under P1 High)
- **Audit Report:** `audit-reports/backend-knowledge-base.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `knowledge_service.py` file contains three separate `AttributeError` bugs where code references model attributes that do not exist on the target SQLAlchemy model classes. Each of these will cause a runtime crash when the affected code path is executed.

**Bug 1: `knowledge.name` at line 279.** The `update_file_knowledge_name()` method sets `knowledge.name = name`, but the `KnowledgeFiles` model (defined in `src/api/models/knowledge_models/knowledge_model.py:118-160`) has a `file_name` column, not `name`. The `to_dict()` method on `KnowledgeFiles` adds a `name` alias in the dictionary output (`data['name'] = data.get('file_name')` at line 146), which likely caused confusion — but the alias is only in the serialized dict, not on the model itself. Setting `knowledge.name` on the ORM object will raise `AttributeError` at runtime.

**Bug 2: `knowledge.title` at line 572.** The `update_web_knowledge_title()` method sets `knowledge.title = title`, but the `Website` model (defined at lines 90-115 of the same file) has no `title` column. The model only has: `id`, `workspace_id`, `knowledge_base_id`, `url`, `status`, `char_count`, and `word_count`. This means the "update web knowledge title" feature is completely broken — any attempt to rename a web knowledge entry will crash.

**Bug 3: `kb.created_by_user_id` at line 687.** The `_send_kb_processing_completed_email()` method queries `Users.id == kb.created_by_user_id` to find the user who created the knowledge base, but the `KnowledgeBase` model (defined at lines 13-68) has no `created_by_user_id` field. The model only has: `id`, `workspace_id`, `name`, `description`, `type`, `created_at`, `updated_at`. This means the email notification after file processing will always crash, though the error is caught by the outer try/except and doesn't fail the file upload itself.

All three bugs were verified against the current code. The audit report line numbers are slightly off from the actual current code (the audit listed 269, 566, 677), but the bugs are confirmed at the lines stated above.

---

## Current Code

```python
# File: rext-backend/src/services/knowledge_service.py
# Lines: 264-292 (Bug 1: update_file_knowledge_name)
    async def update_file_knowledge_name(
        self,
        workspace_id: UUID,
        file_id: UUID,
        name: str,
    ) -> Dict[str, Any]:
        """
        Update the display name for a file knowledge entry.
        """
        knowledge = await self._get_file_knowledge_or_404(file_id, workspace_id)
        knowledge.name = name  # BUG: KnowledgeFiles has 'file_name', not 'name'
        await self.db.flush()
        await self.db.refresh(knowledge)
        # ...
        return knowledge.to_dict()
```

```python
# File: rext-backend/src/services/knowledge_service.py
# Lines: 569-575 (Bug 2: update_web_knowledge_title)
    async def update_web_knowledge_title(self, workspace_id: UUID, web_id: UUID, title: str) -> Dict[str, Any]:
        """Update the title for a web knowledge entry."""
        knowledge = await self._get_website_or_404(web_id, workspace_id)
        knowledge.title = title  # BUG: Website model has no 'title' field
        await self.db.flush()
        await self.db.refresh(knowledge)
        return knowledge.to_dict()
```

```python
# File: rext-backend/src/services/knowledge_service.py
# Lines: 685-692 (Bug 3: _send_kb_processing_completed_email)
            # Fetch user who created the KB (owner)
            result = await self.db.execute(
                select(Users).where(Users.id == kb.created_by_user_id)  # BUG: no created_by_user_id
            )
            user = result.scalar_one_or_none()
            if not user:
                logger.warning(f"User {kb.created_by_user_id} not found, skipping email")
                return
```

---

## Why This Matters (Context & Reasoning)

These three bugs affect different features of the knowledge base module:

1. **File renaming (Bug 1):** Users who upload files may want to change the display name from the original filename (e.g., rename "report_2024_Q3_final_v2.pdf" to "Q3 Financial Report"). This feature is exposed via the route layer and will crash every time a user attempts to rename a file.

2. **Web knowledge title update (Bug 2):** After scraping a URL, users can set a human-readable title for the entry. The route at `workspace_knowledge.py:176-181` calls this method immediately after web knowledge creation if `payload.title` is provided. This means web knowledge creation with a title will crash mid-operation — the web scraping succeeds, the record is created, but the title update fails, leaving an inconsistent state.

3. **Email notification (Bug 3):** After file processing completes, the system attempts to send a "Knowledge Base Ready" email to the user who created the KB. This always fails because `created_by_user_id` doesn't exist on the model. While the error is caught (line 725) and doesn't crash the upload, it means users never receive processing completion emails — a degraded experience.

---

## Impact

- **Severity:** Bug 1 and Bug 2 cause `AttributeError` runtime crashes on user-triggered operations. Bug 3 silently breaks email notifications.
- **Affected Users/Flows:** Bug 1: File knowledge rename. Bug 2: Web knowledge creation with title. Bug 3: All file upload email notifications.
- **Blast Radius:** Per-workspace — each bug only affects the specific user operation. However, Bug 2 is triggered during a common flow (web knowledge creation with title), making it high-frequency.

---

## Recommended Solution

### Step 1: Fix Bug 1 — Change `knowledge.name` to `knowledge.file_name`

```python
# File: rext-backend/src/services/knowledge_service.py
# Replace line 279:
# OLD: knowledge.name = name
# NEW:
        knowledge.file_name = name
```

### Step 2: Fix Bug 2 — Add `title` Column to Website Model

The Website model needs a `title` column to support the title update feature. This requires an Alembic migration.

```python
# File: rext-backend/src/api/models/knowledge_models/knowledge_model.py
# In the Website class (after line 98, after the 'status' column), add:
    title = Column(String(255), nullable=True)
```

The full Website class should look like:

```python
# File: rext-backend/src/api/models/knowledge_models/knowledge_model.py
# Lines: 90-115 (updated Website class)
class Website(Base, SerializableMixin):
    __tablename__ = "website"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    knowledge_base_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False)

    url = Column(String, nullable=False)
    title = Column(String(255), nullable=True)  # NEW: Human-readable title for the web knowledge entry
    status = Column(String, nullable=False, default="process")
    char_count = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=True)

    workspace = relationship("WorkspaceModel", back_populates="websites")
    knowledge_base = relationship("KnowledgeBase", back_populates="websites")

    def to_dict(self, **kwargs) -> dict:
        """Custom serialization with computed fields"""
        data = super().to_dict(**kwargs)
        data['processing_status'] = self.status
        data['content_metrics'] = {
            'char_count': self.char_count or 0,
            'word_count': self.word_count or 0,
            'estimated_reading_time': (self.word_count or 0) // 200
        }
        return data
```

Then create an Alembic migration:

```bash
cd rext-backend
alembic revision --autogenerate -m "add_title_column_to_website"
alembic upgrade head
```

### Step 3: Fix Bug 3 — Add `created_by_user_id` to KnowledgeBase Model OR Use Workspace Owner

There are two options. The simpler approach that doesn't require a migration is to find the workspace owner instead:

```python
# File: rext-backend/src/services/knowledge_service.py
# Replace lines 685-692 with:

            # Fetch workspace owner to send email notification
            from src.api.models.workspace_models.workspace_member import WorkspaceMembers
            result = await self.db.execute(
                select(WorkspaceMembers).where(
                    WorkspaceMembers.workspace_id == workspace_id,
                    WorkspaceMembers.is_default == True,
                )
            )
            owner_member = result.scalar_one_or_none()
            if not owner_member:
                logger.warning(f"No owner found for workspace {workspace_id}, skipping email")
                return

            result = await self.db.execute(
                select(Users).where(Users.id == owner_member.user_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                logger.warning(f"User {owner_member.user_id} not found, skipping email")
                return
```

**Alternative (preferred long-term):** Add `created_by_user_id` to the KnowledgeBase model to track who created each KB. This requires an Alembic migration:

```python
# File: rext-backend/src/api/models/knowledge_models/knowledge_model.py
# In the KnowledgeBase class, after the 'type' column, add:
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
```

Then update the knowledge base creation code to set this field. For now, the workspace owner approach is the safer fix.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/routes/workspaces/workspace_knowledge.py` | `176-181` | Calls `update_web_knowledge_title` — will crash without the title column fix |
| `rext-backend/src/api/routes/workspaces/workspace_knowledge.py` | `51-54` | `FileKnowledgeUpdateRequest` schema — uses `name` field which maps to the service method |
| `rext-backend/src/services/knowledge_base_service.py` | N/A | If KB creation is updated to set `created_by_user_id`, this service needs updating |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. **Bug 1:** Upload a file to knowledge base, then try to rename it:
   ```bash
   curl -X PATCH "http://localhost:8000/api/workspaces/<ws_id>/knowledge/file/<file_id>" \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"name": "New Display Name"}'
   ```
   Observe `AttributeError: 'KnowledgeFiles' object has no attribute 'name'`

2. **Bug 2:** Create web knowledge with a title:
   ```bash
   curl -X POST "http://localhost:8000/api/workspaces/<ws_id>/knowledge/web" \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://example.com", "title": "Example Site"}'
   ```
   Observe `AttributeError: 'Website' object has no attribute 'title'`

3. **Bug 3:** Upload a file and check server logs for email error:
   Observe `AttributeError: 'KnowledgeBase' object has no attribute 'created_by_user_id'`

### After Fix (Verify the Solution):
1. **Bug 1:** Rename a file knowledge entry — should succeed, `file_name` updated in DB
2. **Bug 2:** Create web knowledge with title — should succeed, title stored in new column
3. **Bug 3:** Upload a file — email notification should be sent (or at least no AttributeError in logs)
4. Verify all three operations return correct data in API responses

### Run Existing Tests:
```bash
cd rext-backend
python -m pytest tests/ -v -k "knowledge" --no-header
```

### Run Alembic Migration:
```bash
cd rext-backend
alembic revision --autogenerate -m "add_title_to_website_model"
alembic upgrade head
```

---

## Acceptance Criteria

- [ ] `update_file_knowledge_name()` uses `knowledge.file_name` instead of `knowledge.name`
- [ ] `Website` model has a `title` column (String, nullable)
- [ ] Alembic migration is created and applied for the `title` column
- [ ] `update_web_knowledge_title()` works without errors
- [ ] Email notification no longer crashes with `AttributeError` on `created_by_user_id`
- [ ] All three code paths have been manually tested via API calls
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy Column Definition](https://docs.sqlalchemy.org/en/20/core/metadata.html#sqlalchemy.schema.Column)
- **Security Advisory:** N/A
- **Migration Guide:** [Alembic Auto-generation Guide](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
- **Best Practice Reference:** [SQLAlchemy ORM Mapped Class Configuration](https://docs.sqlalchemy.org/en/20/orm/mapping_styles.html)
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-062 (B3 — Non-Existent User Model Attributes), TASK-091 (B4 — Update Route Passes Wrong Keyword Arguments)
