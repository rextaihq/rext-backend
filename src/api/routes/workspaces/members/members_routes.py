from fastapi import (
    APIRouter, Depends, Request,
)
from uuid import UUID
from src.utils.logger import logger
from src.api.schema.workspace_schema import WorkspaceSchema
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.user_models.users import Users
from src.api.models.knowledge_models.knowledge_model import BrandVoice
from src.api.schema.knowledge_schema import BrandSchema
from src.flow.model.llm_manager import load_model
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.api.database.async_database import get_async_db
from src.utils.helper import web_page_scraper
from src.utils.response_utils import success, error, created
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    RextExternalServiceException,
    RextValidationException,
    RextAuthenticationException,
    RextAPIException
)
from datetime import datetime, timezone
from src.api.security.dependencies import get_current_user
from src.services.member_service import MemberService

router = APIRouter(
    prefix="/workspace/members",
    tags=["workspace", "members"],
    responses={404: {"description": "Not found"}},
)


@router.post("/add", summary="Add a member to a workspace")
@db_transaction_handler("add member to workspace", auto_commit=True)
@require_permissions("member.invite", workspace_scoped=True)
async def add_member_to_workspace(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: str = Depends(get_current_user)
):
    """
    Add a member to a workspace - Thin controller using MemberService
    
    Args:
        workspace_id: Workspace UUID (query parameter)
    """
    # Check if workspace exists
    result = await db.execute(
        select(WorkspaceModel).where(
            WorkspaceModel.id == workspace_id,
            WorkspaceModel.user_id == user.get("identity")
        )
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise ResourceNotFoundException(
            message=f"Workspace with id {workspace_id} not found",
            resource_type="workspace",
            resource_id=workspace_id
        )

    # Use MemberService to add member
    service = MemberService(db)
    new_member = await service.add_member(
        workspace_id=UUID(workspace_id),
        user_id=UUID(user.get("identity"))
    )

    return {
        "data": {"user_id": str(user.get("identity")), "workspace_id": workspace_id},
        "message": "User added to workspace successfully"
    }
