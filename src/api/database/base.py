"""
Database Base - Declarative Base for SQLAlchemy Models

This module provides the declarative base for all database models.
Uses SQLAlchemy 2.0's DeclarativeBase for modern type checking support.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.

    All models should inherit from this class:
        class MyModel(Base):
            __tablename__ = "my_table"
            ...

    For models that also need the SerializableMixin:
        class MyModel(Base, SerializableMixin):
            __tablename__ = "my_table"
            ...
    """

    pass
