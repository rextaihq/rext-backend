# Task 188: Break Very Long Lines in content_service.py

## Metadata
- **Task ID:** TASK-188
- **Source:** Backend Content Management Audit (Finding #34 under P3 Low)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

Several lines in `src/services/content_service.py` significantly exceed reasonable line length limits, reducing readability and making code review more difficult. The project does not have an explicit line-length configuration in `pyproject.toml` (no Ruff, Black, or Flake8 settings are defined), but the Python community standard (PEP 8) recommends 79 characters, and modern formatters like Black and Ruff default to 88 characters. Even with a generous 120-character limit, at least 9 lines in this file exceed that threshold.

The worst offenders are:

1. **Line 143** (157 chars): A `for` loop iterating over a long list of field name strings, all on one line.
2. **Line 155** (161 chars): Another `for` loop with 10 SEO field names in a single-line list.
3. **Line 168** (139 chars): A `ContentMedia` constructor call with four keyword arguments on one line.
4. **Line 181** (152 chars): A `select()` query with `.where()` and `.options()` chained on one line.
5. **Line 184** (148 chars): A `count_query` with `select(func.count()).select_from().where()` all chained.
6. **Line 188** (162 chars): A query execution with `.order_by().offset().limit().scalars().all()` chained.
7. **Line 219** (140 chars): A slug uniqueness query with three `.where()` conditions.
8. **Line 225** (140 chars): A content lookup query with three `.where()` conditions.
9. **Line 232** (177 chars): A status transition dictionary with all allowed transitions on one line.

Long lines force horizontal scrolling, make diff reviews harder, and reduce readability on standard-width terminals and side-by-side editor panes. Breaking these into multi-line statements with proper indentation improves clarity and maintainability.

---

## Current Code

```python
# File: src/services/content_service.py
# Line: 143
        for field in ["content_language", "introduction", "body_markdown", "body_html", "tags", "images_data", "links_data", "schema_markup", "langgraph_thread_id"]:
```

```python
# File: src/services/content_service.py
# Line: 155
            for field in ["meta_title", "meta_description", "focus_keyphrase", "keyphrase_density", "secondary_keywords", "search_intent", "seo_score", "readability_score", "trust_score", "seo_details"]:
```

```python
# File: src/services/content_service.py
# Line: 168
                self.db.add(ContentMedia(content_id=content.id, media_id=item.media_id, usage_type=item.usage_type, position=item.position))
```

```python
# File: src/services/content_service.py
# Line: 181
        query = select(Content).where(Content.workspace_id == workspace_id, Content.deleted_at == None).options(selectinload(Content.seo_data))
```

```python
# File: src/services/content_service.py
# Line: 232
        ALLOWED = {"generating": ["ready", "archived", "draft"], "draft": ["ready", "archived", "generating"], "ready": ["published", "draft", "archived", "generating"], "published": ["archived", "ready"], "archived": []}
```

---

## Why This Matters (Context & Reasoning)

`content_service.py` is the central business logic layer for the content management feature. It handles content creation, updates, deletion, listing, and publishing. Developers will frequently read and modify this file. Lines that extend to 150-177 characters are difficult to parse at a glance, especially during code review in GitHub's diff view (which wraps at ~120 characters) or when using a side-by-side editor layout.

Formatting this file with reasonable line lengths improves developer experience, reduces the chance of bugs introduced during modifications (it's easier to miss issues in dense single-line code), and prepares the codebase for adopting an automated formatter like Ruff or Black in the future.

---

## Impact

- **Severity:** No runtime impact — purely a readability improvement.
- **Affected Users/Flows:** No user-facing impact. Improves developer experience.
- **Blast Radius:** Isolated to `src/services/content_service.py`. No functional change.

---

## Recommended Solution

### Step 1: Break field name lists onto multiple lines (lines 143 and 155)

```python
# File: src/services/content_service.py
# Replace line 143 with:
        updatable_fields = [
            "content_language", "introduction", "body_markdown",
            "body_html", "tags", "images_data", "links_data",
            "schema_markup", "langgraph_thread_id",
        ]
        for field in updatable_fields:
```

```python
# File: src/services/content_service.py
# Replace line 155 with:
            seo_fields = [
                "meta_title", "meta_description", "focus_keyphrase",
                "keyphrase_density", "secondary_keywords", "search_intent",
                "seo_score", "readability_score", "trust_score", "seo_details",
            ]
            for field in seo_fields:
```

### Step 2: Break ContentMedia constructor (line 168)

```python
# File: src/services/content_service.py
# Replace line 168 with:
                self.db.add(ContentMedia(
                    content_id=content.id,
                    media_id=item.media_id,
                    usage_type=item.usage_type,
                    position=item.position,
                ))
```

### Step 3: Break query chains onto multiple lines (lines 181, 184, 188)

```python
# File: src/services/content_service.py
# Replace lines 181-188 of list_content() with:
        query = (
            select(Content)
            .where(
                Content.workspace_id == workspace_id,
                Content.deleted_at == None,
            )
            .options(selectinload(Content.seo_data))
        )
        if status:
            query = query.where(Content.status == status)

        count_query = (
            select(func.count())
            .select_from(Content)
            .where(
                Content.workspace_id == workspace_id,
                Content.deleted_at == None,
            )
        )
        if status:
            count_query = count_query.where(Content.status == status)

        total_count = (await self.db.execute(count_query)).scalar()
        result = await self.db.execute(
            query.order_by(Content.created_at.desc()).offset(offset).limit(limit)
        )
        items = result.scalars().all()
```

### Step 4: Break slug query (line 219)

```python
# File: src/services/content_service.py
# Replace line 219 with:
            query = select(Content).where(
                Content.workspace_id == workspace_id,
                Content.slug == slug,
                Content.deleted_at == None,
            )
```

### Step 5: Break content lookup query (line 225)

```python
# File: src/services/content_service.py
# Replace line 225 with:
        query = select(Content).where(
            Content.id == content_id,
            Content.workspace_id == workspace_id,
            Content.deleted_at == None,
        )
```

### Step 6: Break status transition dictionary (line 232)

```python
# File: src/services/content_service.py
# Replace line 232 with:
        ALLOWED = {
            "generating": ["ready", "archived", "draft"],
            "draft": ["ready", "archived", "generating"],
            "ready": ["published", "draft", "archived", "generating"],
            "published": ["archived", "ready"],
            "archived": [],
        }
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/content_service.py` | `135` | Another long line (slug generation + title update) — consider breaking |
| `src/api/routes/content/modules/publish_content.py` | Various | Some long lines in query chains, but less severe |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open `src/services/content_service.py` and observe lines 143, 155, 168, 181, 184, 188, 219, 225, 232 — all exceed 120 characters.

### After Fix (Verify the Solution):
1. Confirm all modified lines are under 120 characters.
2. Verify the file still has correct Python syntax by importing it: `python -c "from src.services.content_service import ContentService"`
3. Run the test suite to confirm no behavioral changes.

### Run Existing Tests:
```bash
cd rext-backend
python -m pytest tests/unit/services/test_content_service.py -v
```

---

## Acceptance Criteria

- [ ] All lines in `content_service.py` are under 120 characters
- [ ] Field name lists are extracted into named variables for readability
- [ ] Query chains are broken across multiple lines with consistent formatting
- [ ] Status transition dictionary is formatted as a multi-line dictionary
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [PEP 8 — Maximum Line Length](https://peps.python.org/pep-0008/#maximum-line-length) — Recommends 79 characters for code
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Ruff E501 — Line Too Long](https://docs.astral.sh/ruff/rules/line-too-long/) — Ruff defaults to 88 characters, aligning with Black
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** None — this is an isolated formatting task
