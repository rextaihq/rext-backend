from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user

from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.content_models.content import Content
from src.api.models.knowledge_models.persona_model import Persona

# ✅ define router ONCE
router = APIRouter(prefix="/dashboard")


@router.get("/{workspace_id}")
async def get_dashboard_details(
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    # --- Total workspace members ---
    total_members = await db.scalar(
        select(func.count()).select_from(WorkspaceMembers).where(
            WorkspaceMembers.workspace_id == workspace_id
        )
    )

    # --- Total content ---
    total_content = await db.scalar(
        select(func.count()).select_from(Content).where(
            Content.workspace_id == workspace_id
        )
    )

    # --- Published content ---
    published_content = await db.scalar(
        select(func.count()).select_from(Content).where(
            Content.workspace_id == workspace_id,
            Content.status == "published"
        )
    )

    # --- Draft content ---
    draft_content = await db.scalar(
        select(func.count()).select_from(Content).where(
            Content.workspace_id == workspace_id,
            Content.status == "draft"
        )
    )

    # --- Total personas ---
    total_personas = await db.scalar(
        select(func.count()).select_from(Persona).where(
            Persona.workspace_id == workspace_id
        )
    )

    return {
        "workspace_id": workspace_id,
        "members": total_members,
        "content": {
            "total": total_content,
            "published": published_content,
            "draft": draft_content,
        },
        "personas": total_personas,
    }
