from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.flow.engines.competitors.pipeline import select_top_competitors
from src.services.brand_voice_service import BrandVoiceService
from src.services.workspace_service import WorkspaceService
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions

router = APIRouter(tags=["workspace-competitors"])


@router.post("/{workspace_id}/competitors/discover")
@db_transaction_handler("trigger competitor discovery", "Competitor discovery initiated", auto_commit=True)
@require_permissions("workspace.update", workspace_scoped=True)
async def discover_competitors(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Trigger standalone SERP-based competitor discovery and return an operation ID for SSE tracking."""
    user_id = UUID(str(user.get("identity")))
    workspace_uuid = UUID(workspace_id)

    service = WorkspaceService(db)
    operation_id = await service.trigger_competitor_discovery(
        workspace_id=workspace_uuid,
        user_id=user_id,
    )

    return success(
        data={"operation_id": operation_id},
        request=request,
        message="Competitor discovery initiated",
    )


@router.get("/{workspace_id}/competitors")
@db_transaction_handler("get competitor discovery results", "Competitor discovery results retrieved")
@require_permissions("workspace.read", workspace_scoped=True)
async def get_competitors(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Fetch the most recent SERP-based competitor discovery results for a workspace."""
    user_id = UUID(str(user.get("identity")))
    workspace_uuid = UUID(workspace_id)

    service = BrandVoiceService(db)
    brand_voice = await service.get_brand_voice(workspace_id=workspace_uuid, user_id=user_id)

    analysis = brand_voice.competitor_analysis if brand_voice else None

    return success(
        data={
            "competitor_analysis": analysis,
            "top_competitors": select_top_competitors(analysis),
        },
        request=request,
        message="Competitor discovery results retrieved"
        if analysis else "No competitor discovery results yet — trigger discovery first",
    )


__all__ = ["router"]
