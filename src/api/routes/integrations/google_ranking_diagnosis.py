from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.models.content_models.content import Content
from src.api.schema.ranking_diagnosis_schema import RankingDiagnosisResponse
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.ranking_diagnosis_service import RankingDiagnosisService
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace

router = APIRouter(prefix="/google", tags=["Google Integration"])


@router.get(
    "/content/{content_id}/ranking-diagnosis",
    response_model=SuccessResponse[RankingDiagnosisResponse],
)
@db_transaction_handler("get ranking diagnosis")
@require_permissions("content.read", workspace_scoped=True)
async def get_ranking_diagnosis(
    content_id: UUID,
    workspace_id: str,
    request: Request,
    days: int = 28,
    generate_ai_summary: bool = False,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Module 5 (AI Diagnosis): explains why this article's search performance
    changed. Always returns a rule-based diagnosis (deterministic, free,
    reuses Modules 1-4 data). Pass generate_ai_summary=true to additionally
    have an LLM narrate the same detected signals into clearer prose
    (credit-gated) — if unavailable for any reason, the rule-based diagnosis
    is returned unchanged, never blocked or fabricated.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    content = await db.get(Content, content_id)
    if not content or content.workspace_id != workspace.id or content.deleted_at is not None:
        raise ResourceNotFoundException(resource_type="Content", resource_id=str(content_id))

    result = await RankingDiagnosisService(db).diagnose(
        content_id,
        window_days=days,
        generate_ai_summary=generate_ai_summary,
        user_id=user_id,
    )
    if not result:
        raise ResourceNotFoundException(resource_type="Content", resource_id=str(content_id))

    return {
        "content_id": result.content_id,
        "classification": result.classification,
        "window_days": result.window_days,
        "position_current": result.position_current,
        "position_previous": result.position_previous,
        "position_delta": result.position_delta,
        "clicks_current": result.clicks_current,
        "clicks_previous": result.clicks_previous,
        "clicks_delta_pct": result.clicks_delta_pct,
        "impressions_current": result.impressions_current,
        "impressions_previous": result.impressions_previous,
        "impressions_delta_pct": result.impressions_delta_pct,
        "top_query": result.top_query,
        "top_query_position": result.top_query_position,
        "signals": [
            {"key": s.key, "label": s.label, "detail": s.detail} for s in result.signals
        ],
        "summary": result.summary,
        "reasons": result.reasons,
        "ai_generated": result.ai_generated,
        "ai_unavailable_reason": result.ai_unavailable_reason,
    }
