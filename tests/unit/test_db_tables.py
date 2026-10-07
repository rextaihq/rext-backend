"""The shared helper database-backed fixtures make their tables with (rext-control G44.14)."""

from types import SimpleNamespace

import tests.db_tables as db_tables
from src.api.database.base import Base
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.user_models.users import Users
from tests.db_tables import create_tables_unless_migrated, with_parents


def _database(monkeypatch, migrated: bool) -> list:
    """A database that is migrated or not; returns the create_all calls it receives."""
    monkeypatch.setattr(
        db_tables,
        "inspect",
        lambda sync: SimpleNamespace(has_table=lambda name: migrated and name == "alembic_version"),
    )
    calls = []
    monkeypatch.setattr(
        Base.metadata, "create_all", lambda sync, tables, checkfirst: calls.append(tables)
    )
    return calls


def test_parents_are_included_once_for_models_and_tables():
    tables = with_parents([UserSubscription, UserSubscription.__table__, Users])

    assert tables[0] is UserSubscription.__table__
    assert Users.__table__ in tables
    assert SubscriptionPlan.__table__ in tables
    assert len(tables) == len(set(tables))


def test_an_unmigrated_database_gets_the_tables_and_their_parents(monkeypatch):
    calls = _database(monkeypatch, migrated=False)

    create_tables_unless_migrated(object(), [UserSubscription])

    assert len(calls) == 1
    assert {UserSubscription.__table__, Users.__table__, SubscriptionPlan.__table__} <= set(
        calls[0]
    )


def test_a_migrated_database_gets_nothing(monkeypatch):
    """Its schema is the migrations': a table a migration lacks must fail the test."""
    calls = _database(monkeypatch, migrated=True)

    create_tables_unless_migrated(object(), [UserSubscription])

    assert calls == []
