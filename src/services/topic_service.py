"""
Topic Service - Business Logic for Topic Operations

This service encapsulates all business logic related to topic management,
including creating, updating, deleting, and retrieving topics.

Responsibilities:
- Topic CRUD operations
- Batch topic creation with enrichment
- Topic approval workflow
- Topic retrieval with filtering

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Authentication/authorization (that's decorators)
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.topic_models.topic_models import TopicsModel as Topics
from src.api.schema.topic_schema import UpdateTopicRequest
from src.states.schemas import SaveTopicRequest
from src.services.topic_enrichment_service import TopicEnrichmentService
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    WrextValidationException
)


class TopicService:
    """Service for topic business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize TopicService.

        Args:
            db: Async database session
        """
        self.db = db
        self.enrichment_service = TopicEnrichmentService()

    async def create_topics(
        self,
        workspace_id: UUID,
        user_id: UUID,
        topics_data: List[SaveTopicRequest]
    ) -> List[Topics]:
        """
        Create multiple topics with enrichment.

        Business Rules:
        - Topics are enriched with suggested defaults, goal alignment, etc.
        - Topics default to unapproved status (approved=False)
        - Failed topics are logged but don't stop batch processing

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID (for logging)
            topics_data: List of topic data to save

        Returns:
            List of created Topic objects

        Raises:
            WrextValidationException: If all topics fail to save
        """
        saved = []

        for save_topic_data in topics_data:
            try:
                # Convert SaveTopicRequest to dict for enrichment
                basic_topic_dict = {
                    "title": save_topic_data.title,
                    "angle": save_topic_data.angle,
                    "description": save_topic_data.description,
                    "channel_fit": save_topic_data.channel_fit,
                    "audience_fit": save_topic_data.audience_fit,
                    "why_it_works": save_topic_data.why_it_works,
                    "tags": save_topic_data.tags,
                    "scores": save_topic_data.scores
                }

                # Use input params if provided, otherwise use defaults
                input_params = save_topic_data.input_params or {}

                # Enrich the topic with full structured data
                enriched_topic = self.enrichment_service.enrich_topic(basic_topic_dict, input_params)

                # Use the provided ID from frontend, ensuring it's a proper UUID
                topic_uuid = UUID(save_topic_data.id) if isinstance(save_topic_data.id, str) else save_topic_data.id
                enriched_topic.id = topic_uuid

                # Create database record with fully enriched data
                db_topic = Topics(
                    id=topic_uuid,
                    workspace_id=workspace_id,
                    title=enriched_topic.title,
                    angle=enriched_topic.angle,
                    description=enriched_topic.description,
                    channel_fit=enriched_topic.channel_fit,
                    audience_fit=enriched_topic.audience_fit,
                    why_it_works=enriched_topic.why_it_works,
                    scores=enriched_topic.scores.model_dump(),
                    tags=enriched_topic.tags,
                    approved=False,  # Explicitly set to false - topics require manual approval
                    approved_at=None,  # Will be set when topic is approved
                    suggested_defaults=enriched_topic.suggested_defaults.model_dump(),
                    goal_alignment=enriched_topic.goal_alignment.model_dump(),
                    content_guidance=enriched_topic.content_guidance.model_dump(),
                    audience_insights=enriched_topic.audience_insights.model_dump(),
                    internal_research_config=enriched_topic.internal_research_config.model_dump(),
                    user_settings=enriched_topic.user_settings.model_dump()
                )
                self.db.add(db_topic)
                saved.append(db_topic)

            except Exception as topic_err:
                logger.info(f"Failed to process topic {save_topic_data.id}: {topic_err}")
                # Continue with other topics rather than failing entirely
                continue

        if not saved:
            raise WrextValidationException(
                message="No topics could be saved successfully",
                field_errors={"topics": ["All topic saves failed"]}
            )

        logger.info(
            f"Created {len(saved)} topics",
            extra={"workspace_id": str(workspace_id), "user_id": str(user_id), "count": len(saved)}
        )

        return saved

    async def update_topic(
        self,
        topic_id: UUID,
        workspace_id: UUID,
        data: UpdateTopicRequest
    ) -> Topics:
        """
        Update an existing topic.

        Args:
            topic_id: Topic UUID
            workspace_id: Workspace UUID (for verification)
            data: Topic update data

        Returns:
            Updated Topic object

        Raises:
            ResourceNotFoundException: If topic not found
        """
        topic = await self._get_topic_or_404(topic_id, workspace_id)

        updated_fields = []

        # Update only the fields that are provided
        if data.title is not None:
            topic.title = data.title
            updated_fields.append("title")

        if data.angle is not None:
            topic.angle = data.angle
            updated_fields.append("angle")

        if data.description is not None:
            topic.description = data.description
            updated_fields.append("description")

        if data.channel_fit is not None:
            topic.channel_fit = data.channel_fit
            updated_fields.append("channel_fit")

        if data.audience_fit is not None:
            topic.audience_fit = data.audience_fit
            updated_fields.append("audience_fit")

        if data.why_it_works is not None:
            topic.why_it_works = data.why_it_works
            updated_fields.append("why_it_works")

        if data.scores is not None:
            topic.scores = data.scores.model_dump() if hasattr(data.scores, 'model_dump') else data.scores
            updated_fields.append("scores")

        if data.tags is not None:
            topic.tags = data.tags
            updated_fields.append("tags")

        if data.approved is not None:
            topic.approved = data.approved
            updated_fields.append("approved")
            if data.approved:
                topic.approved_at = datetime.now(timezone.utc)

        topic.updated_at = datetime.now(timezone.utc)

        logger.info(
            f"Topic updated: {topic_id}, fields: {', '.join(updated_fields)}",
            extra={"workspace_id": str(workspace_id), "topic_id": str(topic_id)}
        )

        return topic

    async def delete_topics(
        self,
        topic_ids: List[UUID],
        workspace_id: UUID
    ) -> Dict[str, Any]:
        """
        Delete multiple topics by IDs.

        Args:
            topic_ids: List of topic UUIDs to delete
            workspace_id: Workspace UUID (for verification)

        Returns:
            Dict with deleted_count, deleted_ids, missing_ids

        Raises:
            ResourceNotFoundException: If no topics found
        """
        # Fetch topics - only from the specified workspace
        result = await self.db.execute(
            select(Topics).where(
                Topics.id.in_(topic_ids),
                Topics.workspace_id == workspace_id
            )
        )
        topics = result.scalars().all()

        if not topics:
            raise ResourceNotFoundException(
                message="No topics found for the provided IDs",
                resource_type="topics",
                context={"requested_ids": [str(tid) for tid in topic_ids]}
            )

        # Check if all requested topics were found
        found_ids = [topic.id for topic in topics]
        missing_ids = [tid for tid in topic_ids if tid not in found_ids]

        # Delete all found topics
        deleted_count = 0
        for topic in topics:
            await self.db.delete(topic)
            deleted_count += 1

        logger.info(
            f"Deleted {deleted_count} topics",
            extra={"workspace_id": str(workspace_id), "deleted_count": deleted_count}
        )

        return {
            "deleted_count": deleted_count,
            "deleted_ids": found_ids,
            "missing_ids": missing_ids if missing_ids else None
        }

    async def approve_topic(
        self,
        topic_id: UUID,
        workspace_id: UUID,
        user_id: UUID
    ) -> Topics:
        """
        Approve a topic for content generation.

        Business Rules:
        - Sets approved=True
        - Sets approved_at timestamp
        - Permission check ('topic.approve') handled in route decorator

        Args:
            topic_id: Topic UUID
            workspace_id: Workspace UUID
            user_id: User UUID (for logging)

        Returns:
            Approved Topic object

        Raises:
            ResourceNotFoundException: If topic not found
        """
        topic = await self._get_topic_or_404(topic_id, workspace_id)

        topic.approved = True
        topic.approved_at = datetime.now(timezone.utc)
        topic.updated_at = datetime.now(timezone.utc)

        logger.info(
            f"Topic approved: {topic_id}",
            extra={"workspace_id": str(workspace_id), "user_id": str(user_id)}
        )

        return topic

    async def get_topics(
        self,
        workspace_id: UUID,
        approved_only: bool = False
    ) -> List[Topics]:
        """
        Get all topics for a workspace.

        Args:
            workspace_id: Workspace UUID
            approved_only: If True, return only approved topics

        Returns:
            List of Topic objects
        """
        query = select(Topics).where(Topics.workspace_id == workspace_id)

        if approved_only:
            query = query.where(Topics.approved == True)

        query = query.order_by(
            Topics.updated_at.desc().nulls_last(),
            Topics.created_at.desc()
        )

        result = await self.db.execute(query)
        topics = result.scalars().all()

        logger.info(
            f"Retrieved {len(topics)} topics",
            extra={"workspace_id": str(workspace_id), "approved_only": approved_only, "count": len(topics)}
        )

        return topics

    async def get_topic(
        self,
        topic_id: UUID,
        workspace_id: UUID
    ) -> Topics:
        """
        Get a single topic by ID.

        Args:
            topic_id: Topic UUID
            workspace_id: Workspace UUID (for verification)

        Returns:
            Topic object

        Raises:
            ResourceNotFoundException: If topic not found
        """
        return await self._get_topic_or_404(topic_id, workspace_id)

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _get_topic_or_404(self, topic_id: UUID, workspace_id: UUID) -> Topics:
        """
        Get topic by ID or raise 404.

        Args:
            topic_id: Topic UUID
            workspace_id: Workspace UUID (for verification)

        Returns:
            Topic object

        Raises:
            ResourceNotFoundException: If topic not found or not in workspace
        """
        result = await self.db.execute(
            select(Topics).where(
                Topics.id == topic_id,
                Topics.workspace_id == workspace_id
            )
        )
        topic = result.scalar_one_or_none()

        if not topic:
            raise ResourceNotFoundException(
                resource_type="Topic",
                resource_id=str(topic_id)
            )

        return topic
