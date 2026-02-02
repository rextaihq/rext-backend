from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class Library(Base, SerializableMixin):
    __tablename__ = "library"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False
    )

    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspace.id"),
        nullable=False
    )

    keywords = Column(String(100))

    user = relationship(
        "Users",
        back_populates="library_items"
    )

    workspace = relationship(
        "WorkspaceModel",
        back_populates="library_items"
    )
