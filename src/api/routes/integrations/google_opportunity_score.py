from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.models.content_models.content import Content
from src.api.schema.opportunity_score_schema import (
    OpportunityRankedListResponse,
    OpportunityScoreResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.opportunity_score_service import OpportunityScoreService
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace

router = APIRouter(prefix="/google", tags=["Google Integration"])


@router.get("/opportunities", response_model=SuccessResponse[OpportunityRankedListResponse])
@db_transaction_handler("get opportunity ranked list")
@require_permissions("content.read", workspace_scoped=True)
async def get_ranked_opportunities(
    workspace_id: str,
    request: Request,
    days: int = 28,
    page: int = 1,
    page_size: int = 25,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Module 4 Opportunity Score: published articles ranked by expected traffic
    growth potential after optimization. Built entirely from already-synced
    GSC data (page-level + per-query) — no external API calls in this
    request path.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    result = await OpportunityScoreService(db).list_ranked_opportunities(
        workspace_id=workspace.id, window_days=days, page=page, page_size=page_size,
    )

    return {"workspace_id": workspace.id, **result}


@router.get("/content/{content_id}/opportunity-score", response_model=SuccessResponse[OpportunityScoreResponse])
@db_transaction_handler("get content opportunity score")
@require_permissions("content.read", workspace_scoped=True)
async def get_content_opportunity_score(
    content_id: UUID,
    workspace_id: str,
    request: Request,
    days: int = 28,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Module 4 Opportunity Score: full breakdown for a single article."""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    content = await db.get(Content, content_id)
    if not content or content.workspace_id != workspace.id or content.deleted_at is not None:
        raise ResourceNotFoundException(resource_type="Content", resource_id=str(content_id))

    result = await OpportunityScoreService(db).score_content(content_id, window_days=days)
    if not result:
        raise ResourceNotFoundException(resource_type="Content", resource_id=str(content_id))

    return {
        "content_id": result.content_id,
        "score": result.score,
        "estimated_traffic_gain": result.estimated_traffic_gain,
        "estimated_ranking_gain": result.estimated_ranking_gain,
        "priority_level": result.priority_level,
        "estimated_time_to_improve": result.estimated_time_to_improve,
        "target_query": result.target_query,
        "target_query_impressions": result.target_query_impressions,
        "current_position": result.current_position,
        "target_position": result.target_position,
        "current_impressions": result.current_impressions,
        "capped_due_to_indexing": result.capped_due_to_indexing,
    }
