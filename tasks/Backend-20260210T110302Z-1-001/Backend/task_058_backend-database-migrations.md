# Task 058: Standardize Migration File Naming Convention

## Metadata
- **Task ID:** TASK-058
- **Source:** Backend Database & Migrations Audit (Finding #32 under P3 Low)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The Alembic migration directory (`rext-backend/alembic/versions/`) contains approximately 115 migration files using three inconsistent naming patterns for revision IDs, making it difficult for developers to distinguish auto-generated migrations from hand-crafted ones and to understand the migration chain's history.

**Pattern 1: Standard Alembic hex IDs (~91 files)** — Auto-generated 12-character hexadecimal revision IDs produced by `alembic revision --autogenerate`. These follow the default `file_template = %(rev)s_%(slug)s` setting. Example: `cc3bde5553b9_initial_schema_baseline.py` with `revision: str = 'cc3bde5553b9'`.

**Pattern 2: Custom semantic prefixes (15+ files)** — Hand-crafted revision IDs using semantic prefixes that categorize the migration's purpose:
- Seed data: `seed005` through `seed009` (5 files)
- Admin features: `admin001` (1 file)
- Invitation features: `inv001`, `inv002` (2 files)
- Date-prefixed: `ls20251020`, `onb20251020`, `rem20251020`, `20251111_add_bio_and_expand_notifications` (4 files)
- PgVector: `pgv001`, `pgv002`, `pgv003` (3 files)

**Pattern 3: Fake hex with invalid characters (5+ files)** — Revision IDs that visually resemble hex strings but contain non-hex characters (g-m), making them look auto-generated when they are actually hand-crafted. Example: `b2c3d4e5f6g7` (contains 'g'), `g1h2i3j4k5l6` (contains 'g'-'l'), `h2i3j4k5l6m7` (contains 'h'-'m'). Additionally, files like `a1b2c3d4e5f6` and `f9e8d7c6b5a4` use valid hex characters but with sequential/patterned sequences that indicate manual crafting.

These inconsistencies cause confusion because: (1) developers cannot tell at a glance whether a migration was auto-generated or hand-crafted, (2) fake hex IDs (Pattern 3) are especially misleading since they appear auto-generated but are not, (3) custom prefixes (Pattern 2) create an undocumented categorization scheme, and (4) the migration directory is not chronologically sorted since the default `file_template` does not include timestamps.

The [Alembic documentation](https://alembic.sqlalchemy.org/en/latest/tutorial.html) provides a built-in timestamp-based `file_template` option that is already present (but commented out) in the project's `alembic.ini` at line 14. The [Alembic Discussion #1241](https://github.com/sqlalchemy/alembic/discussions/1241) and [community best practices](https://dev.to/welel/best-practices-for-alembic-and-sqlalchemy-3b34) recommend enabling timestamp-based templates for better directory sorting.

---

## Current Code

```ini
# File: rext-backend/alembic.ini
# Lines: 10-14
# template used to generate migration file names; The default value is %%(rev)s_%%(slug)s
# Uncomment the line below if you want the files to be prepended with date and time
# see https://alembic.sqlalchemy.org/en/latest/tutorial.html#editing-the-ini-file
# for all available tokens
# file_template = %%(year)d_%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d-%%(rev)s_%%(slug)s
```

```python
# File: rext-backend/alembic/versions/cc3bde5553b9_initial_schema_baseline.py
# Lines: 14-18 — Standard auto-generated hex ID
revision: str = 'cc3bde5553b9'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
```

```python
# File: rext-backend/alembic/versions/seed005_default_email_templates.py
# Lines: 16-20 — Custom prefix: "seed005"
revision: str = 'seed005'
down_revision: Union[str, Sequence[str], None] = 'cc6f7933fed1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
```

```python
# File: rext-backend/alembic/versions/b2c3d4e5f6g7_fix_user_sessions_duplicate_indexes.py
# Lines: 14-18 — Fake hex: "b2c3d4e5f6g7" (contains 'g', not valid hex)
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
```

```python
# File: rext-backend/alembic/versions/g1h2i3j4k5l6_add_email_templates_table.py
# Lines: 14-17 — Fake hex: "g1h2i3j4k5l6" (contains 'g'-'l', not valid hex)
revision: str = 'g1h2i3j4k5l6'
down_revision: Union[str, Sequence[str], None] = 'f9e8d7c6b5a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
```

---

## Why This Matters (Context & Reasoning)

The Alembic migration chain is the backbone of database schema management for the Rext backend. With 115 migration files, it is already a large chain (TASK-038 identified 15 merge migrations indicating branch coordination issues). Inconsistent naming adds unnecessary cognitive overhead when developers need to:

1. **Trace migration history:** Understanding the dependency chain (`down_revision` → `revision`) is harder when IDs don't follow a consistent pattern. Fake hex IDs can be confused with auto-generated ones, leading to incorrect assumptions about authorship.

2. **Debug migration failures:** When `alembic upgrade head` fails, the error message references a revision ID. Standard hex IDs can be quickly identified as auto-generated; custom IDs (`seed005`, `admin001`) immediately indicate hand-crafted migrations that may need manual attention.

3. **Maintain the migration chain:** When creating new migrations, developers should use `alembic revision --autogenerate` exclusively. The existence of hand-crafted IDs may encourage future developers to continue the pattern, compounding the inconsistency.

4. **Sort the directory:** Without timestamps in filenames, the `alembic/versions/` directory lists files alphabetically by revision ID, which has no correlation with chronological order. This makes it difficult to find recent migrations.

It is critical to note that **existing migration files must NOT be renamed or have their revision IDs changed.** The `alembic_version` table in every deployed database stores the current revision ID. Changing a revision ID would break `alembic upgrade head` on all existing databases. The fix is forward-looking only.

---

## Impact

- **Severity:** No runtime errors or data corruption. Developer experience and migration chain maintainability issue. The naming inconsistency does not affect Alembic's ability to resolve the migration chain (Alembic uses `revision`/`down_revision` pointers, not filenames, for ordering).
- **Affected Users/Flows:** Developers creating new migrations, DevOps engineers debugging migration failures, anyone browsing the `alembic/versions/` directory.
- **Blast Radius:** All future migrations will benefit from the convention change. Existing 115 migration files are unaffected (and must remain unchanged).

---

## Recommended Solution

This is primarily a process and configuration change, not a code refactor. The goal is to ensure all future migrations use consistent auto-generated revision IDs with timestamp-prefixed filenames.

### Step 1: Enable timestamp-based file template in `alembic.ini`

```ini
# File: rext-backend/alembic.ini
# Uncomment and modify line 14 to enable timestamps:
file_template = %%(year)d_%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d-%%(rev)s_%%(slug)s
```

This changes new migration filenames from:
```
a1b2c3d4e5f6_add_some_table.py
```
To:
```
2026_02_06_1430-a1b2c3d4e5f6_add_some_table.py
```

The benefits: files sort chronologically in the directory, and the timestamp provides immediate context about when the migration was created.

### Step 2: Add a team convention comment to `alembic.ini`

```ini
# File: rext-backend/alembic.ini
# Add after the file_template line:

# CONVENTION: Always use `alembic revision --autogenerate -m "description"` to create
# new migrations. Never hand-craft revision IDs. Let Alembic generate them automatically.
# See TASK-058 for context on why custom revision IDs are discouraged.
```

### Step 3: Document the convention in the alembic directory

```markdown
# File: rext-backend/alembic/MIGRATION_CONVENTIONS.md

# Alembic Migration Conventions

## Creating New Migrations

Always use the autogenerate command:

    alembic revision --autogenerate -m "add user preferences table"

**Never** hand-craft revision IDs. Let Alembic generate them automatically.

## Why This Matters

The migration directory historically contains three naming patterns:
1. **Standard Alembic hex IDs** (correct — auto-generated)
2. **Custom prefixes** like `seed005`, `admin001`, `inv001` (legacy — do not continue this pattern)
3. **Fake hex IDs** like `b2c3d4e5f6g7` containing non-hex characters (legacy — do not continue this pattern)

Existing migrations with non-standard IDs must NOT be renamed (this would break the `alembic_version` table in deployed databases). All future migrations should use auto-generated IDs.

## File Naming

The `file_template` in `alembic.ini` prepends timestamps to migration filenames for chronological sorting:

    2026_02_06_1430-a1b2c3d4e5f6_add_some_table.py

## Seed Data

Seed data should NOT be added as Alembic migrations. Use standalone seed scripts in `scripts/seeds/` instead (see TASK-056).
```

### Step 4: Verify the template works

```bash
# Test by generating a new empty migration (can be deleted after verification):
cd rext-backend && alembic revision --autogenerate -m "test_naming_convention"

# Verify the generated filename starts with a timestamp:
ls -la alembic/versions/ | grep "test_naming_convention"

# Delete the test migration:
rm alembic/versions/*test_naming_convention*.py
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/alembic/versions/seed005_default_email_templates.py` | 17 | Custom prefix `seed005` — legacy, do not rename |
| `rext-backend/alembic/versions/seed006_additional_rbac_permissions.py` | Revision line | Custom prefix `seed006` — legacy, do not rename |
| `rext-backend/alembic/versions/seed007_license_permissions.py` | Revision line | Custom prefix `seed007` — legacy, do not rename |
| `rext-backend/alembic/versions/seed008_media_permissions.py` | Revision line | Custom prefix `seed008` — legacy, do not rename |
| `rext-backend/alembic/versions/seed009_comprehensive_rbac_permissions.py` | Revision line | Custom prefix `seed009` — legacy, do not rename |
| `rext-backend/alembic/versions/admin001_create_admin_invitations.py` | 3 | Custom prefix `admin001` — legacy, do not rename |
| `rext-backend/alembic/versions/inv001_add_reminder_sent_field.py` | 15 | Custom prefix `inv001` — legacy, do not rename |
| `rext-backend/alembic/versions/inv002_add_invitation_indexes.py` | Revision line | Custom prefix `inv002` — legacy, do not rename |
| `rext-backend/alembic/versions/b2c3d4e5f6g7_fix_user_sessions_duplicate_indexes.py` | 15 | Fake hex containing 'g' — legacy, do not rename |
| `rext-backend/alembic/versions/c3d4e5f6g7h8_add_updated_at_tracking_columns.py` | Revision line | Fake hex containing 'g','h' — legacy, do not rename |
| `rext-backend/alembic/versions/d1e2f3g4h5i6_add_timestamps_to_brand_voice.py` | Revision line | Fake hex containing 'g'-'i' — legacy, do not rename |
| `rext-backend/alembic/versions/g1h2i3j4k5l6_add_email_templates_table.py` | 14 | Fake hex containing 'g'-'l' — legacy, do not rename |
| `rext-backend/alembic/versions/h2i3j4k5l6m7_add_workspace_id_to_topics.py` | Revision line | Fake hex containing 'h'-'m' — legacy, do not rename |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. List migration files and observe the inconsistent naming: `ls rext-backend/alembic/versions/ | head -20`
2. Check the current `file_template` setting: `grep "file_template" rext-backend/alembic.ini` — should show the line is commented out
3. Generate a test migration and observe the default naming: `cd rext-backend && alembic revision --autogenerate -m "test_before_fix"` — filename will not have a timestamp prefix
4. Delete the test migration: `rm rext-backend/alembic/versions/*test_before_fix*.py`

### After Fix (Verify the Solution):
1. Verify the `file_template` is uncommented in `alembic.ini`: `grep "^file_template" rext-backend/alembic.ini` should return the timestamp template
2. Generate a test migration: `cd rext-backend && alembic revision --autogenerate -m "test_after_fix"`
3. Verify the filename has a timestamp prefix: `ls rext-backend/alembic/versions/ | grep "test_after_fix"` — should show something like `2026_02_06_1430-a1b2c3d4e5f6_test_after_fix.py`
4. Verify the revision ID inside the file is a standard hex string (not hand-crafted)
5. Delete the test migration: `rm rext-backend/alembic/versions/*test_after_fix*.py`
6. Verify `alembic history` still works correctly: `cd rext-backend && alembic history --verbose | head -20`
7. Verify the convention documentation file exists: `cat rext-backend/alembic/MIGRATION_CONVENTIONS.md`

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v --no-header
```

---

## Acceptance Criteria

- [ ] `alembic.ini` has `file_template` uncommented with the timestamp-based template
- [ ] New migrations generated by `alembic revision --autogenerate` produce filenames with timestamp prefixes
- [ ] `alembic/MIGRATION_CONVENTIONS.md` exists documenting the team convention
- [ ] A comment in `alembic.ini` explains the convention (never hand-craft revision IDs)
- [ ] No existing migration files were renamed or had their revision IDs changed
- [ ] `alembic history` still correctly resolves the full migration chain
- [ ] `alembic upgrade head` and `alembic downgrade` still work correctly
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Alembic Tutorial — Editing the .ini File](https://alembic.sqlalchemy.org/en/latest/tutorial.html#editing-the-ini-file) — Documents the `file_template` configuration option with all available tokens including year, month, day, hour, minute
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Best Practices for Alembic and SQLAlchemy (DEV Community)](https://dev.to/welel/best-practices-for-alembic-and-sqlalchemy-3b34) — Community guide recommending timestamp templates and consistent naming; [Alembic Discussion #1241 — Numeric prefix for migration filenames](https://github.com/sqlalchemy/alembic/discussions/1241) — Discussion on enabling timestamp sorting for migration files
- **Related Issues/PRs:** [Better migration file naming for Alembic (GitHub Gist)](https://gist.github.com/amanelis/a9fc48039faddcdcbb4a5f2e5fba556a) — Example configuration for timestamp-based Alembic migration naming

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-040 (Hand-crafted Non-hex Revision IDs — P1 High, covers the specific technical risk of fake hex IDs like `b2c3d4e5f6g7`; this task covers the broader naming convention), TASK-038 (15 Merge Migrations — migration chain complexity is compounded by inconsistent naming), TASK-056 (Seed Data Mixed Into Migration Chain — seed migrations use custom prefixes like `seed005`)
