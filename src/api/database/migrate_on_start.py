"""The pending Alembic migrations, applied when the server starts.

G32 (revnix/rext-control#358, founder decision 2026-10-06): every deploy applies the
migrations its image carries before the new code serves. The image turns it on
(`MIGRATE_ON_START=true` in langgraph.json's dockerfile_lines), so a deploy needs no
setting of its own, and a checkout's tests and `langgraph dev` never migrate.

- One server at a time: a Postgres advisory lock, taken in the migrations' own
  transaction. A second server waits for it, then finds nothing left to apply.
- The DDL goes to the database directly when that's proven safe: the LangGraph
  runtime's direct address (DATABASE_URI, then DATABASE_URL), only when it reaches
  the very database POSTGRES_URI_CUSTOM reaches (the same name, the same server, the
  same database oid). Otherwise POSTGRES_URI_CUSTOM itself, which may go through
  PgBouncer; one transaction and no prepared statements keep that safe. The runtime's
  own database, where it has one, is never migrated.
- psycopg in a worker thread: Alembic reads and imports its scripts, which is
  blocking work, and psycopg keeps the address's sslmode and channel_binding as given.
- A migration that fails stops the start, so no code serves against a schema it
  doesn't match. A database newer than the image (an older image started to roll
  back) is left alone: the image starts and says so. A database on a revision the
  2026-10 squash retired never reached the preserved head, so the start refuses it.
- A database with no subscription plan yet (a brand-new one, or one whose first seed
  didn't finish) gets the rows every database needs from scripts/seeds once it's
  migrated: the plans, roles and permissions, email templates and the super admin.
  The seeds only insert what's missing; a database with plans is never seeded, nor
  one newer than the image. They run in one transaction under the same lock, on the
  app's own engine: all of them are kept or none, and one server seeds at a time.
"""

import asyncio
import os
from pathlib import Path
from typing import Callable, NamedTuple, Optional

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.script.revision import ResolutionError
from alembic.util import CommandError
from sqlalchemy import create_engine, pool, text
from sqlalchemy.engine import URL, Connection, Engine, make_url
from sqlalchemy.ext.asyncio import AsyncConnection

from alembic import command
from src.api.database.retired_revisions import RETIRED_REVISIONS
from src.utils.logger import logger

ROOT = Path(__file__).resolve().parents[3]

# Any fixed number, the same for every server: each environment has its own database.
MIGRATION_LOCK = 358_000_001

# Which database, on which running server: two servers never share a start time.
_IDENTITY = text(
    "SELECT current_database(),"
    " (SELECT oid FROM pg_database WHERE datname = current_database()),"
    " pg_postmaster_start_time()"
)


class MigrationFailed(RuntimeError):
    """A pending migration failed, or couldn't be run: the server must not start."""


def _summary(error: BaseException) -> str:
    """What failed, as the error's type and SQLSTATE only.

    PostgreSQL can put a row's values in any part of its message (a constraint's
    detail, or "invalid input syntax for type ...: <value>" in the primary one), so
    none of it is kept. Running the migration by hand shows the full error.
    """
    cause = getattr(error, "orig", None) or error.__cause__ or error
    sqlstate = getattr(getattr(cause, "diag", None), "sqlstate", None)
    return f"{type(cause).__name__} (SQLSTATE {sqlstate})" if sqlstate else type(cause).__name__


class Outcome(NamedTuple):
    before: Optional[str]
    after: Optional[str]
    head: Optional[str]
    ahead: bool = False  # the database is at a revision this image doesn't know


def _engine(url: URL, *, connect_timeout: Optional[int] = None) -> Engine:
    connect_args = {"prepare_threshold": None}  # through PgBouncer, no prepared statements
    if connect_timeout:
        connect_args["connect_timeout"] = connect_timeout
    return create_engine(
        url.set(drivername="postgresql+psycopg"), poolclass=pool.NullPool, connect_args=connect_args
    )


def _identity(engine: Engine) -> tuple:
    with engine.connect() as connection:
        return tuple(connection.execute(_IDENTITY).one())


def migration_engine() -> Engine:
    """The engine to migrate the app's database over (see the module's notes)."""
    app_address = os.getenv("POSTGRES_URI_CUSTOM")
    if not app_address:
        raise MigrationFailed("no database address: POSTGRES_URI_CUSTOM is unset")
    app_url = make_url(app_address)
    app_engine, app_identity = _engine(app_url), None
    for name in ("DATABASE_URI", "DATABASE_URL"):
        address = os.getenv(name)
        if not address or make_url(address).database != app_url.database:
            continue
        # A probe of an address that may not answer: a short wait, then the fallback.
        direct = _engine(make_url(address), connect_timeout=5)
        try:
            app_identity = app_identity or _identity(app_engine)
            if _identity(direct) == app_identity:
                logger.info(f"Database migration: over {name}, the same database, directly")
                app_engine.dispose()
                return direct
            logger.warning(f"Database migration: {name} reaches another database; not used")
        except Exception as e:  # noqa: BLE001 - the app's own address is the fallback
            logger.warning(f"Database migration: {name} not usable ({type(e).__name__})")
        direct.dispose()
    logger.info("Database migration: over POSTGRES_URI_CUSTOM")
    return app_engine


