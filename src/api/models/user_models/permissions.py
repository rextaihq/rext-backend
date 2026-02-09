from sqlalchemy import Column, String, Text
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin


# -------------------------
# Permissions Model
# -------------------------
class Permission(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "permissions"

    # id, created_at now provided by mixins
    name = Column(String(150), nullable=False)
    display_name = Column(String(200))
    description = Column(Text)
    resource = Column(String(50))
    action = Column(String(50))

    # Relationships
    roles = relationship("RolePermission", back_populates="permission")

    # to_dict() inherited from SerializableMixin