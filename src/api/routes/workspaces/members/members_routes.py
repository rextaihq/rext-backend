from fastapi import (
    APIRouter, Depends, Request,
)
from src.utils.logger import logger
from src.api.schema.workspace_schema import WorkspaceSchema
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.user_models.users import Users
from src.utils.vector_store import add_to_vector_store,delete_vectors
from src.api.models.knowledge_models.knowledge_model import BrandVoice
from src.api.schema.knowledge_schema import BrandSchema
from src.model.model import load_model
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
    WrextExternalServiceException,
    WrextValidationException,
    WrextAuthenticationException,
    WrextAPIException
)
from datetime import datetime, timezone
from src.api.security.dependencies import get_current_user

router = APIRouter(
    prefix="/workspace/members",
    tags=["workspace", "members"],
    responses={404: {"description": "Not found"}},
)


@router.post("/{workspace_id}/add", summary="Add a member to a workspace")
@db_transaction_handler("add member to workspace", auto_commit=True)
@require_permissions("member.invite", workspace_scoped=True)
async def add_member_to_workspace(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: str = Depends(get_current_user)
):
    """
    Add a member to a workspace.
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

    # Check if user is already a member
    result = await db.execute(
        select(WorkspaceMembers).where(
            WorkspaceMembers.workspace_id == workspace_id,
            WorkspaceMembers.user_id == user.get("identity")
        )
    )
    existing_member = result.scalar_one_or_none()
    if existing_member:
        raise DuplicateResourceException(
            message="User is already a member of this workspace",
            resource_type="workspace_member",
            conflicting_field="user_id",
            conflicting_value=str(user.get("identity"))
        )

    # Add user as a member
    new_member = WorkspaceMembers(
        user_id=user.get("identity"),
        workspace_id=workspace_id,
        status="active",
        joined_at=datetime.now(timezone.utc),
        last_activity_at=datetime.now(timezone.utc)
    )
    db.add(new_member)
    await db.flush()
    await db.refresh(new_member)

    return {
        "data": {"user_id": str(user.get("identity")), "workspace_id": workspace_id},
        "message": "User added to workspace successfully"
    }
