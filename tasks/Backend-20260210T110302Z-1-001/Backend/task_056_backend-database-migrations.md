# Task 056: Separate Seed Data from Alembic Migration Chain

## Metadata
- **Task ID:** TASK-056
- **Source:** Backend Database & Migrations Audit (Finding #30 under P3 Low)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P3 Low
- **Category:** refactoring
- **Effort Estimate:** large (4+ hours)

---

## Description

The Rext backend's Alembic migration chain contains 5 seed migration files (`seed005` through `seed009`) interleaved with schema migrations, plus additional data migrations scattered throughout the 112-file migration chain. These seed migrations insert initial application data (email templates, RBAC permissions, license permissions, media permissions) directly within the Alembic version history, making it impossible to re-seed data independently of schema migrations.

The 5 seed migration files are:

1. **`seed005_default_email_templates.py`** — Inserts 5 default email templates (workspace invitation, invitation accepted, role changed, member removed, welcome) with `workspace_id = NULL` for global defaults. Reads from environment and uses `datetime.utcnow()`. Depends on revision `cc6f7933fed1`.

2. **`seed006_additional_rbac_permissions.py`** — Seeds additional RBAC permission records into the `permissions` table.

3. **`seed007_license_permissions.py`** — Seeds license-related permission records.

4. **`seed008_media_permissions.py`** — Seeds media management permission records.

5. **`seed009_comprehensive_rbac_permissions.py`** — Seeds a comprehensive set of RBAC permissions covering all application features.

These seed migrations are problematic because:

- **They run as part of `alembic upgrade head`**, meaning schema migrations and data seeding are coupled. A fresh deployment must run all seed migrations in sequence, and there is no way to re-seed data without running the full migration chain.

- **They are not idempotent by default.** While `seed005` checks for existing templates before inserting, the behavior of `seed006-009` would need verification. Running migrations on a database that already has seed data could create duplicates or fail with unique constraint violations.

- **They use deprecated APIs.** `seed005` (line 167-168) uses `datetime.utcnow()` for timestamps, which is deprecated in Python 3.12+ (see TASK-045).

- **They couple data concerns with schema concerns.** Alembic's design philosophy and [official documentation](https://alembic.sqlalchemy.org/en/latest/cookbook.html) explicitly note that data migrations "don't fit in the schema migration model at all" and recommend that "data migrations may very well need to be completely separate and outside of schema migrations totally."

- **Environment variables must be set correctly during migration.** If seed migrations reference settings or env vars, the migration environment must be configured identically to the application environment, which may not be the case in all deployment pipelines.

---

## Current Code

```python
# File: rext-backend/alembic/versions/seed005_default_email_templates.py
# Lines: 1-185 (full file)
# Revision ID: seed005
# Depends on: cc6f7933fed1

def upgrade() -> None:
    """Seed default email templates for all template types."""
    connection = op.get_bind()

    from sqlalchemy import inspect
    inspector = inspect(connection)
    if 'email_templates' not in inspector.get_table_names():
        print("⚠️ email_templates table does not exist. Skipping seed migration.")
        return

    templates = [
        {
            'template_type': 'workspace_invitation',
            'subject': 'You\'ve been invited to join {workspace_name}',
            'body': '...',  # Full template text
        },
        # ... 4 more templates ...
    ]

    for template in templates:
        result = connection.execute(
            sa.text("SELECT id FROM email_templates WHERE template_type = :type AND workspace_id IS NULL"),
            {'type': template['template_type']}
        )
        existing = result.fetchone()
        if existing:
            continue
        connection.execute(sa.text("INSERT INTO email_templates ..."), {
            'template_type': template['template_type'],
            'created_at': datetime.utcnow(),  # Deprecated!
            'updated_at': datetime.utcnow(),
        })

def downgrade() -> None:
    """Remove default email templates."""
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM email_templates WHERE is_default = true AND workspace_id IS NULL")
    )
```

---

## Why This Matters (Context & Reasoning)

In a SaaS application like Rext, seed data (default permissions, email templates, subscription plans) needs to be managed independently of database schema migrations. Common scenarios where this matters:

1. **Re-seeding after data corruption:** If permission records are accidentally deleted, you need to re-seed them without running `alembic upgrade head` (which may already be at the latest revision).

2. **Different seed data per environment:** Development, staging, and production may need different seed data (e.g., test permissions in dev, full permissions in prod). Migration-based seeds provide no mechanism for environment-specific data.

3. **Migration squashing:** If the team decides to squash the migration chain (a common practice mentioned in TASK-038), seed migrations interleaved with schema migrations make squashing much more complex.

4. **CI/CD pipelines:** Schema migrations should be fast and deterministic. Seed migrations that read environment variables or perform conditional logic add unpredictability.

The [Alembic documentation](https://alembic.sqlalchemy.org/en/latest/cookbook.html) and [community discussions](https://github.com/sqlalchemy/alembic/discussions/972) consistently recommend separating data migrations from schema migrations, especially for seed data that may need to be re-applied.

---

## Impact

- **Severity:** Not a runtime bug. Architectural concern that limits operational flexibility: cannot re-seed independently, cannot customize seed data per environment, increases migration chain complexity.
- **Affected Users/Flows:** DevOps engineers running migrations in deployment pipelines, developers setting up local environments, QA teams provisioning test databases.
- **Blast Radius:** Affects the entire migration chain (112 files) and deployment workflow. The actual fix is additive (create new scripts) with optional removal of old migrations.

---

## Recommended Solution

Create standalone seed scripts that can be run independently of Alembic. Keep the existing seed migrations in the Alembic chain for backward compatibility (they are already applied in existing databases), but all future data seeding should use the new scripts.

### Step 1: Create the seed scripts directory

```bash
mkdir -p rext-backend/scripts/seeds
```

### Step 2: Create a seed runner utility

```python
# File: rext-backend/scripts/seeds/__init__.py
"""
Standalone seed data scripts for the Rext backend.

Usage:
    # Seed all data:
    python -m scripts.seeds.run_all

    # Seed specific category:
    python -m scripts.seeds.seed_email_templates
    python -m scripts.seeds.seed_permissions
"""
```

```python
# File: rext-backend/scripts/seeds/base.py
"""Base utilities for seed scripts."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.api.config import get_settings


@asynccontextmanager
async def get_seed_session():
    """Create an async database session for seeding."""
    settings = get_settings()
    db_url = settings.POSTGRES_URI_CUSTOM
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()


def utc_now() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)
```

### Step 3: Create the email templates seed script

```python
# File: rext-backend/scripts/seeds/seed_email_templates.py
"""Seed default email templates."""

import asyncio
from sqlalchemy import select, text

from scripts.seeds.base import get_seed_session, utc_now


TEMPLATES = [
    {
        "template_type": "workspace_invitation",
        "subject": "You've been invited to join {workspace_name}",
        "body": """Hello {invitee_name},

{inviter_name} has invited you to join the workspace "{workspace_name}" as a {role_name}.

Click the link below to accept your invitation:
{invitation_url}

This invitation will expire in 7 days.

Best regards,
The Rext Team""",
    },
    {
        "template_type": "invitation_accepted",
        "subject": "{invitee_name} has accepted your invitation",
        "body": """Hello {inviter_name},

Good news! {invitee_name} ({invitee_email}) has accepted your invitation to join "{workspace_name}".

They now have {role_name} access to your workspace.

Best regards,
The Rext Team""",
    },
    {
        "template_type": "role_changed",
        "subject": "Your role has been updated in {workspace_name}",
        "body": """Hello {member_name},

Your role in the workspace "{workspace_name}" has been updated to {role_name}.

This change affects your permissions and access levels within the workspace.

If you have any questions about your new role, please contact your workspace administrator.

Best regards,
The Rext Team""",
    },
    {
        "template_type": "member_removed",
        "subject": "You have been removed from {workspace_name}",
        "body": """Hello {member_name},

You have been removed from the workspace "{workspace_name}".

You no longer have access to this workspace and its content.

If you believe this was done in error, please contact the workspace administrator.

Best regards,
The Rext Team""",
    },
    {
        "template_type": "welcome",
        "subject": "Welcome to {workspace_name}!",
        "body": """Hello {member_name},

Welcome to "{workspace_name}"! We're excited to have you on board.

You've been granted {role_name} access. Here's what you can do to get started:

1. Complete your profile
2. Explore the workspace features
3. Connect with other team members
4. Start creating content

If you have any questions, don't hesitate to reach out to your workspace administrator.

Best regards,
The Rext Team""",
    },
]


async def seed_email_templates():
    """Seed default email templates (idempotent — skips existing)."""
    async with get_seed_session() as session:
        created = 0
        skipped = 0

        for template in TEMPLATES:
            result = await session.execute(
                text("SELECT id FROM email_templates WHERE template_type = :type AND workspace_id IS NULL"),
                {"type": template["template_type"]},
            )
            existing = result.fetchone()

            if existing:
                skipped += 1
                continue

            now = utc_now()
            await session.execute(
                text("""
                    INSERT INTO email_templates (
                        id, workspace_id, template_type, subject, body,
                        is_active, is_default, created_at, updated_at
                    ) VALUES (
                        gen_random_uuid(), NULL, :template_type, :subject, :body,
                        true, true, :created_at, :updated_at
                    )
                """),
                {
                    "template_type": template["template_type"],
                    "subject": template["subject"],
                    "body": template["body"],
                    "created_at": now,
                    "updated_at": now,
                },
            )
            created += 1

        print(f"Email templates: {created} created, {skipped} already existed")


if __name__ == "__main__":
    asyncio.run(seed_email_templates())
```

### Step 4: Create the permissions seed script

```python
# File: rext-backend/scripts/seeds/seed_permissions.py
"""Seed RBAC permissions. Consolidates seed006-seed009 into a single idempotent script."""

import asyncio
from sqlalchemy import text

from scripts.seeds.base import get_seed_session, utc_now


# Consolidate all permissions from seed006-seed009 here
# Each permission: (name, display_name, description, resource, action)
PERMISSIONS = [
    # Add all permission definitions from seed006-seed009 here
    # Example:
    # ("content:create", "Create Content", "Allow creating content", "content", "create"),
    # ... (extract from actual seed migration files)
]


async def seed_permissions():
    """Seed RBAC permissions (idempotent — skips existing by name)."""
    async with get_seed_session() as session:
        created = 0
        skipped = 0

        for name, display_name, description, resource, action in PERMISSIONS:
            result = await session.execute(
                text("SELECT id FROM permissions WHERE name = :name"),
                {"name": name},
            )
            if result.fetchone():
                skipped += 1
                continue

            now = utc_now()
            await session.execute(
                text("""
                    INSERT INTO permissions (id, name, display_name, description, resource, action, created_at)
                    VALUES (gen_random_uuid(), :name, :display_name, :description, :resource, :action, :created_at)
                """),
                {
                    "name": name,
                    "display_name": display_name,
                    "description": description,
                    "resource": resource,
                    "action": action,
                    "created_at": now,
                },
            )
            created += 1

        print(f"Permissions: {created} created, {skipped} already existed")


if __name__ == "__main__":
    asyncio.run(seed_permissions())
```

### Step 5: Create a unified seed runner

```python
# File: rext-backend/scripts/seeds/run_all.py
"""Run all seed scripts in order."""

import asyncio

from scripts.seeds.seed_email_templates import seed_email_templates
from scripts.seeds.seed_permissions import seed_permissions


async def run_all_seeds():
    """Run all seed scripts."""
    print("=" * 50)
    print("Running all seed scripts...")
    print("=" * 50)

    await seed_email_templates()
    await seed_permissions()

    print("=" * 50)
    print("All seeds completed.")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(run_all_seeds())
```

### Step 6: Document the migration

Add a note to the existing seed migrations indicating they are superseded:

```python
# Add at the top of each seed migration file (seed005-seed009):
# NOTE: This seed migration is superseded by scripts/seeds/.
# It remains in the migration chain for backward compatibility with existing databases.
# For new environments, use: python -m scripts.seeds.run_all
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/alembic/versions/seed005_default_email_templates.py` | All | Email template seed — to be superseded by `scripts/seeds/seed_email_templates.py` |
| `rext-backend/alembic/versions/seed006_additional_rbac_permissions.py` | All | RBAC permissions seed — to be consolidated into `scripts/seeds/seed_permissions.py` |
| `rext-backend/alembic/versions/seed007_license_permissions.py` | All | License permissions — to be consolidated into `scripts/seeds/seed_permissions.py` |
| `rext-backend/alembic/versions/seed008_media_permissions.py` | All | Media permissions — to be consolidated into `scripts/seeds/seed_permissions.py` |
| `rext-backend/alembic/versions/seed009_comprehensive_rbac_permissions.py` | All | Comprehensive RBAC — to be consolidated into `scripts/seeds/seed_permissions.py` |
| `rext-backend/pyproject.toml` | 66-67 | Scripts section — may add a `seed` command entry |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Run `alembic history | grep seed` to see seed migrations interleaved in the chain
2. Try to re-seed email templates without running `alembic upgrade head` — there is no mechanism to do so
3. Try to seed a fresh database without Alembic: impossible, because seed data is locked inside migration files

### After Fix (Verify the Solution):
1. Verify standalone seed scripts exist in `rext-backend/scripts/seeds/`
2. Create a test database and run schema migrations only: `alembic upgrade head`
3. Run the standalone seed script: `cd rext-backend && python -m scripts.seeds.run_all`
4. Verify email templates were created: query the `email_templates` table
5. Verify permissions were created: query the `permissions` table
6. Run the seed script again (idempotency test): should report "already existed" for all records
7. Verify existing databases with seed migrations already applied are unaffected

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v --no-header
```

---

## Acceptance Criteria

- [ ] `scripts/seeds/` directory exists with seed scripts for email templates and permissions
- [ ] `scripts/seeds/base.py` provides async session management utility
- [ ] `scripts/seeds/run_all.py` runs all seeds in order
- [ ] All seed scripts are idempotent (safe to run multiple times)
- [ ] All seed scripts use `datetime.now(timezone.utc)` instead of deprecated `datetime.utcnow()`
- [ ] Existing seed migrations (seed005-seed009) remain in the Alembic chain for backward compatibility
- [ ] Existing seed migrations are annotated with a comment pointing to the new scripts
- [ ] A fresh database can be seeded using `python -m scripts.seeds.run_all` after `alembic upgrade head`
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Alembic Cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html) — Official Alembic documentation noting that data migrations "don't fit in the schema migration model"
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Alembic Discussion #972 — Document how to do data migrations](https://github.com/sqlalchemy/alembic/discussions/972) — Community discussion on separating data migrations from schema migrations
- **Related Issues/PRs:** [Alembic Discussion #1259 — Managing large sets of Alembic files](https://github.com/sqlalchemy/alembic/discussions/1259) — Discussion on migration chain management best practices

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-038 (15 Merge Migrations — migration chain cleanup is easier when seed data is separate), TASK-040 (Hand-crafted Revision IDs — seed migrations use custom IDs like `seed005`), TASK-045 (Deprecated datetime.utcnow — seed005 uses it at line 167-168)
