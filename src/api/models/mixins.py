"""
Reusable SQLAlchemy model mixins for the Rext backend.

These mixins provide standardized column definitions for common patterns:
- UUIDPrimaryKeyMixin: UUID primary key
- TimestampMixin: created_at / updated_at columns
- SoftDeleteMixin: deleted_at column with filtering helpers
- WorkspaceScopedMixin: workspace_id FK with index

Usage:
    from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin
    from src.api.database.base import Base
    from src.api.models.base import SerializableMixin

    class MyModel(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin):
        __tablename__ = "my_table"
        name = Column(String, nullable=False)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID


class UUIDPrimaryKeyMixin:
    """Standardized UUID primary key for all models."""
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False,
    )


class TimestampMixin:
    """Standardized created_at/updated_at timestamps with timezone awareness."""
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class SoftDeleteMixin:
    """Standardized soft delete support with deleted_at timestamp."""
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    @classmethod
    def active_filter(cls):
        """Return a filter expression for non-deleted records.

        Usage in queries:
            query = select(MyModel).where(MyModel.active_filter())
        """
        return cls.deleted_at.is_(None)

    @property
    def is_deleted(self) -> bool:
        """Check if the record has been soft-deleted."""
        return self.deleted_at is not None

    def soft_delete(self):
        """Mark the record as deleted."""
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self):
        """Restore a soft-deleted record."""
        self.deleted_at = None


class WorkspaceScopedMixin:
    """Standardized workspace_id FK with index for workspace-scoped models."""
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
