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
            **topic_data
        )
        self.db.add(topic)
        await self.db.flush()
        return topic

    async def update_topic(self, topic_id: UUID, update_data: Dict[str, Any]) -> TopicsModel:
        topic = await self.get_topic_by_id(topic_id)
        for key, value in update_data.items():
            if hasattr(topic, key):
                setattr(topic, key, value)
        
        if 'approved' in update_data and update_data['approved']:
            topic.approved_at = datetime.now(timezone.utc)
            
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
