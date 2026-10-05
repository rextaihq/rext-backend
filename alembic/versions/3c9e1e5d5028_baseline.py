"""baseline: the schema the first 204 migrations built

Revision ID: 3c9e1e5d5028
Revises:
Create Date: 2026-10-05 18:00:00 UTC

The 204 migrations up to this revision were squashed into this one on
2026-10-05. It keeps the old head's id, so a database already at that head
(stage, live, every local copy) has nothing to run, and a new database gets
exactly the same schema: alembic/baseline/3c9e1e5d5028_schema.sql is
`pg_dump --schema-only` of a database built by the old chain, with pg_dump's
session settings and the alembic_version table left out. The old files are in
git history; seed data now lives in scripts/seed.py. How to squash again:
alembic/MIGRATION_CONVENTIONS.md.
"""

from collections.abc import Iterator, Sequence
from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c9e1e5d5028"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = Path(__file__).resolve().parent.parent / "baseline" / f"{revision}_schema.sql"


def _statements(sql: str) -> Iterator[str]:
    """One statement at a time (asyncpg runs one per call); a $$-quoted function
    body may hold semicolons of its own."""
    statement: list[str] = []
    quoted = False
    for line in sql.splitlines():
        if not statement and not line.strip():
            continue
        statement.append(line)
        if line.count("$$") % 2 == 1:
            quoted = not quoted
        if not quoted and line.rstrip().endswith(";"):
            yield "\n".join(statement)
            statement = []
    if statement:
        raise ValueError(f"unterminated statement at the end of {SCHEMA.name}")


def upgrade() -> None:
    bind = op.get_bind()
    for statement in _statements(SCHEMA.read_text()):
        bind.exec_driver_sql(statement)


def downgrade() -> None:
    raise NotImplementedError(
        "The baseline is the start of the history: drop the database instead."
    )
