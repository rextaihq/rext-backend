# Task 163: Test File Has Import Error — ContentSEODataSchema Not Imported

## Metadata
- **Task ID:** TASK-163
- **Source:** B6 - Content Management (Finding #10 under P1 High)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

The content service test file at `rext-backend/tests/unit/services/test_content_service.py` references `ContentSEODataSchema` on line 74 inside the `test_create_content_with_all_fields` test method, but this schema class is never imported. The import block at lines 19-22 imports `ContentCreate` and `ContentUpdate` from `src.api.schema.content_schema`, but omits `ContentSEODataSchema`.

The test constructs a `ContentCreate` object with `seo_data=ContentSEODataSchema(...)` on line 74, which will fail with `NameError: name 'ContentSEODataSchema' is not defined` at test collection time. This means the entire `TestContentServiceCreate` test class cannot run, causing pytest to report a collection error for this test module.

Looking at the actual schema file (`src/api/schema/content_schema.py`), `ContentSEODataSchema` is defined at lines 21-33 and is a valid Pydantic `BaseModel` with fields like `meta_title`, `meta_description`, `focus_keyphrase`, and `trust_score`. It is properly used in the `ContentCreate` schema (line 53: `seo_data: Optional[ContentSEODataSchema] = None`), so the test is correct in its intent — it just forgot the import.

This is a straightforward missing import that prevents a critical test from running. The test `test_create_content_with_all_fields` is intended to verify that content creation with SEO data works end-to-end, which is an important business flow.

---

## Current Code

```python
# File: rext-backend/tests/unit/services/test_content_service.py
# Lines: 18-22 (imports)
from src.services.content_service import ContentService
from src.api.schema.content_schema import (
    ContentCreate,
    ContentUpdate,
)
```

```python
# File: rext-backend/tests/unit/services/test_content_service.py
# Lines: 69-81 (usage of undefined ContentSEODataSchema)
        content_data = ContentCreate(
            title="Complete Article",
            body_markdown="# Full Content",
            status="draft",
            content_language="Spanish",
            seo_data=ContentSEODataSchema(  # <-- NameError: not imported
                meta_title="SEO Title",
                meta_description="SEO Description",
                focus_keyphrase="keyphrase",
                trust_score=0.95
            ),
            tags=["tag1", "tag2"]
        )
```

---

## Why This Matters (Context & Reasoning)

This test file is the primary unit test suite for `ContentService`, which handles all content CRUD operations. The broken test (`test_create_content_with_all_fields`) specifically validates that content creation with nested SEO data works correctly — a core business flow since SEO optimization is a key feature of Rext AI.

With this import missing, pytest will fail to collect the entire test module (or at minimum the test class containing this test), effectively disabling all content service tests. This creates a false sense of confidence if CI is configured to pass with zero collected tests from this module, or causes CI failures that may be ignored as "known broken tests."

---

## Impact

- **Severity:** The entire content service test suite is non-functional. Any regressions in content creation, update, or deletion logic go undetected by unit tests.
- **Affected Users/Flows:** Development team — inability to validate content service behavior through automated tests.
- **Blast Radius:** Isolated to the test file. Does not affect production code, but significantly undermines test coverage for the content management domain.

---

## Recommended Solution

### Step 1: Add ContentSEODataSchema to the import statement

```python
# File: rext-backend/tests/unit/services/test_content_service.py
# Replace lines 19-22 with:
from src.api.schema.content_schema import (
    ContentCreate,
    ContentUpdate,
    ContentSEODataSchema,
)
```

This is the only change needed. The `ContentSEODataSchema` class is already defined in `src/api/schema/content_schema.py` at line 21 and is a standard Pydantic BaseModel.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `tests/unit/services/test_content_service.py` | `96-98` | Same test also has incorrect assertion paths — see TASK-164 |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Navigate to the backend directory: `cd rext-backend`
2. Run the content service tests:
   ```bash
   python -m pytest tests/unit/services/test_content_service.py -v
   ```
3. Observe that the test module fails to collect with a `NameError` referencing `ContentSEODataSchema`

### After Fix (Verify the Solution):
1. Run the content service tests again:
   ```bash
   python -m pytest tests/unit/services/test_content_service.py -v
   ```
2. Verify that the `test_create_content_with_all_fields` test is now collected (may still fail due to TASK-164 assertion issues, but should not fail at collection)
3. Verify that all other tests in the module also run correctly

### Run Existing Tests:
```bash
cd rext-backend
python -m pytest tests/unit/services/test_content_service.py -v --tb=short
```

---

## Acceptance Criteria

- [ ] `ContentSEODataSchema` is imported from `src.api.schema.content_schema` in the test file
- [ ] `test_create_content_with_all_fields` test is collected by pytest (no `NameError`)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [pytest — How to write and report assertions in tests](https://docs.pytest.org/en/stable/how-to/assert.html)
- **Official Docs:** [pytest — Good Integration Practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html) — Guidance on test imports with src layout
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Pydantic v2 Models Documentation](https://docs.pydantic.dev/latest/concepts/models/) — Confirms the schema pattern used
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** TASK-164 (Test assertions reference wrong attributes — fixing the import is prerequisite to even reaching the assertion lines)
- **Related:** TASK-164 (same test has wrong assertion paths for SEO data attributes)
