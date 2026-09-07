from sqlalchemy import Column, String, Boolean, Integer, Text
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin


# -------------------------
# Roles
# -------------------------
class Role(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "roles"

    # id, created_at, updated_at provided by mixins
    name = Column(String(100), unique=True, nullable=False)
    display_name = Column(String(150), nullable=False)
    description = Column(Text)
    hierarchy_level = Column(Integer, default=0)

    # Role Classification
    is_system_role = Column(Boolean, default=False)
    is_workspace_role = Column(Boolean, default=False, nullable=False)

    # Relationships
    permissions = relationship("RolePermission", back_populates="role")
    user_roles = relationship("UserRole", back_populates="role")
    invited_roles = relationship("UserInvitations", back_populates="role", passive_deletes=True)
