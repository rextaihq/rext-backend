# Migration Conventions

## The baseline

The first 204 migrations were squashed into one baseline on 2026-10-05: `versions/3c9e1e5d5028_baseline.py`. It keeps the old head's revision id, so every database that was already at that head (stage, live, every local copy) has nothing to run, and a new database gets exactly the schema the old chain built: `baseline/3c9e1e5d5028_schema.sql` is `pg_dump --schema-only` of a database built by the old chain. The old files, including their non-standard revision ids (`seed005`, `admin001`, `b2c3d4e5f6g7`, …), are in git history; no database refers to them any more, because `alembic_version` only ever holds the current head.

The baseline cannot be downgraded. To start over locally, drop the database (or `python scripts/db.py reset`) and run `alembic upgrade head` again.

## Policy for new migrations

1. **Let Alembic generate the id and the file.** `alembic revision --autogenerate -m "add trust score to content seo data"`; never `--rev-id`, never a hand-made id. The message says what the migration does.
2. **Read the generated file before running it.** A `drop_table` or `drop_column` you did not intend means the models no longer declare something the database holds: stop and find out why.
3. **The LangGraph tables are never in a migration.** The runtime's and the store's tables (`thread`, `run`, `checkpoints`, `store`, …: `src/api/database/langgraph_tables.py`) have no models; the server creates and migrates them itself. `alembic/env.py` leaves them out of autogenerate, so it no longer proposes to drop them. Add a name there when a LangGraph upgrade brings a new table.
4. **Columns of a `TypeDecorator` type** (`EncryptedText`) are written as the type they store (`sa.String()`), so a migration never imports application code.
5. **Seed data belongs in `scripts/seeds/`, not in migrations.** `python scripts/seed.py` inserts what is missing on every environment and never overwrites. A change to rows that already exist on stage and live (a renamed permission, a corrected plan) is a migration of its own, written for that change.
6. **The models and the database agree.** `alembic check` against a database at head reports "No new upgrade operations detected"; when it does not, either the models drifted (fix the model) or a migration is missing (write it).
7. **Schema work happens on a copy.** Locally, on a cloned database, with a dump and row counts before and after (the app rework's `rext-app-db-safety` skill has the steps).

## Squashing again

When the chain grows long, the same recipe gives a new baseline with no change to any database:

1. Build an empty database with the current chain: `alembic upgrade head`.
2. `pg_dump --schema-only --no-owner --no-privileges <that database>`; drop pg_dump's `SET`, `SELECT pg_catalog.set_config` and `\restrict` lines and the `alembic_version` table, and save it as `baseline/<head id>_schema.sql`.
3. Replace `versions/` with one file whose `revision` is the current head's id and whose `down_revision` is `None`, executing that SQL (copy `3c9e1e5d5028_baseline.py`).
4. Prove it: an empty database built from the new baseline and one built from the old chain give the same `pg_dump --schema-only` (a CHECK constraint whose expression pg_dump prints differently is written as the original migration wrote it; see the two in the current baseline), and `alembic check` is clean on both.
