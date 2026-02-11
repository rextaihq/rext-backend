# Task 175: Remove Non-Existent Backend Fields from Frontend ContentItem Type

## Metadata
- **Task ID:** TASK-175
- **Source:** Backend Content Management Audit (Finding #28 under P2 Medium)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The frontend TypeScript interface `ContentItem` in `rext-admin/types/content.ts` (lines 210-232) defines several fields that do not exist in the backend Content model (`rext-backend/src/api/models/content_models/content.py`) or backend response schema `ContentResponse` (`rext-backend/src/api/schema/content_schema.py`, lines 93-130). The mismatched fields are:

| Frontend Field | Type | Backend Equivalent | Status |
|---|---|---|---|
| `topic_id` | `string?` | None | Does not exist in Content model or schema |
| `assigned_to_user_id` | `string?` | None | Does not exist in Content model or schema |
| `author_id` | `string?` | None | Does not exist — backend uses `created_by_user_id` |
| `content_format` | `string` | None | Does not exist in Content model or schema |
| `content_metadata` | `ContentMetadataSchema?` | None | Does not exist — backend has no metadata nested object in response |

A grep search across the entire backend `src/` directory confirmed that none of these field names (`topic_id`, `assigned_to_user_id`, `author_id`, `content_format`, `content_metadata`) appear in any backend model, schema, service, or route file related to content.

The backend `ContentResponse` Pydantic schema (the actual API response shape) includes these fields that the frontend `ContentItem` is missing or has misnamed:
- `created_by_user_id` (backend) → `author_id` (frontend) — misnamed
- `images_data`, `links_data`, `schema_markup` (backend JSONB fields) → not present in frontend type
- `wordpress_post_id`, `wordpress_url`, `wordpress_published_at` (backend) → not present in frontend type

This creates two problems:
1. **Phantom fields**: The frontend type promises `topic_id`, `assigned_to_user_id`, `content_format`, and `content_metadata` will be available, but they are always `undefined` at runtime because the API never returns them. Components that reference these fields silently fail or show empty values.
2. **Missing fields**: The frontend type doesn't declare fields that the backend DOES return (`images_data`, `links_data`, `schema_markup`, `wordpress_post_id`, `wordpress_url`, `wordpress_published_at`), so TypeScript would error if components try to access them.

Additionally, the frontend `CreateContentRequest` (lines 177-189) and `UpdateContentRequest` (lines 194-205) also include `topic_id`, `assigned_to_user_id`, and `content_format`, meaning the frontend may send these fields in create/update requests. The backend Pydantic schemas (`ContentCreate`, `ContentUpdate`) don't define these fields, so Pydantic silently drops them — the data is never persisted.

---

## Current Code

```typescript
// File: rext-admin/types/content.ts
// Lines: 210-232
export interface ContentItem {
  id: string;
  workspace_id: string;
  topic_id?: string;                    // ← Does NOT exist in backend
  created_by_user_id: string;
  assigned_to_user_id?: string;         // ← Does NOT exist in backend
  author_id?: string;                   // ← Does NOT exist — backend has created_by_user_id
  title: string;
  slug: string;
  body_markdown?: string;
  body_html?: string;
  content_format: string;               // ← Does NOT exist in backend
  status: ContentStatus;
  content_language: string;
  langgraph_thread_id?: string;
  created_at: string;
  updated_at?: string;
  deleted_at?: string;
  tags?: string[];
  introduction?: string;
  content_metadata?: ContentMetadataSchema;  // ← Does NOT exist in backend response
  seo_data?: ContentSEODataSchema;
}
```

```python
# File: rext-backend/src/api/schema/content_schema.py
# Lines: 93-130 — Backend ContentResponse (actual API response)
class ContentResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    created_by_user_id: UUID
    title: str
    slug: str
    status: str
    content_language: str
    introduction: Optional[str] = None
    body_markdown: Optional[str] = None
    body_html: Optional[str] = None
    tags: Optional[List[str]] = None
    seo_data: Optional[ContentSEODataSchema] = None
    images_data: Optional[Dict[str, Any]] = None
    links_data: Optional[Dict[str, Any]] = None
    schema_markup: Optional[Dict[str, Any]] = None
    langgraph_thread_id: Optional[UUID] = None
    wordpress_post_id: Optional[int] = None
    wordpress_url: Optional[str] = None
    wordpress_published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    class Config:
        from_attributes = True
```

---

## Why This Matters (Context & Reasoning)

The `ContentItem` type is the primary type used throughout the frontend for rendering content lists, content detail pages, and content cards. When this type promises fields that the API never returns, it creates a false contract that leads to silent runtime failures. Developers writing new components trust the TypeScript type to reflect reality, but `topic_id`, `assigned_to_user_id`, `content_format`, and `content_metadata` are always undefined at runtime. This also makes the frontend code harder to maintain because developers can't tell which fields actually have data and which are phantom.

The OWASP API Security guidelines (API3:2023) recommend that client-side data models should match the API contract exactly. Phantom fields in the frontend type can also mask bugs — if a feature depends on `topic_id` being present, it will silently fail rather than producing a TypeScript error.

Conversely, the backend returns fields like `images_data`, `links_data`, `schema_markup`, and WordPress publishing fields that the frontend type doesn't declare. If future frontend features need to access these fields, TypeScript will block access even though the data is available in the API response.

---

## Impact

- **Severity:** Frontend components silently show empty/undefined values for phantom fields. Data sent in create/update requests for these fields is silently dropped by the backend. Developers are misled by inaccurate type definitions.
- **Affected Users/Flows:** All content CRUD operations. Any component rendering `ContentItem` data. The `CreateContentRequest` and `UpdateContentRequest` types also send phantom data that is never persisted.
- **Blast Radius:** Affects the content creation page, content detail page, content list page, and any component that uses the `ContentItem` type.

---

## Recommended Solution

Align the frontend `ContentItem` type with the backend `ContentResponse` schema. Remove fields that don't exist in the backend, add fields that the backend returns but the frontend is missing, and fix the `author_id` → `created_by_user_id` naming mismatch.

### Step 1: Update the `ContentItem` interface

```typescript
// File: rext-admin/types/content.ts
// Replace lines 210-232 with:

/**
 * Content item schema — matches backend ContentResponse exactly.
 *
 * Backend schema: rext-backend/src/api/schema/content_schema.py (ContentResponse)
 * Backend model: rext-backend/src/api/models/content_models/content.py
 */
export interface ContentItem {
  id: string;
  workspace_id: string;
  created_by_user_id: string;
  title: string;
  slug: string;
  status: ContentStatus;
  content_language: string;

  // Core content fields
  introduction?: string;
  body_markdown?: string;
  body_html?: string;
  tags?: string[];

  // Nested SEO data
  seo_data?: ContentSEODataSchema;

  // Flow-generated structured data
  images_data?: Record<string, unknown>;
  links_data?: Record<string, unknown>;
  schema_markup?: Record<string, unknown>;

  // LangGraph workflow tracking
  langgraph_thread_id?: string;

  // WordPress publishing fields
  wordpress_post_id?: number;
  wordpress_url?: string;
  wordpress_published_at?: string;

  // Timestamps
  created_at: string;
  updated_at?: string;
  deleted_at?: string;
}
```

### Step 2: Update `CreateContentRequest` to match backend `ContentCreate`

```typescript
// File: rext-admin/types/content.ts
// Replace lines 177-189 with:

/**
 * Request schema for creating content — matches backend ContentCreate.
 */
export interface CreateContentRequest {
  workspace_id?: string;
  title: string;
  introduction?: string;
  body_markdown?: string;
  body_html?: string;
  status?: ContentStatus;
  content_language?: string;
  tags?: string[];
  langgraph_thread_id?: string;
  seo_data?: ContentSEODataSchema;
  media_items?: Array<{
    media_id: string;
    usage_type?: string;
    position?: number;
  }>;
  images_data?: Record<string, unknown>;
  links_data?: Record<string, unknown>;
  schema_markup?: Record<string, unknown>;
}
```

### Step 3: Update `UpdateContentRequest` to match backend `ContentUpdate`

```typescript
// File: rext-admin/types/content.ts
// Replace lines 194-205 with:

/**
 * Request schema for updating content — matches backend ContentUpdate.
 */
export interface UpdateContentRequest {
  title?: string;
  status?: ContentStatus;
  content_language?: string;
  introduction?: string;
  body_markdown?: string;
  body_html?: string;
  tags?: string[];
  seo_data?: ContentSEODataSchema;
  media_items?: Array<{
    media_id: string;
    usage_type?: string;
    position?: number;
  }>;
  images_data?: Record<string, unknown>;
  links_data?: Record<string, unknown>;
  schema_markup?: Record<string, unknown>;
  langgraph_thread_id?: string;
  wordpress_post_id?: number;
  wordpress_url?: string;
  wordpress_published_at?: string;
}
```

### Step 4: Update any components referencing removed fields

Search for and update references to removed fields. Common patterns to fix:

```typescript
// If any component references author_id, replace with created_by_user_id:
// Before:
item.author_id
// After:
item.created_by_user_id

// If any component references content_format, remove the reference:
// Before:
item.content_format
// After:
// Remove or use a default value

// If any component references content_metadata, use individual fields from seo_data or top-level fields instead
```

### Step 5: Remove `ContentMetadataSchema` if no longer needed

If `ContentMetadataSchema` (lines 104-121) is only used by `ContentItem.content_metadata` (which is being removed) and by `CreateContentRequest.metadata` / `UpdateContentRequest.metadata` (also being removed), it can be marked as unused. Check if it's referenced elsewhere before removing:

```bash
grep -r "ContentMetadataSchema" rext-admin/
```

If only used in `types/content.ts`, remove the interface. If used elsewhere (e.g., in the content generation flow), keep it but remove it from `ContentItem`.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/types/content.ts` | `177-189` | `CreateContentRequest` includes phantom fields `topic_id`, `assigned_to_user_id`, `content_format` |
| `rext-admin/types/content.ts` | `194-205` | `UpdateContentRequest` includes phantom fields `topic_id`, `assigned_to_user_id` |
| `rext-admin/types/content.ts` | `104-121` | `ContentMetadataSchema` may become unused after removing `content_metadata` from `ContentItem` |
| `rext-admin/app/w/[workspaceSlug]/content/create/page.tsx` | Various | May reference `topic_id`, `assigned_to_user_id`, or `content_format` |
| `rext-admin/components/content/content-card.tsx` | Various | May reference `author_id` or `content_format` |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open the browser developer tools network tab.
2. Navigate to a content detail page.
3. Inspect the API response for `GET /api/v1/content/{id}`.
4. Observe: the response does NOT contain `topic_id`, `assigned_to_user_id`, `author_id`, `content_format`, or `content_metadata`.
5. In the console, check `typeof contentItem.topic_id` — it's `undefined`.

### After Fix (Verify the Solution):
1. Run `npm run build` — verify TypeScript compilation succeeds with no errors.
2. Check that all components that previously referenced `author_id` now use `created_by_user_id`.
3. Verify content list page renders correctly.
4. Verify content detail page renders correctly.
5. Create new content and verify the request payload only contains fields the backend accepts.
6. Verify no `undefined` access warnings in the browser console.

### Run Existing Tests:
```bash
cd rext-admin
npm run build    # TypeScript compilation check
npm run lint     # Biome linting
npm test         # Jest tests
```

---

## Acceptance Criteria

- [ ] `ContentItem` interface matches backend `ContentResponse` schema field-for-field
- [ ] Removed fields: `topic_id`, `assigned_to_user_id`, `author_id`, `content_format`, `content_metadata`
- [ ] Added missing fields: `images_data`, `links_data`, `schema_markup`, `wordpress_post_id`, `wordpress_url`, `wordpress_published_at`
- [ ] `CreateContentRequest` matches backend `ContentCreate` schema
- [ ] `UpdateContentRequest` matches backend `ContentUpdate` schema
- [ ] All component references to removed fields have been updated or removed
- [ ] TypeScript compilation succeeds without errors (`npm run build`)
- [ ] No runtime errors when rendering content pages
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [TypeScript — Interfaces](https://www.typescriptlang.org/docs/handbook/2/objects.html) — defining accurate object types
- **Security Advisory:** [OWASP API3:2023 — Broken Object Property Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/) — client-side data models should match API contracts
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html) — recommends schema validation and contract alignment between frontend and backend
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-174 (Frontend SEO Field Names Mismatch — B6), TASK-161 (Status Enum Mismatch Between Frontend and Backend — B6), TASK-068 (Frontend-Backend User Type Mismatch — B3)
