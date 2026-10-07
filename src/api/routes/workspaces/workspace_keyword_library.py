"""Removing a keyword from the caller's own Keywords library (G78, rext-control#627).

The library lives in the LangGraph store under ``("library", <user id>, <workspace id>)``:
the graph writes it in-process, and the dashboard reads it through the store's HTTP route,
which `own_keyword_library` (src/api/security/auth.py) keeps to reads of the caller's own
namespace. Deleting is this route's: the namespace comes from the token and the workspace,
never from the request, so a user can only remove their own items.
"""

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.utils.response_utils import success
from src.utils.route_decorators import require_permissions
from src.utils.workspace_utils import resolve_workspace_for_route

router = APIRouter(tags=["workspace-keyword-library"])

NOT_IN_LIBRARY = "That keyword isn't in your library."


class LibraryItemDeleted(BaseModel):
    deleted_key: str


def library_namespace(user_id: str, workspace_id: str) -> tuple[str, str, str]:
    return ("library", user_id, workspace_id)


def library_research_namespace(user_id: str, workspace_id: str) -> tuple[str, str, str]:
    """Where an analysis keeps the item's search results, under the same key (E24,
    rextaihq/rext-backend#888)."""
    return ("library_research", user_id, workspace_id)


@router.delete(
    "/{workspace_id}/keyword-library/items",
    response_model=SuccessResponse[LibraryItemDeleted],
)
@require_permissions("content.read", workspace_scoped=True)
async def delete_library_item(
    workspace_id: str,
    request: Request,
    key: str = Query(..., min_length=1, max_length=512, description="The item's store key"),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Remove one keyword, and the search results kept beside it, from the caller's library."""
    from langgraph_sdk import get_client
    from langgraph_sdk.errors import NotFoundError

    workspace, _ = await resolve_workspace_for_route(
        db=db, workspace_identifier=workspace_id, user=user
    )
    owner, workspace_key = str(user.get("identity")), str(workspace.id)
    # The in-process client skips the store's auth handlers, which allow only reads.
    store = get_client().store
    namespace = library_namespace(owner, workspace_key)
    try:
        item = await store.get_item(namespace, key=key)
    except NotFoundError:
        item = None
    if not item:
        raise ResourceNotFoundException(message=NOT_IN_LIBRARY, resource_type="keyword")

    await store.delete_item(namespace, key=key)
    try:
        await store.delete_item(library_research_namespace(owner, workspace_key), key=key)
    except NotFoundError:
        pass  # nothing kept for this item
    return success(
        data={"deleted_key": key},
        request=request,
        message="Keyword removed from your library",
    )
