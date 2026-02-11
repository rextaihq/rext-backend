# Migration Conventions

## Historical Non-Standard Revision IDs

The following migrations use non-standard revision IDs. These should NOT be changed
as they exist in production databases' `alembic_version` tables.

### Custom Prefix Pattern
These use semantic prefixes instead of random hex:
- `seed005`-`seed009`: Seed data migrations
- `admin001`: Admin features
- `inv001`-`inv002`: Invitation features
- `ls20251020`, `onb20251020`, `rem20251020`: Date-prefixed feature migrations
- `pgv001`-`pgv003`: PgVector migrations
- `20251111_bio_notif`: Bio and notifications expansion

### Fake Hex Pattern
These look like hex but contain invalid characters (g-m):
- `b2c3d4e5f6g7`, `c3d4e5f6g7h8`, `d1e2f3g4h5i6`, `g1h2i3j4k5l6`, `h2i3j4k5l6m7`
- `a1b2c3d4e5f6`, `a1f2e3d4c5b6`, `a8b9c0d1e2f3`, `f23456789abc`, `f9e8d7c6b5a4` (Additional ones found in `alembic/versions`)

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

## Migration ID Policy

1. **Never hand-craft revision IDs.** Always use `alembic revision --autogenerate` or `alembic revision` without `--rev-id`.

2. **Use descriptive migration messages.** The message should describe what the migration does:
   - Good: `alembic revision -m "add_trust_score_column_to_content_seo_data"`
   - Bad: `alembic revision --rev-id "seo001" -m "add column"`

3. **Seed data belongs in scripts, not migrations.** Do not create `seed*` migrations. Use standalone seed scripts (see TASK-038).

4. **Review migration IDs in PRs.** Check that new migrations have standard Alembic hex IDs.
