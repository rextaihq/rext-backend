# Task 119: Split `WorkspaceSchema` Into Separate Workspace and Brand Voice Schemas

## Metadata
- **Task ID:** TASK-119
- **Source:** B4 - Workspace Management (Finding #31 under P3 Low)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `WorkspaceSchema` Pydantic model in `src/api/schema/workspace_schema.py` (lines 29-41) violates the Single Responsibility Principle by mixing workspace metadata fields (`name`, `timezone`, `url`) with brand voice fields (`about`, `customer_profile`, `selling_position`, `target_audience`, `brand_voice`, `competitors`, `content_strategy`). This is problematic because the brand voice fields are **never used** by any workspace endpoint — every route handler that accepts `WorkspaceSchema` as a request body (`create_workspace`, `update_workspace`, `create_workspace_restful`, `update_workspace_restful`) only accesses `data.name`, `data.timezone`, and `data.url`, completely ignoring the seven brand voice fields.

Meanwhile, a dedicated `BrandSchema` already exists in `src/api/schema/knowledge_schema.py` (line 56) and is properly used by the brand voice endpoints in `src/api/routes/workspaces/workspace_brand_voice.py`. The `BrandSchema` has richer type definitions too — for example, `target_audience`, `brand_voice`, `competitors`, and `content_pillar` are typed as `List[str]` with proper examples, while the same fields in `WorkspaceSchema` are all typed as `Optional[str]` (a type mismatch that could cause confusion).

The practical impact is that FastAPI auto-generates OpenAPI documentation showing all seven brand voice fields as accepted parameters on the workspace create/update endpoints. This misleads API consumers into thinking they can set brand voice data through the workspace endpoints, when in reality those fields are silently discarded. According to Pydantic v2 and FastAPI best practices, request schemas should contain only the fields that the endpoint actually processes, and different operations (create vs update vs brand voice management) should use separate, purpose-specific schemas.

Additionally, `WorkspaceSchema` is imported in `src/api/routes/workspaces/members/members_routes.py` (line 6) but never actually used in that file — it is an unused import.

---

## Current Code

```python
# File: src/api/schema/workspace_schema.py
# Lines: 29-41
class WorkspaceSchema(BaseModel):
    name: Optional[str] = Field(None, description="Optional workspace title")
    timezone: Optional[str] = Field(None, description="IANA timezone identifier (e.g., 'America/New_York', 'UTC')")
    url: Optional[HttpUrl] = Field(None, description="Workspace URL")

    # Extra fields from brand_data
    about: Optional[str] = Field(None, description="About the brand")
    customer_profile: Optional[str] = Field(None, description="Customer profile details")
    selling_position: Optional[str] = Field(None, description="Selling position of the brand")
    target_audience: Optional[str] = Field(None, description="Target audience details")
    brand_voice: Optional[str] = Field(None, description="Tone and voice of the brand")
    competitors: Optional[str] = Field(None, description="Competitors information")
    content_strategy: Optional[str] = Field(None, description="Content strategy pillars")
```

---

## Why This Matters (Context & Reasoning)

The workspace management system in Rext AI is a core feature area: users create workspaces, configure them with metadata (name, URL, timezone), and separately manage brand voice data (about, audience, competitors, etc.) through dedicated brand voice endpoints. These are two distinct domain concepts served by different services (`WorkspaceService` for workspace CRUD, `BrandVoiceService` for brand voice management) at different API endpoints.

Having the `WorkspaceSchema` mix both concerns creates a confusing developer experience — both for API consumers who see irrelevant fields in the Swagger UI, and for backend developers who might incorrectly assume the brand voice fields are processed by workspace endpoints. Additionally, if someone adds validation logic for brand voice fields to `WorkspaceSchema`, it would erroneously block workspace create/update requests that don't include brand data. Separating schemas prevents this class of bugs and makes the API contract explicit.

The fix is straightforward: remove the brand voice fields from `WorkspaceSchema` (since they're already properly defined in `BrandSchema`) and clean up the unused import in `members_routes.py`.

---

## Impact

- **Severity:** Low — no runtime errors or data corruption; the brand voice fields are silently ignored. The impact is limited to misleading API documentation and minor confusion for API consumers.
- **Affected Users/Flows:** Developers integrating with the workspace create/update API, and anyone generating API clients from the OpenAPI spec.
- **Blast Radius:** Isolated to the workspace schema definition and the OpenAPI documentation for workspace endpoints. No functional behavior changes.

---

## Recommended Solution

### Step 1: Remove Brand Voice Fields from `WorkspaceSchema`

```python
# File: src/api/schema/workspace_schema.py
# Replace the entire WorkspaceSchema class (lines 29-41) with:
class WorkspaceSchema(BaseModel):
    name: Optional[str] = Field(None, description="Optional workspace title")
    timezone: Optional[str] = Field(None, description="IANA timezone identifier (e.g., 'America/New_York', 'UTC')")
    url: Optional[HttpUrl] = Field(None, description="Workspace URL")
```

This removes the seven brand voice fields (`about`, `customer_profile`, `selling_position`, `target_audience`, `brand_voice`, `competitors`, `content_strategy`) that are never used by any workspace endpoint.

### Step 2: Remove Unused `WorkspaceSchema` Import from `members_routes.py`

```python
# File: src/api/routes/workspaces/members/members_routes.py
# Remove line 6:
# from src.api.schema.workspace_schema import WorkspaceSchema
```

This import is unused in the file. Removing it eliminates a dead import.

### Step 3: Verify All Usages Still Work

After the change, confirm all remaining usages of `WorkspaceSchema` only depend on `name`, `timezone`, and `url`:

| File | Line | Usage | Fields Accessed |
|------|------|-------|-----------------|
| `src/api/routes/workspaces/__init__.py` | 47, 91 | `create_workspace_restful`, `update_workspace_restful` | `data.name`, `data.timezone`, `data.url` |
| `src/api/routes/workspaces/workspace_route.py` | 93, 168 | `create_workspace`, `update_workspace` | `data.name`, `data.timezone`, `data.url` |

All four usages only access the three workspace metadata fields. No code accesses the brand voice fields on `WorkspaceSchema`.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/schema/knowledge_schema.py` | 56-91 | `BrandSchema` — the proper schema for brand voice data, already used by brand voice endpoints. No changes needed. |
| `src/api/routes/workspaces/workspace_brand_voice.py` | 7, 39, 67 | Already correctly uses `BrandSchema` from `knowledge_schema.py`. No changes needed. |
| `src/api/routes/workspaces/__init__.py` | 15 | Imports `WorkspaceSchema` — still valid after the change, no modification needed. |
| `src/api/routes/workspaces/workspace_route.py` | 9 | Imports `WorkspaceSchema` — still valid after the change, no modification needed. |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server: `cd rext-backend && uvicorn src.main:app --reload`
2. Open the Swagger UI at `http://localhost:8000/docs`
3. Navigate to the `POST /workspaces` (create workspace) endpoint
4. Observe the request body schema shows brand voice fields (`about`, `customer_profile`, `selling_position`, `target_audience`, `brand_voice`, `competitors`, `content_strategy`) alongside workspace fields
5. Submit a create workspace request with brand voice fields filled in — note that they are silently ignored

### After Fix (Verify the Solution):
1. Start the backend server: `cd rext-backend && uvicorn src.main:app --reload`
2. Open the Swagger UI at `http://localhost:8000/docs`
3. Navigate to the `POST /workspaces` (create workspace) endpoint
4. Verify the request body schema shows only `name`, `timezone`, and `url`
5. Verify brand voice fields are NOT shown on workspace create/update endpoints
6. Navigate to the `PUT /{workspace_id}/brand-voice` endpoint
7. Verify that brand voice fields are still correctly shown there (via `BrandSchema`)
8. Create a workspace with name, timezone, and url — verify it works as before
9. Update a workspace — verify it works as before

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "workspace" --tb=short
```

---

## Acceptance Criteria

- [ ] `WorkspaceSchema` in `src/api/schema/workspace_schema.py` contains only `name`, `timezone`, and `url` fields
- [ ] Brand voice fields (`about`, `customer_profile`, `selling_position`, `target_audience`, `brand_voice`, `competitors`, `content_strategy`) are removed from `WorkspaceSchema`
- [ ] Unused `WorkspaceSchema` import is removed from `src/api/routes/workspaces/members/members_routes.py`
- [ ] OpenAPI/Swagger documentation for workspace create/update endpoints no longer shows brand voice fields
- [ ] Brand voice endpoints still correctly use `BrandSchema` and function normally
- [ ] Workspace create and update endpoints function identically to before the change
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Pydantic v2 Models Documentation](https://docs.pydantic.dev/latest/concepts/models/) — guidance on model design and configuration in Pydantic v2
- **Security Advisory:** N/A
- **Migration Guide:** [Pydantic v2 Migration Guide](https://docs.pydantic.dev/latest/migration/) — reference for `class Config` to `model_config` migration (relevant to the existing `class Config` usage in `ChangeMemberRoleRequest` and `AddWorkspaceMemberRequest` in the same file)
- **Best Practice Reference:** [FastAPI — Separate OpenAPI Schemas for Input and Output](https://fastapi.tiangolo.com/how-to/separate-openapi-schemas/) — official FastAPI guidance on designing purpose-specific schemas for different operations
- **Best Practice Reference:** [FastAPI Best Practices](https://github.com/zhanymkanov/fastapi-best-practices) — community best practices including schema design patterns for create vs update vs read operations
- **Related Issues/PRs:** None identified

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-098 (`content_pillar` vs `content_strategy` field name mismatch — the `BrandSchema` uses `content_pillar` while `WorkspaceSchema` uses `content_strategy`, further evidence these schemas should not share fields), TASK-084 (Inline Pydantic Schemas in Preferences Route — similar schema design concern in B3), TASK-097 (Update Route Bypasses Pydantic Validation — related workspace schema validation issue)
