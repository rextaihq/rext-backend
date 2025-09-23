from sqlalchemy import Column, String, func, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.api.database.database import Base
import uuid

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    notification_type = Column(String, nullable=False)  # error/success/info/warn/system/user
    status = Column(String, nullable=False, default="unread")  # read/unread
    created_time = Column(DateTime(timezone=True), server_default=func.now())
    updated_time = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self):
        return {
            "id": str(self.id),
            "title": self.title,
            "description": self.description,
            "notification_type": self.notification_type,
            "status": self.status,
            "created_time": self.created_time.isoformat() if self.created_time else None,
            "updated_time": self.updated_time.isoformat() if self.updated_time else None,
        }
