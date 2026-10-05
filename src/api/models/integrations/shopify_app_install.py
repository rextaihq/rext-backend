import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from src.api.database.base import Base
from src.utils.encryption import EncryptedLongText


class ShopifyAppInstall(Base):
    """Global registry of Shopify stores that have installed the app."""

    __tablename__ = "shopify_app_installs"
    __table_args__ = (UniqueConstraint("shop_url", name="shopify_app_installs_shop_url_key"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_url = Column(String(255), nullable=False, index=True)
    access_token = Column(EncryptedLongText, nullable=False)
    scopes = Column(String, nullable=True)
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspace.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    linked_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_at = Column(DateTime(timezone=True), nullable=True)
    installed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
