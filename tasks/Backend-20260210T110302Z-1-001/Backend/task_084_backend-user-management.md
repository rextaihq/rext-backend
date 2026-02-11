# Task 084: Move Inline Pydantic Schemas from Preferences Route to Shared Schema File

## Metadata
- **Task ID:** TASK-084
- **Source:** B3 - User Management (Finding #26 under P2 Medium)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `src/api/routes/users/preferences.py` file defines two Pydantic schemas inline — `UserPreferencesResponse` (lines 24-34) and `UpdateUserPreferencesRequest` (lines 37-43) — directly within the route module rather than in a dedicated schema file under `src/api/schema/`. Every other route module in the project follows the convention of importing schemas from the shared `src/api/schema/` directory (e.g., `user_schema.py`, `onboarding_schemas.py`, `notification_schema.py`, `session_schema.py`, etc.), making this the sole exception to the project's architectural pattern.

This inconsistency has several consequences. First, these schemas are not discoverable alongside the rest of the project's API contract definitions, making it harder for developers to find and reason about the full set of request/response schemas. Second, if any other route or service needs to reference `UserPreferencesResponse` or `UpdateUserPreferencesRequest`, it would need to import from a route file rather than a schema file, which inverts the dependency hierarchy (routes should depend on schemas, not the other way around). Third, tools that generate API documentation or frontend TypeScript types from Pydantic models typically scan the `schema/` directory — inline schemas in route files may be missed. According to FastAPI best practices, schemas should be organized in dedicated files separated from routing logic to maintain clear boundaries between concerns and support consistent API documentation generation.

The fix involves creating a new `src/api/schema/preferences_schema.py` file, moving both schema classes there, and updating the import in `preferences.py`.

---

## Current Code

```python
# File: rext-backend/src/api/routes/users/preferences.py
# Lines: 7-43
from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from pydantic import BaseModel, Field
from typing import Optional

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import require_permissions
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.utils.logger import logger
from src.services.user_preferences_service import UserPreferencesService

router = APIRouter()


class UserPreferencesResponse(BaseModel):
    """User preferences response schema"""
    id: str
    user_id: str
    theme: Optional[str] = "system"
    date_format: Optional[str] = "iso"
    time_format: Optional[str] = "24h"
    items_per_page: Optional[int] = 25
    sidebar_collapsed: Optional[bool] = False
    created_at: str
    updated_at: str


class UpdateUserPreferencesRequest(BaseModel):
    """Update user preferences request schema"""
    theme: Optional[str] = Field(None, pattern="^(system|light|dark)$")
    date_format: Optional[str] = Field(None, pattern="^(iso|us|eu|relative)$")
    time_format: Optional[str] = Field(None, pattern="^(24h|12h)$")
    items_per_page: Optional[int] = Field(None, ge=10, le=100)
    sidebar_collapsed: Optional[bool] = None
```

---

## Why This Matters (Context & Reasoning)

The preferences route handles user-specific UI settings (theme, date format, time format, items per page, sidebar state). These schemas define the API contract for reading and updating preferences. Having them inline in the route file breaks the established project convention where all API schemas live in `src/api/schema/`. This convention exists to:

1. Keep route files focused on request handling logic, not data modeling.
2. Enable schema reuse across routes, services, and tests.
3. Support automated tooling (OpenAPI doc generation, type exports) that scans the schema directory.
4. Maintain a single source of truth for the API contract.

If not fixed, this inconsistency will likely propagate as new developers copy the pattern, leading to schemas scattered across route files instead of centralized in the schema directory.

---

## Impact

- **Severity:** Schema definitions are not centralized, reducing discoverability and breaking the project's established architecture pattern. No runtime impact.
- **Affected Users/Flows:** Developers working on preferences-related features or API documentation/type generation tooling.
- **Blast Radius:** Isolated to `preferences.py` and any future consumers of these schemas.

---

## Recommended Solution

### Step 1: Create the new schema file

```python
# File: rext-backend/src/api/schema/preferences_schema.py
"""
Pydantic schemas for user preferences endpoints.

Defines request and response models for the preferences API,
following the project convention of centralized schema definitions.
"""

from typing import Optional

from pydantic import BaseModel, Field


class UserPreferencesResponse(BaseModel):
    """User preferences response schema"""
    id: str
    user_id: str
    theme: Optional[str] = "system"
    date_format: Optional[str] = "iso"
    time_format: Optional[str] = "24h"
    items_per_page: Optional[int] = 25
    sidebar_collapsed: Optional[bool] = False
    created_at: str
    updated_at: str


class UpdateUserPreferencesRequest(BaseModel):
    """Update user preferences request schema"""
    theme: Optional[str] = Field(None, pattern="^(system|light|dark)$")
    date_format: Optional[str] = Field(None, pattern="^(iso|us|eu|relative)$")
    time_format: Optional[str] = Field(None, pattern="^(24h|12h)$")
    items_per_page: Optional[int] = Field(None, ge=10, le=100)
    sidebar_collapsed: Optional[bool] = None
```

### Step 2: Update imports in the preferences route

```python
# File: rext-backend/src/api/routes/users/preferences.py
# Replace lines 1-21 with:
"""
User Preferences API endpoints.

This module provides endpoints for managing user-specific preferences.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import require_permissions
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.schema.preferences_schema import UserPreferencesResponse, UpdateUserPreferencesRequest
from src.utils.logger import logger
from src.services.user_preferences_service import UserPreferencesService

router = APIRouter()
```

### Step 3: Remove the inline schema class definitions

Delete the `UserPreferencesResponse` and `UpdateUserPreferencesRequest` class definitions from `preferences.py` (lines 24-43). The route endpoints (`get_user_preferences` at line 46 and `update_user_preferences` at line 77) remain unchanged since they reference the schemas by the same names.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/routes/users/preferences.py` | `7, 10, 24-43` | Remove unused `HTTPException`, `status`, `BaseModel`, `Field`, `Optional` imports that are only needed for inline schemas; remove inline schema classes |
| `rext-backend/src/services/user_preferences_service.py` | All | Service that the preferences route calls — no changes needed, but verify it still works after the refactor |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Confirm the schemas are defined inline: open `rext-backend/src/api/routes/users/preferences.py` and observe `UserPreferencesResponse` and `UpdateUserPreferencesRequest` class definitions within the file.
2. Confirm no `preferences_schema.py` exists in `rext-backend/src/api/schema/`.

### After Fix (Verify the Solution):
1. Confirm `rext-backend/src/api/schema/preferences_schema.py` exists with both schema classes.
2. Confirm `rext-backend/src/api/routes/users/preferences.py` imports from `src.api.schema.preferences_schema` and no longer defines schemas inline.
3. Start the application and test the preferences endpoints:
   ```bash
   # GET preferences
   curl -H "Authorization: Bearer <token>" http://localhost:8000/api/users/preferences
   # PATCH preferences
   curl -X PATCH -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
     -d '{"theme": "dark"}' http://localhost:8000/api/users/preferences
   ```
4. Verify both endpoints return the same response format as before.
5. Check that `/docs` (Swagger UI) still shows the correct schema for these endpoints.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "preferences" -v
```

---

## Acceptance Criteria

- [ ] New file `src/api/schema/preferences_schema.py` exists with `UserPreferencesResponse` and `UpdateUserPreferencesRequest`
- [ ] `preferences.py` imports schemas from `src.api.schema.preferences_schema` instead of defining them inline
- [ ] No inline Pydantic schema classes remain in `preferences.py`
- [ ] Unused imports (`HTTPException`, `status`, `BaseModel`, `Field`, `Optional`) removed from `preferences.py`
- [ ] GET and PATCH `/preferences` endpoints work identically to before
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Response Model](https://fastapi.tiangolo.com/tutorial/response-model/) — documents best practices for using Pydantic models with FastAPI endpoints
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Best Practices - Project Structure](https://github.com/zhanymkanov/fastapi-best-practices) — recommends separating schemas into dedicated files within domain-specific or shared schema directories
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-082 (Notification Preferences Created in Route Layer Instead of Service — also in preferences-adjacent code)
