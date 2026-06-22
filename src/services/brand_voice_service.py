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

from typing import Optional, Dict, Any, Union
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from src.api.models.knowledge_models.knowledge_model import BrandVoice
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.utils.logger import logger
from src.api.cache.decorators import invalidate_cache_key
from src.api.middleware.exceptions import RextAuthenticationException
from src.api.schema.knowledge_schema import BrandSchema


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
            RextAuthenticationException: If user not workspace member
        """
        # Verify workspace membership
        await self._verify_workspace_membership(workspace_id, user_id)

        from sqlalchemy.orm import joinedload
        # Get brand voice with workspace and personas loaded
        result = await self.db.execute(
            select(BrandVoice)
            .options(
                joinedload(BrandVoice.workspace).joinedload(WorkspaceModel.personas)
            )
            .where(BrandVoice.workspace_id == workspace_id)
        )
        brand_voice = result.unique().scalar_one_or_none()

        return brand_voice

    async def upsert_brand_voice(
        self,
        workspace_id: UUID,
        user_id: UUID,
        brand_data: Union[BrandSchema, Dict[str, Any]]
    ) -> BrandVoice:
        """
        Create or update brand voice for workspace.

        Business Rules:
        - User must be workspace member
        - Creates new if doesn't exist
        - Updates existing if exists
        - Supports data provided as BrandSchema or mapping

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID (for membership check)
            brand_data: Structured brand voice payload

        Returns:
            BrandVoice object (created or updated)

        Raises:
            RextAuthenticationException: If user not workspace member
        """
        # Verify workspace membership
        await self._verify_workspace_membership(workspace_id, user_id)

        # Check if brand voice exists
        result = await self.db.execute(
            select(BrandVoice).where(BrandVoice.workspace_id == workspace_id)
        )
        brand_voice = result.scalar_one_or_none()

        payload = self._normalize_brand_data(brand_data)

        if brand_voice:
            for field, value in payload.items():
                setattr(brand_voice, field, value)

            action = "updated"
        else:
            # Create new brand voice entry
            brand_voice = BrandVoice(
                workspace_id=workspace_id,
                **payload
            )
            self.db.add(brand_voice)
            action = "created"

        await self.db.flush()
        
        # Eagerly load workspace and personas for serialization
        from sqlalchemy.orm import joinedload
        result = await self.db.execute(
            select(BrandVoice)
            .options(
                joinedload(BrandVoice.workspace).joinedload(WorkspaceModel.personas)
            )
            .where(BrandVoice.id == brand_voice.id)
        )
        brand_voice = result.unique().scalar_one()

        logger.info(
            f"Brand voice {action} for workspace {workspace_id}",
            extra={"workspace_id": str(workspace_id), "action": action}
        )
        
        # Invalidate workspace:brand_voice cache
        cache_key = f"workspace:brand_voice:{workspace_id}"
        await invalidate_cache_key(cache_key)

        return brand_voice

    async def delete_brand_voice(
        self,
        workspace_id: UUID,
        user_id: UUID
    ) -> bool:
        """
        Delete brand voice for a workspace.

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID (for membership check)

        Returns:
            True if deleted, False if not found

        Raises:
            RextAuthenticationException: If user not workspace member
        """
        # Verify workspace membership
        await self._verify_workspace_membership(workspace_id, user_id)

        # Delete brand voice
        result = await self.db.execute(
            delete(BrandVoice).where(BrandVoice.workspace_id == workspace_id)
        )

        deleted_count = result.rowcount
        
        if deleted_count > 0:
            # Invalidate workspace:brand_voice cache
            cache_key = f"workspace:brand_voice:{workspace_id}"
            await invalidate_cache_key(cache_key)
            
        return deleted_count > 0

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
            RextAuthenticationException: If user not member
        """
        result = await self.db.execute(
            select(WorkspaceMembers).where(
                WorkspaceMembers.workspace_id == workspace_id,
                WorkspaceMembers.user_id == user_id
            )
        )
        membership = result.scalar_one_or_none()

        if not membership:
            raise RextAuthenticationException(
                message="You are not a member of this workspace",
                context={"workspace_id": str(workspace_id)}
            )

        return membership

    # --------------------------------------------------------------------
    # Internal helpers
    # --------------------------------------------------------------------

    def _normalize_brand_data(
        self,
        brand_data: Union[BrandSchema, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Convert brand voice payload into model-compatible structure.
        
        This method ensures all fields are correctly extracted from either a 
        BrandSchema instance or a dictionary.
        """
        if isinstance(brand_data, BrandSchema):
            data = brand_data.model_dump()
        else:
            data = dict(brand_data)

        return {
            "about": data.get("about"),
            "customer_profile": data.get("customer_profile"),
            "selling_position": data.get("selling_position"),
            "target_audience": data.get("target_audience"),
            "brand_voice": data.get("brand_voice"),
            "competitors": data.get("competitors"),
            # content_strategy is already mapped to content_pillar by Pydantic AliasChoices
            "content_pillar": data.get("content_pillar"),
            # PLC fields
            "product_name": data.get("product_name"),
            "product_vocabulary": data.get("product_vocabulary"),
            "forbidden_words": data.get("forbidden_words"),
            "brand_ctas": data.get("brand_ctas"),
            "key_differentiators": data.get("key_differentiators"),
            "tone_examples": data.get("tone_examples"),
            "use_cases": data.get("use_cases"),
        }
