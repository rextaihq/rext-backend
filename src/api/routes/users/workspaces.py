"""
User Workspaces Routes

These routes handle user's workspace memberships and provide workspace listing
for workspace switcher functionality.

Public endpoints:
- GET /api/v1/user/workspaces - Get all workspaces for current user
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.workspace_service import WorkspaceService
from src.services.member_service import MemberService
from src.utils.route_decorators import db_transaction_handler
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.user_workspace_responses import UserWorkspaceListResponse
from src.utils.response_utils import success
from src.utils.logger import logger

router = APIRouter(prefix="/user/workspaces", tags=["User Workspaces"])


@router.get("", response_model=SuccessResponse[UserWorkspaceListResponse])
@db_transaction_handler("get user workspaces", auto_commit=False)
async def get_user_workspaces(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get all workspaces for the current user.

    Returns workspaces where the user is a member, including:
    - Workspace details (id, name, slug, etc.)
    - User's role in each workspace
    - Workspace statistics (knowledge count, members count)
    - Owner information

    This endpoint is used by:
    - Workspace switcher component
    - Dashboard workspace listing
    - Pending invitations context

    Response structure:
    {
        "workspaces": [
            {
                "id": "workspace-uuid",
                "name": "Workspace Name",
                "slug": "workspace-slug",
                "url": "https://...",
                "timezone": "UTC",
                "created_at": "ISO datetime",
                "updated_at": "ISO datetime",
                "owner": {
                    "name": "Owner Name",
                    "email": "owner@example.com"
                },
                "user_role": {
                    "id": "role-uuid",
                    "name": "editor",
                    "display_name": "Editor"
                },
                "knowledge_stats": {
                    "web_knowledge": 10,
                    "files": 5,
                    "text_knowledge": 3,
                    "total": 18
                },
                "members_count": 5,
                "is_owner": true,
                "status": "active"
            }
        ],
        "total_count": 1,
        "owned_count": 1,
        "member_count": 0
    }

    Args:
        request: FastAPI request object
        db: Database session
        current_user: Current authenticated user from JWT

    Returns:
        List of workspaces with role information

    Raises:
        AuthenticationException: If user not authenticated
    """
    user_id = UUID(current_user.get("identity"))

    # Get base workspace data
    workspace_service = WorkspaceService(db)
    workspaces = await workspace_service.get_user_workspaces(user_id)

    # Enhance with role information
    member_service = MemberService(db)

    enhanced_workspaces = []
    owned_count = 0
    member_count = 0

    for workspace_data in workspaces:
        workspace_id = UUID(workspace_data["id"])

        # Get user's role in this workspace
        try:
            membership = await member_service.get_workspace_member(
                workspace_id=workspace_id,
                user_id=user_id
            )

            # Get role details
            role_data = None
            if membership.get("workspace_role"):
                role = membership["workspace_role"]
                role_data = {
                    "id": role.get("id"),
                    "name": role.get("name"),
                    "display_name": role.get("display_name")
                }

            # Add role information to workspace data
            workspace_data["user_role"] = role_data

            # Determine if user is owner
            is_owner = workspace_data["user_id"] == str(user_id)
            workspace_data["is_owner"] = is_owner

            if is_owner:
                owned_count += 1
            else:
                member_count += 1

            enhanced_workspaces.append(workspace_data)

        except Exception as e:
            logger.warning(
                f"Failed to get role for workspace {workspace_id}: {str(e)}",
                extra={"user_id": str(user_id), "workspace_id": str(workspace_id)}
            )
            # Include workspace without role info rather than failing completely
            workspace_data["user_role"] = None
            workspace_data["is_owner"] = False
            enhanced_workspaces.append(workspace_data)

    logger.info(
        f"Retrieved {len(enhanced_workspaces)} workspaces for user",
        extra={
            "user_id": str(user_id),
            "total_count": len(enhanced_workspaces),
            "owned_count": owned_count,
            "member_count": member_count
        }
    )

    return success(
        data={
            "workspaces": enhanced_workspaces,
            "total_count": len(enhanced_workspaces),
            "owned_count": owned_count,
            "member_count": member_count
        },
        request=request,
        message="User workspaces retrieved successfully"
    )
