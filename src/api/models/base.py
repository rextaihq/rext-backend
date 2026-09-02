"""
Base Model Mixins for SQLAlchemy Models

Provides common functionality for all models:
- Serialization (to_dict)
- UUID/datetime handling
- Relationship loading
- Field exclusion for sensitive data

Usage:
    from src.api.models.base import SerializableMixin
    from src.api.database.base import Base

    class MyModel(Base, SerializableMixin):
        __tablename__ = "my_table"

        id = Column(UUID(as_uuid=True), primary_key=True)
        name = Column(String, nullable=False)
        created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Basic serialization
    obj = MyModel(name="Example")
    data = obj.to_dict()
    # {'id': '123e4567-e89b-12d3-a456-426614174000', 'name': 'Example', 'created_at': '2025-01-15T10:30:00+00:00'}

    # With relationships
    data = obj.to_dict(include_relationships=["related_items"])

    # Exclude sensitive fields
    data = user.to_dict(exclude=["password_hash", "api_key"])

    # Custom fields (override to_dict)
    class CustomModel(Base, SerializableMixin):
        def to_dict(self, **kwargs):
            data = super().to_dict(**kwargs)
            data['computed_field'] = self.some_computation()
            return data
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.inspection import inspect
from sqlalchemy.orm import class_mapper


class SerializableMixin:
    """Mixin to add to_dict() method to SQLAlchemy models"""

    def to_dict(
        self,
        include_relationships: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        include_nulls: bool = False,
    ) -> Dict[str, Any]:
        """
        Convert model to dictionary for JSON serialization.

        Automatically handles:
        - UUID → string conversion
        - datetime → ISO 8601 string conversion
        - None value filtering
        - Relationship inclusion
        - Sensitive field exclusion

        Args:
            include_relationships: List of relationship names to include in output.
                                  Relationships are not included by default.
                                  Example: ["members", "topics"]
            exclude: List of column names to exclude from output.
                    Useful for sensitive fields like passwords.
                    Example: ["password_hash", "api_key", "secret_token"]
            include_nulls: Whether to include None values in output.
                          Default: False (None values are excluded)

        Returns:
            Dictionary representation of model with automatic type conversion

        Examples:
            >>> workspace = WorkspaceModel(name="Acme Corp", slug="acme")
            >>> data = workspace.to_dict()
            >>> print(data)
            {
                'id': '123e4567-e89b-12d3-a456-426614174000',
                'name': 'Acme Corp',
                'slug': 'acme',
                'created_at': '2025-01-15T10:30:00+00:00'
            }

            >>> # With relationships
            >>> data = workspace.to_dict(include_relationships=["members", "topics"])
            >>> print(data['members'])
            [{'id': '...', 'name': '...'}, ...]

            >>> # Exclude sensitive fields
            >>> user = User(email="user@example.com", password_hash="hashed")
            >>> data = user.to_dict(exclude=["password_hash"])
            >>> 'password_hash' in data
            False

            >>> # Include null values
            >>> content = Content(title="Draft", body_markdown=None)
            >>> data = content.to_dict(include_nulls=True)
            >>> data['body_markdown']
            None
        """
        exclude = exclude or []
        data = {}

        # Serialize columns
        mapper = class_mapper(self.__class__)
        for column in mapper.columns:
            if column.name in exclude:
                continue

            value = getattr(self, column.key)

            # Skip None values if requested
            if value is None and not include_nulls:
                continue

            # Type conversion
            if isinstance(value, UUID):
                data[column.name] = str(value)
            elif isinstance(value, datetime):
                data[column.name] = value.isoformat() if value else None
            elif isinstance(value, Decimal):
                data[column.name] = float(value)
            else:
                data[column.name] = value

        # Include relationships if requested
        if include_relationships:
            # Use inspection to check if relationships are loaded without triggering lazy loading
            inspector = inspect(self)

            for rel_name in include_relationships:
                # Check if the relationship exists on the model
                if rel_name not in inspector.mapper.relationships:
                    continue

                # Check if the relationship is loaded (won't trigger lazy load)
                from sqlalchemy.orm.base import NO_VALUE

                rel_state = inspector.attrs.get(rel_name)
                if rel_state is None or rel_state.loaded_value is NO_VALUE:
                    # Relationship not loaded, skip it
                    continue

                rel_obj = getattr(self, rel_name)

                if rel_obj is None:
                    data[rel_name] = None
                elif isinstance(rel_obj, list):
                    # One-to-many relationship
                    data[rel_name] = [
                        item.to_dict() if hasattr(item, "to_dict") else str(item)
                        for item in rel_obj
                    ]
                else:
                    # One-to-one or many-to-one relationship
                    data[rel_name] = (
                        rel_obj.to_dict() if hasattr(rel_obj, "to_dict") else str(rel_obj)
                    )

        return data


from sqlalchemy import Column, DateTime  # noqa: E402 -- intentional: avoids a circular import
from sqlalchemy.ext.hybrid import (  # noqa: E402 -- intentional: avoids a circular import
    hybrid_property,  # noqa: E402 -- intentional: avoids a circular import
)


class SoftDeleteMixin:
    """
    Mixin for soft-delete support on SQLAlchemy models.

    Adds a `deleted_at` column and provides:
    - `soft_delete()` / `restore()` instance methods
    - `is_deleted` hybrid property (works in Python and SQL)
    - `active()` class method for filtering queries

    Usage:
        class MyModel(Base, SerializableMixin, SoftDeleteMixin):
            __tablename__ = "my_table"

        # Query only active records:
        stmt = select(MyModel).where(MyModel.is_deleted == False)
        # Or use the helper:
        stmt = select(MyModel).where(MyModel.active())
    """

    deleted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Soft delete timestamp. NULL = active, non-NULL = deleted.",
    )

    @hybrid_property
    def is_deleted(self) -> bool:
        """Python-side check: is this record soft-deleted?"""
        return self.deleted_at is not None

    @is_deleted.expression
    def is_deleted(cls):
        """SQL-side expression: generates `deleted_at IS NOT NULL`."""
        return cls.deleted_at.isnot(None)

    def soft_delete(self) -> None:
        """Mark this record as soft-deleted."""
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.deleted_at = None

    @classmethod
    def active(cls):
        """Return a filter expression for non-deleted records.

        Usage: select(Model).where(Model.active())
        """
        return cls.deleted_at.is_(None)
