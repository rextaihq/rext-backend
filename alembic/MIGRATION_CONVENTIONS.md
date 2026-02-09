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
