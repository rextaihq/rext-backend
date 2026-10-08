"""Hooks alembic/env.py passes to Alembic: what autogenerate compares and how it writes types."""

from sqlalchemy import TypeDecorator

from src.api.database.langgraph_tables import LANGGRAPH_TABLES

# Tables whose models went with the old product (rext-control#369, step 1) and whose rows stay
# until the migration that drops them (step 2, a later release). Until then they have no model,
# so they are left out here: an autogenerate run for something else must not propose to drop
# them early. The drop migration takes each name off this list.
RETIRED_TABLES = frozenset(
    {
        "customer_notes",
        "email_templates",
        "license_activations",
        "licenses",
    }
)


def include_object(object, name, type_, reflected, compare_to):
    """Leave the LangGraph tables and the retired ones, and everything on them, out of migrations.

    The LangGraph tables have no models, so without this every autogenerate run proposes to
    drop them, and a migration that does wipes the runtime's own migration record (the server
    then never starts again). The retired tables wait for their own drop migration.
    """
    table = object if type_ == "table" else getattr(object, "table", None)
    return getattr(table, "name", None) not in LANGGRAPH_TABLES | RETIRED_TABLES


def render_item(type_, obj, autogen_context):
    """Write a TypeDecorator column (EncryptedText) as the type it stores, so a
    migration never imports application code."""
    if type_ == "type" and isinstance(obj, TypeDecorator):
        return f"sa.{obj.impl_instance!r}"
    return False
