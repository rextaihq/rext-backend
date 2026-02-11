# Task 174: Fix Frontend SEO Field Names Mismatch with Backend Schema

## Metadata
- **Task ID:** TASK-174
- **Source:** Backend Content Management Audit (Finding #27 under P2 Medium)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P2 Medium
- **Category:** bug
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The frontend TypeScript type `ContentSEODataSchema` in `rext-admin/types/content.ts` (lines 126-172) defines SEO field names that do not match the backend Pydantic schema `ContentSEODataSchema` in `rext-backend/src/api/schema/content_schema.py` (lines 21-32) or the database model `ContentSEOData` in `rext-backend/src/api/models/content_models/content_seo_data.py` (lines 10-33).

The specific mismatches are:

| Frontend Field Name | Backend Field Name | Database Column |
|---|---|---|
| `content_primary_keywords` | `focus_keyphrase` (single string) | `focus_keyphrase` (Text) |
| `content_secondary_keywords` | `secondary_keywords` | `secondary_keywords` (ARRAY(Text)) |
| `content_meta_description` | `meta_description` | `meta_description` (Text) |
| `content_search_intent` | `search_intent` | `search_intent` (ARRAY(Text)) |
| `content_seo_score` | `seo_score` | `seo_score` (Float) |

The frontend uses these mismatched names actively in several components:
- `rext-admin/app/w/[workspaceSlug]/content/create/page.tsx` (line 102): sends `content_primary_keywords` in the SEO data payload
- `rext-admin/app/w/[workspaceSlug]/content/create/page.tsx` (line 104): sends `content_meta_description`
- `rext-admin/app/w/[workspaceSlug]/content/[id]/page.tsx` (line 355): reads `content_seo_score` from response
- `rext-admin/components/content/content-card.tsx` (lines 146, 156-157): displays `content_seo_score`

There is also a type mismatch: the frontend defines `content_primary_keywords` as `string[]` (array of strings), but the backend's `focus_keyphrase` is a single `str` (not an array). The backend does have `secondary_keywords` as `List[str]`, but the frontend has a separate `content_secondary_keywords` for that.

The frontend `ContentSEODataSchema` also includes fields that exist in both the frontend and backend with the same names (`meta_title`, `meta_description`, `focus_keyphrase`, `readability_score`, `keyphrase_density`, `seo_details`, `trust_score`), creating ambiguity — for example, `content_meta_description` and `meta_description` both exist in the frontend type, and it's unclear which one the frontend actually sends to the API.

When the frontend sends `content_primary_keywords` in the SEO payload, the backend's Pydantic schema ignores it (since the field doesn't exist in `ContentSEODataSchema`) and the data is silently dropped. This means SEO keywords entered by users during content creation are never persisted to the database.

---

## Current Code

```typescript
// File: rext-admin/types/content.ts
// Lines: 126-172
export interface ContentSEODataSchema {
  content_primary_keywords: string[];       // Backend: focus_keyphrase (str, not array)
  content_secondary_keywords?: string[];    // Backend: secondary_keywords
  content_meta_description: string;         // Backend: meta_description
  content_search_intent?: string[];         // Backend: search_intent
  content_seo_score?: number;               // Backend: seo_score
  readability_score?: number;               // Same name ✓
  meta_title?: string;                      // Same name ✓
  meta_description?: string;                // Same name ✓ (duplicate of content_meta_description)
  focus_keyphrase?: string;                 // Same name ✓ (duplicate of content_primary_keywords)
  keyphrase_density?: number;               // Same name ✓
  seo_details?: string;                     // Same name ✓
  trust_score?: number;                     // Same name ✓
  eeat_data?: EEATData | string;            // Not in backend schema
}
```

```python
# File: rext-backend/src/api/schema/content_schema.py
# Lines: 21-32
class ContentSEODataSchema(BaseModel):
    """SEO data schema for separate table"""
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    focus_keyphrase: Optional[str] = None
    keyphrase_density: Optional[float] = None
    secondary_keywords: Optional[List[str]] = None
    search_intent: Optional[List[str]] = None
    seo_score: Optional[float] = None
    readability_score: Optional[float] = None
    trust_score: Optional[float] = None
    seo_details: Optional[str] = None
```

