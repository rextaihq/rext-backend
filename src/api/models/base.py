"""
Base Model Mixins for SQLAlchemy Models

Provides common functionality for all models:
- Serialization (to_dict)
- UUID/datetime handling
- Relationship loading
- Field exclusion for sensitive data

Usage:
    from src.api.models.base import SerializableMixin
    from src.api.database.database import Base

    class MyModel(Base, SerializableMixin):
        __tablename__ = "my_table"

        id = Column(UUID(as_uuid=True), primary_key=True)
        name = Column(String, nullable=False)
        created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

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

from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import UUID
from decimal import Decimal

from sqlalchemy.orm import class_mapper


class SerializableMixin:
    """Mixin to add to_dict() method to SQLAlchemy models"""

    def to_dict(
        self,
        include_relationships: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        include_nulls: bool = False
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

            value = getattr(self, column.name)

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
            for rel_name in include_relationships:
                if hasattr(self, rel_name):
                    rel_obj = getattr(self, rel_name)

                    if rel_obj is None:
                        data[rel_name] = None
                    elif isinstance(rel_obj, list):
                        # One-to-many relationship
                        data[rel_name] = [
                            item.to_dict() if hasattr(item, 'to_dict') else str(item)
                            for item in rel_obj
                        ]
                    else:
                        # One-to-one or many-to-one relationship
                        data[rel_name] = (
                            rel_obj.to_dict() if hasattr(rel_obj, 'to_dict') else str(rel_obj)
                        )

        return data
