# Task 082: Move Notification Preferences Creation from Route Layer to Service Layer

## Metadata
- **Task ID:** TASK-082
- **Source:** B3 - User Management (Finding #19 under P2 Medium)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `get_notification_preferences` endpoint in `rext-backend/src/api/routes/users/profile.py` (lines 477–518) and the `update_notification_preferences` endpoint (lines 521–616) both contain inline business logic for creating default `NotificationPreferences` records. When a user's notification preferences do not exist, the route handler directly instantiates a `NotificationPreferences` model, adds it to the database session, commits the transaction, and refreshes the object. This violates the project's explicit layered architecture where routes should be thin controllers delegating all business logic to services.

The problem is compounded by the fact that the same "create default notification preferences" logic is duplicated **5 times total** across 2 files:

1. `profile.py:503-508` — `get_notification_preferences` route (uses `db.commit()`)
2. `profile.py:547-550` — `update_notification_preferences` route (uses `db.add()` without explicit commit)
3. `auth.py:148-175` — `register` endpoint (25 explicit field defaults + `db.commit()` + `db.refresh()`)
4. `auth.py:364-391` — `register_with_invitation` endpoint (identical 25-field block)
5. `auth.py:857-882` — OAuth login endpoint (identical 25-field block with get-or-create check)

The `auth.py` copies are especially problematic: they hardcode **25 field values** (e.g., `email_notifications=True`, `ws_invite_received=True`, `marketing_updates=False`) rather than relying on the `NotificationPreferences` model's column-level defaults. The model already defines sensible defaults for all 35+ columns via SQLAlchemy `Column(Boolean, default=True)` and `Column(Boolean, default=False)` declarations (see `notification_preferences.py`). A simple `NotificationPreferences(user_id=user_id)` constructor call already produces correct defaults. The 25-field explicit initialization in `auth.py` is redundant with the model defaults and creates a maintenance hazard — if a new notification category column is added to the model with `default=True`, the `auth.py` copies won't include it, leading to inconsistent defaults for users created via registration vs. users whose preferences are created on first access.

The `profile.py` route also commits the transaction directly (`await db.commit()` at line 506) instead of using `flush()` and letting the route decorator or middleware manage transaction boundaries. This is inconsistent with the project's conventions and can break transaction atomicity if the endpoint does additional work after this point. Per SQLAlchemy's official documentation, `flush()` sends changes to the database but keeps them within the current transaction, while `commit()` makes them permanent — services should use `flush()` to allow callers to control the transaction boundary.

A `UserPreferencesService` already exists (`rext-backend/src/services/user_preferences_service.py`) with a `get_or_create_preferences()` method for UI preferences (`UserPreferences`) that properly uses `flush()` instead of `commit()`. The notification preferences should follow the exact same pattern.

The project uses Pydantic `>=2.0.0`, SQLAlchemy async with `asyncpg>=0.30.0`, and Python `>=3.11,<3.12` (per `pyproject.toml`). The recommended solution follows the established `UserPreferencesService` pattern and aligns with SQLAlchemy 2.0 async best practices for session management.

---

## Current Code

### GET endpoint — `get_notification_preferences` (lines 477–518):

```python
# File: rext-backend/src/api/routes/users/profile.py
# Lines: 477-518
@router.get("/preferences/notifications", response_model=None)
@require_permissions("user.read", workspace_scoped=False)
async def get_notification_preferences(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current user's notification preferences.
    Creates default preferences if none exist.
    """
    try:
        user_id = current_user.get("identity")

        # Get existing preferences
        result = await db.execute(
            select(NotificationPreferences).where(
                NotificationPreferences.user_id == user_id
            )
        )
        preferences = result.scalar_one_or_none()

        # Create defaults if needed — THIS IS BUSINESS LOGIC IN THE ROUTE
        if not preferences:
            preferences = NotificationPreferences(user_id=user_id)
            db.add(preferences)
            await db.commit()       # ← Route commits directly (should be flush)
            await db.refresh(preferences)
            logger.info(f"Created default notification preferences for user {user_id}")

        return success(
            data=preferences.to_dict(),
            request=request,
            message="Notification preferences retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Failed to get notification preferences: {str(e)}")
        raise
```

### PATCH endpoint — `update_notification_preferences` (lines 521–616, get-or-create block):

```python
# File: rext-backend/src/api/routes/users/profile.py
# Lines: 536-550 (get-or-create block within update handler)
    try:
        user_id = current_user.get("identity")

        # Get or create preferences — ALSO INLINED IN THE ROUTE
        result = await db.execute(
            select(NotificationPreferences).where(
                NotificationPreferences.user_id == user_id
            )
        )
        preferences = result.scalar_one_or_none()

        if not preferences:
            preferences = NotificationPreferences(user_id=user_id)
            db.add(preferences)
            logger.info(f"Creating notification preferences for user {user_id}")

        # ... category mapping and field update logic follows ...
        await db.commit()
```

### auth.py duplication — 3 identical blocks with 25 explicit field defaults:

```python
# File: rext-backend/src/api/routes/users/auth.py
# Lines: 148-175 (register), 364-391 (register-with-invitation), 857-882 (OAuth login)
# All three blocks create NotificationPreferences with redundant explicit defaults:
notification_preference = NotificationPreferences(
    user_id=new_user.id,
    email_notifications=True,        # ← Model default is already True
    in_app_notifications=True,       # ← Model default is already True
    ws_invite_received=True,         # ← Model default is already True
    ws_invite_accepted=True,         # ← Model default is already True
    ws_role_changed=True,            # ← Model default is already True
    ws_member_removed=True,          # ← Model default is already True
    gen_started=True,                # ← Model default is already True
    gen_completed=True,              # ← Model default is already True
    gen_failed=True,                 # ← Model default is already True
    gen_published=True,              # ← Model default is already True
    billing_payment_success=True,    # ← Model default is already True
    billing_payment_failed=True,     # ← Model default is already True
    billing_subscription_cancelled=True,
    billing_subscription_expiring=True,
    billing_trial_ending=True,
    billing_usage_limit_warning=True,
    billing_usage_limit_exceeded=True,
    kb_processing_completed=True,
    kb_processing_failed=True,
    digest_enabled=True,
    digest_frequency="daily",        # ← Model default is already "daily"
    marketing_updates=False           # ← Model default is already False
)
db.add(notification_preference)
await db.commit()
await db.refresh(notification_preference)
```

### Existing pattern to follow — `UserPreferencesService` (correct implementation):

```python
# File: rext-backend/src/services/user_preferences_service.py
# Lines: 40-74
class UserPreferencesService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_preferences(self, user_id: UUID) -> UserPreferences:
        query = select(UserPreferences).where(UserPreferences.user_id == user_id)
        result = await self.db.execute(query)
        preferences = result.scalar_one_or_none()
        if not preferences:
            preferences = UserPreferences(
                user_id=user_id,
                theme="system",
                date_format="iso",
                time_format="24h",
                items_per_page=25,
                sidebar_collapsed=False
            )
            self.db.add(preferences)
            await self.db.flush()  # ← Correctly uses flush(), not commit()
            logger.info(f"Created default preferences for user {user_id}")
        else:
            logger.debug(f"Retrieved existing preferences for user {user_id}")
        return preferences
```

**Note:** The `UserPreferencesService.update_preferences()` method at line 122 has its own issue — it calls `await self.db.commit()` inside the service, violating the "Does NOT commit transactions" doctrine. This is tracked by TASK-074.

---

## Why This Matters (Context & Reasoning)

The project explicitly follows a Routes → Services → Models layered architecture. Every service file's docstring states "Does NOT handle HTTP requests/responses (that's routes)" and "Does NOT commit transactions (that's decorators/routes)." Having model creation logic in the route layer:

- **Creates invisible duplication** across the codebase. The same "create default notification preferences" logic exists in 5 locations across 2 files (`profile.py` ×2, `auth.py` ×3). Any change to default values, field additions, or creation logic must be replicated 5 times.
- **Uses `db.commit()` directly in the route**, which conflicts with decorator-managed transactions and breaks atomicity. SQLAlchemy's official documentation recommends that services use `flush()` (sends to DB within the transaction) while callers control `commit()` (makes permanent). The `UserPreferencesService` already follows this pattern correctly.
- **Cannot be reused** by other routes, background tasks, or CLI commands without copying the logic yet again.
- **Creates drift risk** between the `auth.py` copies (25 explicit field defaults) and the `profile.py` copies (relying on model column defaults). If a new notification column is added to the model with a default, the `auth.py` copies won't include it unless manually updated.
- **Violates single source of truth** for default notification preferences. The model defines defaults, the `auth.py` copies restate them, and if they ever diverge, users created via different paths will have different default preferences.

The `NotificationPreferences` model (`notification_preferences.py`) already defines column-level defaults for all boolean fields (`default=True` for all except `marketing_updates` which is `default=False`) and for `digest_frequency` (`default="daily"`). A simple `NotificationPreferences(user_id=user_id)` constructor call already produces the correct defaults — SQLAlchemy applies column defaults at INSERT time. The 25-field explicit initialization in `auth.py` is entirely redundant.

---

## Impact

- **Severity:** Architectural violation. No runtime bug, but the duplicated logic across 5 locations creates maintenance burden and risk of inconsistent defaults.
- **Affected Users/Flows:** Any flow where a user's notification preferences are accessed for the first time (profile page load, preference update), and any flow that creates a new user (registration, invitation acceptance, OAuth login).
- **Blast Radius:** Currently affects `profile.py` (2 locations) and `auth.py` (3 locations). Will affect any future endpoint or background task that needs notification preferences.

---

## Recommended Solution

### Step 1: Create `NotificationPreferencesService` with a `get_or_create` method

Create a new dedicated service file following the established `UserPreferencesService` pattern. The service relies on model column defaults — it does NOT hardcode 25 field values.

```python
# File: rext-backend/src/services/notification_preferences_service.py (NEW FILE)

"""
Notification Preferences Service - Business Logic for Notification Preference Operations

This service encapsulates all business logic related to notification preferences,
including creation of defaults and retrieval.

Responsibilities:
- Get or create notification preferences
- Provide a single source of truth for default preference creation

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.utils.logger import logger


class NotificationPreferencesService:
    """Service for notification preferences business logic."""

    def __init__(self, db: AsyncSession):
        """
        Initialize service with database session.

        Args:
            db: Async database session
        """
        self.db = db

    async def get_or_create(self, user_id: UUID) -> NotificationPreferences:
        """
        Get notification preferences or create default ones if they don't exist.

        Uses model-level column defaults for all boolean fields, ensuring
        a single source of truth for default values. Does NOT commit —
        the caller or a transaction decorator is responsible for committing.

        Args:
            user_id: User UUID (can be str or UUID — will be used as-is in the query)

        Returns:
            NotificationPreferences object (existing or newly created)
        """
        query = select(NotificationPreferences).where(
            NotificationPreferences.user_id == user_id
        )
        result = await self.db.execute(query)
        preferences = result.scalar_one_or_none()

        if not preferences:
            # Rely on model column defaults — do NOT hardcode field values
            preferences = NotificationPreferences(user_id=user_id)
            self.db.add(preferences)
            await self.db.flush()  # Flush to get ID but don't commit
            logger.info(f"Created default notification preferences for user {user_id}")
        else:
            logger.debug(f"Retrieved existing notification preferences for user {user_id}")

        return preferences
```

### Step 2: Update `get_notification_preferences` in `profile.py` to use the service

```python
# File: rext-backend/src/api/routes/users/profile.py
# Add to imports at the top of the file (e.g., after the UserService import at line 14):
from src.services.notification_preferences_service import NotificationPreferencesService

# Replace the get_notification_preferences handler (lines 477-518) with:
@router.get("/preferences/notifications", response_model=None)
@require_permissions("user.read", workspace_scoped=False)
async def get_notification_preferences(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current user's notification preferences.
    Creates default preferences if none exist.
    """
    try:
        user_id = current_user.get("identity")

        service = NotificationPreferencesService(db)
        preferences = await service.get_or_create(user_id)
        await db.commit()

        return success(
            data=preferences.to_dict(),
            request=request,
            message="Notification preferences retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Failed to get notification preferences: {str(e)}")
        raise
```

### Step 3: Update `update_notification_preferences` in `profile.py` to use the service

Replace the inline get-or-create block (lines 536–550) with a service call:

```python
# File: rext-backend/src/api/routes/users/profile.py
# Replace lines 536-550 within update_notification_preferences:
    try:
        user_id = current_user.get("identity")

        notification_service = NotificationPreferencesService(db)
        preferences = await notification_service.get_or_create(user_id)

        # Update preferences dynamically from the request
        update_data = preferences_update.model_dump(exclude_unset=True)

        # Handle simplified categories if provided
        if "categories" in update_data:
            categories = update_data.pop("categories")
            mapping = {
                "mentions": ["email_mentions", "in_app_mentions"],
                "workspace_invites": ["ws_invite_received"],
                "content_updates": ["email_content_updates", "in_app_content_updates"],
                "comments": ["email_comments", "in_app_comments"],
                "team_activity": ["email_team_activity", "in_app_team_activity"],
                "security_alerts": ["email_security_alerts", "in_app_security_alerts"],
                "billing_updates": ["email_billing_updates", "in_app_billing_updates"],
                "product_updates": ["email_product_updates", "in_app_product_updates"],
            }

            for cat, value in categories.items():
                if cat in mapping:
                    for db_field in mapping[cat]:
                        if hasattr(preferences, db_field):
                            setattr(preferences, db_field, value)
                            logger.debug(f"Updated category preference '{cat}' -> '{db_field}' to {value}")

        # Handle all other fields directly
        for field, value in update_data.items():
            if hasattr(preferences, field):
                setattr(preferences, field, value)
                logger.debug(f"Updated notification preference '{field}' for user {user_id}")

        # Commit changes to database
        await db.commit()

        # ... rest of the handler (notification scheduling, response) remains unchanged ...
```

### Step 4: Verify import cleanup in `profile.py`

After the refactor, check whether `select` is still used elsewhere in `profile.py`. The `select` import at line 18 (`from sqlalchemy import select`) is used by the notification preferences queries we just replaced. However, `select` may also be used elsewhere in the file (e.g., in the `deactivate_account` endpoint at line 683 for `UserSubscription` queries). Verify before removing.

```python
# File: rext-backend/src/api/routes/users/profile.py
# Line 18: from sqlalchemy import select
# KEEP — still used by deactivate_account endpoint for subscription queries (line 683)
```

The `NotificationPreferences` import at line 9 is still needed because the model is referenced in the `update_notification_preferences` handler for `setattr` calls on the preferences object.

### Note on `auth.py` duplication (out of scope)

The 3 identical `NotificationPreferences` creation blocks in `auth.py` (lines 148–175, 364–391, 857–882) should also be replaced with `NotificationPreferencesService.get_or_create()` calls. However, this is **out of scope for this task** — the `auth.py` changes are tracked as B1 DRY-3 remediation and should be a separate follow-up task. Once the service exists (after this task), the `auth.py` refactor becomes trivial: replace 25-line blocks with 2-line service calls.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/routes/users/auth.py` | 148-175 | `register` endpoint — creates `NotificationPreferences` with 25 explicit field defaults. Should be replaced with `NotificationPreferencesService.get_or_create()` in a follow-up task |
| `rext-backend/src/api/routes/users/auth.py` | 364-391 | `register_with_invitation` endpoint — identical 25-field block |
| `rext-backend/src/api/routes/users/auth.py` | 857-882 | OAuth login endpoint — identical 25-field block with get-or-create check |
| `rext-backend/src/services/user_preferences_service.py` | 40-74 | Existing analogous service for `UserPreferences` — follow the same pattern |
| `rext-backend/src/services/user_preferences_service.py` | 122 | `update_preferences()` calls `await self.db.commit()` inside the service — this is a separate issue tracked by TASK-074 |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Delete the `notification_preferences` row for a test user in the database:
   ```sql
   DELETE FROM notification_preferences WHERE user_id = '<test-user-uuid>';
   ```
2. Call `GET /api/v1/user/profile/preferences/notifications` as that user
3. Observe that default preferences are created — inspect `profile.py:503-508` to confirm creation happens in the route layer
4. Check database: all boolean columns should be `True` except `marketing_updates` which should be `False`

### After Fix (Verify the Solution):
1. Delete the `notification_preferences` row for a test user in the database
2. Call `GET /api/v1/user/profile/preferences/notifications` as that user
3. Verify default preferences are created correctly (same JSON response structure as before)
4. Check database: all column values should match the model defaults exactly
5. Call the endpoint again — verify existing preferences are returned without re-creation
6. Delete preferences again, then call `PATCH /api/v1/user/profile/preferences/notifications` with `{"email_notifications": false}` — verify preferences are created via the service and then updated
7. Verify the response format is unchanged (matches the `to_dict()` output structure)
8. Inspect the code: creation logic now lives in `NotificationPreferencesService.get_or_create()` and uses `flush()` instead of `commit()`

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "notification or preferences or profile" -v
```

---

## Acceptance Criteria

- [ ] New file `rext-backend/src/services/notification_preferences_service.py` created with `NotificationPreferencesService` class
- [ ] `get_or_create()` method follows the same pattern as `UserPreferencesService.get_or_create_preferences()` in `user_preferences_service.py`
- [ ] Service method uses `await self.db.flush()` instead of `await db.commit()`
- [ ] Service method relies on model column defaults (does NOT hardcode 25 field values)
- [ ] `get_notification_preferences` route in `profile.py` uses `NotificationPreferencesService.get_or_create()`
- [ ] `update_notification_preferences` route in `profile.py` uses `NotificationPreferencesService.get_or_create()`
- [ ] Inline `select()` + `NotificationPreferences()` creation logic removed from both route handlers in `profile.py`
- [ ] Response format unchanged for both GET and PATCH endpoints (same JSON structure from `to_dict()`)
- [ ] Import of `NotificationPreferencesService` added to `profile.py`
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 — Session Basics (flush vs commit)](https://docs.sqlalchemy.org/en/20/orm/session_basics.html) — explains why services should use `flush()` (sends to DB within transaction) while callers control `commit()` (makes permanent)
- **Official Docs:** [SQLAlchemy 2.0 — Column INSERT/UPDATE Defaults](https://docs.sqlalchemy.org/en/20/core/defaults.html) — explains how column-level `default=` values are applied at INSERT time, making explicit constructor arguments redundant when they match the column defaults
- **Official Docs:** [SQLAlchemy 2.0 — AsyncIO Extension](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) — async session patterns, `expire_on_commit=False` best practice
- **Official Docs:** [FastAPI — Bigger Applications - Multiple Files](https://fastapi.tiangolo.com/tutorial/bigger-applications/) — recommended project structure separating routes from business logic
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Service Layer Architecture Best Practices (2025)](https://medium.com/@abhinav.dobhal/building-production-ready-fastapi-applications-with-service-layer-architecture-in-2025-f3af8a6ac563) — recommends thin route handlers delegating all business logic to services
- **Best Practice Reference:** [Layered Architecture & Dependency Injection for Clean FastAPI Code](https://dev.to/markoulis/layered-architecture-dependency-injection-a-recipe-for-clean-and-testable-fastapi-code-3ioo) — detailed guide on service layer separation
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:**
  - TASK-074 (B3 Finding #15, P2 Medium — service layer commits transactions via `db.commit()` in `user_preferences_service.py:122` and `member_service.py:626`; same architectural principle)
  - B1 DRY-3 (3x duplication of `NotificationPreferences` creation in `auth.py` — follow-up task should also adopt `NotificationPreferencesService.get_or_create()` to eliminate the 25-field explicit blocks)
