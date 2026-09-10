from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.models.content_models.content import Content
from src.api.models.user_models.users import Users
from src.api.security.dependencies import get_current_user

router = APIRouter(prefix="/recent-activities")


@router.get("/{workspace_id}")
async def get_recent_activities(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):

    query = (
        select(
            Content.title,
            Users.full_name,
            Content.status,
        )
        .join(Users, Users.id == Content.created_by_user_id, isouter=True)
        .where(Content.workspace_id == workspace_id)
        .order_by(Content.created_at.desc())
        .limit(20)
    )

    result = await db.execute(query)
    rows = result.all()

    activities = [
        {
            "content_title": row.title,
            "content_status": row.status,
            "author": row.full_name,
        }
        for row in rows
    ]

    return {"workspace_id": workspace_id, "activities": activities}