```typescript
// File: rext-admin/app/w/[workspaceSlug]/content/create/page.tsx
// Line 102-104 — sends mismatched field names
seo_data: {
    content_primary_keywords: primaryKeywords,
    // ...
    content_meta_description: metaDescription.slice(0, 160),
}
```

---

## Why This Matters (Context & Reasoning)

SEO data is a core feature of Rext AI — the platform generates AI content with SEO optimization. When users create content, they input primary keywords, meta descriptions, and other SEO fields. These are sent to the backend as part of the `seo_data` nested object. Because the frontend uses different field names than the backend schema expects, Pydantic silently drops the unrecognized fields. This means:

1. **Primary keywords are never saved**: The user enters keywords, they appear in the UI, but they are lost when the content is saved because the backend sees `content_primary_keywords` instead of `focus_keyphrase`.
2. **Meta description may be lost**: If the frontend only sends `content_meta_description` (not `meta_description`), it's dropped.
3. **SEO scores don't display correctly**: The frontend reads `content_seo_score` from the response, but the backend returns `seo_score`, causing the SEO score to always show as undefined in the UI.

This is a data integrity issue that directly impacts the product's core value proposition.

---

## Impact

- **Severity:** SEO keywords and meta descriptions entered by users are silently lost during content creation. SEO scores do not display in the frontend.
- **Affected Users/Flows:** All users creating or editing content with SEO data. The content creation page, content detail page, and content card component are all affected.
- **Blast Radius:** All content created through the frontend has incomplete or missing SEO data in the database. The AI content generation pipeline may also be affected if it reads SEO data from the database for optimization.

---

## Recommended Solution

The backend field names match the database columns and are the source of truth. The frontend should be updated to use the backend field names. This approach is recommended because: (1) changing the backend would require a database migration to rename columns, (2) the backend naming convention (`focus_keyphrase`, `meta_description`, `seo_score`) follows SEO industry terminology more closely, and (3) OWASP API Security guidelines (API3:2023) recommend using a shared schema as the single source of truth.

### Step 1: Update the frontend `ContentSEODataSchema` type

```typescript
// File: rext-admin/types/content.ts
// Replace lines 126-172 with:

/**
 * SEO data schema for content
 *
 * Field names must match backend ContentSEODataSchema exactly.
 * Backend schema: rext-backend/src/api/schema/content_schema.py
 * Database model: rext-backend/src/api/models/content_models/content_seo_data.py
 */
export interface ContentSEODataSchema {
  /** Meta title for SEO (50-60 chars recommended) */
  meta_title?: string;

  /** Meta description for SEO and social sharing (150-160 chars recommended) */
  meta_description?: string;

  /** Primary focus keyphrase for SEO optimization */
  focus_keyphrase?: string;

  /** Keyphrase density percentage */
  keyphrase_density?: number;

  /** Secondary/supporting keywords for SEO */
  secondary_keywords?: string[];

  /** Search intent categories (informational, transactional, etc.) */
  search_intent?: string[];

  /** SEO quality score (0-100) */
  seo_score?: number;

  /** Content readability score */
  readability_score?: number;

  /** Trust score for content */
  trust_score?: number;

  /** Full SEO assessment details as JSON string */
  seo_details?: string;

  /** EEAT data for content (frontend-only, not persisted to SEO table) */
  eeat_data?: EEATData | string;
}
```

### Step 2: Update content creation page to use correct field names

```typescript
// File: rext-admin/app/w/[workspaceSlug]/content/create/page.tsx
// Replace line 102-104 (seo_data construction):

seo_data: {
    focus_keyphrase: primaryKeywords.join(", "),  // Convert array to comma-separated string
    meta_description: metaDescription.slice(0, 160),
}
```

Note: The backend `focus_keyphrase` is a single string, not an array. If the frontend collects multiple keywords as an array, join them into a comma-separated string. Alternatively, use the `secondary_keywords` field for additional keywords:

