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
from src.utils.workspace_utils import resolve_workspace_for_route

# ✅ define router ONCE
router = APIRouter(prefix="/dashboard")


@router.get("/{workspace_id}", response_model=SuccessResponse[WorkspaceDashboardResponse])
async def get_dashboard_details(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    # Members only: counts, audit entries and content data are workspace data.
    workspace, _ = await resolve_workspace_for_route(
        db=db, workspace_identifier=workspace_id, user=current_user
    )
    ws_uuid = workspace.id

    # 1. Get analytics from WorkspaceService (members, content)
    workspace_service = WorkspaceService(db)
    analytics = await workspace_service.get_workspace_analytics(ws_uuid)

    # 2. Get recent activity from AuditService
    audit_service = AuditService(db)
    logs = await audit_service.fetch_logs(
        workspace_id=str(ws_uuid), limit=10, status_filter="success"
    )
    formatted_logs = [format_audit_log(log, include_details=False) for log in logs]

    # 3. Calculate content breakdown. Like the library (ContentService.list_content),
    # the counts leave out what is in the trash, and they use the resolved id, so a
    # slug in the path counts the same as the UUID.
    total_content = analytics["content_count"]
    in_library = (Content.workspace_id == ws_uuid, Content.deleted_at.is_(None))
    published_content = await db.scalar(
        select(func.count()).select_from(Content).where(*in_library, Content.status == "published")
    )
    draft_content = await db.scalar(
        select(func.count()).select_from(Content).where(*in_library, Content.status == "draft")
    )

    # 4. Total personas (deleted personas are removed, not trashed)
    total_personas = await db.scalar(
        select(func.count()).select_from(Persona).where(Persona.workspace_id == ws_uuid)
    )

    return success(
        data={
            "workspace_id": str(ws_uuid),
            "members": analytics["members_count"],
            "content": {
                "total": total_content,
                "published": published_content,
                "draft": draft_content,
            },
            "personas": total_personas,
            "recent_activities": formatted_logs,
        },
        request=request,
        message="Dashboard details retrieved successfully",
    )
