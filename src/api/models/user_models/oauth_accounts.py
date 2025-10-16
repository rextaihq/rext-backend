"""
OAuth Accounts Model

Tracks OAuth provider accounts linked to users.
Enables users to sign in with multiple OAuth providers.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class OAuthAccount(Base, SerializableMixin):
    """
    OAuth provider accounts linked to users.

    Each record represents one OAuth account (e.g., Google, GitHub) linked to a user.
    Users can have multiple OAuth accounts for different providers.
    """
    __tablename__ = "oauth_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)

    # User this OAuth account belongs to
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # OAuth provider details
    provider = Column(String(50), nullable=False)  # google, github, etc.
    provider_account_id = Column(String(255), nullable=False)  # Provider's unique ID for this account
    provider_account_email = Column(String(255))  # Email from provider (may differ from user.email)

    # OAuth tokens (encrypted in production)
    access_token = Column(Text)  # OAuth access token
    refresh_token = Column(Text)  # OAuth refresh token (if provider supports it)
    token_expires_at = Column(TIMESTAMP)  # When the access token expires

    # Account metadata
    provider_username = Column(String(255))  # Username from provider
    provider_profile_url = Column(String(500))  # Profile URL from provider
    provider_avatar_url = Column(String(500))  # Avatar URL from provider

    # Timestamps
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = Column(TIMESTAMP)  # Last time this account was used to sign in

    # Relationships
    user = relationship("Users", back_populates="oauth_accounts")

    # Constraints
    __table_args__ = (
        # Each provider account can only be linked to one user
        UniqueConstraint('provider', 'provider_account_id', name='uq_provider_account'),
    )

    def to_dict(self, **kwargs):
        """Exclude sensitive tokens from serialization"""
        if 'exclude' not in kwargs:
            kwargs['exclude'] = ['access_token', 'refresh_token']
        return super().to_dict(**kwargs)
