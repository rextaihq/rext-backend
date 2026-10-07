import logging
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import RextValidationException
from src.api.schema.response.content_responses import ContentDetailResponse, ContentListResponse
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.cms_status_service import CMSStatusService
from src.services.content_service import (
    CONTENT_LIST_SORTS,
    CONTENT_LIST_STATUSES,
    ContentService,
)
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace

logger = logging.getLogger(__name__)

router = APIRouter()


def _listed(raw: Optional[str]) -> List[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def parse_statuses(raw: Optional[str]) -> List[str]:
    """``draft,review``: the library's statuses; anything else is a 422."""
    statuses = _listed(raw)
    unknown = [s for s in statuses if s not in CONTENT_LIST_STATUSES]
    if unknown:
        raise RextValidationException(
            message="Unknown content status",
            field_errors={"status": [f"Not a content status: {', '.join(unknown)}"]},
        )
    return statuses


def parse_personas(raw: Optional[str]) -> List[str]:
    """Persona ids, or ``none`` for articles without one; anything else is a 422."""
    personas = _listed(raw)
    for persona in personas:
        if persona == "none":
            continue
        try:
            UUID(persona)
        except ValueError:
            raise RextValidationException(
                message="Unknown persona",
                field_errors={"persona": ["Persona ids, or none"]},
            ) from None
    return personas


def parse_sort(raw: Optional[str]) -> Tuple[str, bool]:
    """``<column>.<asc|desc>``: one of the library's columns, newest first by default."""
    if not raw:
        return "created_at", True
    column, _, direction = raw.partition(".")
    if column not in CONTENT_LIST_SORTS or direction not in ("asc", "desc"):
        raise RextValidationException(
            message="Unknown sort",
            field_errors={"sort": [f"<{'|'.join(CONTENT_LIST_SORTS)}>.<asc|desc>"]},
        )
    return column, direction == "desc"


# -------------------------
# List Content for Workspace
# -------------------------
@router.get("/", response_model=SuccessResponse[ContentListResponse])
@require_permissions("content.read", workspace_scoped=True)
@db_transaction_handler("list content", auto_commit=True)
async def list_content(
    request: Request,
    workspace_id: str,
    status: Optional[str] = Query(
        None, description="Statuses, comma-separated (draft,review); the trash is never listed"
    ),
    persona: Optional[str] = Query(
        None, description="Author persona ids, comma-separated; none for articles without one"
    ),
    q: Optional[str] = Query(
        None,
        max_length=200,
        description="Matches the title, or the address of a site the article was sent to",
    ),
    sort: Optional[str] = Query(
        None, description="<column>.<asc|desc>; created_at.desc by default"
    ),
    limit: int = Query(100, le=500, description="Maximum number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    List all content for a workspace with optional filtering and pagination.

    The library searches, filters and sorts here, a page at a time
    (rext-control#381); total_count counts the filtered set.

    Args:
        workspace_id: Workspace UUID or slug (query parameter)

    Requires:
        - JWT authentication
        - Workspace membership verification
    """
    user_id = user.get("identity")
    statuses = parse_statuses(status)
    personas = parse_personas(persona)
    sort_column, descending = parse_sort(sort)

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Sync CMS statuses — returns fast if no integrations present
    cms_svc = CMSStatusService(db)
    await cms_svc.bulk_sync_workspace(workspace.id)

    # Use ContentService
    service = ContentService(db)
    result = await service.list_content(
        workspace_id=workspace.id,
        limit=limit,
        offset=offset,
        statuses=statuses,
        personas=personas,
        q=q,
        sort=sort_column,
        descending=descending,
    )

    # Return wrapped response
    return success(
        data={
            "content": result["content"],
            "total_count": result["total_count"],
            "workspace_id": str(workspace.id),
            "limit": limit,
            "offset": offset,
        },
        request=request,
    )


# -------------------------
# Get Single Content by ID
# -------------------------
@router.get("/{content_id}", response_model=SuccessResponse[ContentDetailResponse])
@require_permissions("content.read", workspace_scoped=True)
@db_transaction_handler("get content", "Content retrieved successfully", auto_commit=False)
async def get_content(
    content_id: UUID,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Get a single content item by ID"""
    user_id = user.get("identity")

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Use ContentService
    service = ContentService(db)
    content_data = await service.get_content(content_id=content_id, workspace_id=workspace.id)

    # Return wrapped response
    return success(
        data={"content": content_data}, request=request, message="Content retrieved successfully"
    )
