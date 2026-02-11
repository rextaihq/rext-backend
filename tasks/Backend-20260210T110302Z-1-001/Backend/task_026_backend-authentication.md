# Task 026: Remove Unused Import `os` in Auth Routes

## Metadata
- **Task ID:** TASK-026
- **Source:** B1 - Authentication & Authorization (Finding #24 under P3 Low)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The file `src/api/routes/users/auth.py` contains an unused import statement on line 22:

```python
import os
```

The `os` module is imported but never used anywhere in the 1,046-line file. While there is a reference to `user_agent.os.family` on line 489, this is accessing the `os` property of a parsed user-agent object (from the `user-agents` library), not the Python `os` module.

Unused imports are a form of technical debt that:
1. **Clutter the code:** Developers must scan past them when reading imports
2. **Mislead readers:** Suggests the module is used when it isn't
3. **Slow imports (marginally):** Python loads the module even if unused
4. **Fail linting:** Tools like `flake8`, `pylint`, and `ruff` flag unused imports as errors
5. **Increase attack surface (theoretically):** Importing modules makes their functionality available even if unused

This is a simple cleanup task with no behavioral impact on the application.

---

## Current Code

```python
# File: rext-backend/src/api/routes/users/auth.py
# Lines: 1-32 (import section)
from fastapi import APIRouter, Depends, Request, BackgroundTasks, Header
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.schema.user_schema import LoginUser, RegisterUser, RegisterWithInvitation, LoginWithInvitation
from src.api.security.token_utils import verify_token
from src.api.config import get_settings
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.email_service import EmailService
from src.api.database.async_database import get_async_db
from src.utils.response_utils import success, error, created
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    RextAuthenticationException,
    ResourceNotFoundException,
    BusinessRuleViolationException
)
from datetime import datetime
from src.services.notification_helper import schedule_if_allowed
from user_agents import parse as parse_user_agent
from src.api.models.user_models.notification_preferences import NotificationPreferences
import os  # <-- UNUSED - Line 22
from src.api.middleware.rate_limiter import (
    login_rate_limit,
    registration_rate_limit
)
from src.services.auth_service import AuthService
from src.services.invitation_service import InvitationService
from src.services.user_service import UserService
from src.utils.invitation_utils import is_invitation_expired
from uuid import UUID

router = APIRouter()
```

### False Positive: user_agent.os.family

There is one reference to `os` in the file, but it's not the `os` module:

```python
# File: rext-backend/src/api/routes/users/auth.py
# Line: 489
device_name = f"{user_agent.browser.family} on {user_agent.os.family}"
```

This is accessing the `os` property of a `UserAgent` object from the `user-agents` library, which contains parsed OS information (e.g., "Windows", "macOS", "iOS"). This is completely unrelated to Python's `os` module.

---

## Why This Matters (Context & Reasoning)

While this is a minor issue, maintaining clean imports is part of code hygiene:

1. **CI/CD Pipeline:** If the project has linting enabled (flake8, pylint, ruff), this unused import may cause CI failures or warnings.
2. **Code Reviews:** Unused imports often get flagged in code reviews, wasting reviewer time.
3. **IDE Warnings:** Most IDEs (VS Code, PyCharm) will highlight this as an issue.
4. **Professionalism:** Clean code with no dead imports reflects attention to detail.

The import was likely added during development (perhaps for `os.environ` access) and never removed when the usage was refactored to use `get_settings()` instead.

---

## Impact

- **Severity:** None. Removing the import has zero behavioral impact.
- **Affected Users/Flows:** None.
- **Blast Radius:** None. This is a cosmetic/hygiene fix.

---

## Recommended Solution

Simply delete the unused import line.

### Step 1: Remove the Import

```python
# File: rext-backend/src/api/routes/users/auth.py
# Line 22 - DELETE this line:
import os
```

### Step 2: Verify No Other Usage Exists

Before deleting, confirm no other usage exists:

```bash
grep -n "\bos\." rext-backend/src/api/routes/users/auth.py
```

The only match should be `user_agent.os.family` which is not the `os` module.

Also check for bare `os` usage (without dot):

```bash
grep -n "\bos\b" rext-backend/src/api/routes/users/auth.py
```

This will match:
- Line 22: `import os` (the import we're removing)
- Line 489: `user_agent.os.family` (user-agent property, not os module)

Neither is an actual usage of the `os` module.

---

## Other Affected Locations

The audit report mentions unused `import os` in multiple files. This task addresses only `auth.py`. Related findings in other audit reports may cover:

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/routes/users/auth.py` | 22 | This task |
| Other files | Various | Covered in other audit reports (B3, B4) |

---

## Testing Instructions

### Before Fix (Current State):
1. Run a linter to confirm the unused import is flagged:
   ```bash
   cd rext-backend
   ruff check src/api/routes/users/auth.py --select F401
   # Or with flake8:
   flake8 src/api/routes/users/auth.py --select=F401
   ```
2. Observe output like: `auth.py:22: F401 'os' imported but unused`

### After Fix (Verify the Change):
1. Remove the import
2. Run the linter again:
   ```bash
   ruff check src/api/routes/users/auth.py --select F401
   ```
3. Verify no F401 errors for `os`

4. Verify the application still works:
   - Start the server: `uvicorn src.api.server:app --reload`
   - Test login endpoint works
   - Test registration endpoint works

### Verify user_agent.os.family Still Works:
```bash
# Call login endpoint and check logs show device info like:
# "Chrome on Windows" or "Safari on macOS"
```

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "auth"
```

---

## Acceptance Criteria

- [ ] `import os` removed from `auth.py`
- [ ] File still imports all actually-used modules
- [ ] No linting errors for unused imports in `auth.py`
- [ ] Login functionality works correctly
- [ ] Registration functionality works correctly
- [ ] Device name detection (`user_agent.os.family`) still works
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python Import System](https://docs.python.org/3/reference/import.html)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Flake8 F401 - Module imported but unused](https://www.flake8rules.com/rules/F401.html)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** Similar unused `import os` findings in B3 (Finding 29), B4 (Finding 28)
