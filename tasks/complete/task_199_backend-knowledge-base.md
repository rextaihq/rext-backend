# Task 199: Implement Tags Update for Text Knowledge Entries

## Metadata
- **Task ID:** TASK-199
- **Source:** Backend Knowledge Base Audit (Finding #7 under P1 High)
- **Audit Report:** `audit-reports/backend-knowledge-base.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `TextKnowledgeUpdateRequest` Pydantic schema in `src/api/routes/workspaces/workspace_knowledge.py` (line 48) accepts an optional `tags` field of type `Optional[list[constr(...)]]`. When a user sends a PATCH request to `/workspaces/{workspace_id}/knowledge/text/{text_id}` with tags in the payload, the route handler at line 621 validates that at least one field is provided (checking `payload.tags` is included in the `any()` check). However, when `service.update_text_knowledge()` is called at line 634, only `title` and `content` are passed — **tags are never forwarded to the service layer**. Instead, at line 641-642, the route logs a warning: `"Tags update for text knowledge is not yet supported"` and silently drops the tags.

The same pattern exists for the create endpoint at line 543-544 where tags provided during creation are also logged and ignored.

The `TextKnowledge` model in `src/api/models/knowledge_models/knowledge_model.py` (line 173) already has a `tags` column defined as `Column(JSONB, nullable=True)`, so the database schema fully supports tags. The model, the schema, and the route all reference tags — only the service layer is missing the implementation.

According to SQLAlchemy documentation on mutation tracking, when updating a JSONB column, you must either reassign the entire value (which triggers change detection) or use `flag_modified()` from `sqlalchemy.orm.attributes` to mark the column as dirty after in-place mutation. Since tags are replaced entirely (not mutated in-place), simple reassignment (`knowledge.tags = new_tags`) is sufficient.

---

## Current Code

```python
# File: rext-backend/src/api/routes/workspaces/workspace_knowledge.py
# Lines: 609-648 (update_text_knowledge route)
@router.patch("/text/{text_id}")
@require_permissions("knowledge.update", workspace_scoped=True)
@db_transaction_handler("update text knowledge", auto_commit=True)
async def update_text_knowledge(
    workspace_id: str,
    text_id: str,
    request: Request,
    payload: TextKnowledgeUpdateRequest = Body(...),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Update title/content for a text knowledge entry."""
    if not any([payload.title, payload.content, payload.tags]):
        raise RextValidationException(
            message="At least one field (title, content, tags) must be provided",
            field_errors={"payload": ["No fields supplied for update"]},
        )

    workspace, _ = await _resolve_workspace(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    knowledge = await service.update_text_knowledge(
        UUID(text_id),
        workspace.id,
        title=payload.title,
        content=payload.content,
    )

    if payload.tags:
        logger.warning("Tags update for text knowledge is not yet supported", extra={"tags": payload.tags})

    return success(
        data={"text_knowledge": knowledge},
        request=request,
        message="Text knowledge updated successfully",
    )
```

```python
# File: rext-backend/src/services/knowledge_service.py
# Lines: 379-427 (update_text_knowledge method)
async def update_text_knowledge(
    self,
    knowledge_id: UUID,
    workspace_id: UUID,
    *,
    title: Optional[str] = None,
    content: Optional[str] = None,
) -> Dict[str, Any]:
    # ... fetches knowledge, updates title/content, returns dict
    # Tags parameter is completely absent
```

---

## Why This Matters (Context & Reasoning)

Tags are a fundamental organizing mechanism in knowledge management. The frontend likely renders a tags input field because the schema and model both support it. Users who add tags during text knowledge creation or update expect those tags to persist. Currently, the UI may appear to accept tags, but they are silently discarded. This creates a confusing user experience where tags seem to work but are never actually saved, and disappear on the next page load.

The `TextKnowledge.to_dict()` method (line 181-196) already includes tags in its serialization output, meaning the API response format already supports tags — only the write path is broken.

---

## Impact

- **Severity:** Tags provided by users are silently discarded. Users cannot organize or filter text knowledge by tags.
- **Affected Users/Flows:** Any user creating or updating text knowledge entries with tags.
- **Blast Radius:** Isolated to text knowledge CRUD operations. Does not affect file or web knowledge.

---

## Recommended Solution

### Step 1: Add `tags` Parameter to `KnowledgeService.update_text_knowledge()`

```python
# File: rext-backend/src/services/knowledge_service.py
# Replace the update_text_knowledge method (lines 379-427):

    async def update_text_knowledge(
        self,
        knowledge_id: UUID,
        workspace_id: UUID,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Update metadata for a text knowledge entry.

        Args:
            knowledge_id: Text knowledge UUID
            workspace_id: Workspace UUID
            title: Optional new title
            content: Optional new content
            tags: Optional new tags list (replaces existing tags)
        """
        result = await self.db.execute(
            select(TextKnowledge).where(
                TextKnowledge.id == knowledge_id,
                TextKnowledge.workspace_id == workspace_id,
            )
        )
        knowledge = result.scalar_one_or_none()

        if not knowledge:
            raise ResourceNotFoundException(
                resource_type="TextKnowledge",
                resource_id=str(knowledge_id),
            )

        if title:
            knowledge.title = title

        if content:
            knowledge.content = content

        if tags is not None:
            knowledge.tags = tags

        await self.db.flush()
        await self.db.refresh(knowledge)

        logger.info(
            "Text knowledge updated",
            extra={
                "workspace_id": str(workspace_id),
                "knowledge_id": str(knowledge_id),
            },
        )

        return knowledge.to_dict()
```

### Step 2: Pass `tags` from Route to Service

```python
# File: rext-backend/src/api/routes/workspaces/workspace_knowledge.py
# Replace lines 634-642 in the update_text_knowledge route:

    service = KnowledgeService(db)
    knowledge = await service.update_text_knowledge(
        UUID(text_id),
        workspace.id,
        title=payload.title,
        content=payload.content,
        tags=payload.tags,
    )

    return success(
        data={"text_knowledge": knowledge},
        request=request,
        message="Text knowledge updated successfully",
    )
```

### Step 3: Save Tags During Creation

```python
# File: rext-backend/src/api/routes/workspaces/workspace_knowledge.py
# In the create_text_knowledge route, replace lines 536-544:

    service = KnowledgeService(db)
    knowledge = await service.add_text_knowledge(
        workspace.id,
        payload.title,
        payload.content,
        knowledge_base_id=payload.knowledge_base_id,
        tags=payload.tags,
    )
```

### Step 4: Add `tags` Parameter to `add_text_knowledge()`

```python
# File: rext-backend/src/services/knowledge_service.py
# Update the add_text_knowledge method signature and body:

    async def add_text_knowledge(
        self,
        workspace_id: UUID,
        title: str,
        content: str,
        knowledge_base_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
    ) -> TextKnowledge:
        """
        Add text knowledge to workspace.

        Args:
            workspace_id: Workspace UUID
            title: Knowledge title
            content: Knowledge content
            knowledge_base_id: Optional knowledge base UUID (uses default if None)
            tags: Optional list of tags
        """
        # Get or use default knowledge base
        if knowledge_base_id is None:
            kb_service = KnowledgeBaseService(self.db)
            kb = await kb_service.get_default_knowledge_base(workspace_id)
            knowledge_base_id = kb.id

        # Split content into chunks
        chunks = split_data(
            documents=content,
            chunk_size=1000,
            overlap=200
        )

        # Save to database
        new_knowledge = TextKnowledge(
            workspace_id=workspace_id,
            knowledge_base_id=knowledge_base_id,
            title=title,
            content=content,
            tags=tags,
        )
        self.db.add(new_knowledge)
        await self.db.flush()
        await self.db.refresh(new_knowledge)

        # Add to vector store
        add_to_vector_store(
            blog_context=chunks,
            workspace_id=str(workspace_id),
            knowledge_base_id=str(knowledge_base_id) if knowledge_base_id else None,
            knowledge_id=str(new_knowledge.id),
            knowledge_type="text"
        )

        logger.info(
            f"Text knowledge created: {new_knowledge.id}",
            extra={"workspace_id": str(workspace_id), "title": title}
        )

        return new_knowledge
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/models/knowledge_models/knowledge_model.py` | `173` | `tags = Column(JSONB, nullable=True)` — already supports tags storage |
| `rext-backend/src/api/routes/workspaces/workspace_knowledge.py` | `543-544` | Create endpoint also ignores tags — needs same fix |
| `rext-backend/tests/unit/services/test_knowledge_service.py` | `283-308` | `test_add_text_knowledge_success` — should be extended to test tags |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create text knowledge: `POST /workspaces/{id}/knowledge/text` with body `{"title": "Test", "content": "Long enough content here", "tags": ["tag1", "tag2"]}`
2. Get the created entry: `GET /workspaces/{id}/knowledge/text/{text_id}`
3. Observe: `tags` field is `null` in response (tags were silently dropped)
4. Update with tags: `PATCH /workspaces/{id}/knowledge/text/{text_id}` with body `{"tags": ["tag3"]}`
5. Observe: Server logs show warning "Tags update for text knowledge is not yet supported"

### After Fix (Verify the Solution):
1. Create text knowledge with tags — response should show `tags: ["tag1", "tag2"]`
2. Get the entry — tags should persist
3. Update with new tags — tags should change to the new values
4. Update with `tags: []` — tags should be cleared to empty array
5. Update with `tags: null` (omitted from payload) — tags should remain unchanged
6. Create without tags — tags should be `null`

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/services/test_knowledge_service.py -v
```

---

## Acceptance Criteria

- [ ] Tags are saved when creating text knowledge via POST
- [ ] Tags are updated when patching text knowledge via PATCH
- [ ] Tags set to `[]` clears existing tags
- [ ] Omitting tags from PATCH payload leaves existing tags unchanged
- [ ] Warning log about unsupported tags is removed
- [ ] API responses include the saved tags
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy Mutation Tracking for JSON](https://docs.sqlalchemy.org/en/20/orm/extensions/mutable.html)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [SQLAlchemy JSONB Column Best Practices](https://docs.sqlalchemy.org/en/21/orm/extensions/mutable.html)
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** None
