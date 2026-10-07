"""Hooks alembic/env.py passes to Alembic: what autogenerate compares and how it writes types."""

from sqlalchemy import TypeDecorator

from src.api.database.langgraph_tables import LANGGRAPH_TABLES


def include_object(object, name, type_, reflected, compare_to):
    """Leave the LangGraph tables, and everything on them, out of migrations.

    They have no models, so without this every autogenerate run proposes to drop
    them, and a migration that does wipes the runtime's own migration record (the
    server then never starts again).
    """
    table = object if type_ == "table" else getattr(object, "table", None)
    return getattr(table, "name", None) not in LANGGRAPH_TABLES


def render_item(type_, obj, autogen_context):
    """Write a TypeDecorator column (EncryptedText) as the type it stores, so a
    migration never imports application code."""
    if type_ == "type" and isinstance(obj, TypeDecorator):
        return f"sa.{obj.impl_instance!r}"
    return False
