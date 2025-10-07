"""
Brand Voice Service - Business Logic for Workspace Brand Voice Management

This service encapsulates all business logic related to workspace brand voice
configuration, including creation, update, and retrieval.

Responsibilities:
- Brand voice upsert (create or update)
- Brand voice retrieval
- Workspace membership validation

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Validate workspace existence (assumes valid UUID)
"""

from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.models.workspace_models.brand_voice import BrandVoice
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    WrextAuthenticationException
)


class BrandVoiceService:
    """Service for workspace brand voice management"""

    def __init__(self, db: AsyncSession):
        """
        Initialize BrandVoiceService.

        Args:
            db: Async database session
        """
        self.db = db

    async def get_brand_voice(
        self,
        workspace_id: UUID,
        user_id: UUID
    ) -> Optional[BrandVoice]:
        """
        Get brand voice for a workspace.

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID (for membership check)

        Returns:
            BrandVoice object or None if not configured

        Raises:
            WrextAuthenticationException: If user not workspace member
        """
        # Verify workspace membership
        await self._verify_workspace_membership(workspace_id, user_id)

        # Get brand voice
        result = await self.db.execute(
            select(BrandVoice).where(BrandVoice.workspace_id == workspace_id)
        )
        brand_voice = result.scalar_one_or_none()

        return brand_voice

    async def upsert_brand_voice(
        self,
        workspace_id: UUID,
        user_id: UUID,
        tone: Optional[str] = None,
        style: Optional[str] = None,
        vocabulary: Optional[str] = None,
        guidelines: Optional[str] = None
    ) -> BrandVoice:
        """
        Create or update brand voice for workspace.

        Business Rules:
        - User must be workspace member
        - Creates new if doesn't exist
        - Updates existing if exists
        - Only updates provided fields

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID (for membership check)
            tone: Optional brand tone description
            style: Optional writing style description
            vocabulary: Optional vocabulary guidelines
            guidelines: Optional additional guidelines

        Returns:
            BrandVoice object (created or updated)

        Raises:
            WrextAuthenticationException: If user not workspace member
        """
        # Verify workspace membership
        await self._verify_workspace_membership(workspace_id, user_id)

        # Check if brand voice exists
        result = await self.db.execute(
            select(BrandVoice).where(BrandVoice.workspace_id == workspace_id)
        )
        brand_voice = result.scalar_one_or_none()

        if brand_voice:
            # Update existing
            if tone is not None:
                brand_voice.tone = tone
            if style is not None:
                brand_voice.style = style
            if vocabulary is not None:
                brand_voice.vocabulary = vocabulary
            if guidelines is not None:
                brand_voice.guidelines = guidelines

            brand_voice.updated_at = datetime.utcnow()
            brand_voice.updated_by_user_id = user_id

            action = "updated"
        else:
            # Create new
            brand_voice = BrandVoice(
                workspace_id=workspace_id,
                tone=tone,
                style=style,
                vocabulary=vocabulary,
                guidelines=guidelines,
                created_by_user_id=user_id,
                updated_by_user_id=user_id
            )
            self.db.add(brand_voice)
            action = "created"

        await self.db.flush()
        await self.db.refresh(brand_voice)

        logger.info(
            f"Brand voice {action} for workspace {workspace_id}",
            extra={"workspace_id": str(workspace_id), "action": action}
        )

        return brand_voice

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _verify_workspace_membership(
        self,
        workspace_id: UUID,
        user_id: UUID
    ) -> WorkspaceMembers:
        """
        Verify user is workspace member.

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID

        Returns:
            WorkspaceMembers object

        Raises:
            WrextAuthenticationException: If user not member
        """
        result = await self.db.execute(
            select(WorkspaceMembers).where(
                WorkspaceMembers.workspace_id == workspace_id,
                WorkspaceMembers.user_id == user_id
            )
        )
        membership = result.scalar_one_or_none()

        if not membership:
            raise WrextAuthenticationException(
                message="You are not a member of this workspace",
                context={"workspace_id": str(workspace_id)}
            )

        return membership
