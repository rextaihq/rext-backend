from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.security.dependencies import get_current_user
from src.services.content_activity import CONTENT_RESOURCE
from src.utils.workspace_utils import resolve_workspace_for_route

router = APIRouter(prefix="/recent-activities")

#: How many events the dashboard panel shows. Unchanged from when this read
#: the content table, so the panel is the same size it always was.
_ACTIVITY_LIMIT = 20


@router.get("/{workspace_id}")
async def get_recent_activities(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """The workspace's most recent content events, newest first.

    This used to select from `content`: one row per article, ordered by when
    the article was created. That could not answer what it was being asked.
    Editing an article rewrote its status in place, so a draft becoming
    published looked like the existing entry had been overwritten rather than
    a new thing having happened; deleting one left nothing behind at all,
    because the delete is a soft one and the row simply stayed as it was; and
    the author came from a join on `created_by_user_id`, so it named whoever
    wrote the article rather than whoever did the thing being listed.

    It now reads the append-only log those events are written to, so a status
    change adds an entry instead of replacing one, a deletion is an entry of
    its own, and the name is the person who acted.

    The title and status come from the logged values rather than from a join
    back to `content`. That is deliberate: the article may since have been
    renamed, moved on, or deleted, and the entry still has to read as what
    happened at the time - a deletion in particular has no content row left to
    join to.
    """
    # Content titles and author names are workspace data: members only.
    await resolve_workspace_for_route(
        db=db, workspace_identifier=str(workspace_id), user=current_user
    )

    query = (
        select(AuditLog)
        .where(
            AuditLog.workspace_id == workspace_id,
            AuditLog.resource_type == CONTENT_RESOURCE,
        )
        # By when the event happened. The old ordering was by the article's
        # created_at, which never changes, so an article edited today stayed
        # wherever its creation date had put it and the newest activity was
        # not at the top.
        .order_by(AuditLog.created_at.desc())
        .limit(_ACTIVITY_LIMIT)
    )

    result = await db.execute(query)
    logs = result.scalars().all()

    activities = [
        {
            # The three keys the dashboard already renders, unchanged, so this
            # endpoint stays a drop-in for the panel as it stands.
            "content_title": (log.new_values or {}).get("title"),
            "content_status": (log.new_values or {}).get("status"),
            "author": log.full_name or log.user_email,
            # What actually happened, for a panel that wants to say so rather
            # than inferring it from a status alone.
            "action": log.action,
            "previous_status": (log.old_values or {}).get("status"),
            "content_id": log.resource_id,
            "occurred_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]

    return {"workspace_id": workspace_id, "activities": activities}
