from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.models.content_models.content import Content
from src.api.schema.content_health_schema import ContentHealthScoreResponse
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.content_health_score_service import ContentHealthScoreService
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace

router = APIRouter(prefix="/google/content", tags=["Google Integration"])


@router.get("/{content_id}/health-score", response_model=SuccessResponse[ContentHealthScoreResponse])
@db_transaction_handler("get content health score")
@require_permissions("content.read", workspace_scoped=True)
async def get_content_health_score(
    content_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Module 3 Content Health Score: composite 0-100 quality score for a single
    article, with the 6-component breakdown. Built entirely from data other
    jobs have already synced (GSC/GA4, index status, on-page SEO fields) —
    no external API calls in this request path.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    content = await db.get(Content, content_id)
    if not content or content.workspace_id != workspace.id or content.deleted_at is not None:
        raise ResourceNotFoundException(resource_type="Content", resource_id=str(content_id))

    result = await ContentHealthScoreService(db).score_content(content_id)
    if not result:
        raise ResourceNotFoundException(resource_type="Content", resource_id=str(content_id))

    return {
        "content_id": result.content_id,
        "overall": result.overall,
        "components": result.components,
        "capped_due_to_indexing": result.capped_due_to_indexing,
    }
