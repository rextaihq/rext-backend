from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.schema.content_schema import ContentResponse
from src.api.schema.response.content_responses import (
    ContentVersionDetailResponse,
    ContentVersionListResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.content_service import ContentService
from src.services.content_version_service import ContentVersionService, detail
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace

router = APIRouter()

# The editor's history (FB2.25, rext-control #706). All three ask for the permission to edit the
# article: the history is a part of the editor, and a restore is an edit.


@router.get("/{content_id}/versions", response_model=SuccessResponse[ContentVersionListResponse])
@require_permissions("content.update", workspace_scoped=True)
@db_transaction_handler("list content versions", auto_commit=False)
async def list_content_versions(
    content_id: UUID,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """The article's versions, newest first, without their bodies."""
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user.get("identity")))
    # The article itself is looked up first: one of another workspace, or in the trash, is a 404.
    await ContentService(db)._get_content_or_404(content_id, workspace.id)
    versions = await ContentVersionService(db).list(content_id, workspace.id)
    return success(data={"versions": versions}, request=request)


@router.get(
    "/{content_id}/versions/{version_id}",
    response_model=SuccessResponse[ContentVersionDetailResponse],
)
@require_permissions("content.update", workspace_scoped=True)
@db_transaction_handler("get content version", auto_commit=False)
async def get_content_version(
    content_id: UUID,
    version_id: UUID,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """One version with its text, as the history shows it before a restore."""
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user.get("identity")))
    await ContentService(db)._get_content_or_404(content_id, workspace.id)
    version, maker = await ContentVersionService(db).get(content_id, version_id, workspace.id)
    return success(data=detail(version, maker), request=request)


@router.post(
    "/{content_id}/versions/{version_id}/restore",
    response_model=SuccessResponse[ContentResponse],
)
@db_transaction_handler("restore content version", "Version restored successfully")
@require_permissions("content.update", workspace_scoped=True)
async def restore_content_version(
    content_id: UUID,
    version_id: UUID,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Put a version's text back on the article. The text as it stood is kept as a version
    first; the answer is the article, as a save of it answers."""
    user_id = UUID(user.get("identity"))
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, user_id)
    content = await ContentService(db).restore_version(
        content_id=content_id, version_id=version_id, workspace_id=workspace.id, user_id=user_id
    )
    return success(
        data=content.to_dict(include_relationships=["seo_data"]),
        request=request,
        message="Version restored successfully",
    )
