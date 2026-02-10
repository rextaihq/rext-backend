"""Customer Note model for admin internal notes."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class CustomerNote(Base, SerializableMixin):
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
