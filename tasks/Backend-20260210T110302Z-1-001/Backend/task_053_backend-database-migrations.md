# Task 053: Remove Unused Imports Across Model Files

## Metadata
- **Task ID:** TASK-053
- **Source:** Backend Database & Migrations Audit (Finding #27 under P3 Low)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

Six model files in the Rext backend import SQLAlchemy types and Python standard library names that are never used within the file. These unused imports create code noise, can confuse developers reading the code, and trigger linter warnings (flake8 F401 / ruff F401). While there is no runtime impact, unused imports are a code quality issue that accumulates technical debt and makes it harder to understand the actual dependencies of each module.

The specific files and their unused imports are:

1. **`roles.py:1-2`** — Imports `ForeignKey`, `UniqueConstraint` from `sqlalchemy` and `JSONB` from `sqlalchemy.dialects.postgresql`, but the `Role` model only uses `Column`, `String`, `Boolean`, `Integer`, `Text`, `TIMESTAMP`, and `UUID`. Neither `ForeignKey`, `UniqueConstraint`, nor `JSONB` appear in the file body.

2. **`permissions.py:1-2`** — Same broad import from `sqlalchemy` includes `Boolean`, `Integer`, `ForeignKey`, `UniqueConstraint`, and `JSONB` from the PostgreSQL dialect, but `Permission` only uses `Column`, `String`, `Text`, `TIMESTAMP`, and `UUID`.

3. **`user_roles.py:2-3`** — Imports `String`, `Integer`, `Text`, `JSONB`, and `INET`, but `UserRole` only uses `Column`, `Boolean`, `TIMESTAMP`, `ForeignKey`, and `UUID`.

4. **`invitations.py:2`** — Imports `Integer`, `Text`, `JSONB`, and `INET`, but `UserInvitations` only uses `Column`, `String`, `Boolean`, `TIMESTAMP`, `ForeignKey`, `UniqueConstraint`, and `UUID`.

5. **`onboarding.py:5`** — Imports `List` from `typing` but never uses it in the module. The `UserOnboarding` model uses `JSON` columns but no `List` type hint.

6. **`workspace_model.py:1`** — Imports `func` from `sqlalchemy` but never uses it. The `WorkspaceModel` uses `Column`, `String`, `DateTime`, `ForeignKey`, and `UUID`.

The project does not currently use a linter like [Ruff](https://docs.astral.sh/ruff/rules/unused-import/) or flake8 to catch these issues automatically. Adding a linting configuration would prevent unused imports from accumulating in the future.

---

## Current Code

```python
# File: rext-backend/src/api/models/user_models/roles.py
# Lines: 1-2
from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
# Unused: ForeignKey, UniqueConstraint, JSONB, Integer (Integer is used for hierarchy_level)
# Actually unused: ForeignKey, UniqueConstraint, JSONB
```

```python
# File: rext-backend/src/api/models/user_models/permissions.py
# Lines: 1-2
from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
# Unused: Boolean, Integer, ForeignKey, UniqueConstraint, JSONB
```

```python
# File: rext-backend/src/api/models/user_models/user_roles.py
# Lines: 2-3
from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
# Unused: String, Integer, Text, JSONB, INET
```

```python
# File: rext-backend/src/api/models/user_models/invitations.py
# Lines: 2
from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
# Unused: Integer, Text, JSONB, INET
```

```python
# File: rext-backend/src/api/models/user_models/onboarding.py
# Line: 5
from typing import List
# Unused: List (never referenced in the module)
```

```python
# File: rext-backend/src/api/models/workspace_models/workspace_model.py
# Line: 1
from sqlalchemy import Column, String, DateTime, func, ForeignKey
# Unused: func (never referenced in the module)
```

---

## Why This Matters (Context & Reasoning)

Unused imports are a common code quality issue that compounds over time. Each unused import:
- Adds cognitive load for developers reading the file (they expect the import to be used)
- Can mask actual dependency issues (a developer might think `ForeignKey` is used in `roles.py` when it isn't)
- Triggers warnings in static analysis tools, creating noise that hides real issues
- Suggests copy-paste development where imports were carried over from a template without trimming

In this codebase, the pattern is clear: models were likely created from a template that included all common SQLAlchemy types, and the unused ones were never cleaned up. This is a quick fix with zero risk of runtime impact.

---

## Impact

- **Severity:** No runtime impact. Code quality and maintainability issue only.
- **Affected Users/Flows:** None directly. Developer experience improvement.
- **Blast Radius:** Isolated to 6 model files. No behavioral changes.

---

## Recommended Solution

Remove the unused imports from each file. Additionally, consider adding Ruff to the project's development dependencies to automatically catch unused imports in the future.

### Step 1: Fix roles.py

```python
# File: rext-backend/src/api/models/user_models/roles.py
# Replace lines 1-2 with:
from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
```

### Step 2: Fix permissions.py

```python
# File: rext-backend/src/api/models/user_models/permissions.py
# Replace lines 1-2 with:
from sqlalchemy import Column, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
```

### Step 3: Fix user_roles.py

```python
# File: rext-backend/src/api/models/user_models/user_roles.py
# Replace lines 2-3 with:
from sqlalchemy import Column, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
```

### Step 4: Fix invitations.py

```python
# File: rext-backend/src/api/models/user_models/invitations.py
# Replace line 2 (and adjust line 3 if INET/JSONB are on it) with:
from sqlalchemy import Column, String, Boolean, TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
```

### Step 5: Fix onboarding.py

```python
# File: rext-backend/src/api/models/user_models/onboarding.py
# Remove line 5 entirely:
# DELETE: from typing import List
```

### Step 6: Fix workspace_model.py

```python
# File: rext-backend/src/api/models/workspace_models/workspace_model.py
# Replace line 1 with:
from sqlalchemy import Column, String, DateTime, ForeignKey
```

### Step 7 (Optional): Add Ruff to development dependencies

```toml
# File: rext-backend/pyproject.toml
# Add to [dependency-groups] dev section:
[dependency-groups]
dev = [
    "pytest>=8.4.2",
    "pytest-asyncio>=1.2.0",
    "factory-boy>=3.3.1",
    "faker>=20.0.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.9.0",
]
```

```toml
# Add Ruff configuration to pyproject.toml:
[tool.ruff]
target-version = "py311"
line-length = 120

[tool.ruff.lint]
select = ["F401"]  # Start with unused imports; expand later
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/models/user_models/role_permissions.py` | 19 | Has `# # Relationships` (double hash comment) — cosmetic issue in same area |
| `rext-backend/alembic/env.py` | 23-29 | Duplicate imports — related issue (TASK-055) |
| Other model files | Various | May have additional unused imports not cataloged in this audit finding — Ruff would catch them |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open `rext-backend/src/api/models/user_models/roles.py` and note `ForeignKey`, `UniqueConstraint`, `JSONB` are imported but not used in the file
2. If Ruff is installed: run `ruff check rext-backend/src/api/models/user_models/roles.py` — observe F401 warnings

### After Fix (Verify the Solution):
1. Open each modified file and verify only used imports remain
2. Run the application: `cd rext-backend && python -c "from src.api.models.user_models.roles import Role; print('OK')"` — should print OK without ImportError
3. Repeat for all modified models
4. If Ruff was added: run `ruff check rext-backend/src/api/models/` — should report no F401 violations for the fixed files

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v --no-header
```

---

## Acceptance Criteria

- [ ] `roles.py` imports only `Column`, `String`, `Boolean`, `Integer`, `Text`, `TIMESTAMP` from sqlalchemy and `UUID` from postgresql dialect
- [ ] `permissions.py` imports only `Column`, `String`, `Text`, `TIMESTAMP` from sqlalchemy and `UUID` from postgresql dialect
- [ ] `user_roles.py` imports only `Column`, `Boolean`, `TIMESTAMP`, `ForeignKey` from sqlalchemy and `UUID` from postgresql dialect
- [ ] `invitations.py` no longer imports `Integer`, `Text`, `JSONB`, `INET`
- [ ] `onboarding.py` no longer imports `List` from `typing`
- [ ] `workspace_model.py` no longer imports `func` from `sqlalchemy`
- [ ] All model files still import correctly (no `ImportError` at runtime)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Ruff — unused-import (F401)](https://docs.astral.sh/ruff/rules/unused-import/) — Ruff's documentation for the F401 unused import rule, including auto-fix support
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Flake8 Rules — F401](https://www.flake8rules.com/rules/F401.html) — Standard Python linting rule for detecting unused imports
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-026 (Unused Import `os` in Auth Routes — same type of issue in B1), TASK-055 (Alembic env.py duplicate imports — related cleanup)
