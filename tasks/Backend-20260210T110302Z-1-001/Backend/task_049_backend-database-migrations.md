# Task 049: Add SerializableMixin to 5 Models with Manual to_dict() Implementations

## Metadata
- **Task ID:** TASK-049
- **Source:** Backend Database & Migrations Audit (Finding #16 under P2 Medium)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

Five SQLAlchemy models in the codebase do not inherit from `SerializableMixin` (`src/api/models/base.py`, lines 49-166), despite all other ~28 models in the project using it. Instead, four of these models define manual `to_dict()` methods that re-implement the same UUID-to-string and datetime-to-ISO-format conversion logic that `SerializableMixin` already provides. The fifth model (`ImpersonationSession`) has no `to_dict()` method at all, meaning it cannot be serialized to JSON without triggering `TypeError: Object of type UUID is not JSON serializable`.

The five models are:

1. **`EmailPreferences`** (`src/api/models/user_models/email_preferences.py:16`) — `class EmailPreferences(Base):` with manual `to_dict()` at line 64 that exposes `unsubscribe_token` in the serialized output (potential security concern — tokens should not be included in general API responses).

2. **`UserPreferences`** (`src/api/models/user_models/user_preferences.py:16`) — `class UserPreferences(Base):` with manual `to_dict()` at line 43 performing manual `str(self.id)` and `isoformat()` conversions.

3. **`ImpersonationSession`** (`src/api/models/user_models/impersonation_session.py:13`) — `class ImpersonationSession(Base):` with NO `to_dict()` method. Any code attempting to serialize this model to JSON will fail at runtime.

4. **`CustomerNote`** (`src/api/models/admin_models/customer_note.py:12`) — `class CustomerNote(Base):` with manual `to_dict()` at line 43 performing the same manual conversions.

5. **`ErrorLog`** (`src/api/models/admin_models/error_log.py:12`) — `class ErrorLog(Base):` with manual `to_dict()` at line 42. This model has a `JSONB` column (`error_metadata`, line 33) aliased as `"metadata"` in the database — the manual `to_dict()` returns it as `"metadata"` (line 53) rather than `"error_metadata"`, creating an inconsistency between the Python attribute name and the serialized key.

`SerializableMixin.to_dict()` (lines 52-166) handles UUID conversion, datetime ISO formatting, Decimal-to-float conversion, None filtering, relationship inclusion, and field exclusion — all of which the manual implementations partially replicate. The manual implementations are also missing features like `include_relationships`, `exclude` parameter support, and `include_nulls` control.

---

## Current Code

```python
# File: rext-backend/src/api/models/user_models/email_preferences.py
# Line 16: Missing SerializableMixin
class EmailPreferences(Base):
    # ...
    def to_dict(self):  # Line 64: Manual implementation
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            # ...
            "unsubscribe_token": self.unsubscribe_token,  # Security concern!
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
```

```python
# File: rext-backend/src/api/models/user_models/impersonation_session.py
# Line 13: Missing SerializableMixin AND no to_dict() at all
class ImpersonationSession(Base):
    __tablename__ = "impersonation_sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    is_valid = Column(Boolean, default=False, nullable=False)
    invalidated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # No to_dict() method — will cause TypeError on JSON serialization
```

```python
# File: rext-backend/src/api/models/admin_models/error_log.py
# Line 12: Missing SerializableMixin
class ErrorLog(Base):
    # ...
    error_metadata = Column("metadata", JSONB, default=dict)  # Line 33: aliased column
    # ...
    def to_dict(self) -> dict:  # Line 42: Manual implementation
        return {
            # ...
            "metadata": self.error_metadata,  # Returns as "metadata" not "error_metadata"
            # ...
        }
```

---

## Why This Matters (Context & Reasoning)

`SerializableMixin` is the established serialization contract for the entire Rext backend. When 28+ models use it and 5 do not, the codebase has two serialization paths that behave differently. The mixin handles edge cases (null UUIDs, null datetimes, Decimal types, relationship loading) that the manual implementations may miss. For example, `EmailPreferences.to_dict()` would crash with `AttributeError` if `self.created_at` were a non-datetime type, while `SerializableMixin` handles type checking before conversion.

More critically, `ImpersonationSession` having no `to_dict()` at all means any endpoint that tries to serialize it will produce a 500 Internal Server Error. And `EmailPreferences.to_dict()` exposes the `unsubscribe_token` in every API response — this token provides unauthenticated access to modify a user's email preferences and should be excluded from general serialization.

---

## Impact

- **Severity:** `ImpersonationSession` serialization will fail at runtime. `EmailPreferences.to_dict()` leaks the `unsubscribe_token` in API responses. Manual implementations miss edge cases handled by `SerializableMixin`.
- **Affected Users/Flows:** Admin flows (customer notes, error logs), user preference management, impersonation sessions, email preference API endpoints.
- **Blast Radius:** Moderate. Each model is relatively isolated, but the `EmailPreferences` token leakage affects all users.

---

## Recommended Solution

For each model: add `SerializableMixin` to the class declaration, remove the manual `to_dict()` method (or convert it to call `super().to_dict()` with customizations), and add appropriate field exclusions for sensitive data.

### Step 1: Fix EmailPreferences

```python
# File: rext-backend/src/api/models/user_models/email_preferences.py
# Add import:
from src.api.models.base import SerializableMixin

# Change class declaration (line 16):
class EmailPreferences(Base, SerializableMixin):
    __tablename__ = "email_preferences"
    # ... all columns remain unchanged ...

    # Replace manual to_dict() (lines 64-100) with:
    def to_dict(self, **kwargs):
        """Serialize preferences, excluding the unsubscribe token by default."""
        if 'exclude' not in kwargs:
            kwargs['exclude'] = ['unsubscribe_token']
        return super().to_dict(**kwargs)
```

### Step 2: Fix UserPreferences

```python
# File: rext-backend/src/api/models/user_models/user_preferences.py
# Add import:
from src.api.models.base import SerializableMixin

# Change class declaration (line 16):
class UserPreferences(Base, SerializableMixin):
    __tablename__ = "user_preferences"
    # ... all columns remain unchanged ...

    # Remove the entire manual to_dict() method (lines 43-55).
    # SerializableMixin handles all conversions automatically.
```

### Step 3: Fix ImpersonationSession

```python
# File: rext-backend/src/api/models/user_models/impersonation_session.py
# Add import:
from src.api.models.base import SerializableMixin

# Change class declaration (line 13):
class ImpersonationSession(Base, SerializableMixin):
    __tablename__ = "impersonation_sessions"
    # ... all columns remain unchanged ...
    # No to_dict() override needed — SerializableMixin handles everything.
```

### Step 4: Fix CustomerNote

```python
# File: rext-backend/src/api/models/admin_models/customer_note.py
# Add import:
from src.api.models.base import SerializableMixin

# Change class declaration (line 12):
class CustomerNote(Base, SerializableMixin):
    __tablename__ = "customer_notes"
    # ... all columns remain unchanged ...

    # Remove the entire manual to_dict() method (lines 43-53).
    # SerializableMixin handles all conversions automatically.
```

### Step 5: Fix ErrorLog

```python
# File: rext-backend/src/api/models/admin_models/error_log.py
# Add import:
from src.api.models.base import SerializableMixin

# Change class declaration (line 12):
class ErrorLog(Base, SerializableMixin):
    __tablename__ = "error_logs"
    # ... all columns remain unchanged ...

    # Remove the entire manual to_dict() method (lines 42-57).
    # Note: SerializableMixin will serialize the column using its Python
    # attribute name "error_metadata", not the database alias "metadata".
    # If API consumers expect "metadata" as the key, add a custom override:
    def to_dict(self, **kwargs):
        """Serialize with 'metadata' key for backward compatibility."""
        data = super().to_dict(**kwargs)
        # Rename error_metadata to metadata for API compatibility
        if 'error_metadata' in data:
            data['metadata'] = data.pop('error_metadata')
        return data
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/models/workspace_models/workspace_integration.py` | 42-57 | Also has a manual `to_dict()` that doesn't call `super()` and leaks `app_password`/`api_key` — related issue (TASK-029) |
| `rext-backend/src/api/models/notification/notification_model.py` | 178-194 | Manual `to_dict()` returns raw UUID and datetime objects without conversion |
| `rext-backend/src/api/models/knowledge_models/persona_model.py` | ~58-59 | Manual `to_dict()` returns raw datetime objects |
| `rext-backend/src/api/models/subscription_models/discount_usage.py` | 118-131 | Manual `to_dict()` that doesn't call `super()` despite inheriting `SerializableMixin` |
| `rext-backend/src/api/routes/users/email_preferences.py` | 82 | Calls `prefs.to_dict()` — will now exclude `unsubscribe_token` by default |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Try serializing an `ImpersonationSession` instance: `json.dumps(session.__dict__)` — observe `TypeError: Object of type UUID is not JSON serializable`
2. Call `GET /user/email-preferences/` — observe that `unsubscribe_token` is present in the response body
3. Inspect `ErrorLog.to_dict()` output — note the key is `"metadata"` not `"error_metadata"`

### After Fix (Verify the Solution):
1. Create an `ImpersonationSession` and call `.to_dict()` — should return a valid dict with UUIDs as strings and datetimes as ISO format
2. Call `GET /user/email-preferences/` — verify `unsubscribe_token` is NOT in the response
3. Call `ErrorLog().to_dict()` — verify the `"metadata"` key is preserved for backward compatibility
4. Call `CustomerNote().to_dict()` — verify UUIDs are strings, datetimes are ISO format
5. Call `UserPreferences().to_dict()` — verify output matches the old manual implementation

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "preferences or impersonation or customer_note or error_log" --no-header
```

---

## Acceptance Criteria

- [ ] All 5 models inherit from `SerializableMixin`
- [ ] `EmailPreferences.to_dict()` excludes `unsubscribe_token` by default
- [ ] `ImpersonationSession` has serialization capability (`.to_dict()` works)
- [ ] `ErrorLog.to_dict()` preserves `"metadata"` key name for backward compatibility
- [ ] `UserPreferences` and `CustomerNote` no longer have manual `to_dict()` methods
- [ ] All serialized output matches the format expected by existing API consumers (no breaking changes to response shapes)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy ORM Mixins](https://docs.sqlalchemy.org/en/20/orm/declarative_mixins.html) — SQLAlchemy documentation for declarative mixins used to share common functionality across models
- **Security Advisory:** N/A — but the `unsubscribe_token` exposure is a data leakage concern per OWASP API Security Top 10 (API3: Excessive Data Exposure)
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP API Security: Excessive Data Exposure](https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/) — Reference for why sensitive tokens should be excluded from default serialization
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-029 (WorkspaceIntegration.to_dict() leaks credentials — same pattern of manual to_dict bypassing SerializableMixin), TASK-047 (EmailPreferences involved in duplicate preference consolidation — if TASK-047 deprecates EmailPreferences, this fix is still valuable during the transition period)
