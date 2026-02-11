# Task 041: Replace Deprecated declarative_base() with Modern DeclarativeBase

## Metadata
- **Task ID:** TASK-041
- **Source:** Backend Database & Migrations Audit (Finding #15 under P2 Medium)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P2 Medium
- **Category:** dependency
- **Effort Estimate:** small (< 1 hour)

---

## Description

The file `src/api/database/base.py` uses the deprecated `declarative_base()` function from `sqlalchemy.ext.declarative`, which has been deprecated since SQLAlchemy 1.4 and is marked for removal in a future SQLAlchemy version. The current code:

```python
from sqlalchemy.ext.declarative import declarative_base
Base = declarative_base()
```

Should be migrated to the modern SQLAlchemy 2.0 pattern using the `DeclarativeBase` class from `sqlalchemy.orm`:

```python
from sqlalchemy.orm import DeclarativeBase
class Base(DeclarativeBase):
    pass
```

According to the [SQLAlchemy 2.0 Migration Guide](https://docs.sqlalchemy.org/en/20/changelog/migration_20.html), the `DeclarativeBase` superclass supersedes `declarative_base()` and provides better integration with Python type checking tools (PEP 484) without requiring plugins. The old function-based approach still works in SQLAlchemy 2.0 for backward compatibility but generates deprecation warnings and will eventually be removed.

The project's `pyproject.toml` specifies `pydantic>=2.0.0` and uses modern Python 3.11+, indicating the codebase is already targeting modern patterns. Migrating the Base class aligns with this direction and eliminates deprecation warnings that may appear in logs.

This change affects 47+ files that import `Base` from this module, but no import statements need to change - only the definition of `Base` itself.

---

## Current Code

```python
# File: rext-backend/src/api/database/base.py
# Lines: 1-10
"""
Database Base - Declarative Base for SQLAlchemy Models

This module provides the declarative base for all database models.
"""

from sqlalchemy.ext.declarative import declarative_base

# Create declarative base for SQLAlchemy models
Base = declarative_base()
```

**Files that import Base (47+ files):**
- `alembic/env.py`
- `src/api/server.py`
- `tests/conftest.py`
- All model files in `src/api/models/` (40+ files)

---

## Why This Matters (Context & Reasoning)

The `Base` class is the foundation of all SQLAlchemy ORM models in the application. Every model class inherits from `Base`, making this a critical piece of the database layer.

Using deprecated APIs creates several risks:

1. **Deprecation warnings in logs:** SQLAlchemy emits warnings when using deprecated features, cluttering production logs and making it harder to spot real issues.

2. **Future compatibility:** The deprecated `declarative_base()` function will be removed in a future SQLAlchemy major version. Migrating now prevents a forced migration later when upgrading SQLAlchemy becomes a breaking change.

3. **Type checking support:** The new `DeclarativeBase` pattern integrates with Python type checkers (mypy, pyright) natively, without requiring plugins. This enables better IDE support and static analysis.

4. **Modern patterns:** The new approach aligns with SQLAlchemy 2.0's emphasis on native Python typing, preparing the codebase for eventual migration to `Mapped`/`mapped_column` column definitions (a separate, larger refactor).

The good news is this change is low-risk: the new `Base` class is fully compatible with existing model definitions. Models that inherit from `Base` and use `Column()` will continue to work unchanged.

---

## Impact

- **Severity:** Low immediate impact; deprecation warnings in logs; future upgrade blocker
- **Affected Users/Flows:** No runtime impact on users; affects developer experience (warnings) and future maintainability
- **Blast Radius:** Foundational change but backward-compatible - all 40+ models inherit from Base but don't need modifications

---

## Recommended Solution

### Step 1: Update the Base class definition

```python
# File: rext-backend/src/api/database/base.py
# Replace entire file contents with:

"""
Database Base - Declarative Base for SQLAlchemy Models

This module provides the declarative base for all database models.
Uses SQLAlchemy 2.0's DeclarativeBase for modern type checking support.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.

    All models should inherit from this class:
        class MyModel(Base):
            __tablename__ = "my_table"
            ...

    For models that also need the SerializableMixin:
        class MyModel(Base, SerializableMixin):
            __tablename__ = "my_table"
            ...
    """
    pass
```

### Step 2: Verify no import changes are needed

The existing import statements in all model files:
```python
from src.api.database.base import Base
```

Will continue to work unchanged because we're defining `Base` as a class with the same name.

### Step 3: Run tests to verify compatibility

```bash
cd rext-backend
pytest tests/ -v
```

### Step 4: Verify Alembic still works

```bash
cd rext-backend
alembic check
alembic heads
alembic upgrade head --sql > /dev/null  # Dry run
```

### Step 5: Check for deprecation warnings

```bash
cd rext-backend
python -W default -c "from src.api.database.base import Base; print('Base loaded successfully')"
# Should not show any DeprecationWarning about declarative_base
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/database/base.py` | All | Primary file to modify |
| `rext-backend/alembic/env.py` | `22` | Imports Base for Alembic metadata |
| `rext-backend/src/api/server.py` | `26` | Imports Base for app initialization |
| `rext-backend/tests/conftest.py` | `13` | Imports Base for test fixtures |
| `rext-backend/src/api/models/**/*.py` | Various | 40+ model files import Base (no changes needed) |

---

## Testing Instructions

### Before Fix (Verify the Issue):
1. Check for deprecation warning:
   ```bash
   cd rext-backend
   python -W default -c "from sqlalchemy.ext.declarative import declarative_base; b = declarative_base()"
   ```
   This should show a deprecation warning (if SQLAlchemy version is recent enough)

2. Verify current import works:
   ```bash
   python -c "from src.api.database.base import Base; print(type(Base))"
   # Should print: <class 'sqlalchemy.orm.decl_api.DeclarativeMeta'>
   ```

### After Fix (Verify the Solution):
1. Verify new import works:
   ```bash
   cd rext-backend
   python -c "from src.api.database.base import Base; print(type(Base))"
   # Should print: <class 'sqlalchemy.orm.decl_api.DeclarativeAttributeIntercept'>
   ```

2. Verify no deprecation warnings:
   ```bash
   python -W error::DeprecationWarning -c "from src.api.database.base import Base"
   # Should succeed without raising DeprecationWarning
   ```

3. Verify models still work:
   ```bash
   python -c "from src.api.models.user_models.users import Users; print(Users.__tablename__)"
   # Should print: users
   ```

4. Verify Alembic integration:
   ```bash
   alembic check
   alembic heads
   alembic upgrade head --sql > /dev/null
   ```

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v --tb=short
pytest tests/database/ -v  # If database-specific tests exist
```

---

## Acceptance Criteria

- [ ] `src/api/database/base.py` uses `DeclarativeBase` from `sqlalchemy.orm`
- [ ] No `declarative_base` import remains in the codebase
- [ ] All existing model files work without modification
- [ ] `alembic check` passes
- [ ] `alembic upgrade head` works
- [ ] No deprecation warnings when importing Base
- [ ] All existing tests pass
- [ ] No new warnings or errors introduced
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 Declarative Mapping Styles](https://docs.sqlalchemy.org/en/20/orm/declarative_styles.html)
- **Security Advisory:** N/A
- **Migration Guide:** [SQLAlchemy 2.0 Major Migration Guide](https://docs.sqlalchemy.org/en/20/changelog/migration_20.html)
- **Best Practice Reference:** [What's New in SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/changelog/whatsnew_20.html)
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None (but enables future migration to Mapped/mapped_column if desired)
- **Related:** None from B2; this is a foundational modernization task
