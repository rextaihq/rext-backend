# Task 046: Replace Deprecated Pydantic class Config with model_config in Settings

## Metadata
- **Task ID:** TASK-046
- **Source:** Backend Database & Migrations Audit (Finding #25 under P2 Medium)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P2 Medium
- **Category:** dependency
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `Settings` class in `src/api/config.py` (lines 329-334) uses the Pydantic v1-style inner `class Config:` pattern for configuration. This pattern is deprecated in Pydantic v2 in favor of the `model_config` class attribute using `SettingsConfigDict` (for `BaseSettings` subclasses) or `ConfigDict` (for regular `BaseModel` subclasses).

The project's `pyproject.toml` specifies `pydantic>=2.0.0` and `pydantic-settings>=2.0.0`, confirming that Pydantic v2 is the target version. While the `class Config:` pattern still works in Pydantic v2 for backwards compatibility, it is officially deprecated and will be removed in a future major version. Additionally, the class-based config does not support all new Pydantic v2 configuration options.

The `src/api/config.py` file imports from `pydantic_settings` (line 10: `from pydantic_settings import BaseSettings`), so the `Settings` class is a `BaseSettings` subclass. The correct replacement is `SettingsConfigDict` from `pydantic_settings`, not `ConfigDict` from `pydantic`.

Beyond the main `Settings` class, a codebase search reveals that the deprecated `class Config:` pattern is used in **80+ Pydantic schema files** across `src/api/schema/`, `src/config/`, `src/utils/`, and route files. While those occurrences are outside the scope of this B2 audit finding (which specifically targets `config.py`), they should be listed in "Other Affected Locations" for awareness and future migration.

---

## Current Code

```python
# File: rext-backend/src/api/config.py
# Lines: 1-13 (imports and class declaration)
"""
API Configuration Settings

Centralized configuration using environment variables with Pydantic validation.
Note: dotenv is loaded in server.py before importing this module.
"""
from typing import List, Optional
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables with validation."""
    # ... (300+ lines of settings fields) ...

    # Lines 329-334 (deprecated Config class):
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # Ignore extra env vars not defined in this class
```

---

## Why This Matters (Context & Reasoning)

The `Settings` class is the central configuration hub for the entire Rext backend. It is instantiated once at application startup (via the `get_settings()` singleton at line 341) and provides all environment-variable-driven configuration to the rest of the application. If this class breaks due to a Pydantic upgrade removing `class Config:` support, the entire application fails to start.

The Pydantic v2 migration guide explicitly states: "In Pydantic V2, to specify config on a model, you should set a class attribute called `model_config` to be a dict with the key/value pairs you want to be used as the config. The Pydantic V1 behavior to create a class called `Config` in the namespace of the parent `BaseModel` subclass is now deprecated."

For `BaseSettings` subclasses specifically, the `pydantic-settings` package provides `SettingsConfigDict` which extends `ConfigDict` with settings-specific options like `env_file`, `env_prefix`, etc.

---

## Impact

- **Severity:** Deprecation warning now; application startup failure when Pydantic removes `class Config:` support in a future version.
- **Affected Users/Flows:** All — the Settings class is loaded at application startup and affects every feature.
- **Blast Radius:** System-wide if the Settings class fails to load. The fix itself is localized to `config.py`.

---

## Recommended Solution

### Step 1: Update Imports

```python
# File: rext-backend/src/api/config.py
# Line 10 — update the import to include SettingsConfigDict:

# BEFORE:
from pydantic_settings import BaseSettings

# AFTER:
from pydantic_settings import BaseSettings, SettingsConfigDict
```

### Step 2: Replace class Config with model_config

```python
# File: rext-backend/src/api/config.py
# Replace lines 329-334:

# BEFORE:
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # Ignore extra env vars not defined in this class

# AFTER:
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )
```

### Step 3: Verify Other Settings/Config Classes

Check if `src/config/payment_config.py` and `src/config/storage_config.py` also use `class Config:` and update them similarly:

```python
# File: rext-backend/src/config/payment_config.py
# Line 46 — if it uses BaseSettings, update to SettingsConfigDict
# If it uses BaseModel, update to ConfigDict from pydantic

# File: rext-backend/src/config/storage_config.py
# Line 65 — same check and update
```

For schema files using `class Config:` with regular `BaseModel` (not `BaseSettings`), the replacement is `ConfigDict` from `pydantic`:

```python
# For regular Pydantic models (BaseModel subclasses):
from pydantic import ConfigDict

class MySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    # ...
```

---

## Other Affected Locations

The `class Config:` pattern is used in 80+ additional locations. These are Pydantic schema files (not `BaseSettings`), so they need `ConfigDict` from `pydantic`, not `SettingsConfigDict`:

| File | Line(s) | Description |
|------|---------|-------------|
| `src/config/payment_config.py` | `46` | Settings subclass — use SettingsConfigDict |
| `src/config/storage_config.py` | `65` | Settings subclass — use SettingsConfigDict |
| `src/utils/response_utils.py` | `109` | BaseModel schema — use ConfigDict |
| `src/api/schema/impersonation_schema.py` | `16, 34, 55, 77` | 4 schemas — use ConfigDict |
| `src/api/schema/persona_schema.py` | `144` | Schema — use ConfigDict |
| `src/api/schema/user_role_schema.py` | `27, 50` | 2 schemas — use ConfigDict |
| `src/api/schema/content_schema.py` | `129, 175` | 2 schemas — use ConfigDict |
| `src/api/schema/role_schema.py` | `42, 73, 91, 106, 114, 126` | 6 schemas — use ConfigDict |
| `src/api/schema/knowledge_schema.py` | `49` | Schema — use ConfigDict |
| `src/api/schema/webhook_schema.py` | `55` | Schema — use ConfigDict |
| `src/api/schema/onboarding_schemas.py` | `48` | Schema — use ConfigDict |
| `src/api/schema/response_schemas.py` | `224, 269, 310` | 3 schemas — use ConfigDict |
| `src/api/schema/notification_schema.py` | `25, 108` | 2 schemas — use ConfigDict |
| `src/api/schema/email_schema.py` | `104` | Schema — use ConfigDict |
| `src/api/schema/email_preview_schema.py` | `38, 119, 155` | 3 schemas — use ConfigDict |
| `src/api/schema/audit_schema.py` | `98, 138, 170, 215, 251, 277` | 6 schemas — use ConfigDict |
| `src/api/schema/workspace_schema.py` | `9, 21` | 2 schemas — use ConfigDict |
| `src/api/schema/security_schema.py` | `38, 61, 97, 131, 167, 198, 210` | 7 schemas — use ConfigDict |
| `src/api/schema/permission_schema.py` | `56, 93, 111, 125, 133` | 5 schemas — use ConfigDict |
| `src/api/schema/subscription/*.py` | Multiple | 20+ schemas across subscription schema files |
| `src/api/routes/admin/email_admin_routes.py` | `43` | Inline schema — use ConfigDict |
| `src/api/routes/subscriptions/trial_routes.py` | `40` | Inline schema — use ConfigDict |

**Note:** The full migration of all 80+ schema files is a separate, larger effort. This task focuses on the `Settings` class in `config.py` and the other settings/config classes. The schema files should be addressed in a dedicated refactoring task.

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Check the current config pattern: `cd rext-backend && grep -n "class Config:" src/api/config.py`
2. Should show `329:    class Config:` — the deprecated pattern.
3. Optionally, run with Python 3.12+ (if available) to see the deprecation warning.

### After Fix (Verify the Solution):
1. Verify the fix: `cd rext-backend && grep -n "model_config" src/api/config.py`
2. Should show the `model_config = SettingsConfigDict(...)` line.
3. Verify settings still load correctly: `cd rext-backend && python -c "from src.api.config import get_settings; s = get_settings(); print(s.ENVIRONMENT)"`
4. Should print the environment value (e.g., `development`) without errors.
5. Verify that `.env` file is still loaded: `cd rext-backend && python -c "from src.api.config import Settings; print(Settings.model_config)"`
6. Should show the config dict with `env_file`, `case_sensitive`, etc.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v
```

---

## Acceptance Criteria

- [ ] `class Config:` in `src/api/config.py` is replaced with `model_config = SettingsConfigDict(...)`
- [ ] `SettingsConfigDict` is imported from `pydantic_settings`
- [ ] Settings still load correctly from `.env` file
- [ ] `case_sensitive=True` behavior is preserved
- [ ] `extra="ignore"` behavior is preserved
- [ ] `src/config/payment_config.py` and `src/config/storage_config.py` are also updated if they use the deprecated pattern
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Pydantic v2 — Model Config](https://docs.pydantic.dev/latest/concepts/config/) — documents `model_config = ConfigDict(...)` as the replacement for `class Config:`
- **Security Advisory:** N/A
- **Migration Guide:** [Pydantic v2 Migration Guide](https://docs.pydantic.dev/latest/migration/) — comprehensive guide for migrating from v1 to v2, including config changes
- **Best Practice Reference:** [Pydantic Settings Management](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — documents `SettingsConfigDict` for `BaseSettings` subclasses
- **Related Issues/PRs:** [Pydantic Discussion #7701](https://github.com/pydantic/pydantic/discussions/7701) — community discussion on `Field` and `BaseSettings` migration to v2

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** All 80+ schema files using `class Config:` should be migrated in a future dedicated task. TASK-041 (Deprecated declarative_base import — similar deprecation pattern in a different library)
