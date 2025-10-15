"""
Content Generation Routes

Handles AI-powered content generation using LangGraph workflows.
"""

from fastapi import APIRouter, Depends, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional
from pydantic import BaseModel, Field

from src.utils.logger import logger
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import WrextValidationException
from src.api.middleware.rate_limiter import ai_content_generation_rate_limit
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.services.langgraph_content_service import LangGraphContentService


router = APIRouter()


class GenerateContentRequest(BaseModel):
    """Request model for content generation"""
    content_id: UUID = Field(..., description="Content ID to generate for")
    topic_id: Optional[UUID] = Field(None, description="Topic ID for context")
    thread_id: Optional[UUID] = Field(None, description="Existing thread ID for continuation")
    regenerate: bool = Field(False, description="Whether to regenerate existing content")


class GenerateContentResponse(BaseModel):
    """Response model for content generation"""
    success: bool
    thread_id: str
    content_id: str
    message: str
    generated_content: Optional[dict] = None


# -------------------------
# Generate Content with LangGraph
# -------------------------
@router.post("/generate", response_model=GenerateContentResponse)
@db_transaction_handler("generate content", "Content generation initiated successfully")
@require_permissions("content.create", workspace_scoped=True)
async def generate_content_with_ai(
    data: GenerateContentRequest,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(ai_content_generation_rate_limit())
):
    """
    Generate content using LangGraph AI workflow.

    This endpoint triggers the LangGraph content generation workflow which:
    1. Creates or uses an existing thread ID for workflow tracking
    2. Fetches context from workspace, topic, and brand voice
    3. Executes the content generation pipeline
    4. Updates the content with generated text and thread ID

    Args:
        workspace_id: Workspace UUID or slug (query parameter)
        data: Generation request data including content_id and optional thread_id

    Returns:
        GenerateContentResponse with thread_id and generation status

    Requires:
        - JWT authentication
        - Workspace membership verification
        - content.create permission
    """
    user_id = user.get("identity")

    # Verify workspace access and membership
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    logger.info(
        f"Starting AI content generation for content {data.content_id} "
        f"in workspace {workspace.id} by user {user_id}"
    )

    # Initialize LangGraph service
    service = LangGraphContentService(db)

    try:
        # Generate content using LangGraph workflow
        result = await service.generate_content_with_langgraph(
            content_id=data.content_id,
            workspace_id=workspace.id,
            topic_id=data.topic_id,
            thread_id=data.thread_id,
            regenerate=data.regenerate
        )

        logger.info(
            f"Content generation completed for content {data.content_id} "
            f"with thread {result['thread_id']}"
        )

        return GenerateContentResponse(
            success=True,
            thread_id=result["thread_id"],
            content_id=str(data.content_id),
            message="Content generated successfully",
            generated_content=result.get("generated_content")
        )

    except Exception as e:
        logger.error(f"Content generation failed: {str(e)}")
        raise WrextValidationException(
            message=f"Content generation failed: {str(e)}",
            context={"content_id": str(data.content_id)}
        )


# -------------------------
# Get Thread History
# -------------------------
@router.get("/thread/{thread_id}/history")
@db_transaction_handler("get thread history", auto_commit=False)
@require_permissions("content.read", workspace_scoped=True)
async def get_thread_history(
    thread_id: UUID,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Get the execution history for a LangGraph thread.

    This endpoint retrieves the conversation and execution history
    for a specific LangGraph thread ID.

    Args:
        thread_id: LangGraph thread UUID
        workspace_id: Workspace UUID or slug (query parameter)

    Returns:
        Thread history information

    Requires:
        - JWT authentication
        - Workspace membership verification
        - content.read permission
    """
    user_id = user.get("identity")

    # Verify workspace access and membership
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    logger.info(f"Fetching thread history for {thread_id} in workspace {workspace.id}")

    # Initialize LangGraph service
    service = LangGraphContentService(db)

    # Get thread history
    history = await service.get_thread_history(thread_id)

    return {
        "thread_id": str(thread_id),
        "history": history
    }