# Task 165: Legacy Frontend API Client Uses Wrong HTTP Method for Content Updates

## Metadata
- **Task ID:** TASK-165
- **Source:** B6 - Content Management (Finding #12 under P1 High)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

The audit report identified that the frontend uses `PUT` for content updates while the backend expects `PATCH`. Investigation of the current codebase reveals a nuanced situation:

**The new API client (`rext-admin/lib/api-client/content.ts`) at line 78 already uses `method: "PATCH"` correctly.** This file is part of the new unified API client system described in `rext-admin/lib/api-client/index.ts` (which states it "Replaces BackendService, ContentApiService, WorkspaceApiService, etc.").

**However, the legacy `ContentApiService` class (`rext-admin/services/content-api.ts`) at line 221 still uses `method: "PUT"` for its `updateContent()` method.** This legacy service class is still exported (line 303: `export const contentApiService = new ContentApiService()`) and could potentially be imported by components that haven't been migrated to the new API client.

The backend endpoint for content updates is defined as `@router.patch("/{content_id}")` in `rext-backend/src/api/routes/content/modules/publish_content.py:301`. FastAPI/Starlette will return HTTP 405 Method Not Allowed for a `PUT` request to a `PATCH`-only endpoint.

According to RFC 7231 (PUT) and RFC 5789 (PATCH), `PUT` replaces the entire resource while `PATCH` applies partial modifications. The backend correctly uses `PATCH` since `ContentUpdate` is a Pydantic model where all fields are optional (partial updates). Using `PUT` would be semantically incorrect even if the endpoint accepted it, because the client only sends changed fields.

Additionally, the legacy service uses a different URL pattern (`/api/v1/content/${workspaceId}/${contentId}` at line 215) compared to the new client (`/api/v1/content/${contentId}?workspace_id=...`), which is a further source of failure.

---

## Current Code

```typescript
// File: rext-admin/services/content-api.ts
// Lines: 210-224 (legacy service — USES PUT)
  async updateContent(
    workspaceId: string,
    contentId: string,
    data: UpdateContentRequest,
  ): Promise<ContentResponse> {
    const url = `${this.baseUrl}/api/v1/content/${workspaceId}/${contentId}`;

    this.log.info("Updating content", { workspaceId, contentId });

    try {
      const response = await authenticatedFetch(url, {
        method: "PUT",  // WRONG: backend expects PATCH
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
```

```typescript
// File: rext-admin/lib/api-client/content.ts
// Lines: 70-83 (new API client — CORRECTLY USES PATCH)
    update: async (
      workspaceId: string,
      contentId: string,
      data: Record<string, unknown>,
    ) => {
      return client.request<ContentResponse>(
        `/api/v1/content/${contentId}?workspace_id=${encodeURIComponent(workspaceId)}`,
        {
          method: "PATCH",  // Correct
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        },
      );
    },
```

```python
# File: rext-backend/src/api/routes/content/modules/publish_content.py
# Line: 301
@router.patch("/{content_id}", response_model=ContentResponse)
```

---

## Why This Matters (Context & Reasoning)

The legacy `ContentApiService` is part of an older service-oriented architecture in the frontend that is being replaced by the unified API client in `lib/api-client/`. However, the legacy service is still exported and accessible. If any component still imports from `services/content-api.ts` (either directly or indirectly), content update operations will fail with HTTP 405 Method Not Allowed.

Even though the new API client has the correct method, leaving the legacy service with a broken HTTP method creates a maintenance trap: a developer unfamiliar with the migration might use the legacy service and encounter mysterious 405 errors. The legacy file should either be deleted (if fully replaced) or corrected (if still in use during migration).

---

## Impact

- **Severity:** Any component using the legacy `ContentApiService.updateContent()` will get HTTP 405 errors. The new API client works correctly.
- **Affected Users/Flows:** Content editing flows if they reference the legacy service. Users would see failed save operations when editing content.
- **Blast Radius:** Limited to components that still import `ContentApiService` from `services/content-api.ts`. The new API client path is unaffected.

---

## Recommended Solution

### Option A (Preferred): Remove the legacy service file entirely

If the new API client (`lib/api-client/content.ts`) fully replaces the legacy `ContentApiService`, the cleanest fix is to delete the legacy file and remove any remaining imports.

#### Step 1: Search for any remaining imports of the legacy service

```bash
cd rext-admin
grep -r "ContentApiService\|content-api\|contentApiService" --include="*.ts" --include="*.tsx" | grep -v "node_modules" | grep -v ".taskmaster"
```

#### Step 2: Migrate any remaining consumers to the new API client

If any components still import from `services/content-api.ts`, update them to use the new API client from `lib/api-client/`.

#### Step 3: Delete the legacy file

```bash
rm rext-admin/services/content-api.ts
```

### Option B (If legacy service is still needed during migration): Fix the HTTP method

```typescript
// File: rext-admin/services/content-api.ts
// Replace line 221:
        method: "PATCH",
```

Also fix the URL pattern on line 215 to match the backend's expected format:

```typescript
// File: rext-admin/services/content-api.ts
// Replace line 215:
    const url = `${this.baseUrl}/api/v1/content/${contentId}?workspace_id=${encodeURIComponent(workspaceId)}`;
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/services/content-api.ts` | `162` | Legacy `createContent()` also uses different URL pattern (`/api/v1/content/${workspaceId}`) |
| `rext-admin/services/content-api.ts` | `303` | Exports singleton `contentApiService` that may be imported elsewhere |
| `rext-admin/lib/api-client/index.ts` | `5` | Comment confirms new client replaces legacy services |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Search the codebase for any active imports of the legacy service:
   ```bash
   cd rext-admin
   grep -r "from.*services/content-api\|import.*content-api" --include="*.ts" --include="*.tsx" | grep -v node_modules
   ```
2. If imports exist, test the update flow using that component — observe HTTP 405 error in the browser network tab

### After Fix (Verify the Solution):
1. If Option A was chosen: verify no remaining imports reference the deleted file
   ```bash
   npm run build
   ```
   A successful build confirms no broken imports.
2. If Option B was chosen: test content editing flows using both the new and legacy API clients
3. Verify content updates succeed with HTTP 200 response

### Run Existing Tests:
```bash
cd rext-admin
npm run test
npm run build
```

---

## Acceptance Criteria

- [ ] The legacy `ContentApiService` is either removed (Option A) or corrected to use `PATCH` (Option B)
- [ ] No remaining frontend code calls content update endpoints with `PUT` method
- [ ] Content update operations work correctly via the frontend
- [ ] `npm run build` succeeds without errors
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [MDN — HTTP PATCH method](https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods/PATCH) — Defines PATCH semantics for partial resource modification
- **Official Docs:** [MDN — HTTP 405 Method Not Allowed](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/405) — The error returned when the wrong method is used
- **Official Docs:** [FastAPI — Path Operation Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/) — How FastAPI maps HTTP methods to route handlers
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [RFC 5789 — PATCH Method for HTTP](https://tools.ietf.org/html/rfc5789) — Formal specification of the PATCH method
- **Best Practice Reference:** [REST API Best Practices — PUT vs PATCH](https://www.baeldung.com/http-put-patch-difference-spring) — When to use PUT vs PATCH
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-166 (Frontend calls non-existent endpoint — same frontend API client has another endpoint mismatch)
