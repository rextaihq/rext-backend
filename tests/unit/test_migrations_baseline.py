"""The squashed baseline, the Alembic hooks and the seed data stay consistent."""

import importlib.util
import re
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import Column, Index, MetaData, Table

from scripts.seeds.seed_permissions import PERMISSIONS, ROLE_PERMISSION_ASSIGNMENTS, ROLES
from scripts.seeds.seed_subscription_plans import PLANS
from src.api.database.langgraph_tables import LANGGRAPH_TABLES
from src.api.database.migrations import include_object, render_item
from src.utils.encryption import EncryptedLongText, EncryptedText

BASELINE = Path(__file__).parents[2] / "alembic" / "versions" / "3c9e1e5d5028_baseline.py"


def _baseline():
    spec = importlib.util.spec_from_file_location("baseline", BASELINE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_baseline_keeps_the_old_head_and_starts_the_history():
    baseline = _baseline()

    assert baseline.revision == "3c9e1e5d5028"
    assert baseline.down_revision is None


def test_the_baseline_schema_splits_into_whole_statements():
    baseline = _baseline()
    statements = list(baseline._statements(baseline.SCHEMA.read_text()))

    assert len(statements) == 463
    assert all(statement.rstrip().endswith(";") for statement in statements)
    (function,) = [s for s in statements if s.startswith("CREATE FUNCTION")]
    assert function.count("$$") == 2
    assert not any("alembic_version" in s for s in statements)
    assert not any(
        s.startswith(f"CREATE TABLE public.{t} (") for t in LANGGRAPH_TABLES for s in statements
    )


def test_the_schema_holds_nothing_op_execute_would_read_as_a_bind_parameter():
    # op.execute wraps each statement in text(), which reads ":name" as a parameter
    # (SQLAlchemy's pattern); a "::" cast or "00:00" is not one.
    schema = _baseline().SCHEMA.read_text()

    assert re.findall(r"(?<![:\w\\]):(\w+)(?!:)", schema) == []


def test_a_function_body_with_semicolons_stays_one_statement():
    sql = (
        "CREATE FUNCTION public.f() RETURNS trigger\n    LANGUAGE plpgsql\n    AS $$\nBEGIN\n"
        "    RETURN NEW;\nEND;\n$$;\n\nCREATE TABLE public.t (\n    id integer\n);\n"
    )

    statements = list(_baseline()._statements(sql))

    assert len(statements) == 2
    assert statements[0].endswith("END;\n$$;")
    assert statements[1].startswith("CREATE TABLE public.t")


def test_langgraph_tables_are_left_out_of_autogenerate():
    metadata = MetaData()
    thread = Table(
        "thread", metadata, Column("thread_id", sa.Uuid), Index("thread_status_idx", "thread_id")
    )
    users = Table("users", metadata, Column("id", sa.Uuid), Index("ix_users_id", "id"))

    assert include_object(thread, "thread", "table", True, None) is False
    assert include_object(thread.c.thread_id, "thread_id", "column", True, None) is False
    assert (
        include_object(next(iter(thread.indexes)), "thread_status_idx", "index", True, None)
        is False
    )
    assert include_object(users, "users", "table", False, users) is True
    assert include_object(users.c.id, "id", "column", False, users.c.id) is True
    assert include_object(next(iter(users.indexes)), "ix_users_id", "index", False, None) is True


def test_encrypted_columns_are_written_as_the_type_they_store():
    assert render_item("type", EncryptedText(), None) == "sa.String()"
    assert render_item("type", EncryptedLongText(), None) == "sa.Text()"
    assert render_item("type", sa.Integer(), None) is False
    assert render_item("column", EncryptedText(), None) is False


def test_role_permissions_name_seeded_roles_and_permissions():
    roles = {role["name"] for role in ROLES}
    permissions = {permission[0] for permission in PERMISSIONS}

    for role, granted in ROLE_PERMISSION_ASSIGNMENTS.items():
        assert role in roles
        assert set(granted) <= permissions, role


def test_seed_plans_are_unique_by_name():
    names = [plan["name"] for plan in PLANS]

    assert len(names) == len(set(names)) == 6
