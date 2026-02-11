# Task 110: Replace Hardcoded Magic Numbers with Named Constants

## Metadata
- **Task ID:** TASK-110
- **Source:** B4 - Workspace Management (Finding #17 under P2 Medium)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

Two hardcoded numeric literals ("magic numbers") are embedded directly in the workspace management code without descriptive names. In `src/services/workspace_service.py` at line 465, the value `200` is used as a words-per-minute constant to estimate reading time: `estimated_reading_time = total_words // 200`. In `src/services/workspace_pipeline.py` at line 41 (now a class attribute `_MAX_BRAND_VOICE_CHARS = 5_000`), the value `5_000` is used to limit the character count of scraped content sent to the LLM for brand voice extraction.

While the pipeline class already defines `_MAX_BRAND_VOICE_CHARS` as a class-level constant (which is a step in the right direction), the words-per-minute value in `workspace_service.py` remains an inline literal. This same magic number `200` appears in two other locations across the codebase: `src/api/tool/tools.py:59` where it's used as `round(word_count / 200)`, and `src/api/models/knowledge_models/knowledge_model.py:113` where it's used as `(self.word_count or 0) // 200`. Having the same literal scattered across three files means that if the reading speed estimate needs adjustment, a developer must find and update all occurrences manually — a process prone to inconsistency and bugs.

PEP 8 prescribes that constants should be "defined on a module level and written in all capital letters with underscores separating words." Replacing magic numbers with named constants makes the code self-documenting, centralizes configuration, and reduces the risk of inconsistent updates.

---

## Current Code

```python
# File: rext-backend/src/services/workspace_service.py
# Line: 465
            estimated_reading_time = total_words // 200
```

```python
# File: rext-backend/src/api/tool/tools.py
# Line: 59
    min_read = max(1, round(word_count / 200)) if word_count > 0 else 0
```

```python
# File: rext-backend/src/api/models/knowledge_models/knowledge_model.py
# Line: 113
            'estimated_reading_time': (self.word_count or 0) // 200  # ~200 WPM
```

```python
# File: rext-backend/src/services/workspace_pipeline.py
# Line: 41 (already a class constant, but could be centralized)
    _MAX_BRAND_VOICE_CHARS = 5_000
```

---

## Why This Matters (Context & Reasoning)

The words-per-minute constant directly affects user-facing analytics displayed on the workspace dashboard. The reading time estimate is returned as part of `content_metrics` in the analytics response and is shown to users to help them understand how much knowledge content their workspace has. If this constant is wrong or needs updating (e.g., adjusting for different content types or audience reading levels), having it scattered across three files as an unnamed literal makes the update error-prone.

The `_MAX_BRAND_VOICE_CHARS` limit determines how much scraped web content is fed to the LLM during workspace onboarding. This directly affects the quality of brand voice extraction — too little content may produce inaccurate brand voice profiles, too much may waste tokens and increase latency. While it's already a class attribute, centralizing it with other pipeline configuration would make it easier to tune.

---

## Impact

- **Severity:** Low operational risk, but high maintainability cost. If the words-per-minute value is changed in one file but not others, different parts of the application will show inconsistent reading time estimates.
- **Affected Users/Flows:** Workspace analytics display, content metrics, brand voice extraction pipeline.
- **Blast Radius:** Three files use the `200` WPM constant. The `5_000` char limit is isolated to the pipeline class.

---

## Recommended Solution

### Step 1: Create a shared constants module for content-related constants

```python
# File: rext-backend/src/utils/constants.py
# Add these constants (create file if it doesn't exist, or add to existing):

# Average adult reading speed in words per minute.
# Used for estimated reading time calculations across the application.
# Source: https://scholarwithin.com/average-reading-speed
WORDS_PER_MINUTE = 200

# Maximum number of characters from scraped web content sent to the LLM
# for brand voice extraction during workspace onboarding.
MAX_BRAND_VOICE_CONTENT_CHARS = 5_000
```

### Step 2: Update `workspace_service.py` to use the named constant

```python
# File: rext-backend/src/services/workspace_service.py
# Add import near the top (after other utility imports, around line 50):
from src.utils.constants import WORDS_PER_MINUTE

# Replace line 465:
# Before:
#             estimated_reading_time = total_words // 200
# After:
            estimated_reading_time = total_words // WORDS_PER_MINUTE
```

### Step 3: Update `workspace_pipeline.py` to use the shared constant

```python
# File: rext-backend/src/services/workspace_pipeline.py
# Add import near the top (after other imports):
from src.utils.constants import MAX_BRAND_VOICE_CONTENT_CHARS

# Replace line 41 in the class body:
# Before:
#     _MAX_BRAND_VOICE_CHARS = 5_000
# After:
    _MAX_BRAND_VOICE_CHARS = MAX_BRAND_VOICE_CONTENT_CHARS
```

### Step 4: Update `tools.py` to use the named constant

```python
# File: rext-backend/src/api/tool/tools.py
# Add import near the top:
from src.utils.constants import WORDS_PER_MINUTE

# Replace line 59:
# Before:
#     min_read = max(1, round(word_count / 200)) if word_count > 0 else 0
# After:
    min_read = max(1, round(word_count / WORDS_PER_MINUTE)) if word_count > 0 else 0
```

### Step 5: Update `knowledge_model.py` to use the named constant

```python
# File: rext-backend/src/api/models/knowledge_models/knowledge_model.py
# Add import near the top:
from src.utils.constants import WORDS_PER_MINUTE

# Replace line 113:
# Before:
#             'estimated_reading_time': (self.word_count or 0) // 200  # ~200 WPM
# After:
            'estimated_reading_time': (self.word_count or 0) // WORDS_PER_MINUTE
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/tool/tools.py` | `59` | Same `200` WPM magic number used for reading time estimate |
| `src/api/models/knowledge_models/knowledge_model.py` | `113` | Same `200` WPM magic number in model serialization |

---

## Testing Instructions

### Before Fix (Confirm the Issue):
1. Search the codebase for `// 200` and `/ 200` to confirm three occurrences of the magic number
2. Verify that no named constant exists for words-per-minute

### After Fix (Verify the Solution):
1. Verify `src/utils/constants.py` exists with `WORDS_PER_MINUTE = 200` and `MAX_BRAND_VOICE_CONTENT_CHARS = 5_000`
2. Search the codebase for `// 200` and `/ 200` — there should be zero occurrences in Python files (excluding the constant definition itself)
3. Verify each updated file imports and uses the named constant
4. Call the workspace analytics endpoint and verify reading time calculations are unchanged

### Run Existing Tests:
```bash
cd rext-backend
python -m pytest tests/ -x -q
```

---

## Acceptance Criteria

- [ ] A `WORDS_PER_MINUTE` constant is defined in a shared constants module
- [ ] A `MAX_BRAND_VOICE_CONTENT_CHARS` constant is defined in a shared constants module
- [ ] All three occurrences of the `200` magic number reference the named constant
- [ ] The `_MAX_BRAND_VOICE_CHARS` class attribute references the shared constant
- [ ] Reading time calculations produce identical results before and after the change
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [PEP 8 — Naming Conventions: Constants](https://peps.python.org/pep-0008/#constants) — "Constants are usually defined on a module level and written in all capital letters with underscores separating words"
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Replace Magic Number with Symbolic Constant — Refactoring Guru](https://refactoring.guru/replace-magic-number-with-symbolic-constant)
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** None
