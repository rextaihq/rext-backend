"""A workspace's trash: its deleted articles and personas, restored or deleted for good (G45).

The list shows the kinds the caller may read. Restoring an item or deleting it for good takes
the permission that deleting it took: content.delete for an article, persona.delete for a
persona.
"""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.schema.response.trash_responses import TrashActionResponse, TrashListResponse
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.workspace_trash_service import (
    ARTICLE,
    PERSONA,
    WorkspaceTrashService,
    retention_days,
)
from src.utils.rbac_utils import check_permission, is_user_super_admin
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_workspace_for_route

router = APIRouter(tags=["workspace-trash"])


async def _readable_kinds(db: AsyncSession, user_id: UUID, workspace_id: UUID) -> list:
    if await is_user_super_admin(db, user_id):
        return [ARTICLE, PERSONA]
    kinds = []
    if await check_permission(db, user_id, "content.read", workspace_id):
        kinds.append(ARTICLE)
    if await check_permission(db, user_id, "persona.read", workspace_id):
        kinds.append(PERSONA)
    return kinds


@router.get("/{workspace_id}/trash", response_model=SuccessResponse[TrashListResponse])
@require_permissions("content.read", "persona.read", workspace_scoped=True, require_all=False)
@db_transaction_handler("list the workspace's trash", auto_commit=False)
async def list_workspace_trash(
    workspace_id: str,
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """The workspace's deleted articles and personas, newest first, while they can be restored."""
    workspace, _ = await resolve_workspace_for_route(
        db=db, workspace_identifier=workspace_id, user=user
    )
    kinds = await _readable_kinds(db, UUID(user["identity"]), workspace.id)
    items, total = await WorkspaceTrashService(db).list_trash(
        workspace.id, kinds=kinds, limit=limit, offset=offset
    )
    return success(
        data={"items": items, "total_count": total, "retention_days": retention_days()},
        request=request,
        message=f"Retrieved {len(items)} item(s) from the trash",
    )


def _once_committed(db: AsyncSession, task):
    """`task`, to run in the background only if `db`'s transaction has committed."""
    from sqlalchemy import event

    committed = {"yes": False}

    def on_commit(_session) -> None:
        committed["yes"] = True

    # Left in place rather than removed: removing a listener while SQLAlchemy dispatches the
    # event fails the commit (G64). It lives as long as the request's session.
    event.listen(db.sync_session, "after_commit", on_commit)

    async def run() -> None:
        if committed["yes"]:
            await task()

    return run


async def _restore(db, workspace_id: str, user: dict, kind: str, item_id: UUID, request):
    workspace, _ = await resolve_workspace_for_route(
        db=db, workspace_identifier=workspace_id, user=user
    )
    restored = await WorkspaceTrashService(db).restore(
        workspace.id, kind, item_id, user_id=UUID(user["identity"])
    )
    return success(data=restored, request=request, message=f"The {kind} is restored")


async def _delete_forever(
    db, workspace_id: str, user: dict, kind: str, item_id: UUID, request, background_tasks
):
    workspace, _ = await resolve_workspace_for_route(
        db=db, workspace_identifier=workspace_id, user=user
    )
    cleanup = await WorkspaceTrashService(db).delete_forever(workspace.id, kind, item_id)
    # After the response, and only if the transaction committed: a failed commit answers 500
    # with these tasks still attached, and the item stays restorable with its embedding and photo.
    background_tasks.add_task(_once_committed(db, cleanup.run))
    return success(
        data={"kind": kind, "id": str(item_id)},
        request=request,
        message=f"The {kind} is deleted for good",
    )


@router.post(
    "/{workspace_id}/trash/articles/{item_id}/restore",
    response_model=SuccessResponse[TrashActionResponse],
)
@require_permissions("content.delete", workspace_scoped=True)
@db_transaction_handler("restore an article from the trash", auto_commit=True)
async def restore_article(
    workspace_id: str,
    item_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Bring an article back from the trash, as it was."""
    return await _restore(db, workspace_id, user, ARTICLE, item_id, request)


@router.post(
    "/{workspace_id}/trash/personas/{item_id}/restore",
    response_model=SuccessResponse[TrashActionResponse],
)
@require_permissions("persona.delete", workspace_scoped=True)
@db_transaction_handler("restore a persona from the trash", auto_commit=True)
async def restore_persona(
    workspace_id: str,
    item_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Bring a persona back from the trash, as it was."""
    return await _restore(db, workspace_id, user, PERSONA, item_id, request)


@router.delete(
    "/{workspace_id}/trash/articles/{item_id}",
    response_model=SuccessResponse[TrashActionResponse],
)
@require_permissions("content.delete", workspace_scoped=True)
@db_transaction_handler("delete an article for good", auto_commit=True)
async def delete_article_forever(
    workspace_id: str,
    item_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Delete an article in the trash for good."""
    return await _delete_forever(
        db, workspace_id, user, ARTICLE, item_id, request, background_tasks
    )


@router.delete(
    "/{workspace_id}/trash/personas/{item_id}",
    response_model=SuccessResponse[TrashActionResponse],
)
@require_permissions("persona.delete", workspace_scoped=True)
@db_transaction_handler("delete a persona for good", auto_commit=True)
async def delete_persona_forever(
    workspace_id: str,
    item_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Delete a persona in the trash for good, with its uploaded photo."""
    return await _delete_forever(
        db, workspace_id, user, PERSONA, item_id, request, background_tasks
    )


__all__ = ["router"]