def _alembic_config(connection: Connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.attributes["connection"] = connection
    config.attributes["configure_logger"] = False  # the server's logging stays as it is
    return config


def _knows(scripts: ScriptDirectory, revision: str) -> bool:
    try:
        return scripts.get_revision(revision) is not None
    except (CommandError, ResolutionError, KeyError):
        return False


def upgrade_to_head(connection: Connection) -> Outcome:
    """Apply what's pending in the connection's transaction.

    The transaction is the caller's: Alembic sees it open and leaves the commit to it.
    """
    config = _alembic_config(connection)
    scripts = ScriptDirectory.from_config(config)
    head = scripts.get_current_head()
    before = MigrationContext.configure(connection).get_current_revision()
    if before is not None and not _knows(scripts, before):
        if before in RETIRED_REVISIONS:
            raise MigrationFailed(
                f"the database is at {before}, a revision the 2026-10 squash retired: it never "
                f"reached the preserved head 3c9e1e5d5028. Bring it there with an image from "
                f"before the squash, then start this one"
            )
        return Outcome(before, before, head, ahead=True)
    if before != head:
        logger.info(f"Database migration: from {before} to {head}")
        command.upgrade(config, "head")
    after = MigrationContext.configure(connection).get_current_revision()
    return Outcome(before, after, head)


def _take_the_lock(connection: Connection) -> None:
    """The lock for this transaction; it ends with the commit, or with the connection."""
    taken = connection.execute(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK}
    ).scalar()
    if not taken:
        logger.info("Database migration: waiting for another server's migration to finish")
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK})


def migrate(
    url: Optional[URL] = None, *, upgrade: Callable[[Connection], Outcome] = upgrade_to_head
) -> Outcome:
    """Apply the pending migrations under the lock; returns where the database was and is.

    The lock, the migrations and their commit are one transaction, which PgBouncer's
    transaction pooling keeps on one server connection, so the lock holds there too.
    A failure rolls it all back and frees the lock.

    Raises:
        MigrationFailed: a migration failed, or the database couldn't be reached
    """
    try:
        engine = _engine(url) if url is not None else migration_engine()
        try:
            with engine.connect() as connection:
                _take_the_lock(connection)
                outcome = upgrade(connection)
                # Checked before the commit: short of the head, nothing is kept.
                if not outcome.ahead and outcome.after != outcome.head:
                    raise MigrationFailed(
                        f"the database is at {outcome.after} after migrating, "
                        f"not at the head {outcome.head}"
                    )
                connection.commit()
        finally:
            engine.dispose()
    except MigrationFailed:
        raise
    except Exception as e:
        # Not chained: the database's own detail can hold row values (AGENTS.md: no
        # personal data in a log line). Running Alembic by hand shows it in full.
        raise MigrationFailed(
            f"the pending migrations could not be applied: {_summary(e)}"
        ) from None

    if outcome.ahead:
        logger.warning(
            f"Database schema at {outcome.before}, newer than this image's head "
            f"{outcome.head} (an older image, a rollback?): starting without migrating"
        )
    elif outcome.before == outcome.after:
        logger.info(f"Database schema at {outcome.after}, the head: nothing to migrate")
    else:
        logger.info(f"Database migrated from {outcome.before} to {outcome.after}, the head")
    return outcome


async def _has_no_plans(connection: AsyncConnection) -> bool:
    found = await connection.execute(text("SELECT EXISTS (SELECT 1 FROM subscription_plans)"))
    return not found.scalar()


async def seed_a_new_database() -> bool:
    """The rows every database needs, when it has no subscription plan yet; whether it seeded.

    One transaction under the migrations' lock, on the app's own engine (PgBouncer-safe):
    a second server waits, then finds the plans; a seed that fails keeps nothing, so the
    next start finds no plan and seeds it all again.

    Raises:
        MigrationFailed: the seeds failed, or couldn't be checked; the next start tries again
    """
    from scripts.seeds.base import seeding_on
    from scripts.seeds.run_all import run_all_seeds
    from src.api.database.async_database import async_engine

    try:
        async with async_engine.connect() as connection, connection.begin():
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK}
            )
            if not await _has_no_plans(connection):
                return False
            logger.info("Database seeding: no subscription plan yet, a new database: seeding it")
            async with seeding_on(connection):
                await run_all_seeds()
    except Exception as e:
        raise MigrationFailed(f"the database's seeds could not be applied: {_summary(e)}") from None
    logger.info("Database seeding: done")
    return True


async def apply_pending_migrations() -> Optional[str]:
    """migrate() off the event loop, then the seeds for a new database: the server's start
    waits for both, nothing else does. A database newer than the image is never seeded:
    this image's seeds are not its rows to write."""
    outcome = await asyncio.to_thread(migrate)
    if outcome.ahead:
        return outcome.before
    await seed_a_new_database()
    return outcome.after
