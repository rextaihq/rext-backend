# Task 047: Consolidate Duplicate Preference Models (NotificationPreferences & EmailPreferences)

## Metadata
- **Task ID:** TASK-047
- **Source:** Backend Database & Migrations Audit (Finding #22 under P2 Medium)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P2 Medium
- **Category:** refactoring
- **Effort Estimate:** large (4+ hours)

---

## Description

The codebase contains two separate but heavily overlapping models for managing user notification preferences: `NotificationPreferences` (`src/api/models/user_models/notification_preferences.py`, 125 lines) and `EmailPreferences` (`src/api/models/user_models/email_preferences.py`, 101 lines). Both models track preferences for the same notification categories — workspace events, content generation, billing, knowledge base processing, digest settings, and marketing communications — but use different column names, different default values, and different serialization approaches.

`NotificationPreferences` (line 10) inherits from `SerializableMixin` and provides per-channel toggles with `email_*` and `in_app_*` prefixed columns for each category (e.g., `email_team_activity` and `in_app_team_activity`). It already has the architectural capacity to control both email and in-app delivery channels from a single model. `EmailPreferences` (line 16) does NOT inherit from `SerializableMixin`, uses unprefixed column names (e.g., `workspace_invitation`, `content_generation_started`), and includes a unique `unsubscribe_token` column (line 55) for one-click email unsubscribe links — a feature absent from `NotificationPreferences`.

The two models have divergent default values for shared concepts: `NotificationPreferences.digest_frequency` defaults to `"daily"` (line 86), while `EmailPreferences.digest_frequency` defaults to `"weekly"` (line 49). This means a user's digest cadence depends on which model a given service checks, creating unpredictable behavior.

Currently, the `notification_helper.py` service checks `NotificationPreferences` for in-app notification gating (lines 30-33), while `billing_email_service.py` checks `EmailPreferences` for email delivery decisions (lines 274-284). The `email_preferences_service.py` only manages the `EmailPreferences` model. This split means changing notification preferences in one place does not affect the other, leading to inconsistent user experience — a user could disable billing notifications in their email preferences but still receive in-app billing notifications because those are governed by a completely separate model.

---

## Current Code

```python
# File: rext-backend/src/api/models/user_models/notification_preferences.py
# Lines: 10-125 (full model, key sections shown)
class NotificationPreferences(Base, SerializableMixin):
    __tablename__ = "notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Global toggles
    email_notifications = Column(Boolean, default=True, nullable=False)
    in_app_notifications = Column(Boolean, default=True, nullable=False)

    # Per-category, per-channel (e.g., email_team_activity, in_app_team_activity)
    email_team_activity = Column(Boolean, default=True, nullable=False)
    in_app_team_activity = Column(Boolean, default=True, nullable=False)
    # ... 30+ more boolean columns for each category x channel ...

    digest_enabled = Column(Boolean, default=True, nullable=False)
    digest_frequency = Column(String(20), default="daily", nullable=False)

    marketing_updates = Column(Boolean, default=False, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
```

```python
# File: rext-backend/src/api/models/user_models/email_preferences.py
# Lines: 16-101 (full model, key sections shown)
class EmailPreferences(Base):  # NOTE: No SerializableMixin
    __tablename__ = "email_preferences"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Overlapping categories with different column names
    workspace_invitation = Column(Boolean, default=True, nullable=False)
    content_generation_started = Column(Boolean, default=True, nullable=False)
    payment_succeeded = Column(Boolean, default=True, nullable=False)
    kb_processing_completed = Column(Boolean, default=True, nullable=False)

    digest_enabled = Column(Boolean, default=False, nullable=False)  # Different default!
    digest_frequency = Column(String(20), default="weekly", nullable=False)  # Different default!

    marketing = Column(Boolean, default=False, nullable=False)
    unsubscribe_token = Column(String, unique=True, nullable=False, default=lambda: secrets.token_urlsafe(32))

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
```

---

## Why This Matters (Context & Reasoning)

Notification preferences are a core user-facing feature that affects every communication sent by the platform — workspace invitations, billing receipts, content generation updates, knowledge base processing alerts, and marketing emails. When two separate models govern overlapping preference domains, the system cannot guarantee consistent behavior: a user who disables billing notifications expects ALL billing notifications to stop, regardless of delivery channel.

The current architecture forces every new feature that sends notifications to know about both models and check the right one — or risk ignoring user preferences. The `billing_email_service.py` checks `EmailPreferences` (line 276) but uses a column name `billing_notifications` (line 65) that does not exist on the `EmailPreferences` model (the field is split into `payment_succeeded`, `payment_failed`, etc.), so the `getattr(..., True)` fallback means billing emails are always sent regardless of user preference.

Consolidating into a single model eliminates this class of bugs entirely, reduces the number of database tables, simplifies the service layer, and creates a single source of truth for user notification preferences.

---

## Impact

- **Severity:** User notification preferences may be silently ignored. The `billing_email_service._check_preferences()` method always returns `True` for billing emails because it checks for `billing_notifications` which doesn't exist as a column on `EmailPreferences`.
- **Affected Users/Flows:** All users — affects every notification delivery decision (workspace invites, billing, content generation, knowledge base, digest, marketing).
- **Blast Radius:** System-wide. Touches the Users model relationships, the notification helper service, the billing email service, the email preferences service, email preferences routes, and potentially frontend notification settings UI.

---

## Recommended Solution

The recommended approach is to **keep `NotificationPreferences` as the single source of truth** (since it already has per-channel toggles) and **migrate the `unsubscribe_token` feature into it**, then deprecate and eventually remove `EmailPreferences`.

### Step 1: Add `unsubscribe_token` to NotificationPreferences

```python
# File: rext-backend/src/api/models/user_models/notification_preferences.py
# Add import at top of file:
import secrets

# Add after line 91 (after marketing_updates column):
    # Unsubscribe token for one-click email unsubscribe links
    unsubscribe_token = Column(
        String,
        unique=True,
        nullable=False,
        default=lambda: secrets.token_urlsafe(32)
    )
```

### Step 2: Create Alembic Migration to Add Column and Migrate Data

```python
# File: rext-backend/alembic/versions/<auto>_add_unsubscribe_token_to_notification_preferences.py
"""Add unsubscribe_token to notification_preferences and migrate from email_preferences."""

from alembic import op
import sqlalchemy as sa
import secrets


def upgrade():
    # Add unsubscribe_token column to notification_preferences
    op.add_column(
        'notification_preferences',
        sa.Column('unsubscribe_token', sa.String(), nullable=True, unique=True)
    )

    # Migrate existing unsubscribe tokens from email_preferences
    op.execute("""
        UPDATE notification_preferences np
        SET unsubscribe_token = ep.unsubscribe_token
        FROM email_preferences ep
        WHERE np.user_id = ep.user_id
        AND ep.unsubscribe_token IS NOT NULL
    """)

    # Generate tokens for any rows that still don't have one
    # (users who had notification_preferences but not email_preferences)
    connection = op.get_bind()
    result = connection.execute(
        sa.text("SELECT id FROM notification_preferences WHERE unsubscribe_token IS NULL")
    )
    for row in result:
        connection.execute(
            sa.text("UPDATE notification_preferences SET unsubscribe_token = :token WHERE id = :id"),
            {"token": secrets.token_urlsafe(32), "id": row[0]}
        )

    # Make the column non-nullable after populating
    op.alter_column('notification_preferences', 'unsubscribe_token', nullable=False)


def downgrade():
    op.drop_column('notification_preferences', 'unsubscribe_token')
```

### Step 3: Update BillingEmailService to Use NotificationPreferences

```python
# File: rext-backend/src/services/billing_email_service.py
# Replace import on line 15:
# OLD: from src.api.models.user_models.email_preferences import EmailPreferences
# NEW:
from src.api.models.user_models.notification_preferences import NotificationPreferences

# Replace _check_preferences method (lines 274-284):
    async def _check_preferences(self, user_id: UUID, preference_key: str) -> bool:
        """Check if user has billing notifications enabled."""
        query = select(NotificationPreferences).where(
            NotificationPreferences.user_id == user_id
        )
        result = await self.db.execute(query)
        prefs = result.scalar_one_or_none()

        if not prefs:
            return True  # Default to enabled if no preferences set

        # Check master email toggle first
        if not prefs.email_notifications:
            return False

        # Map billing preference keys to NotificationPreferences columns
        billing_pref_mapping = {
            "billing_notifications": "email_billing_updates",
            "payment_succeeded": "billing_payment_success",
            "payment_failed": "billing_payment_failed",
            "subscription_cancelled": "billing_subscription_cancelled",
            "trial_ending": "billing_trial_ending",
        }
        mapped_key = billing_pref_mapping.get(preference_key, preference_key)
        return getattr(prefs, mapped_key, True)
```

### Step 4: Update EmailPreferencesService to Use NotificationPreferences

```python
# File: rext-backend/src/services/email_preferences_service.py
# Replace the entire EmailPreferences import and update the service to work
# with NotificationPreferences instead. Key changes:

from src.api.models.user_models.notification_preferences import NotificationPreferences

class EmailPreferencesService:
    """Service for managing email preferences via NotificationPreferences model."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_preferences(self, user_id: UUID, db: AsyncSession) -> NotificationPreferences:
        """Get user preferences or create default if not exists."""
        result = await db.execute(
            select(NotificationPreferences).where(NotificationPreferences.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()

        if not prefs:
            prefs = NotificationPreferences(
                user_id=user_id,
                unsubscribe_token=secrets.token_urlsafe(32)
            )
            db.add(prefs)
            await db.flush()
            await db.refresh(prefs)
            logger.info(f"Created default notification preferences for user {user_id}")

        return prefs

    async def check_can_send(self, user_id: UUID, email_type: str, db: AsyncSession) -> bool:
        """Check if user allows this email type."""
        prefs = await self.get_or_create_preferences(user_id, db)

        # Check master email toggle first
        if not prefs.email_notifications:
            return False

        # Map email types to NotificationPreferences columns
        type_mapping = {
            "workspace_invitation": prefs.ws_invite_received,
            "invitation": prefs.ws_invite_received,
            "invitation_accepted": prefs.ws_invite_accepted,
            "role_changed": prefs.ws_role_changed,
            "member_removed": prefs.ws_member_removed,
            "marketing": prefs.marketing_updates,
        }

        return type_mapping.get(email_type, True)

    async def get_unsubscribe_link(self, user_id: UUID, frontend_url: str, db: AsyncSession) -> str:
        """Get unsubscribe link for user."""
        prefs = await self.get_or_create_preferences(user_id, db)
        return f"{frontend_url}/unsubscribe?token={prefs.unsubscribe_token}"
```

### Step 5: Update Email Preferences Routes

```python
# File: rext-backend/src/api/routes/users/email_preferences.py
# Update the route handlers to work with the unified model.
# The UpdatePreferencesRequest schema fields need to map to
# NotificationPreferences columns. Update the mapping in the
# update_preferences handler.
```

### Step 6: Update Users Model Relationships

```python
# File: rext-backend/src/api/models/user_models/users.py
# Line 51 can remain as-is (email_preferences relationship) for backward
# compatibility during the migration period. Once EmailPreferences table
# is dropped, remove this relationship.
```

### Step 7: Create Migration to Drop EmailPreferences Table (After Verification)

After confirming all services use `NotificationPreferences`, create a final migration to drop the `email_preferences` table. This should be done in a separate deployment cycle after the migration has been validated.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/services/email_helpers.py` | Various | May import or reference EmailPreferences for email sending decisions |
| `rext-backend/src/api/routes/workspaces/invitations.py/modules/invitation_list.py` | Various | References notification or email preferences for invitation emails |
| `rext-backend/src/api/routes/workspaces/invitations.py/modules/invitation_manage.py` | Various | References notification or email preferences for invitation management |
| `rext-backend/src/api/routes/users/auth.py` | Various | May create EmailPreferences during user registration |
| `rext-backend/src/api/routes/users/profile.py` | Various | Returns preference data in profile responses |
| `rext-backend/src/api/models/user_models/__init__.py` | Various | Exports EmailPreferences — needs update after removal |
| `rext-backend/src/api/schema/notification_schema.py` | Various | Schema definitions for notification preference API requests/responses |
| `rext-backend/src/api/registry/routes.py` | Various | Route registration for email preferences endpoints |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a user and check both `notification_preferences` and `email_preferences` tables — both should have rows for the same user
2. Call `PUT /user/email-preferences/` to set `digest_frequency: "monthly"` — this only updates `email_preferences`
3. Observe that `notification_preferences.digest_frequency` still says `"daily"` — the two tables are out of sync
4. Call the billing email service and observe that `_check_preferences` with `preference_key="billing_notifications"` always returns `True` because `EmailPreferences` has no `billing_notifications` column

### After Fix (Verify the Solution):
1. Create a new user — only `notification_preferences` should be created (with `unsubscribe_token`)
2. Verify `unsubscribe_token` is populated and unique
3. Update email preferences via API — changes should reflect in `notification_preferences`
4. Disable `email_billing_updates` on `NotificationPreferences` — billing emails should be blocked
5. Test the unsubscribe endpoint with the token from `notification_preferences`
6. Verify existing users' tokens were migrated from `email_preferences` to `notification_preferences`

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "notification" --no-header
cd rext-backend && python -m pytest tests/ -v -k "email_pref" --no-header
cd rext-backend && python -m pytest tests/ -v -k "billing" --no-header
```

---

## Acceptance Criteria

- [ ] `NotificationPreferences` model has an `unsubscribe_token` column
- [ ] Alembic migration successfully adds the column and migrates existing tokens
- [ ] `BillingEmailService` checks `NotificationPreferences` instead of `EmailPreferences`
- [ ] `EmailPreferencesService` reads/writes `NotificationPreferences`
- [ ] Email preferences API routes function correctly with the unified model
- [ ] Unsubscribe endpoint works with tokens from `NotificationPreferences`
- [ ] No references to `EmailPreferences` remain in service layer (except the model file itself for migration period)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy JSONB PostgreSQL Dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#sqlalchemy.dialects.postgresql.JSONB) — For potential future migration to JSONB-based preference storage
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [PostgreSQL JSONB with SQLAlchemy patterns](https://fullstack.rocks/article/sqlalchemy/brewing_with_sqlalchemy/sqlalchemy_json_and_jsonb) — Reference for JSONB-based flexible preference schemas if the boolean column approach becomes unwieldy
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-049 (EmailPreferences missing SerializableMixin — will be resolved when EmailPreferences is deprecated), TASK-045 (deprecated `datetime.utcnow()` — the `NotificationPreferences` model still uses `datetime.utcnow` on lines 96-101)
