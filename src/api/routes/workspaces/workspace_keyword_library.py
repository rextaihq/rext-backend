"""
Workspace Keyword Library Routes

Expose a small API for listing and deleting keyword library items stored in LangGraph.
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import db_transaction_handler, require_permissions

router = APIRouter()


class DeleteKeywordLibraryItemRequest(BaseModel):
    key: str


@router.get("/{workspace_id}/keyword-library")
@require_permissions("workspace.read", workspace_scoped=True)
@db_transaction_handler("fetch workspace keyword library", auto_commit=False)
async def list_workspace_keyword_library(
    workspace_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """List keyword library records for the current user and workspace."""
    namespace = ("library", str(user["identity"]), workspace_id)

    from src.flow.store.rext_store import generate_store

    async with generate_store() as store:
        items = await store.asearch(namespace, query=None, limit=1000, offset=0)

    return [item.dict() for item in items]


@router.delete("/{workspace_id}/keyword-library")
@require_permissions("workspace.update", workspace_scoped=True)
@db_transaction_handler("delete workspace keyword library item", auto_commit=False)
async def delete_workspace_keyword_library_item(
    workspace_id: str,
    payload: DeleteKeywordLibraryItemRequest,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Delete a keyword library item by its stored key."""
    namespace = ("library", str(user["identity"]), workspace_id)

    from src.flow.store.rext_store import generate_store

    async with generate_store() as store:
        await store.adelete(namespace=namespace, key=payload.key)

    return {"deleted_key": payload.key}
