# Task 040: Standardize Migration Revision IDs to Alembic Conventions

## Metadata
- **Task ID:** TASK-040
- **Source:** Backend Database & Migrations Audit (Finding #14 under P1 High)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P1 High
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The Alembic migration chain contains numerous hand-crafted revision IDs that deviate from Alembic's standard random hex string format. Alembic generates 12-character lowercase hexadecimal revision IDs by default (e.g., `625b40a3c6ba`). The codebase contains at least 20 migrations with non-standard IDs falling into several categories:

**Category 1: Custom Prefixes (14 migrations)**
- `seed005`, `seed006`, `seed007`, `seed008`, `seed009` - Seed data migrations
- `admin001` - Admin invitation migration
- `inv001`, `inv002` - Invitation migrations
- `ls20251020`, `onb20251020`, `rem20251020` - LemonSqueezy, onboarding, removal migrations
- `pgv001`, `pgv002`, `pgv003` - PgVector migrations
- `20251111_bio_notif` - Bio/notification migration

**Category 2: Fake Hex with Invalid Characters (5 migrations)**
These IDs look like hex but contain letters g-m which are not valid hexadecimal:
- `b2c3d4e5f6g7` (contains 'g')
- `c3d4e5f6g7h8` (contains 'g', 'h')
- `d1e2f3g4h5i6` (contains 'g', 'h', 'i')
- `g1h2i3j4k5l6` (contains 'g', 'h', 'i', 'j', 'k', 'l')
- `h2i3j4k5l6m7` (contains 'h', 'i', 'j', 'k', 'l', 'm')

While these non-standard IDs do not break Alembic functionality (Alembic treats revision IDs as opaque strings), they create several problems:

1. **Inconsistency:** Developers expect Alembic IDs to be random hex strings; custom prefixes and patterns create confusion
2. **Tooling assumptions:** Some Alembic tooling or scripts may assume hex-only IDs
3. **False patterns:** The fake hex IDs (b2c3d4e5f6g7) look like auto-generated IDs at first glance but are actually hand-crafted, making it hard to identify which migrations were auto-generated vs manual
4. **Maintenance burden:** Understanding the ID scheme requires knowledge not documented anywhere

---

## Current Code

**Examples of custom prefix IDs:**

```python
# File: rext-backend/alembic/versions/seed007_license_permissions.py
revision = 'seed007'
down_revision = 'ls20251020'
```

```python
# File: rext-backend/alembic/versions/admin001_create_admin_invitations.py
revision = 'admin001'
down_revision = 'seed008'
```

```python
# File: rext-backend/alembic/versions/pgv002_create_knowledge_embeddings_table.py
revision: str = "pgv002"
down_revision: Union[str, Sequence[str], None] = "pgv001"
```

**Examples of fake hex IDs:**

```python
# File: rext-backend/alembic/versions/b2c3d4e5f6g7_fix_user_sessions_duplicate_indexes.py
revision: str = 'b2c3d4e5f6g7'  # 'g' is not valid hex
```

```python
# File: rext-backend/alembic/versions/g1h2i3j4k5l6_add_email_templates_table.py
revision: str = 'g1h2i3j4k5l6'  # 'g', 'h', 'i', 'j', 'k', 'l' are all invalid hex
```

**Complete list of non-standard revision IDs:**

| File | Revision ID | Type |
|------|-------------|------|
| `seed005_default_email_templates.py` | `seed005` | Custom prefix |
| `seed006_additional_rbac_permissions.py` | `seed006` | Custom prefix |
| `seed007_license_permissions.py` | `seed007` | Custom prefix |
| `seed008_media_permissions.py` | `seed008` | Custom prefix |
| `seed009_comprehensive_rbac_permissions.py` | `seed009` | Custom prefix |
| `admin001_create_admin_invitations.py` | `admin001` | Custom prefix |
| `inv001_add_reminder_sent_field.py` | `inv001` | Custom prefix |
| `inv002_add_invitation_composite_indexes.py` | `inv002` | Custom prefix |
| `ls20251020_add_basic_plan_and_lemonsqueezy_ids.py` | `ls20251020` | Custom prefix |
| `onb20251020_add_onboarding_marketing_fields.py` | `onb20251020` | Custom prefix |
| `rem20251020_remove_tour_fields.py` | `rem20251020` | Custom prefix |
| `pgv001_enable_pgvector_extension.py` | `pgv001` | Custom prefix |
| `pgv002_create_knowledge_embeddings_table.py` | `pgv002` | Custom prefix |
| `pgv003_add_default_kb_unique_constraint.py` | `pgv003` | Custom prefix |
| `20251111_add_bio_and_expand_notifications.py` | `20251111_bio_notif` | Date-based |
| `b2c3d4e5f6g7_fix_user_sessions_duplicate_indexes.py` | `b2c3d4e5f6g7` | Fake hex |
| `c3d4e5f6g7h8_add_updated_at_tracking_columns.py` | `c3d4e5f6g7h8` | Fake hex |
| `d1e2f3g4h5i6_add_timestamps_to_brand_voice.py` | `d1e2f3g4h5i6` | Fake hex |
| `g1h2i3j4k5l6_add_email_templates_table.py` | `g1h2i3j4k5l6` | Fake hex |
| `h2i3j4k5l6m7_add_workspace_id_to_topics.py` | `h2i3j4k5l6m7` | Fake hex |

---

## Why This Matters (Context & Reasoning)

Alembic's revision ID system is designed to be content-addressable - the ID is a random unique identifier, not a semantic descriptor. The migration message/description provides the semantic information. By hand-crafting IDs, developers have imposed structure where Alembic doesn't expect it.

This matters for several reasons:

1. **Onboarding friction:** New developers familiar with Alembic expect standard hex IDs. Custom prefixes require explanation and documentation that doesn't exist.

2. **Automation compatibility:** Any tooling that parses revision IDs assuming hex format may fail or behave unexpectedly. While rare, some CI/CD scripts validate revision ID format.

3. **Deceptive similarity:** The fake hex IDs (`b2c3d4e5f6g7`) look auto-generated at first glance. A developer investigating a migration issue might assume these were auto-generated and not realize they need to look for intentional patterns.

4. **Migration ordering confusion:** Custom prefixes like `seed005` → `seed006` imply sequential ordering, but Alembic's DAG doesn't work that way. A developer might incorrectly assume `seed007` runs after `seed006` without checking the actual `down_revision`.

5. **Future maintenance:** If the team ever needs to squash or reorganize migrations, understanding which IDs are custom vs auto-generated adds complexity.

---

## Impact

- **Severity:** Low runtime impact; medium developer experience and maintenance impact
- **Affected Users/Flows:** Developers working with migrations; CI/CD pipelines; debugging scenarios
- **Blast Radius:** Isolated to migration tooling - no runtime application impact

---

## Recommended Solution

### Step 1: Document the existing non-standard IDs (Immediate)

Since changing existing migration IDs is risky (all deployed databases reference these IDs in the `alembic_version` table), document the existing non-standard IDs rather than renaming them.

Add to the migration documentation:

```markdown
# File: rext-backend/alembic/MIGRATION_CONVENTIONS.md

# Migration Conventions

## Historical Non-Standard Revision IDs

The following migrations use non-standard revision IDs. These should NOT be changed
as they exist in production databases' `alembic_version` tables.

### Custom Prefix Pattern
These use semantic prefixes instead of random hex:
- seed005-009: Seed data migrations
- admin001: Admin features
- inv001-002: Invitation features
- ls20251020, onb20251020, rem20251020: Date-prefixed feature migrations
- pgv001-003: PgVector migrations

### Fake Hex Pattern
These look like hex but contain invalid characters (g-m):
- b2c3d4e5f6g7, c3d4e5f6g7h8, d1e2f3g4h5i6, g1h2i3j4k5l6, h2i3j4k5l6m7

## Policy for New Migrations

All new migrations MUST use Alembic-generated revision IDs:

```bash
# Correct - let Alembic generate the ID
alembic revision --autogenerate -m "add_new_feature"

# Incorrect - do not use custom IDs
alembic revision --rev-id "custom001" -m "add_new_feature"
```

The migration message should be descriptive enough to understand the change
without relying on custom ID prefixes.
```

### Step 2: Establish policy for new migrations (Process)

Add to team guidelines:

```markdown
## Migration ID Policy

1. **Never hand-craft revision IDs.** Always use `alembic revision --autogenerate` or `alembic revision` without `--rev-id`.

2. **Use descriptive migration messages.** The message should describe what the migration does:
   - Good: `alembic revision -m "add_trust_score_column_to_content_seo_data"`
   - Bad: `alembic revision --rev-id "seo001" -m "add column"`

3. **Seed data belongs in scripts, not migrations.** Do not create `seed*` migrations. Use standalone seed scripts (see TASK-038).

4. **Review migration IDs in PRs.** Check that new migrations have standard Alembic hex IDs.
```

### Step 3: Add a pre-commit or CI check (Optional)

Add a simple validation script that can run in CI:

```python
# File: rext-backend/scripts/validate_migration_ids.py
#!/usr/bin/env python3
"""Validate that new migration revision IDs follow Alembic conventions."""

import re
import sys
from pathlib import Path

# Known historical non-standard IDs (do not flag these)
KNOWN_EXCEPTIONS = {
    'seed005', 'seed006', 'seed007', 'seed008', 'seed009',
    'admin001', 'inv001', 'inv002',
    'ls20251020', 'onb20251020', 'rem20251020',
    'pgv001', 'pgv002', 'pgv003',
    '20251111_bio_notif',
    'b2c3d4e5f6g7', 'c3d4e5f6g7h8', 'd1e2f3g4h5i6', 'g1h2i3j4k5l6', 'h2i3j4k5l6m7',
}

# Standard Alembic hex ID pattern (12 lowercase hex chars)
HEX_PATTERN = re.compile(r'^[0-9a-f]{12}$')


def main():
    versions_dir = Path('alembic/versions')
    errors = []

    for migration_file in versions_dir.glob('*.py'):
        if migration_file.name == '__pycache__':
            continue

        content = migration_file.read_text()
        match = re.search(r"revision[:\s]*=\s*['\"]([^'\"]+)['\"]", content)
        if match:
            revision_id = match.group(1)
            if revision_id in KNOWN_EXCEPTIONS:
                continue
            if not HEX_PATTERN.match(revision_id):
                errors.append(f"{migration_file.name}: non-standard revision ID '{revision_id}'")

    if errors:
        print("Migration ID validation failed:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    print("All migration IDs are valid.")
    sys.exit(0)


if __name__ == '__main__':
    main()
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/alembic/versions/` | 20 files | Files with non-standard revision IDs (listed above) |
| Team documentation | N/A | Need to add migration ID policy |

---

## Testing Instructions

### Before Fix (Verify the Issue):
1. List migrations with non-hex IDs:
   ```bash
   cd rext-backend
   grep -r "revision.*=" alembic/versions/ | grep -v "[0-9a-f]\{12\}"
   ```
2. Count non-standard IDs (should be ~20)

### After Fix (Verify the Solution):
1. Verify `MIGRATION_CONVENTIONS.md` exists with documented exceptions
2. Verify team guidelines include migration ID policy
3. If CI check is added, verify it passes for existing migrations
4. Create a test migration and verify it gets a standard hex ID:
   ```bash
   alembic revision -m "test_migration"
   # Check the generated revision ID is 12 hex characters
   # Then delete the test migration
   ```

### Run Existing Tests:
```bash
cd rext-backend
alembic check
alembic heads
alembic upgrade head --sql > /dev/null  # Dry run
```

---

## Acceptance Criteria

- [ ] `MIGRATION_CONVENTIONS.md` documentation file created with historical exceptions
- [ ] Migration ID policy documented in team guidelines
- [ ] (Optional) CI validation script added
- [ ] Team acknowledges policy for new migrations
- [ ] No changes to existing migration files (IDs must remain unchanged for deployed databases)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Alembic Tutorial - Creating an Environment](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Alembic Auto-generating Migrations](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-038 (Migration Chain Instability), TASK-039 (No-op Migration) - all migration chain quality issues
