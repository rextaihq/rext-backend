# Task 098: Unify `content_pillar` / `content_strategy` Field Name Mismatch Across Backend

## Metadata
- **Task ID:** TASK-098
- **Source:** Backend Workspace Management (Finding #13 under P1 High)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The brand voice data model uses two different names for the same concept — `content_pillar` and `content_strategy` — across different layers of the backend, creating a confusing mapping layer that is error-prone and has already led to defensive fallback code.

The current state of the field naming across the codebase:

1. **Pydantic schema (`BrandSchema`):** Uses `content_pillar` (line 87 in `src/api/schema/knowledge_schema.py`). This schema is used as the structured output format for LLM extraction and as the API request body for brand voice updates.

2. **Database column / ORM model (`BrandVoice`):** Uses `content_strategy` as the column name. The `workspace_pipeline.py` explicitly bridges this gap with `data.get("content_pillar")` stored into `content_strategy` (lines 342, 353).

3. **Service layer:** `workspace_service.py:1078` accesses `brand_data.content_pillar` and maps it to `content_strategy=`. The `brand_voice_service.py:222` has a defensive fallback: `data.get("content_strategy") or data.get("content_pillar")`.

4. **API serialization:** `workspace_brand_voice.py:30` serializes the field as `content_strategy` in API responses.

5. **Background task:** `knowledge_task.py:68` accesses `brand_data.content_pillar` and maps to `content_strategy=`.

6. **Tests:** `test_brand_voice_service.py:106,152` use `content_pillar` in BrandSchema construction, then assert `brand_voice.content_strategy == payload.content_pillar`. `test_workspace_pipeline.py:71` uses `content_pillar`. `test_workspace_brand_voice_routes.py:96,132` uses `content_pillar`.

Per the audit report's recommendation (and the user's decision to unify to frontend names), the backend should standardize on `content_strategy` everywhere — renaming the `BrandSchema.content_pillar` field to `content_strategy`. This eliminates all the bridging/mapping code and makes the field name consistent across schema, ORM, service, and API layers.

---

## Current Code

```python
# File: src/api/schema/knowledge_schema.py
# Lines: 87-91
    content_pillar: List[str] = Field(
        default_factory=list,
        description="Main content themes or pillars",
        example=["Sustainability", "Fashion Trends", "Eco-lifestyle"]
    )
```

```python
# File: src/services/workspace_pipeline.py
# Lines: 342, 353 (bridging code)
                existing.content_strategy = data.get("content_pillar") or []
                # ... and in the create path:
                    content_strategy=data.get("content_pillar") or [],
```

```python
# File: src/services/workspace_service.py
# Line: 1078
                content_strategy=brand_data.content_pillar,
```

```python
# File: src/services/brand_voice_service.py
# Line: 222 (defensive fallback)
            "content_strategy": data.get("content_strategy") or data.get("content_pillar"),
```

```python
# File: src/api/tasks/knowledge_task.py
# Line: 68
                content_strategy=brand_data.content_pillar
```

---

## Why This Matters (Context & Reasoning)

The brand voice feature is a core part of the Rext AI product — it extracts and stores brand identity data from a user's website to guide AI content generation. The `content_strategy` / `content_pillar` field stores the main content themes that the AI uses to generate relevant content. Having two names for the same field creates several problems:

1. **Developer confusion:** New developers won't know whether to use `content_pillar` or `content_strategy`. The defensive fallback in `brand_voice_service.py` (`data.get("content_strategy") or data.get("content_pillar")`) is a code smell that suggests even the original developers were uncertain.

2. **Data misalignment risk:** If any code path forgets to do the mapping (using `data.get("content_strategy")` instead of `data.get("content_pillar")`), the data will silently be `None` or an empty list.

3. **LLM output dependency:** The `BrandSchema` is used as the Pydantic structured output format for the LLM. Changing the field name in the schema changes what the LLM is instructed to produce. Since the database stores `content_strategy`, aligning the schema to the same name eliminates the mapping entirely.

---

## Impact

- **Severity:** Confusing naming leads to subtle bugs when code uses the wrong field name. The defensive fallback in `brand_voice_service.py` masks these bugs rather than surfacing them.
- **Affected Users/Flows:** Brand voice extraction pipeline, brand voice API endpoints, any code that reads or writes the content strategy field.
- **Blast Radius:** Touches the schema, pipeline service, workspace service, brand voice service, knowledge task, and multiple test files. However, it's a straightforward rename with no behavioral changes.

---

## Recommended Solution

### Step 1: Rename `content_pillar` to `content_strategy` in BrandSchema

```python
# File: src/api/schema/knowledge_schema.py
# Replace lines 87-91 with:
    content_strategy: List[str] = Field(
        default_factory=list,
        description="Main content strategy themes or pillars",
        example=["Sustainability", "Fashion Trends", "Eco-lifestyle"]
    )
```

### Step 2: Update workspace_pipeline.py to use `content_strategy` directly

