from sqlalchemy import Boolean, Column, String, Text
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


# -------------------------
# Permissions Model
# -------------------------
class Permission(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "permissions"

    # id, created_at now provided by mixins
    name = Column(String(150), nullable=False, unique=True)
    display_name = Column(String(200))
    description = Column(Text)
    resource = Column(String(50))
    action = Column(String(50))
    # Seeded permissions (scripts/seeds/seed_permissions.py) are protected
    # from deletion regardless of role assignment - see
    # PermissionService.delete_permission.
    is_system = Column(Boolean, nullable=False, default=False, server_default="false")

    # Relationships
    roles = relationship("RolePermission", back_populates="permission")

    # to_dict() inherited from SerializableMixin
