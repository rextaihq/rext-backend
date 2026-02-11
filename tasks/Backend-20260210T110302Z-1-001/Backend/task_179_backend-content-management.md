# Task 179: Migrate Pydantic `class Config` to `model_config = ConfigDict(...)` in Content Schemas

## Metadata
- **Task ID:** TASK-179
- **Source:** Backend Content Management Audit (Finding #26 under P2 Medium)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P2 Medium
- **Category:** dependency
- **Effort Estimate:** small (< 1 hour)

---

## Description

The content schema file `src/api/schema/content_schema.py` uses the Pydantic V1-style `class Config` inner class at two locations: `ContentResponse` (lines 129-130) and `WorkspaceIntegrationResponse` (lines 175-176). Both use `from_attributes = True` (the V2 renamed version of V1's `orm_mode = True`).

While `class Config` still works in Pydantic V2, it is **officially deprecated** as of Pydantic V2.0 and is scheduled for **removal in Pydantic V3.0**. The deprecation triggers a `PydanticDeprecatedSince20` warning: "Support for class-based `config` is deprecated, use ConfigDict instead." The project depends on `pydantic>=2.0.0` per `pyproject.toml`, so it is already using Pydantic V2 and should adopt the V2-native configuration pattern.

The correct replacement is `model_config = ConfigDict(from_attributes=True)`, using the `ConfigDict` import from `pydantic`. This is not just a style preference — it's a formal deprecation with a scheduled removal timeline. The `model_config` attribute provides the same functionality as `class Config` with identical configuration keys (except for a few renames like `orm_mode` → `from_attributes` and `allow_mutation` → `frozen`).

This finding is scoped to the two occurrences in `content_schema.py`, but the same pattern exists in **73 other locations** across the schema directory (see "Other Affected Locations" for the full list). Each of those occurrences should be addressed in their respective audit report tasks.

---

## Current Code

```python
# File: src/api/schema/content_schema.py
# Lines: 129-130 (in ContentResponse class)
    class Config:
        from_attributes = True
```

```python
# File: src/api/schema/content_schema.py
# Lines: 175-176 (in WorkspaceIntegrationResponse class)
    class Config:
        from_attributes = True
```

---

## Why This Matters (Context & Reasoning)

`ContentResponse` is used as the `response_model` for the `save_content` endpoint (line 101 of `publish_content.py`) and the `update_content` endpoint (line 301). `WorkspaceIntegrationResponse` is used in the `WorkspaceIntegrationListResponse` (line 180) and implicitly in several sites endpoints. These schemas convert SQLAlchemy ORM objects to Pydantic models for API responses.

The `from_attributes = True` setting enables Pydantic to read data from object attributes (like SQLAlchemy model instances) rather than requiring dict input. Without it, returning ORM objects from endpoints would fail with validation errors.

Migrating to `model_config = ConfigDict(...)` ensures:
1. No deprecation warnings in production logs
2. Forward compatibility with Pydantic V3 when it is released
3. Consistency with the modern Pydantic V2 API
4. Access to new V2-only configuration options if needed in the future

---

## Impact

- **Severity:** Currently produces `PydanticDeprecatedSince20` warnings that clutter logs. Will break when Pydantic V3 is released and `class Config` support is removed.
- **Affected Users/Flows:** All API responses using `ContentResponse` or `WorkspaceIntegrationResponse`.
- **Blast Radius:** Scoped to `content_schema.py`, but the same pattern exists in 73 other schema files across the codebase.

---

## Recommended Solution

### Step 1: Add `ConfigDict` import

```python
# File: src/api/schema/content_schema.py
# Replace line 1:
from pydantic import BaseModel, Field, field_validator

# With:
from pydantic import BaseModel, ConfigDict, Field, field_validator
```

### Step 2: Update `ContentResponse` configuration

```python
# File: src/api/schema/content_schema.py
# Replace lines 129-130:
    class Config:
        from_attributes = True

# With:
    model_config = ConfigDict(from_attributes=True)
```

The `model_config` line should be placed as the first attribute in the class body, before any field definitions, per Pydantic V2 convention. In `ContentResponse`, place it right after the class docstring or class declaration line (line 94), before the field definitions.

### Step 3: Update `WorkspaceIntegrationResponse` configuration

```python
# File: src/api/schema/content_schema.py
# Replace lines 175-176:
    class Config:
        from_attributes = True

# With:
    model_config = ConfigDict(from_attributes=True)
```

### Complete updated file sections:

```python
# ContentResponse (around line 93-131):
class ContentResponse(BaseModel):
    """Schema for content response"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    created_by_user_id: UUID
    title: str
    slug: str
    status: str
    content_language: str

    # Core content fields
    introduction: Optional[str] = None
    body_markdown: Optional[str] = None
    body_html: Optional[str] = None
    tags: Optional[List[str]] = None

    # Nested relations
    seo_data: Optional[ContentSEODataSchema] = None

    # Flow-generated structured data
    images_data: Optional[Dict[str, Any]] = None
    links_data: Optional[Dict[str, Any]] = None
    schema_markup: Optional[Dict[str, Any]] = None

    # LangGraph workflow tracking
    langgraph_thread_id: Optional[UUID] = None

    # WordPress fields
    wordpress_post_id: Optional[int] = None
    wordpress_url: Optional[str] = None
    wordpress_published_at: Optional[datetime] = None

    created_at: datetime
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
```

```python
# WorkspaceIntegrationResponse (around line 169-177):
class WorkspaceIntegrationResponse(WorkspaceIntegrationBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
```

---

## Other Affected Locations

The `class Config: from_attributes = True` pattern is used in 73 other locations across the schema directory. These will be addressed by their respective audit report tasks:

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/schema/impersonation_schema.py` | `16, 34, 55, 77` | 4 occurrences of `class Config` |
| `src/api/schema/persona_schema.py` | `144` | 1 occurrence |
| `src/api/schema/notification_schema.py` | `25, 108` | 2 occurrences |
| `src/api/schema/webhook_schema.py` | `55` | 1 occurrence |
| `src/api/schema/user_role_schema.py` | `27, 50` | 2 occurrences |
| `src/api/schema/role_schema.py` | `42, 73, 91, 106, 114, 126` | 6 occurrences |
| `src/api/schema/onboarding_schemas.py` | `48` | 1 occurrence |
| `src/api/schema/permission_schema.py` | `56, 93, 111, 125, 133` | 5 occurrences |
| `src/api/schema/workspace_schema.py` | `9, 21` | 2 occurrences |
| `src/api/schema/security_schema.py` | `38, 61, 97, 131, 167, 198, 210` | 7 occurrences |
| `src/api/schema/subscription/*.py` | Various | ~20 occurrences across subscription schemas |
| `src/api/schema/response_schemas.py` | `224, 269, 310` | 3 occurrences |
| `src/api/schema/audit_schema.py` | `98, 138, 170, 215, 251, 277` | 6 occurrences |
| `src/api/schema/email_schema.py` | `104` | 1 occurrence |
| `src/api/schema/knowledge_schema.py` | `49` | 1 occurrence |
| `src/api/schema/email_preview_schema.py` | `38, 119, 155` | 3 occurrences |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Run the test suite with deprecation warnings enabled:
   ```bash
   cd rext-backend && python -W all -m pytest tests/unit/services/test_content_service.py -v 2>&1 | grep -i "PydanticDeprecatedSince20"
   ```
2. Confirm `PydanticDeprecatedSince20` warnings appear for `ContentResponse` and/or `WorkspaceIntegrationResponse`.

### After Fix (Verify the Solution):
1. Run the same command and confirm no `PydanticDeprecatedSince20` warnings for these two classes.
2. Call `POST /api/v1/content/save` and verify the response still correctly serializes the Content ORM object.
3. Call `GET /api/v1/content/sites/list` and verify the response still correctly serializes WorkspaceIntegration ORM objects.
4. Verify that `from_attributes=True` behavior is preserved — ORM objects are correctly converted to response dicts.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/services/test_content_service.py -v
```

---

## Acceptance Criteria

- [ ] `ConfigDict` is imported from `pydantic` in `content_schema.py`
- [ ] `ContentResponse` uses `model_config = ConfigDict(from_attributes=True)` instead of `class Config`
- [ ] `WorkspaceIntegrationResponse` uses `model_config = ConfigDict(from_attributes=True)` instead of `class Config`
- [ ] No `class Config` inner classes remain in `content_schema.py`
- [ ] API response serialization works identically to before (ORM → dict conversion)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Pydantic V2 Model Config documentation](https://docs.pydantic.dev/latest/api/config/)
- **Security Advisory:** N/A
- **Migration Guide:** [Pydantic V2 Migration Guide](https://docs.pydantic.dev/latest/migration/)
- **Best Practice Reference:** [Pydantic ConfigDict API reference](https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict)
- **Related Issues/PRs:** [Pydantic GitHub Discussion: Class-based config deprecation](https://github.com/pydantic/pydantic/discussions/7076)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-046 (deprecated Pydantic `class Config` in Settings — B2), TASK-080 (deprecated `.dict()` Pydantic v1 method — B3). A codebase-wide migration of all 75 `class Config` occurrences could be done as a single batch task, but each audit report task should address the occurrences within its scope.
