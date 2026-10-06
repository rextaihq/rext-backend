"""Every deploy applies its pending migrations before it serves (G32, revnix/rext-control#358).

The lock is checked on the test PostgreSQL with two starts in two threads, each with
its own event loop and connection, as two servers would be. The migration itself is a
stand-in there: a real upgrade would leave the schema in the test database.
"""

import asyncio
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database import migrate_on_start
from src.api.database.migrate_on_start import (
    MIGRATION_LOCK,
    MigrationFailed,
    apply_pending_migrations,
    direct_database_url,
    upgrade_to_head,
)
from tests.conftest import TEST_DATABASE_URL

URL = make_url(TEST_DATABASE_URL).set(drivername="postgresql+asyncpg")


# --- the address -------------------------------------------------------------------


def test_the_direct_address_is_used_when_it_names_the_apps_database(monkeypatch):
    monkeypatch.setenv(
        "POSTGRES_URI_CUSTOM", "postgresql://u:p@pgbouncer:5432/app?prepare_threshold=0"
    )
    monkeypatch.setenv("DATABASE_URI", "postgresql://u:p@db:5432/app?sslmode=disable")

    url = direct_database_url()

    assert (url.drivername, url.host, url.database) == ("postgresql+asyncpg", "db", "app")
    assert dict(url.query) == {}


def test_the_runtimes_own_database_is_never_migrated(monkeypatch):
    monkeypatch.setenv("POSTGRES_URI_CUSTOM", "postgresql://u:p@127.0.0.1:5441/rext_app")
    monkeypatch.setenv("DATABASE_URI", "postgresql://u:p@127.0.0.1:5441/rext_app_runtime")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5441/rext_app_runtime")

    assert direct_database_url().database == "rext_app"


def test_no_address_stops_the_start(monkeypatch):
    monkeypatch.delenv("POSTGRES_URI_CUSTOM", raising=False)

    with pytest.raises(MigrationFailed, match="no database address"):
        direct_database_url()


# --- the lock, on the test PostgreSQL ----------------------------------------------


def test_two_starts_at_once_never_migrate_together():
    spans, lock = [], threading.Lock()

    def migrate(_connection):
        start = time.monotonic()
        time.sleep(0.4)
        with lock:
            spans.append((start, time.monotonic()))
        return "a", "b", "b"

    def server():
        asyncio.run(apply_pending_migrations(URL, upgrade=migrate))

    servers = [threading.Thread(target=server) for _ in range(2)]
    for thread in servers:
        thread.start()
    for thread in servers:
        thread.join(timeout=30)

    assert len(spans) == 2
    (first_start, first_end), (second_start, _) = sorted(spans)
    assert second_start >= first_end  # the second waited for the first to finish


@pytest.mark.asyncio
async def test_a_failed_migration_stops_the_start_and_frees_the_lock():
    def migrate(_connection):
        raise RuntimeError("column already exists")

    with pytest.raises(MigrationFailed, match="column already exists"):
        await apply_pending_migrations(URL, upgrade=migrate)

    engine = create_async_engine(URL, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            free = (
                await connection.execute(
                    text("SELECT pg_try_advisory_lock(:key)"), {"key": MIGRATION_LOCK}
                )
            ).scalar()
            await connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK}
            )
    finally:
        await engine.dispose()
    assert free is True


@pytest.mark.asyncio
async def test_a_database_short_of_the_head_after_migrating_stops_the_start():
    with pytest.raises(MigrationFailed, match="not at the head"):
        await apply_pending_migrations(URL, upgrade=lambda _c: ("a", "a", "b"))


# --- the Alembic step ----------------------------------------------------------------


@pytest.mark.parametrize(("before", "upgraded"), [("old", True), ("head", False)])
def test_alembic_runs_only_when_the_database_is_behind(before, upgraded):
    connection = MagicMock()
    revisions = iter([before, "head"])
    context = MagicMock()
    context.get_current_revision.side_effect = lambda: next(revisions)
    with (
        patch.object(migrate_on_start.ScriptDirectory, "from_config") as scripts,
        patch.object(migrate_on_start.MigrationContext, "configure", return_value=context),
        patch.object(migrate_on_start.command, "upgrade") as upgrade,
    ):
        scripts.return_value.get_current_head.return_value = "head"
        result = upgrade_to_head(connection)

    assert result == (before, "head", "head")
    assert upgrade.called is upgraded
    if upgraded:
        config = upgrade.call_args.args[0]
        # Alembic gets the locked connection, and leaves the server's logging alone.
        assert config.attributes["connection"] is connection
        assert config.attributes["configure_logger"] is False
