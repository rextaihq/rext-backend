"""The tables a database-backed test makes for itself.

A fixture calls `create_tables_unless_migrated` inside its rolled-back transaction. On
an empty test database (the laptop's) it makes the tables from the models, with every
table their foreign keys reach. On a migrated one (CI's, or a `db.sh clone`) it makes
nothing: the tests then run on the schema the migrations built, so a table or column a
migration lacks fails them instead of being made from the models.
"""

from collections.abc import Iterable

from sqlalchemy import Table, inspect

from src.api.database.base import Base


def with_parents(models: Iterable) -> list[Table]:
    """The models' tables (a model or a Table each), and every table their foreign keys
    reach, in the order first met."""
    found: list[Table] = []

    def visit(table: Table) -> None:
        if table in found:
            return
        found.append(table)
        for key in table.foreign_keys:
            visit(key.column.table)

    for model in models:
        visit(model if isinstance(model, Table) else model.__table__)
    return found


def create_tables_unless_migrated(sync, models: Iterable) -> None:
    """Make the models' tables and their parents, unless the database is migrated."""
    if inspect(sync).has_table("alembic_version"):
        return
    Base.metadata.create_all(sync, tables=with_parents(models), checkfirst=True)