```python
# File: src/services/workspace_pipeline.py
# Replace line 342 with:
                existing.content_strategy = data.get("content_strategy") or []

# Replace line 353 with:
                    content_strategy=data.get("content_strategy") or [],
```

### Step 3: Update workspace_service.py to use `content_strategy`

```python
# File: src/services/workspace_service.py
# Replace line 1078 with:
                content_strategy=brand_data.content_strategy,
```

### Step 4: Remove the defensive fallback in brand_voice_service.py

```python
# File: src/services/brand_voice_service.py
# Replace line 222 with:
            "content_strategy": data.get("content_strategy"),
```

### Step 5: Update knowledge_task.py

```python
# File: src/api/tasks/knowledge_task.py
# Replace line 68 with:
                content_strategy=brand_data.content_strategy
```

### Step 6: Update test files

```python
# File: tests/unit/services/test_brand_voice_service.py
# Replace line 106:
        content_strategy=["Education", "Enablement"],
# Replace line 120:
    assert brand_voice.content_strategy == payload.content_strategy
# Replace line 152:
        content_strategy=["How-to", "Guides"],
# Replace line 163:
    assert updated.content_strategy == payload.content_strategy
```

```python
# File: tests/unit/services/test_workspace_pipeline.py
# Replace line 71:
            content_strategy=["Pillar"],
```

```python
# File: tests/unit/routes/test_workspace_brand_voice_routes.py
# Replace line 96:
        "content_strategy": ["Strategy"],
# Replace line 132:
    assert brand_data.content_strategy == ["Strategy"]
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/schema/knowledge_schema.py` | `87` | Primary change — rename the field in BrandSchema |
| `src/services/workspace_pipeline.py` | `342, 353` | Remove `content_pillar` bridging, use `content_strategy` directly |
| `src/services/workspace_service.py` | `1078` | Change `brand_data.content_pillar` to `brand_data.content_strategy` |
| `src/services/brand_voice_service.py` | `222` | Remove defensive fallback |
| `src/api/tasks/knowledge_task.py` | `68` | Change `brand_data.content_pillar` to `brand_data.content_strategy` |
| `src/api/routes/workspaces/workspace_brand_voice.py` | `30` | Already uses `content_strategy` — no change needed |
| `tests/unit/services/test_brand_voice_service.py` | `106, 120, 152, 163` | Update test assertions |
| `tests/unit/services/test_workspace_pipeline.py` | `71` | Update test data |
| `tests/unit/routes/test_workspace_brand_voice_routes.py` | `96, 132` | Update test data and assertions |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Examine the BrandSchema: `content_pillar` is the field name.
2. Create a brand voice via the pipeline and inspect the database: `content_strategy` is the column name.
3. Note the confusing mapping in `workspace_pipeline.py:342` where `data.get("content_pillar")` is stored into `content_strategy`.

### After Fix (Verify the Solution):
1. Run the brand voice extraction pipeline for a workspace.
2. Verify that the LLM structured output uses `content_strategy` (check pipeline debug logs).
3. Verify the `content_strategy` column in the database is correctly populated.
4. Call `GET /workspaces/{id}/brand-voice` and verify `content_strategy` is present in the response.
5. Call `PUT /workspaces/{id}/brand-voice` with `{"content_strategy": ["Theme1", "Theme2"]}` and verify it is saved correctly.
6. Verify that `content_pillar` is no longer accepted or referenced anywhere.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/services/test_brand_voice_service.py -v
cd rext-backend && python -m pytest tests/unit/services/test_workspace_pipeline.py -v
cd rext-backend && python -m pytest tests/unit/routes/test_workspace_brand_voice_routes.py -v
```

---

## Acceptance Criteria

- [ ] `BrandSchema.content_pillar` renamed to `BrandSchema.content_strategy`
- [ ] All `data.get("content_pillar")` calls replaced with `data.get("content_strategy")`
- [ ] All `brand_data.content_pillar` attribute accesses replaced with `brand_data.content_strategy`
- [ ] Defensive fallback in `brand_voice_service.py` removed (no more `or data.get("content_pillar")`)
- [ ] All test files updated to use `content_strategy`
- [ ] No occurrences of `content_pillar` remain in the backend source code (excluding test output files and audit reports)
- [ ] LLM structured output schema uses `content_strategy` field name
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Pydantic V2 — Field Aliases](https://docs.pydantic.dev/latest/concepts/fields/#field-aliases) — if backward compatibility is needed, Pydantic field aliases can accept both names during a transition period (not recommended here since a clean rename is preferred)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [LangChain — Structured Output](https://python.langchain.com/docs/how_to/structured_output/) — the field names in the Pydantic schema directly control the JSON keys the LLM produces; consistent naming is critical for reliable extraction
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-004 (Deprecated datetime.utcnow() from B1), TASK-079 (datetime.utcnow() from B3) — similar pattern of codebase-wide naming/API consistency issues
