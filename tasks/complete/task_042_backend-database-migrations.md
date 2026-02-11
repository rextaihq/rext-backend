# Task 042: Standardize Inconsistent Timestamp Column Types Across Models

## Metadata
- **Task ID:** TASK-042
- **Source:** Backend Database & Migrations Audit (Finding #20 under P2 Medium)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P2 Medium
- **Category:** refactoring
- **Effort Estimate:** large (4+ hours)

---

## Description

The Rext backend uses four different SQLAlchemy column types for timestamp columns across its 33+ ORM models, creating an inconsistent data layer that can lead to subtle timezone-related bugs. The four patterns are:

1. **`TIMESTAMP` (no timezone)** — Used by the majority of models including `Users`, `Role`, `Permission`, `UserRole`, `RolePermission`, `UserInvitations`, `TokenBlacklist`, `NotificationPreferences`, `UserSession`, `OAuthAccount`, `EmailTemplate`, `SubscriptionPlan`, `UserSubscription`, `Media`, `AuditLog`, `PlatformAdminInvitations`, `Notification`, `WorkspaceMembers`, `PaymentMethod`, `WebhookEvent`, `License`, `Refund`. These map to PostgreSQL `TIMESTAMP WITHOUT TIME ZONE`, storing naive datetimes with no timezone information.

2. **`DateTime(timezone=True)`** — Used by `WorkspaceModel`, `Content`, `ContentSEOData`, `EmailLog`, `EmailEvent`, `UserOnboarding`, `KnowledgeBase`, `BrandVoice`, `KnowledgeFiles`, `TextKnowledge`, `Persona`, `WorkspaceIntegration`, `KnowledgeEmbedding`. These map to PostgreSQL `TIMESTAMP WITH TIME ZONE`, which stores timezone-aware timestamps.

3. **`DateTime` (no timezone)** — Used by `UserPreferences`, `EmailPreferences`, `ImpersonationSession`, `CustomerNote`, `ErrorLog`. These also map to PostgreSQL `TIMESTAMP WITHOUT TIME ZONE`, same as pattern 1 but using a different SQLAlchemy type class.

4. **`TIMESTAMP(timezone=True)`** — Used by `LicenseActivation`, `DiscountUsage`, `TrialConversion`, `ContentMedia`. These map to PostgreSQL `TIMESTAMP WITH TIME ZONE`, same database behavior as pattern 2 but using the `TIMESTAMP` SQLAlchemy type with the timezone flag.

According to the SQLAlchemy 2.0 documentation, `DateTime(timezone=True)` is the recommended portable way to express timezone-aware timestamps. PostgreSQL treats both `TIMESTAMP WITH TIME ZONE` and `DateTime(timezone=True)` identically at the database level — both store UTC internally and convert on output based on the session's timezone setting. However, mixing timezone-aware and timezone-naive columns means that comparisons between models (e.g., joining `Users.created_at` with `Content.created_at`) can produce incorrect results if the server's timezone is not UTC, because naive timestamps have no timezone context.

The project runs on Python 3.11 (`requires-python = ">=3.11,<3.12"` in `pyproject.toml`), and since Python 3.12 officially deprecated `datetime.utcnow()` (which returns naive datetimes), standardizing on timezone-aware columns now prepares the codebase for the inevitable Python upgrade.

---

## Current Code

The four patterns are demonstrated below:

```python
# Pattern 1: TIMESTAMP (no timezone) — e.g., Users model
# File: rext-backend/src/api/models/user_models/users.py
# Lines: 38-41
created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
deactivated_at = Column(TIMESTAMP)
deleted_at = Column(TIMESTAMP)
```

```python
# Pattern 2: DateTime(timezone=True) — e.g., WorkspaceModel
# File: rext-backend/src/api/models/workspace_models/workspace_model.py
# Lines: 21-23
created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)
deleted_at = Column(DateTime(timezone=True), nullable=True)
```

```python
# Pattern 3: DateTime (no timezone) — e.g., UserPreferences
# File: rext-backend/src/api/models/user_models/user_preferences.py
# Lines: 32-33
created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
```

```python
# Pattern 4: TIMESTAMP(timezone=True) — e.g., LicenseActivation
# File: rext-backend/src/api/models/subscription_models/license_activations.py
# Lines: 71-75
activated_at: Mapped[datetime] = mapped_column(
    TIMESTAMP(timezone=True),
    nullable=False,
    server_default=func.current_timestamp()
)
```

---

## Why This Matters (Context & Reasoning)

Rext is a multi-tenant SaaS platform with users across multiple timezones. The `workspace.timezone` field (line 19 of `workspace_model.py`) confirms that timezone-awareness is a product requirement. When timestamp columns store naive datetimes (patterns 1 and 3), any comparison against timezone-aware datetimes (patterns 2 and 4) produces either a Python `TypeError` or a silent incorrect result depending on the database driver.

For example, if a background task compares `subscription.created_at` (TIMESTAMP, naive) against `datetime.now(timezone.utc)` (timezone-aware), the comparison could fail or produce wrong results. This is especially dangerous for time-sensitive business logic like trial expiration checks, subscription renewal dates, and grace period calculations.

Standardizing on `DateTime(timezone=True)` throughout the codebase ensures:
- All timestamps are stored as `TIMESTAMP WITH TIME ZONE` in PostgreSQL
- Python-side comparisons between any two model timestamps work correctly
- The codebase is compatible with Python 3.12+'s timezone-aware best practices
- New developers cannot accidentally introduce timezone bugs by following inconsistent patterns

---

## Impact

- **Severity:** Subtle timezone-related comparison bugs may produce incorrect trial expirations, grace period calculations, or session timeout decisions. Mixing naive and aware datetimes causes `TypeError` in strict comparison contexts.
- **Affected Users/Flows:** All time-sensitive operations — subscription management, trial expiry, token expiry, session management, audit logging, invitation expiry.
- **Blast Radius:** System-wide. Every model with timestamp columns is affected. This is a horizontal concern across all features.

---

## Recommended Solution

### Step 1: Create Alembic Migration to Alter Column Types

Generate a migration that converts all `TIMESTAMP WITHOUT TIME ZONE` columns to `TIMESTAMP WITH TIME ZONE`. PostgreSQL handles this conversion by assuming existing naive values are in UTC.

```python
# File: rext-backend/alembic/versions/<auto-generated>_standardize_timestamp_types.py
"""Standardize all timestamp columns to TIMESTAMP WITH TIME ZONE."""

from alembic import op
import sqlalchemy as sa

revision = '<auto-generated>'
down_revision = '<current-head>'
branch_labels = None
depends_on = None


# All columns that need to be altered from TIMESTAMP WITHOUT TIME ZONE
# to TIMESTAMP WITH TIME ZONE
COLUMNS_TO_ALTER = [
    # users table
    ("users", "password_changed_at"),
    ("users", "locked_until"),
    ("users", "email_verified_at"),
    ("users", "last_login_at"),
    ("users", "created_at"),
    ("users", "updated_at"),
    ("users", "deactivated_at"),
    ("users", "deleted_at"),
    # roles table
    ("roles", "created_at"),
    ("roles", "updated_at"),
    # permissions table
    ("permissions", "created_at"),
    # user_roles table
    ("user_roles", "assigned_at"),
    # role_permissions table
    ("role_permissions", "created_at"),
    # user_invitations table
    ("user_invitations", "created_at"),
    ("user_invitations", "expires_at"),
    # token_blacklist table
    ("token_blacklist", "revoked_at"),
    ("token_blacklist", "expires_at"),
    # notification_preferences table
    ("notification_preferences", "created_at"),
    ("notification_preferences", "updated_at"),
    # user_sessions table
    ("user_sessions", "created_at"),
    ("user_sessions", "last_activity_at"),
    ("user_sessions", "expires_at"),
    ("user_sessions", "revoked_at"),
    # oauth_accounts table
    ("oauth_accounts", "token_expires_at"),
    ("oauth_accounts", "created_at"),
    ("oauth_accounts", "updated_at"),
    ("oauth_accounts", "last_used_at"),
    # workspace_members table
    ("workspace_members", "joined_at"),
    ("workspace_members", "last_activity_at"),
    # email_templates table
    ("email_templates", "created_at"),
    ("email_templates", "updated_at"),
    # subscription_plans table
    ("subscription_plans", "created_at"),
    ("subscription_plans", "updated_at"),
    # user_subscriptions table
    ("user_subscriptions", "start_date"),
    ("user_subscriptions", "end_date"),
    ("user_subscriptions", "trial_end_date"),
    ("user_subscriptions", "cancelled_at"),
    ("user_subscriptions", "renews_at"),
    ("user_subscriptions", "ends_at"),
    ("user_subscriptions", "grace_period_end"),
    ("user_subscriptions", "payment_failed_at"),
    ("user_subscriptions", "usage_reset_date"),
    ("user_subscriptions", "created_at"),
    ("user_subscriptions", "updated_at"),
    # media table
    ("media", "created_at"),
    ("media", "updated_at"),
    ("media", "deleted_at"),
    # audit_logs table
    ("audit_logs", "created_at"),
    # notifications table
    ("notifications", "read_at"),
    ("notifications", "archived_at"),
    ("notifications", "deleted_at"),
    ("notifications", "email_sent_at"),
    ("notifications", "sse_sent_at"),
    ("notifications", "expires_at"),
    ("notifications", "created_at"),
    ("notifications", "updated_at"),
    # user_preferences table
    ("user_preferences", "created_at"),
    ("user_preferences", "updated_at"),
    # email_preferences table
    ("email_preferences", "created_at"),
    ("email_preferences", "updated_at"),
    # impersonation_sessions table
    ("impersonation_sessions", "invalidated_at"),
    ("impersonation_sessions", "created_at"),
    # customer_notes table
    ("customer_notes", "created_at"),
    ("customer_notes", "updated_at"),
    # error_logs table
    ("error_logs", "timestamp"),
    ("error_logs", "resolved_at"),
    # licenses table
    ("licenses", "activated_at"),
    ("licenses", "expires_at"),
    ("licenses", "created_at"),
    ("licenses", "updated_at"),
    # payment_methods table
    ("payment_methods", "created_at"),
    ("payment_methods", "updated_at"),
    # webhook_events table
    ("webhook_events", "processed_at"),
    ("webhook_events", "created_at"),
    ("webhook_events", "updated_at"),
    # refunds table
    ("refunds", "processed_at"),
    ("refunds", "created_at"),
    ("refunds", "updated_at"),
]


def upgrade() -> None:
    for table, column in COLUMNS_TO_ALTER:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.TIMESTAMP(),
            existing_nullable=True,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'"
        )


def downgrade() -> None:
    for table, column in COLUMNS_TO_ALTER:
        op.alter_column(
            table,
            column,
            type_=sa.TIMESTAMP(),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
        )
```

**Note:** Verify each table name matches the actual `__tablename__` in the models before running.

### Step 2: Update All Model Files to Use `DateTime(timezone=True)`

For every model using `TIMESTAMP` or `DateTime` without timezone, change the column type to `DateTime(timezone=True)`. Example for `users.py`:

```python
# File: rext-backend/src/api/models/user_models/users.py
# Replace imports: change TIMESTAMP to DateTime if not already imported
from sqlalchemy import (
    Column, String, Boolean, Integer, Text, DateTime,
    ForeignKey, UniqueConstraint
)

# Replace all TIMESTAMP columns with DateTime(timezone=True):
password_changed_at = Column(DateTime(timezone=True))
locked_until = Column(DateTime(timezone=True))
email_verified_at = Column(DateTime(timezone=True))
last_login_at = Column(DateTime(timezone=True))
created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
deactivated_at = Column(DateTime(timezone=True))
deleted_at = Column(DateTime(timezone=True))
```

Repeat this pattern for all models listed in patterns 1 and 3 above. For models already using pattern 4 (`TIMESTAMP(timezone=True)`), change to `DateTime(timezone=True)` for consistency.

### Step 3: Update Imports in Each Model File

Remove `TIMESTAMP` from imports where it is no longer used, and ensure `DateTime` is imported:

```python
# Before:
from sqlalchemy import Column, String, Boolean, TIMESTAMP, ForeignKey

# After:
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/models/user_models/roles.py` | `28-29` | TIMESTAMP on created_at, updated_at |
| `src/api/models/user_models/permissions.py` | `22` | TIMESTAMP on created_at |
| `src/api/models/user_models/user_roles.py` | `23` | TIMESTAMP on assigned_at |
| `src/api/models/user_models/role_permissions.py` | `17` | TIMESTAMP on created_at |
| `src/api/models/user_models/invitations.py` | `18-19` | TIMESTAMP on created_at, expires_at |
| `src/api/models/user_models/token_blacklist.py` | `29-30` | TIMESTAMP on revoked_at, expires_at |
| `src/api/models/user_models/notification_preferences.py` | `96-100` | TIMESTAMP on created_at, updated_at |
| `src/api/models/user_models/user_sessions.py` | `39-42` | TIMESTAMP on created_at, last_activity_at, expires_at, revoked_at |
| `src/api/models/user_models/oauth_accounts.py` | `39, 47-49` | TIMESTAMP on multiple columns |
| `src/api/models/workspace_models/workspace_member.py` | `21-22` | TIMESTAMP on joined_at, last_activity_at |
| `src/api/models/workspace_models/email_template.py` | `41-42` | TIMESTAMP on created_at, updated_at |
| `src/api/models/subscription_models/plans.py` | `46-47` | TIMESTAMP on created_at, updated_at |
| `src/api/models/subscription_models/subscriptions.py` | `43-74` | TIMESTAMP on ~10 columns |
| `src/api/models/subscription_models/licenses.py` | `44-47` | TIMESTAMP on 4 columns |
| `src/api/models/subscription_models/payment_methods.py` | `39-40` | TIMESTAMP on created_at, updated_at |
| `src/api/models/subscription_models/webhooks.py` | `23, 30-31` | TIMESTAMP on 3 columns |
| `src/api/models/subscription_models/refunds.py` | `94-96` | TIMESTAMP on 3 columns |
| `src/api/models/media_models/media.py` | `100-102` | TIMESTAMP on created_at, updated_at, deleted_at |
| `src/api/models/audit_models/audit_logs.py` | `44` | TIMESTAMP on created_at |
| `src/api/models/admin_models/admin_invitations.py` | `116-157` | TIMESTAMP on multiple columns |
| `src/api/models/notification/notification_model.py` | `104-158` | TIMESTAMP on ~8 columns |
| `src/api/models/user_models/user_preferences.py` | `32-33` | DateTime (no tz) on created_at, updated_at |
| `src/api/models/user_models/email_preferences.py` | `58-59` | DateTime (no tz) on created_at, updated_at |
| `src/api/models/user_models/impersonation_session.py` | `25-26` | DateTime (no tz) on invalidated_at, created_at |
| `src/api/models/admin_models/customer_note.py` | `36-40` | DateTime (no tz) on created_at, updated_at |
| `src/api/models/admin_models/error_log.py` | `22, 35` | DateTime (no tz) on timestamp, resolved_at |
| `src/api/models/subscription_models/license_activations.py` | `72-84` | TIMESTAMP(timezone=True) — change to DateTime(timezone=True) |
| `src/api/models/subscription_models/discount_usage.py` | `87` | TIMESTAMP(timezone=True) — change to DateTime(timezone=True) |
| `src/api/models/subscription_models/trial_conversions.py` | `46-97` | TIMESTAMP(timezone=True) — change to DateTime(timezone=True) |
| `src/api/models/content_models/content_media.py` | `59` | TIMESTAMP(timezone=True) — change to DateTime(timezone=True) |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open a Python shell in the backend environment: `cd rext-backend && python -c "from src.api.models.user_models.users import Users; from src.api.models.workspace_models.workspace_model import WorkspaceModel; print(type(Users.created_at.type)); print(type(WorkspaceModel.created_at.type))"`
2. Observe that Users uses `TIMESTAMP` and WorkspaceModel uses `DateTime` — different types for the same semantic purpose.

### After Fix (Verify the Solution):
1. Run the same check — all models should report `DateTime` with `timezone=True`.
2. Verify the Alembic migration runs successfully: `cd rext-backend && alembic upgrade head`
3. Connect to PostgreSQL and verify column types: `SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'users' AND column_name IN ('created_at', 'updated_at');` — should show `timestamp with time zone`.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v
```

---

## Acceptance Criteria

- [ ] All model timestamp columns use `DateTime(timezone=True)` — no `TIMESTAMP`, `DateTime()`, or `TIMESTAMP(timezone=True)` remain
- [ ] Alembic migration converts all existing `TIMESTAMP WITHOUT TIME ZONE` columns to `TIMESTAMP WITH TIME ZONE`
- [ ] All `TIMESTAMP` imports removed from model files where they are no longer used
- [ ] Existing data is preserved correctly (PostgreSQL interprets naive timestamps as UTC during conversion)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 — Column and Data Types](https://docs.sqlalchemy.org/en/20/core/type_basics.html) — documents `DateTime(timezone=True)` as the recommended approach
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Ensuring Timestamp Storage in UTC with SQLAlchemy](https://mike.depalatis.net/blog/sqlalchemy-timestamps.html) — explains why `DateTime(timezone=True)` with UTC defaults is the correct pattern
- **Related Issues/PRs:** [SQLAlchemy Discussion #10212](https://github.com/sqlalchemy/sqlalchemy/discussions/10212) — community discussion on timestamp type with server defaults

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-045 (Deprecated datetime.utcnow — column defaults should be updated in the same pass), TASK-043 (Missing Timestamps — new timestamp columns should use the standardized type), TASK-004 (B1 datetime.utcnow deprecation in auth code)
