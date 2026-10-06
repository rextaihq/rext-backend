"""The pending Alembic migrations, applied when the server starts.

G32 (revnix/rext-control#358, founder decision 2026-10-06): every deploy applies the
migrations its image carries before the new code serves. The image turns it on
(`MIGRATE_ON_START=true` in langgraph.json's dockerfile_lines), so a deploy needs no
setting of its own, and a checkout's tests and `langgraph dev` never migrate.

- One server at a time: a Postgres advisory lock, taken in the migrations' own
  transaction. A second server waits for it, then finds nothing left to apply.
- The DDL goes to the database directly when it can: the LangGraph runtime's direct
  address (DATABASE_URI, or DATABASE_URL) when it names the app's own database, which
  POSTGRES_URI_CUSTOM names; else POSTGRES_URI_CUSTOM itself, which may go through
  PgBouncer (one transaction and no prepared statements keep that safe). The runtime's
  own database, where it has one, is never migrated.
- A migration that fails stops the start, so no code serves against a schema it
  doesn't match.
"""

import os
from pathlib import Path
from typing import Callable, Optional, Tuple

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import pool, text
from sqlalchemy.engine import URL, Connection, make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from alembic import command
from src.utils.logger import logger

ROOT = Path(__file__).resolve().parents[3]

# Any fixed number, the same for every server: each environment has its own database.
MIGRATION_LOCK = 358_000_001

# asyncpg takes none of these: env.py drops them the same way.
_NOT_FOR_ASYNCPG = ("sslmode", "channel_binding", "prepare_threshold")

Revisions = Tuple[Optional[str], Optional[str], Optional[str]]


class MigrationFailed(RuntimeError):
    """A pending migration failed, or couldn't be run: the server must not start."""


def direct_database_url() -> URL:
    """The address to migrate the app's database over, for asyncpg."""
    app_address = os.getenv("POSTGRES_URI_CUSTOM")
    if not app_address:
        raise MigrationFailed("no database address: POSTGRES_URI_CUSTOM is unset")
    app_url = make_url(app_address)
    chosen, source = app_url, "POSTGRES_URI_CUSTOM"
    for name in ("DATABASE_URI", "DATABASE_URL"):
        direct = os.getenv(name)
        if direct and make_url(direct).database == app_url.database:
            chosen, source = make_url(direct), name
            break
    logger.info(f"Database migration: over {source}")
    query = {key: value for key, value in chosen.query.items() if key not in _NOT_FOR_ASYNCPG}
    return chosen.set(drivername="postgresql+asyncpg", query=query)


def _alembic_config(connection: Connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.attributes["connection"] = connection
    config.attributes["configure_logger"] = False  # the server's logging stays as it is
    return config


def upgrade_to_head(connection: Connection) -> Revisions:
    """Apply what's pending in the connection's transaction: (the revision before, after, the head).

    The transaction is the caller's: Alembic sees it open and leaves the commit to it.
    """
    config = _alembic_config(connection)
    head = ScriptDirectory.from_config(config).get_current_head()
    before = MigrationContext.configure(connection).get_current_revision()
    if before != head:
        logger.info(f"Database migration: from {before} to {head}")
        command.upgrade(config, "head")
    after = MigrationContext.configure(connection).get_current_revision()
    return before, after, head


async def _take_the_lock(connection: AsyncConnection) -> None:
    """The lock for this transaction; it ends with the commit, or with the connection."""
    taken = (
        await connection.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK}
        )
    ).scalar()
    if not taken:
        logger.info("Database migration: waiting for another server's migration to finish")
        await connection.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK}
        )


async def apply_pending_migrations(
    url: Optional[URL] = None, *, upgrade: Callable[[Connection], Revisions] = upgrade_to_head
) -> Optional[str]:
    """Apply the pending migrations under the lock; returns the revision the database is at.

    The lock, the migrations and their commit are one transaction, which PgBouncer's
    transaction pooling keeps on one server connection, so the lock holds there too.
    A failure rolls it all back and frees the lock.

    Raises:
        MigrationFailed: a migration failed, or the database couldn't be reached
    """
    engine = create_async_engine(
        url or direct_database_url(),
        poolclass=pool.NullPool,
        # No prepared statements: a pooled server connection may not hold them.
        connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0},
    )
    try:
        async with engine.connect() as connection:
            await _take_the_lock(connection)
            before, after, head = await connection.run_sync(upgrade)
            await connection.commit()
    except MigrationFailed:
        raise
    except Exception as e:
        raise MigrationFailed(f"the pending migrations could not be applied: {e}") from e
    finally:
        await engine.dispose()

    if after != head:
        raise MigrationFailed(f"the database is at {after} after migrating, not at the head {head}")
    if before == after:
        logger.info(f"Database schema at {after}, the head: nothing to migrate")
    else:
        logger.info(f"Database migrated from {before} to {after}, the head")
    return after
