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
from sqlalchemy.orm import Session
from src.api.security.auth import get_api_key, API_KEY
from src.api.database.database import get_db
from src.utils.helper import web_page_scraper
from src.utils.response_utils import success, error, created
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    WrextExternalServiceException,
    WrextValidationException,
    WrextAuthenticationException
)
from datetime import datetime, timezone
from src.api.security.auth import get_current_user

router = APIRouter(
    prefix="/workspace/members",
    tags=["workspace", "members"],
    responses={404: {"description": "Not found"}},
)


@router.post("/{workspace_id}/add", summary="Add a member to a workspace")
async def add_member_to_workspace(
    workspace_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user)
):
    """
    Add a member to a workspace.
    """
    try:
        # Check if workspace exists
        workspace = db.query(WorkspaceModel).filter(WorkspaceModel.id == workspace_id, WorkspaceModel.user_id == user.get("identity")).first()
        if not workspace:
            raise ResourceNotFoundException(f"Workspace with id {workspace_id} not found")

        # Check if user is already a member
        existing_member = db.query(WorkspaceMembers).filter(
            WorkspaceMembers.workspace_id == workspace_id,
            WorkspaceMembers.user_id == user.get("identity")
        ).first()
        if existing_member:
            raise DuplicateResourceException("User is already a member of this workspace")

        # Add user as a member
        new_member = WorkspaceMembers(
            user_id=user.get("identity"),
            workspace_id=workspace_id,
            status="active",
            joined_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc)
        )
        db.add(new_member)
        db.commit()
        db.refresh(new_member)

        return created(
            message="User added to workspace successfully",
            data={"user_id": str(user.get("identity")), "workspace_id": workspace_id},
            request=request
        )
    except Exception as e:
        logger.exception("Error fetching workspaces")
        return error(
            message="Failed to retrieve workspaces",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )
