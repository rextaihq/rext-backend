"""Every deploy applies its pending migrations before it serves (G32, revnix/rext-control#358).

The address and the lock are checked on the test PostgreSQL; two starts run in two
threads, each with its own connection, as two servers would. The migration itself is
a stand-in there: a real upgrade would leave the schema in the test database.
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from src.api.database import migrate_on_start
from src.api.database.migrate_on_start import (
    MIGRATION_LOCK,
    MigrationFailed,
    Outcome,
    apply_pending_migrations,
    migrate,
    migration_engine,
    upgrade_to_head,
)
from tests.conftest import TEST_DATABASE_URL

URL = make_url(TEST_DATABASE_URL)
SAME_NAME_ELSEWHERE = URL.set(port=1)  # the same database name, nothing listening


def _address(url) -> str:
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


# --- the address -------------------------------------------------------------------


def test_the_direct_address_is_used_when_it_reaches_the_same_database(monkeypatch):
    monkeypatch.setenv("POSTGRES_URI_CUSTOM", _address(URL))
    monkeypatch.setenv("DATABASE_URI", _address(URL.set(query={"sslmode": "prefer"})))

    engine = migration_engine()
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.query.get("sslmode") == "prefer"  # kept as given
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "direct",
    [
        URL.set(database=f"{URL.database}_runtime"),  # the runtime's own database
        SAME_NAME_ELSEWHERE,  # the same name, but not a server it can show is the same
    ],
    ids=["another name", "same name, unverified"],
)
def test_otherwise_the_apps_own_address_is_used(monkeypatch, direct):
    monkeypatch.setenv("POSTGRES_URI_CUSTOM", _address(URL))
    monkeypatch.setenv("DATABASE_URI", _address(direct))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    engine = migration_engine()
    try:
        assert (engine.url.port, engine.url.database) == (URL.port, URL.database)
    finally:
        engine.dispose()


def test_no_address_stops_the_start(monkeypatch):
    monkeypatch.delenv("POSTGRES_URI_CUSTOM", raising=False)

    with pytest.raises(MigrationFailed, match="no database address"):
        migrate()


# --- the lock, on the test PostgreSQL ----------------------------------------------


def test_two_starts_at_once_never_migrate_together():
    spans, lock = [], threading.Lock()

    def upgrade(_connection):
        start = time.monotonic()
        time.sleep(0.4)
        with lock:
            spans.append((start, time.monotonic()))
        return Outcome("a", "b", "b")

    servers = [threading.Thread(target=migrate, args=(URL,), kwargs={"upgrade": upgrade})]
    servers.append(threading.Thread(target=migrate, args=(URL,), kwargs={"upgrade": upgrade}))
    for thread in servers:
        thread.start()
    for thread in servers:
        thread.join(timeout=120)

    assert len(spans) == 2
    (_, first_end), (second_start, _) = sorted(spans)
    assert second_start >= first_end  # the second waited for the first to finish


def test_a_failed_migration_stops_the_start_and_frees_the_lock():
    def upgrade(_connection):
        raise RuntimeError("column already exists")

    with pytest.raises(MigrationFailed, match="column already exists"):
        migrate(URL, upgrade=upgrade)

    engine = create_engine(URL.set(drivername="postgresql+psycopg"), poolclass=NullPool)
    try:
        with engine.connect() as connection:
            free = connection.execute(
                text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK}
            ).scalar()
    finally:
        engine.dispose()
    assert free is True


def test_a_database_short_of_the_head_after_migrating_stops_the_start():
    with pytest.raises(MigrationFailed, match="not at the head"):
        migrate(URL, upgrade=lambda _c: Outcome("a", "a", "b"))


def test_an_older_image_starts_on_a_newer_database():
    # A rollback: the database is at a revision the image's scripts don't have.
    assert (
        migrate(URL, upgrade=lambda _c: Outcome("newer", "newer", "older", ahead=True)) == "newer"
    )


@pytest.mark.asyncio
async def test_the_start_migrates_off_the_event_loop():
    threads = []
    with patch.object(
        migrate_on_start, "migrate", side_effect=lambda: threads.append(threading.current_thread())
    ):
        await apply_pending_migrations()

    assert threads and threads[0] is not threading.main_thread()


# --- the Alembic step ----------------------------------------------------------------


def _alembic(before, *, known=True):
    revisions = iter([before, "head"])
    context = MagicMock()
    context.get_current_revision.side_effect = lambda: next(revisions)
    scripts = MagicMock()
    scripts.get_current_head.return_value = "head"
    if not known:
        scripts.get_revision.side_effect = migrate_on_start.CommandError("Can't locate revision")
    return (
        patch.object(migrate_on_start.ScriptDirectory, "from_config", return_value=scripts),
        patch.object(migrate_on_start.MigrationContext, "configure", return_value=context),
        patch.object(migrate_on_start.command, "upgrade"),
    )


@pytest.mark.parametrize(("before", "upgraded"), [("old", True), ("head", False)])
def test_alembic_runs_only_when_the_database_is_behind(before, upgraded):
    connection = MagicMock()
    scripts, context, upgrade_patch = _alembic(before)
    with scripts, context, upgrade_patch as upgrade:
        result = upgrade_to_head(connection)

    assert result == Outcome(before, "head", "head")
    assert upgrade.called is upgraded
    if upgraded:
        config = upgrade.call_args.args[0]
        # Alembic gets the locked connection, and leaves the server's logging alone.
        assert config.attributes["connection"] is connection
        assert config.attributes["configure_logger"] is False


def test_a_revision_the_image_doesnt_know_is_left_alone():
    scripts, context, upgrade_patch = _alembic("newer", known=False)
    with scripts, context, upgrade_patch as upgrade:
        result = upgrade_to_head(MagicMock())

    assert result == Outcome("newer", "newer", "head", ahead=True)
    upgrade.assert_not_called()
