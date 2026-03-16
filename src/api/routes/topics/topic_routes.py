from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.response_utils import success, created
from src.services.topic_service import TopicService
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.topic_responses import (
    TopicResponse, 
    TopicListResponse, 
    TopicDeleteResponse
)
from src.api.schema.topic_schema import UpdateTopicRequest, DeleteTopics

router = APIRouter(prefix="/workspaces/{workspace_id}/topics", tags=["Topics"])

@router.get("", response_model=SuccessResponse[TopicListResponse])
@require_permissions("workspace.read", workspace_scoped=True)
@db_transaction_handler("list topics", auto_commit=False)
async def list_workspace_topics(
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    """List all topics for a workspace."""
    service = TopicService(db)
    topics = await service.get_workspace_topics(UUID(workspace_id))
    
    return success(data={
        "topics": [t.to_dict() for t in topics],
        "total_count": len(topics)
    })

@router.get("/{topic_id}", response_model=SuccessResponse[TopicResponse])
@require_permissions("workspace.read", workspace_scoped=True)
@db_transaction_handler("get topic", auto_commit=False)
async def get_topic(
    workspace_id: str,
    topic_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    """Get a specific topic by ID."""
    service = TopicService(db)
    topic = await service.get_topic_by_id(UUID(topic_id))
    return success(data=topic.to_dict())

@router.patch("/{topic_id}", response_model=SuccessResponse[TopicResponse])
@require_permissions("workspace.update", workspace_scoped=True)
@db_transaction_handler("update topic")
async def update_topic(
    workspace_id: str,
    topic_id: str,
    update_data: UpdateTopicRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """Update a topic's metadata or approval status."""
    service = TopicService(db)
    # Filter out None values from the request to avoid overwriting with nulls
    data = update_data.model_dump(exclude_unset=True)
    if "topic_id" in data:
        del data["topic_id"]
        
    topic = await service.update_topic(UUID(topic_id), data)
    return success(data=topic.to_dict(), message="Topic updated successfully")

@router.delete("", response_model=SuccessResponse[TopicDeleteResponse])
@require_permissions("workspace.update", workspace_scoped=True)
@db_transaction_handler("delete topics")
async def delete_topics(
    workspace_id: str,
    payload: DeleteTopics,
    db: AsyncSession = Depends(get_async_db)
):
    """Batch delete topics from a workspace."""
    service = TopicService(db)
    count = await service.delete_topics(
        [UUID(tid) for tid in payload.topic_ids], 
        UUID(workspace_id)
    )
    return success(
        data={"message": f"Deleted {count} topics", "deleted_count": count},
        message="Topics deleted successfully"
    )
