"""Customer Note model for admin internal notes."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID

from src.api.database.base import Base


class CustomerNote(Base):
    """
    Model for internal admin notes on customer accounts.

    Used for tracking support interactions, billing issues, technical notes, etc.
    """

    __tablename__ = "customer_notes"

    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    admin_id = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )
    note = Column(Text, nullable=False)
    category = Column(String(50))  # billing, support, technical, other
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict:
        """Convert note to dictionary."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "admin_id": str(self.admin_id),
            "note": self.note,
            "category": self.category,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
