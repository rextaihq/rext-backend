from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy import select, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.models.topic_models.topic_models import TopicsModel
from src.api.middleware.exceptions import ResourceNotFoundException

class TopicService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_workspace_topics(self, workspace_id: UUID) -> List[TopicsModel]:
        stmt = select(TopicsModel).where(
            TopicsModel.workspace_id == workspace_id
        ).order_by(TopicsModel.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_topic_by_id(self, topic_id: UUID) -> TopicsModel:
        stmt = select(TopicsModel).where(TopicsModel.id == topic_id)
        result = await self.db.execute(stmt)
        topic = result.scalar_one_or_none()
        if not topic:
            raise ResourceNotFoundException(resource_type="Topic", resource_id=str(topic_id))
        return topic

    async def create_topic(self, workspace_id: UUID, topic_data: Dict[str, Any]) -> TopicsModel:
        topic = TopicsModel(
            workspace_id=workspace_id,
            title=topic_data.get('title', topic_data.get('topic_name')),
            angle=topic_data.get('angle', ''),
            description=topic_data.get('description', ''),
            channel_fit=topic_data.get('channel_fit', []),
            audience_fit=topic_data.get('audience_fit', []),
            why_it_works=topic_data.get('why_it_works'),
            scores=topic_data.get('scores', {}),
            tags=topic_data.get('tags', []),
            suggested_defaults=topic_data.get('suggested_defaults', {}),
            goal_alignment=topic_data.get('goal_alignment', {}),
            content_guidance=topic_data.get('content_guidance', {}),
            audience_insights=topic_data.get('audience_insights', {}),
            internal_research_config=topic_data.get('internal_research_config', {}),
            user_settings=topic_data.get('user_settings', {}),
            approved=topic_data.get('approved', False)
        )
        self.db.add(topic)
        await self.db.flush()
        return topic

    async def update_topic(self, topic_id: UUID, update_data: Dict[str, Any]) -> TopicsModel:
        topic = await self.get_topic_by_id(topic_id)
        
        # Handle the legacy topic_name field if it's passed
        if 'topic_name' in update_data and 'title' not in update_data:
            update_data['title'] = update_data.pop('topic_name')
            
        for key, value in update_data.items():
            if hasattr(topic, key) and value is not None:
                setattr(topic, key, value)
            
        topic.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return topic

    async def delete_topics(self, topic_ids: List[UUID], workspace_id: UUID) -> int:
        stmt = delete(TopicsModel).where(
            and_(
                TopicsModel.id.in_(topic_ids),
                TopicsModel.workspace_id == workspace_id
            )
        )
        result = await self.db.execute(stmt)
        return result.rowcount
