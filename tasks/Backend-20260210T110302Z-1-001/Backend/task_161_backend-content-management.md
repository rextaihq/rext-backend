# Task 161: Content Status Enum Mismatch Between Frontend and Backend

## Metadata
- **Task ID:** TASK-161
- **Source:** Content Management Audit (Finding #15 under P1 High)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The content management system uses incompatible status values between the frontend and backend. The frontend defines 8 status values in `rext-admin/types/content.ts:4-12`, while the backend's status transition map in `src/services/content_service.py:232` recognizes only 5 status values. There is no shared enum definition — the backend uses a free-text `Column(Text)` for the status field, and the frontend uses a TypeScript union type. The two sets are:

**Frontend statuses** (`rext-admin/types/content.ts:4-12`):
`draft`, `generating`, `generated`, `failed`, `published`, `scheduled`, `review`, `cancelled`

**Backend statuses** (recognized in `content_service.py:232` transition map):
`draft`, `generating`, `ready`, `published`, `archived`

**Mismatches:**
| Status | Frontend | Backend | Issue |
|--------|----------|---------|-------|
| `generated` | Yes | No | Frontend sends this, backend transition map doesn't recognize it |
| `failed` | Yes | No | Frontend sends this, backend has no handling for it |
| `scheduled` | Yes | No | Frontend has UI for this, backend has no scheduling support |
| `review` | Yes | No | Frontend has UI for this, backend has no handling |
| `cancelled` | Yes | No | Frontend has UI for this, backend has no handling |
| `ready` | No | Yes | Backend uses this as the pre-publish state, frontend doesn't display it |
| `archived` | No | Yes | Backend supports archiving, frontend has no UI for it |

The `Content` model at `src/api/models/content_models/content.py:26` uses `Column(Text, nullable=True, default="draft")` — there is no database-level enum constraint, so any string is accepted. This means:

1. The frontend can send `status="generated"` during content update, and the backend will store it without error
2. However, when the user later tries to transition FROM `"generated"` to another status, the backend's `_validate_status_transition()` will fail because `"generated"` is not a key in the `ALLOWED` dictionary (it falls to the default empty list via `.get(current, [])`)
3. The backend's `publish_content()` method at line 204 requires `content.status == "ready"` before publishing, but the frontend never sets status to `"ready"` — it goes from `"generated"` directly

The `CONTENT_STATUS_CONFIG` in `rext-admin/types/content.ts:23-88` defines UI labels, colors, and icons for all 8 frontend statuses. These drive the content list display, status badges, and filter dropdowns. If the backend returns `"ready"` or `"archived"`, the frontend will fail to find a matching config entry, potentially causing a runtime error or showing raw status text without styling.

---

## Current Code

```typescript
// File: rext-admin/types/content.ts
// Lines: 4-12
export type ContentStatus =
  | "draft"
  | "generating"
  | "generated"
  | "failed"
  | "published"
  | "scheduled"
  | "review"
  | "cancelled";
```

```python
# File: src/services/content_service.py
# Line: 232
async def _validate_status_transition(self, current: str, new: str) -> None:
    ALLOWED = {
        "generating": ["ready", "archived", "draft"],
        "draft": ["ready", "archived", "generating"],
        "ready": ["published", "draft", "archived", "generating"],
        "published": ["archived", "ready"],
        "archived": []
    }
    if new not in ALLOWED.get(current, []):
        raise RextValidationException(message=f"Invalid transition: {current} -> {new}")
```

```python
# File: src/services/content_service.py
# Lines: 204-205
async def publish_content(self, content_id: UUID, workspace_id: UUID, user_id: UUID) -> Content:
    content = await self._get_content_or_404(content_id, workspace_id)
    if content.status != "ready": raise RextValidationException(message="Content must be 'ready' to publish")
```

```python
# File: src/api/models/content_models/content.py
# Line: 26
status = Column(Text, nullable=True, default="draft")  # No enum constraint — any string accepted
```

---

## Why This Matters (Context & Reasoning)

Content status is a core concept that drives the entire content lifecycle in Rext AI — from creation through AI generation, review, and publishing. When the frontend and backend disagree on what statuses exist, several things break:

1. **Status transitions fail silently:** The backend stores frontend-sent statuses like `"generated"` without complaint, but subsequent transitions from those statuses fail because the transition map doesn't recognize them. The content becomes "stuck" in an unrecognized state.

2. **The publishing flow is broken:** The backend requires `status="ready"` to publish, but the frontend's content lifecycle goes `draft -> generating -> generated -> published`. The frontend never sets `"ready"`, so the `publish_content()` service method will always reject content generated through the normal flow.

3. **UI rendering issues:** When the backend returns `"ready"` or `"archived"`, the frontend's `CONTENT_STATUS_CONFIG` lookup will fail (undefined status), causing missing badges, broken filters, or runtime errors.

4. **Feature confusion:** The frontend shows "Scheduled", "Review", and "Cancelled" options, but no backend logic supports scheduling, review workflows, or cancellation. Users see these options but they don't do anything meaningful.

This is a cross-cutting issue that affects both frontend and backend teams. The fix requires a coordinated decision about the canonical set of statuses and their transition rules.

---

## Impact

- **Severity:** The content lifecycle is broken for AI-generated content — content that goes through `generating -> generated` cannot be published because the backend expects `"ready"` instead of `"generated"`. Status filtering in the frontend may break when the backend returns unrecognized statuses.
- **Affected Users/Flows:** All content creation and management flows. Status filtering on the content list page. Publishing workflows.
- **Blast Radius:** Cross-cutting — affects both frontend display and backend business logic. Multiple files in both codebases.

---

## Recommended Solution

Align both codebases on a unified set of statuses. The recommended unified set combines the actual needs from both sides:

**Unified status set:**
`draft`, `generating`, `ready`, `published`, `archived`, `failed`

Where:
- `draft` — initial state, content being edited manually
- `generating` — AI is generating content
- `ready` — content generation complete, ready for review/publish (replaces frontend's `"generated"`)
- `published` — content is live on WordPress
- `archived` — content is soft-archived (retained but hidden)
- `failed` — content generation or publishing failed

**Statuses to remove from frontend:** `generated` (replaced by `ready`), `scheduled` (no backend support — defer), `review` (no backend support — defer), `cancelled` (replaced by `archived` or `failed`)

### Step 1: Update the backend status transition map

```python
# File: src/services/content_service.py
# Replace line 232 with:
    async def _validate_status_transition(self, current: str, new: str) -> None:
        ALLOWED = {
            "draft": ["generating", "ready", "archived"],
            "generating": ["ready", "failed", "draft"],
            "ready": ["published", "draft", "archived", "generating"],
            "published": ["archived", "ready"],
            "archived": ["draft"],
            "failed": ["draft", "generating", "archived"],
        }
        if new not in ALLOWED.get(current, []):
            raise RextValidationException(message=f"Invalid transition: {current} -> {new}")
```

Key changes:
- Added `"failed"` state with transitions to `draft`, `generating`, `archived`
- Added `"archived" -> ["draft"]` to allow un-archiving
- Added `"generating" -> "failed"` for generation failures
- Kept `"generating" -> "ready"` as the success path

### Step 2: Update the frontend ContentStatus type

```typescript
// File: rext-admin/types/content.ts
// Replace lines 4-12 with:
export type ContentStatus =
  | "draft"
  | "generating"
  | "ready"
  | "published"
  | "archived"
  | "failed";
```

### Step 3: Update the frontend CONTENT_STATUS_CONFIG

```typescript
// File: rext-admin/types/content.ts
// Replace lines 23-88 with:
export const CONTENT_STATUS_CONFIG: Record<ContentStatus, ContentStatusInfo> = {
  draft: {
    label: "Draft",
    color: "text-gray-700",
    bgColor: "bg-gray-100",
    borderColor: "border-gray-200",
    icon: "Edit3",
    description: "Content is being created or edited",
  },
  generating: {
    label: "Generating",
    color: "text-blue-700",
    bgColor: "bg-blue-100",
    borderColor: "border-blue-200",
    icon: "Loader2",
    description: "AI is generating the content",
  },
  ready: {
    label: "Ready",
    color: "text-green-700",
    bgColor: "bg-green-100",
    borderColor: "border-green-200",
    icon: "CheckCircle",
    description: "Content is ready for review and publishing",
  },
  published: {
    label: "Published",
    color: "text-green-700",
    bgColor: "bg-green-100",
    borderColor: "border-green-200",
    icon: "Globe",
    description: "Content is live and published",
  },
  archived: {
    label: "Archived",
    color: "text-gray-500",
    bgColor: "bg-gray-50",
    borderColor: "border-gray-200",
    icon: "Archive",
    description: "Content has been archived",
  },
  failed: {
    label: "Failed",
    color: "text-red-700",
    bgColor: "bg-red-100",
    borderColor: "border-red-200",
    icon: "AlertCircle",
    description: "Content generation or publishing failed",
  },
};
```

### Step 4: Update frontend components that reference removed statuses

Search the frontend codebase for references to `"generated"`, `"scheduled"`, `"review"`, and `"cancelled"` and update them:

```bash
grep -r '"generated"\|"scheduled"\|"review"\|"cancelled"' rext-admin/ --include="*.ts" --include="*.tsx"
```

Replace `"generated"` with `"ready"` wherever it appears. Remove or comment out references to `"scheduled"`, `"review"`, and `"cancelled"` until those features are implemented.

### Step 5: Consider adding a database-level enum constraint (optional, recommended)

To prevent invalid status values from being stored, add a PostgreSQL CHECK constraint via Alembic migration:

```python
# In a new Alembic migration:
from alembic import op

def upgrade():
    op.execute("""
        ALTER TABLE content
        ADD CONSTRAINT ck_content_status
        CHECK (status IN ('draft', 'generating', 'ready', 'published', 'archived', 'failed'))
    """)

def downgrade():
    op.execute("ALTER TABLE content DROP CONSTRAINT IF EXISTS ck_content_status")
```

**Note:** Before adding this constraint, verify no existing rows have status values outside the new set:
```sql
SELECT DISTINCT status FROM content WHERE status NOT IN ('draft', 'generating', 'ready', 'published', 'archived', 'failed');
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/types/content.ts` | `4-12` | Frontend `ContentStatus` type definition |
| `rext-admin/types/content.ts` | `23-88` | Frontend `CONTENT_STATUS_CONFIG` UI configuration |
| `rext-admin/types/content.ts` | `90-95` | `STATUS_FILTER_OPTIONS` derived from config |
| `rext-admin/types/content.ts` | `183, 198, 222` | `status` field typed as `ContentStatus` in request/response schemas |
| `rext-admin/hooks/use-content.ts` | Various | May reference specific status values |
| `rext-admin/config/feature-tooltips.ts` | Various | May reference content statuses |
| `src/services/content_service.py` | `68` | Sets default status to `"draft"` on creation |
| `src/services/content_service.py` | `204` | Checks for `"ready"` before publishing |
| `src/api/routes/content/modules/publish_content.py` | `134, 205, 285` | Sets `status="published"` after successful publish |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create content that goes through AI generation flow (status becomes `"generated"` or `"generating"`)
2. Attempt to transition content from `"generated"` to `"published"` via the backend
3. **Current behavior:** Backend rejects the transition because `"generated"` is not in the transition map
4. Check the content list in the frontend when backend returns `"ready"` or `"archived"` status
5. **Current behavior:** Status badge may not render correctly or shows raw text

### After Fix (Verify the Solution):
1. Create content through AI generation flow — status should go `draft -> generating -> ready`
2. Transition from `"ready"` to `"published"` — should succeed
3. Transition from `"generating"` to `"failed"` — should succeed
4. Transition from `"failed"` back to `"draft"` — should succeed
5. Frontend content list correctly shows styled badges for all 6 statuses
6. Frontend status filter dropdown shows all 6 options

### Edge Cases:
1. Verify existing content with old status values (`"generated"`, `"scheduled"`, etc.) is handled gracefully
2. Verify the `publish_content()` service method accepts `"ready"` status for publishing
3. Verify `"archived"` content can be un-archived back to `"draft"`

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/unit/services/test_content_service.py -v
```

---

## Acceptance Criteria

- [ ] Backend status transition map includes all 6 unified statuses: `draft`, `generating`, `ready`, `published`, `archived`, `failed`
- [ ] Frontend `ContentStatus` type matches the backend's 6 statuses exactly
- [ ] Frontend `CONTENT_STATUS_CONFIG` has entries for all 6 statuses with proper labels, colors, and icons
- [ ] Content can transition through the full lifecycle: `draft -> generating -> ready -> published`
- [ ] Failed content can be retried: `failed -> draft -> generating`
- [ ] Content can be archived from any terminal state and un-archived
- [ ] No frontend references to removed statuses (`generated`, `scheduled`, `review`, `cancelled`)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Pydantic Enum Validation](https://docs.pydantic.dev/latest/concepts/types/#enums) — for optionally adding an Enum type to the backend schema
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [State Machine Design Patterns](https://refactoring.guru/design-patterns/state) — principles for designing status transitions in domain models
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-160 (B6 — Transaction Boundary Issue introduces `"publish_failed"` which may need to be added to the unified set), TASK-129 (B5 — SubscriptionStatus Enum Mismatch, same pattern in billing domain), TASK-068 (B3 — Frontend-Backend User Type Mismatch, same cross-stack type alignment issue)
