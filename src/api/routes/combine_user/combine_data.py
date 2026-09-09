from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.models.content_models.content import Content
from src.api.models.knowledge_models.persona_model import Persona
from src.api.routes.audit.modules.helpers import format_audit_log
from src.api.schema.response.dashboard_responses import WorkspaceDashboardResponse
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.audit_service import AuditService
from src.services.workspace_service import WorkspaceService
from src.utils.response_utils import success

# ✅ define router ONCE
router = APIRouter(prefix="/dashboard")


@router.get("/{workspace_id}", response_model=SuccessResponse[WorkspaceDashboardResponse])
async def get_dashboard_details(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    ws_uuid = UUID(workspace_id)

    # 1. Get analytics from WorkspaceService (Knowledge items, members, content)
    workspace_service = WorkspaceService(db)
    analytics = await workspace_service.get_workspace_analytics(ws_uuid)

    # 2. Get recent activity from AuditService
    audit_service = AuditService(db)
    logs = await audit_service.fetch_logs(
        workspace_id=workspace_id, limit=10, status_filter="success"
    )
    formatted_logs = [format_audit_log(log, include_details=False) for log in logs]

    # 3. Calculate content breakdown
    total_content = analytics["content_count"]
    # For now we use counts from analytics if available,
    # but published/draft might need specific counts
    # (Checking content specific counts from previous logic)
    published_content = await db.scalar(
        select(func.count())
        .select_from(Content)
        .where(Content.workspace_id == workspace_id, Content.status == "published")
    )
    draft_content = await db.scalar(
        select(func.count())
        .select_from(Content)
        .where(Content.workspace_id == workspace_id, Content.status == "draft")
    )

    # 4. Total personas
    total_personas = await db.scalar(
        select(func.count()).select_from(Persona).where(Persona.workspace_id == workspace_id)
    )

    return success(
        data={
            "workspace_id": workspace_id,
            "members": analytics["members_count"],
            "content": {
                "total": total_content,
                "published": published_content,
                "draft": draft_content,
            },
            "personas": total_personas,
            "total_knowledge_items": analytics["knowledge_stats"]["total_count"],
            "recent_activities": formatted_logs,
        },
        request=request,
        message="Dashboard details retrieved successfully",
    )
