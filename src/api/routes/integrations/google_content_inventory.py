from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.schema.content_inventory_schema import ContentInventoryResponse
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.content_inventory_service import ContentInventoryService
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace

router = APIRouter(prefix="/google/content-inventory", tags=["Google Integration"])


@router.get("/", response_model=SuccessResponse[ContentInventoryResponse])
@db_transaction_handler("get content inventory")
@require_permissions("content.read", workspace_scoped=True)
async def get_content_inventory(
    workspace_id: str,
    request: Request,
    days: int = 28,
    page: int = 1,
    page_size: int = 25,
    filter: Optional[List[str]] = Query(
        default=None,
        description=(
            "Repeatable filter (?filter=published&filter=low_ctr). Valid values: "
            "published, growing, declining, needs_update, high_opportunity, "
            "low_ctr, not_indexed, cannibalized."
        ),
    ),
    sort_by: Optional[str] = Query(
        default=None,
        description=(
            "title, status, opportunity_score (default), organic_clicks, "
            "organic_impressions, ctr, average_position, last_updated"
        ),
    ),
    sort_order: str = "desc",
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Module 2 Content Inventory: every article as an individual asset, with
    already-synced GSC performance + rule-based scoring attached. Built
    entirely from data other jobs have already synced — no external API
    calls in this request path.

    health_score (Module 3) and ai_recommendation (Module 5) are always
    null — those modules haven't been implemented yet.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    result = await ContentInventoryService(db).list_inventory(
        workspace_id=workspace.id,
        window_days=days,
        filters=filter,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )

    return {"workspace_id": workspace.id, **result}