```typescript
seo_data: {
    focus_keyphrase: primaryKeywords[0] || "",  // Primary keyword
    secondary_keywords: primaryKeywords.slice(1),  // Remaining keywords
    meta_description: metaDescription.slice(0, 160),
}
```

### Step 3: Update content detail page to read correct field name

```typescript
// File: rext-admin/app/w/[workspaceSlug]/content/[id]/page.tsx
// Replace line 355:

// Before:
seo_score: content.seo_data?.content_seo_score || 0,

// After:
seo_score: content.seo_data?.seo_score || 0,
```

### Step 4: Update content card component to read correct field name

```typescript
// File: rext-admin/components/content/content-card.tsx
// Replace lines 146 and 156-157:

// Before (line 146):
item.seo_data?.content_seo_score

// After:
item.seo_data?.seo_score

// Before (lines 156-157):
{item.seo_data?.content_seo_score !== undefined && (
  <span>SEO: {item.seo_data.content_seo_score}/100</span>
)}

// After:
{item.seo_data?.seo_score !== undefined && (
  <span>SEO: {item.seo_data.seo_score}/100</span>
)}
```

### Step 5: Search for and update any other frontend references

Search the entire `rext-admin/` codebase for `content_primary_keywords`, `content_meta_description`, and `content_seo_score` and update all occurrences to use the backend field names.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/app/w/[workspaceSlug]/content/create/page.tsx` | `102-104` | Sends `content_primary_keywords` and `content_meta_description` in SEO payload |
| `rext-admin/app/w/[workspaceSlug]/content/[id]/page.tsx` | `355` | Reads `content_seo_score` from response |
| `rext-admin/components/content/content-card.tsx` | `146, 156-157` | Displays `content_seo_score` in content cards |
| `rext-admin/types/content.ts` | `126-172` | Type definition with mismatched field names |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Navigate to the content creation page in the frontend.
2. Enter a title, body, and SEO data (primary keywords, meta description).
3. Save the content.
4. Use the API or database to inspect the saved content's SEO data: `SELECT * FROM content_seo_data WHERE content_id = '<id>';`
5. Observe: `focus_keyphrase` and `meta_description` are NULL — the data was silently dropped.
6. Navigate to the content list page and observe: SEO scores show as undefined/blank.

### After Fix (Verify the Solution):
1. Same steps as above — create content with SEO data.
2. Inspect the database: `focus_keyphrase` and `meta_description` should now contain the values entered in the frontend.
3. Navigate to the content list: SEO scores should display correctly.
4. Edit existing content and verify SEO fields are populated from the response.

### Run Existing Tests:
```bash
cd rext-admin
npm run build  # Verify TypeScript compilation succeeds
npm run lint   # Check for type errors
npm test       # Run existing tests
```

---

## Acceptance Criteria

- [ ] Frontend `ContentSEODataSchema` type uses backend field names: `focus_keyphrase`, `meta_description`, `seo_score`, `secondary_keywords`, `search_intent`
- [ ] Content creation page sends `focus_keyphrase` instead of `content_primary_keywords`
- [ ] Content creation page sends `meta_description` instead of `content_meta_description`
- [ ] Content detail page reads `seo_score` instead of `content_seo_score`
- [ ] Content card component reads `seo_score` instead of `content_seo_score`
- [ ] No duplicate field names in the frontend type (removed `content_*` prefixed duplicates)
- [ ] TypeScript compilation succeeds without errors (`npm run build`)
- [ ] SEO data entered in the frontend is correctly persisted to the database
- [ ] SEO scores display correctly in content list and detail views
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Pydantic V2 — Model Validation](https://docs.pydantic.dev/latest/concepts/models/#model-methods-and-properties) — explains how unknown fields are silently ignored by default
- **Security Advisory:** [OWASP API3:2023 — Broken Object Property Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/) — recommends explicit schema definitions to prevent data model mismatches
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html) — recommends using a shared schema definition (like OpenAPI) as the single source of truth between frontend and backend
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-161 (Status Enum Mismatch Between Frontend and Backend — B6), TASK-175 (Frontend ContentItem Has Fields Not in Backend — B6), TASK-163 (Test File Import Error for ContentSEODataSchema — B6)
