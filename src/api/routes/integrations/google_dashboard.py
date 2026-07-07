from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.schema.dashboard_schema import ContentPerformanceDashboardResponse
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.dashboard_service import ContentPerformanceDashboardService
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace

router = APIRouter(prefix="/google/dashboard", tags=["Google Integration"])


@router.get("/", response_model=SuccessResponse[ContentPerformanceDashboardResponse])
@db_transaction_handler("get content performance dashboard")
@require_permissions("content.read", workspace_scoped=True)
async def get_content_performance_dashboard(
    workspace_id: str,
    request: Request,
    days: int = 28,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Module 1 Dashboard: 9 KPIs + 4 trend charts summarizing organic search
    performance for a workspace. Built entirely from already-synced GSC/GA4
    data (ContentPerformanceMetric, ContentIndexStatus) — no external API
    calls in this request path.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    dashboard = await ContentPerformanceDashboardService(db).get_dashboard(
        workspace_id=workspace.id, days=days
    )

    return {"workspace_id": workspace.id, **dashboard}
