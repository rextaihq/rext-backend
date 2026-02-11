# Task 170: WorkspaceIntegration Response Schema Includes Credentials

## Metadata
- **Task ID:** TASK-170
- **Source:** Content Management Audit (Finding #20 under P2 Medium)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P2 Medium
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `WorkspaceIntegrationResponse` Pydantic schema at `src/api/schema/content_schema.py:169-176` inherits from `WorkspaceIntegrationBase` (lines 142-151), which includes `app_password` and `api_key` as fields. This means that every API response that uses `WorkspaceIntegrationResponse` as its response model — or any route that serializes a `WorkspaceIntegration` object using `to_dict()` — will include the WordPress application password and API key in the JSON response sent to the client.

The `WorkspaceIntegrationBase` schema at lines 142-151 defines:
```
app_password: Optional[str] = None
api_key: Optional[str] = None
```

And `WorkspaceIntegrationResponse` at line 169 inherits all these fields:
```
class WorkspaceIntegrationResponse(WorkspaceIntegrationBase):
```

This is a defense-in-depth issue that compounds with the credential exposure in the `to_dict()` method (already covered by TASK-029). Even if `to_dict()` is fixed to exclude credentials, having a Pydantic response schema that explicitly includes these fields creates a risk surface: any developer who serializes a `WorkspaceIntegration` ORM object through this schema will inadvertently expose credentials. According to OWASP API Security Top 10 (API3:2019 — Excessive Data Exposure), APIs should not return more sensitive data than the client needs, and the filtering should happen server-side, not rely on the client to ignore sensitive fields.

The schema is referenced in `content_schema.py:180` where `WorkspaceIntegrationListResponse` uses `List[WorkspaceIntegrationResponse]` for the `sites` field, meaning the list-all-sites endpoint will also expose credentials for every connected site. Currently, the actual routes in `sites.py` use `site.to_dict()` rather than the Pydantic response model for serialization, but the schema exists and could be used by any developer who follows FastAPI's `response_model` pattern.

---

## Current Code

```python
# File: src/api/schema/content_schema.py
# Lines: 142-176
class WorkspaceIntegrationBase(BaseModel):
    """Base schema for connected sites."""
    integration_type: str = "wordpress"
    is_active: bool = True
    site_url: Optional[str] = None
    api_endpoint: Optional[str] = None
    username: Optional[str] = None
    app_password: Optional[str] = None
    api_key: Optional[str] = None
    config_json: Optional[Dict[str, Any]] = None


class WorkspaceIntegrationCreate(WorkspaceIntegrationBase):
    pass


class WorkspaceIntegrationUpdate(BaseModel):
    integration_type: Optional[str] = None
    is_active: Optional[bool] = None
    site_url: Optional[str] = None
    api_endpoint: Optional[str] = None
    username: Optional[str] = None
    app_password: Optional[str] = None
    api_key: Optional[str] = None
    config_json: Optional[Dict[str, Any]] = None


class WorkspaceIntegrationResponse(WorkspaceIntegrationBase):
    id: UUID
    workspace_id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
```

---

## Why This Matters (Context & Reasoning)

The `WorkspaceIntegration` model stores WordPress credentials — application passwords and API keys — that grant full read/write access to connected WordPress sites. If these credentials are returned in API responses, any user with access to the sites endpoints can extract them. This is particularly dangerous because WordPress application passwords grant persistent API access (they don't expire) and API keys for the Rext-AI WordPress plugin grant bearer token access to the custom publishing endpoints. An exposed credential could be used to publish, modify, or delete content on the connected WordPress site without going through the Rext AI platform.

The Pydantic schema layer is the last line of defense before data reaches the client. Even if the ORM `to_dict()` method is eventually fixed to exclude credentials (TASK-029), the Pydantic response schema should independently enforce that credentials are never serialized in responses. This defense-in-depth approach ensures that no code path can accidentally expose credentials through this schema.

---

## Impact

- **Severity:** Credentials could be exposed in API responses if any route uses this schema as `response_model` or if the schema is used for serialization. Currently the `sites.py` routes use `to_dict()` directly (which also leaks credentials — see TASK-029), but this schema makes the problem structural.
- **Affected Users/Flows:** Any user accessing site management endpoints. The credentials grant access to connected WordPress sites.
- **Blast Radius:** All site-related endpoints that use these schemas: list sites, get site details, connect site, update site, activate/deactivate site.

---

## Recommended Solution

Create a separate response schema that excludes sensitive fields, and update the base schema to mark credentials as write-only (accepted in requests but never returned in responses).

### Step 1: Create a Safe Response Schema

```python
# File: src/api/schema/content_schema.py
# Replace the WorkspaceIntegrationResponse class (lines 169-176) with:

class WorkspaceIntegrationResponse(BaseModel):
    """Safe response schema for connected sites — excludes credentials."""
    id: UUID
    workspace_id: UUID
    integration_type: str
    is_active: bool
    site_url: Optional[str] = None
    api_endpoint: Optional[str] = None
    username: Optional[str] = None
    config_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
```

Note: This response schema does NOT inherit from `WorkspaceIntegrationBase` and does NOT include `app_password` or `api_key`. It also uses the Pydantic v2 `model_config = ConfigDict(from_attributes=True)` pattern instead of the deprecated `class Config` block.

### Step 2: Add ConfigDict Import

```python
# File: src/api/schema/content_schema.py
# Add to the imports at line 1:
from pydantic import BaseModel, Field, field_validator, ConfigDict
```

### Step 3: Update the Existing ContentResponse Config Too

While editing this file, also update `ContentResponse` (line 129) to use the modern Pydantic v2 pattern:

```python
# File: src/api/schema/content_schema.py
# Replace lines 129-130:
    class Config:
        from_attributes = True

# With:
    model_config = ConfigDict(from_attributes=True)
```

### Step 4: Update Sites Routes to Use the Response Schema

```python
# File: src/api/routes/content/modules/sites.py
# Update the list_connected_sites endpoint return (line 41-45) to use the safe schema:

    return {
        "sites": [
            WorkspaceIntegrationResponse.model_validate(site).model_dump()
            for site in sites
        ],
        "total_count": len(sites),
        "workspace_id": str(workspace.id)
    }
```

Apply the same pattern to all other endpoints in `sites.py` that return site data:
- `connect_site` (line 95): `return {"site": WorkspaceIntegrationResponse.model_validate(new_site).model_dump()}`
- `get_site_details` (line 119): `return {"site": WorkspaceIntegrationResponse.model_validate(site).model_dump()}`
- `update_site` (line 155): `return {"site": WorkspaceIntegrationResponse.model_validate(site).model_dump()}`
- `activate_site` (line 208): `return {"site": WorkspaceIntegrationResponse.model_validate(site).model_dump()}`
- `deactivate_site` (line 234): `return {"site": WorkspaceIntegrationResponse.model_validate(site).model_dump()}`

Add the import at the top of `sites.py`:
```python
from src.api.schema.content_schema import WorkspaceIntegrationResponse
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/schema/content_schema.py` | `179-182` | `WorkspaceIntegrationListResponse` uses `List[WorkspaceIntegrationResponse]` — will automatically use the safe schema |
| `src/api/routes/content/modules/sites.py` | `42, 95, 119, 155, 208, 234` | All endpoints returning `site.to_dict()` should use the safe response schema |
| `src/api/models/workspace_models/workspace_integration.py` | `42-57` | `to_dict()` also exposes credentials — addressed by TASK-029 |
| `src/api/routes/content/modules/publish_content.py` | `62-68` | `_publish_to_all_sites` accesses credentials to create `WordPressPublisher` — this is internal and correct (needs credentials to publish) |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Connect a WordPress site to a workspace via `POST /api/v1/content/sites/connect` with an `api_key` or `app_password`
2. Call `GET /api/v1/content/sites/list?workspace_id=...`
3. Observe that the response JSON includes `app_password` and `api_key` fields with their actual values

### After Fix (Verify the Solution):
1. Call `GET /api/v1/content/sites/list?workspace_id=...`
2. Verify the response JSON does NOT contain `app_password` or `api_key` fields at all
3. Call `GET /api/v1/content/sites/{site_id}?workspace_id=...`
4. Verify the single site response also does NOT contain credential fields
5. Call `POST /api/v1/content/sites/connect` with credentials — verify the connect request still accepts `app_password` and `api_key` in the request body (write path is unaffected)
6. Call `PATCH /api/v1/content/sites/{site_id}` with updated credentials — verify the update works but the response does not include credentials
7. Verify that publishing still works (credentials are read from the database, not the response)

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "site or integration or content"
```

---

## Acceptance Criteria

- [ ] `WorkspaceIntegrationResponse` does NOT include `app_password` or `api_key` fields
- [ ] `WorkspaceIntegrationResponse` does NOT inherit from `WorkspaceIntegrationBase`
- [ ] All site-related endpoints return data through the safe response schema
- [ ] `WorkspaceIntegrationCreate` and `WorkspaceIntegrationUpdate` still accept credentials in requests (write path unchanged)
- [ ] Publishing endpoints still work correctly (they read credentials from the ORM object, not the response schema)
- [ ] `WorkspaceIntegrationResponse` uses `model_config = ConfigDict(from_attributes=True)` instead of deprecated `class Config`
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Pydantic v2 — Fields (exclude)](https://docs.pydantic.dev/latest/concepts/fields/) — documentation on field exclusion and serialization control
- **Security Advisory:** [OWASP API3:2019 — Excessive Data Exposure](https://owasp.org/API-Security/editions/2019/en/0xa3-excessive-data-exposure/) — APIs should not return more data than the client needs
- **Migration Guide:** [Pydantic v2 Migration — ConfigDict](https://docs.pydantic.dev/latest/api/config/) — `model_config = ConfigDict(...)` replaces `class Config`
- **Best Practice Reference:** [FastAPI Response Model](https://fastapi.tiangolo.com/tutorial/response-model/) — using response models to control which fields are returned
- **Related Issues/PRs:** None identified

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-029 (WorkspaceIntegration.to_dict() Leaks Credentials) — the model-level fix; this task fixes the schema-level exposure. Both should be implemented for defense-in-depth; TASK-089 (Integration Credentials Stored in Plaintext) — the broader credential security issue
