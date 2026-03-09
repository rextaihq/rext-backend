from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.api.models.user_models.roles import Role
from uuid import UUID
from src.services.workspace_service import WorkspaceService
from typing import Optional
from datetime import datetime, timezone, timedelta

from src.utils.logger import logger
from src.utils.response_utils import success, created
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.auth_utils import verify_current_user
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.schema.workspace_schema import WorkspaceSchema, WorkspaceUpdateSchema, WorkspaceResponseSchema
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.workspace_responses import (
    WorkspaceStatusResponse,
    WorkspaceListResponse,
    SingleWorkspaceResponse,
    AvailableRolesResponse,
    WorkspaceDeleteResponse
)
from src.api.middleware.usage_limiter import check_workspace_limit
from src.services.workspace_service import WorkspaceService
from src.services.email_service import EmailService
from src.services.email_helpers import send_workspace_email
from src.api.dependencies.feature_gate import RequireFeature


router = APIRouter()


# -------------------------
# Health Check
# -------------------------
@router.get("/", response_model=SuccessResponse[WorkspaceStatusResponse])
@db_transaction_handler("get workspace status", success_message="Workspace service is operational")
async def get_status(request: Request) -> dict:
    """Health check for workspace service"""
    return {"status": "operational", "service": "workspace_service"}


# -------------------------
# Create workspace
# -------------------------
@router.post(
    "/",
    dependencies=[Depends(RequireFeature("workspaces"))],
    response_model=SuccessResponse[WorkspaceResponseSchema]
)
@require_permissions("workspace.create", workspace_scoped=False)
@db_transaction_handler("create workspace", auto_commit=True)
async def create_workspace(
    data: WorkspaceSchema,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(check_workspace_limit()),
):
    """
    Create a new workspace for the current user.

    Returns immediately with workspace metadata and an operation identifier for
    tracking background processing via SSE.
    """
    if not data.name:
        raise RextValidationException(
            message="Workspace name is required",
            field_errors={"name": ["Name must be provided"]},
        )

    if not data.url:
        raise RextValidationException(
            message="Workspace URL is required",
            field_errors={"url": ["URL must be provided and valid"]},
        )

    user_id = UUID(str(current_user.get("identity")))
    service = WorkspaceService(db)
    result = await service.create_workspace_for_user(
        user_id=user_id,
        name=data.name,
        timezone=data.timezone,
        url=str(data.url),
    )

    return created(
        data=result,
        request=request,
        message="Workspace created successfully. Background processing initiated.",
    )


# -------------------------
# Get all workspaces for user
# -------------------------
@router.get("/all", response_model=SuccessResponse[WorkspaceListResponse])
@require_permissions("workspace.read", workspace_scoped=False)
@db_transaction_handler("get all workspaces", success_message="Workspaces retrieved successfully")
async def get_workspaces(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
) -> dict:
    """List all workspaces the current user has access to."""
    user_id = user.get("identity")
    await verify_current_user(db, user_id)

    # Use workspace service
    workspace_service = WorkspaceService(db)
    workspace_data = await workspace_service.get_user_workspaces(UUID(user_id))

    return {"workspaces": workspace_data, "total_count": len(workspace_data)}


# -------------------------
# Get workspace by slug
# -------------------------
@router.get("/slug/{workspace_slug}", response_model=SuccessResponse[SingleWorkspaceResponse])
@require_permissions("workspace.read", workspace_scoped=False)
@db_transaction_handler("get workspace by slug", success_message="Workspace retrieved by slug")
async def get_workspace_by_slug(
    workspace_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
) -> dict:
    """Fetch workspace details by its URL slug."""
    user_id = user.get("identity")
    await verify_current_user(db, user_id)

    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace_by_slug_for_user(workspace_slug, UUID(user_id))
    workspace_data = await workspace_service.get_workspace_with_brand_voice(workspace.id)

    analytics = await workspace_service.get_workspace_analytics(workspace.id, include_word_counts=True)

    # Merge analytics into workspace data
    workspace_data["knowledge_stats"] = analytics["knowledge_stats"]
    workspace_data["analytics"] = {
        "knowledge_counts": {
            "web_knowledge": analytics["knowledge_stats"]["web_knowledge"],
            "files": analytics["knowledge_stats"]["files"],
            "text_knowledge": analytics["knowledge_stats"]["text_knowledge"],
            "total_knowledge_items": analytics["knowledge_stats"]["total"]
        },
        "content_metrics": analytics.get("content_metrics", {}),
        "team_metrics": {
            "total_members": analytics["members_count"]
        }
    }

    return {"workspace": workspace_data}


# -------------------------
# Get workspace by ID (Query Param)
# -------------------------
@router.get("/detail", response_model=SuccessResponse[SingleWorkspaceResponse])
@require_permissions("workspace.read")
@db_transaction_handler("get workspace details", success_message="Workspace details retrieved successfully")
async def get_workspace_by_id(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
) -> dict:
    """Legacy detail endpoint using query parameters."""
    user_id = user.get("identity")
    await verify_current_user(db, user_id)

    workspace_service = WorkspaceService(db)
    workspace_data = await workspace_service.get_workspace_with_brand_voice(UUID(workspace_id))
    analytics = await workspace_service.get_workspace_analytics(UUID(workspace_id), include_word_counts=True)

    # Merge analytics into workspace data
    workspace_data["knowledge_stats"] = analytics["knowledge_stats"]
    workspace_data["analytics"] = {
        "knowledge_counts": {
            "web_knowledge": analytics["knowledge_stats"]["web_knowledge"],
            "files": analytics["knowledge_stats"]["files"],
            "text_knowledge": analytics["knowledge_stats"]["text_knowledge"],
            "total_knowledge_items": analytics["knowledge_stats"]["total"]
        },
        "content_metrics": analytics.get("content_metrics", {}),
        "team_metrics": {
            "total_members": analytics["members_count"]
        }
    }

    return {"workspace": workspace_data}


# -------------------------
# Get available roles
# -------------------------
@router.get("/available-roles", response_model=SuccessResponse[AvailableRolesResponse])
@db_transaction_handler("get available roles", auto_commit=False)
async def get_available_roles(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get available roles for workspace member invitations.

    Returns workspace roles that can be assigned to workspace members.
    """
    # Fetch all workspace roles ordered by hierarchy
    query = (
        select(Role)
        .where(Role.is_workspace_role == True)
        .order_by(Role.hierarchy_level.desc())
    )
    result = await db.execute(query)
    roles = result.scalars().all()

    roles_data = [
        {
            "id": str(role.id),
            "name": role.name,
            "display_name": role.display_name,
            "description": role.description,
            "is_system_role": role.is_system_role,
            "is_workspace_role": role.is_workspace_role,
            "hierarchy_level": role.hierarchy_level,
            "created_at": role.created_at.isoformat() if role.created_at else None,
            "updated_at": role.updated_at.isoformat() if role.updated_at else None,
        }
        for role in roles
    ]

    return success(
        data={"roles": roles_data, "total_count": len(roles_data)},
        request=request,
        message=f"Retrieved {len(roles_data)} available role(s)",
    )


# -------------------------
# Get workspace by ID or slug (RESTful)
# -------------------------
@router.get("/{workspace_id}", response_model=SuccessResponse[WorkspaceResponseSchema])
@require_permissions("workspace.read")
@db_transaction_handler("get workspace", success_message="Workspace retrieved successfully")
async def get_workspace_detail(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
) -> SuccessResponse[WorkspaceResponseSchema]:
    """
    Fetch comprehensive workspace details by ID or slug.
    
    Includes brand voice data and aggregated analytics.
    """
    user_id = user.get("identity")
    await verify_current_user(db, user_id)

    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace_by_id_or_slug_for_user(workspace_id, UUID(user_id))
    workspace_data = await workspace_service.get_workspace_with_brand_voice(workspace.id)

    analytics = await workspace_service.get_workspace_analytics(workspace.id, include_word_counts=True)

    # Merge analytics into workspace data
    workspace_data["knowledge_stats"] = analytics["knowledge_stats"]
    workspace_data["analytics"] = {
        "knowledge_counts": {
            "web_knowledge": analytics["knowledge_stats"]["web_knowledge"],
            "files": analytics["knowledge_stats"]["files"],
            "text_knowledge": analytics["knowledge_stats"]["text_knowledge"],
            "total_knowledge_items": analytics["knowledge_stats"]["total"]
        },
        "content_metrics": analytics.get("content_metrics", {}),
        "team_metrics": {
            "total_members": analytics["members_count"]
        }
    }

    return success(data=workspace_data, request=request)


# -------------------------
# Update workspace
# -------------------------
@router.put("/{workspace_id}", response_model=SuccessResponse[SingleWorkspaceResponse])
@require_permissions("workspace.update", workspace_scoped=True)
@db_transaction_handler("update workspace", auto_commit=True)
async def update_workspace(
    workspace_id: str,
    data: WorkspaceUpdateSchema,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Update workspace metadata (name, timezone, url)."""
    user_id = user.get("identity")
    await verify_current_user(db, user_id)

    workspace_service = WorkspaceService(db)
    from src.utils.workspace_utils import resolve_and_verify_workspace
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Support 'title' fallback from raw body for legacy frontend compatibility
    name = data.name
    if not name:
        try:
            body = await request.json()
            name = body.get("title")
        except:
            pass

    updated_workspace = await workspace_service.update_workspace_for_user(
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        name=name,
        timezone=data.timezone,
        url=data.url,
    )

    logger.info(
        "Workspace updated",
        extra={"workspace_id": str(workspace.id), "user_id": user_id}
    )

    return {"workspace": updated_workspace}


# -------------------------
# Delete workspace
# -------------------------
@router.delete("/{workspace_id}", response_model=SuccessResponse[WorkspaceDeleteResponse])
@require_permissions("workspace.delete", workspace_scoped=True)
@db_transaction_handler("delete workspace", success_message="Workspace deleted successfully")
async def delete_workspace_endpoint(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
) -> dict:
    """
    Soft-delete a workspace (30-day recovery period).
    
    Marks the workspace as deleted and sends a confirmation email to the owner.
    """
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace_by_id_or_slug_for_user(workspace_id, UUID(user_id))
    
    # Verify ownership for deletion
    await workspace_service.verify_user_is_workspace_owner(workspace.id, UUID(user_id))

    # Count before deletion for stats
    remaining_count = await workspace_service.count_user_workspaces(UUID(user_id))
    remaining_after_delete = remaining_count - 1

    # Perform soft delete
    await workspace_service.delete_workspace(workspace.id, UUID(user_id))

    logger.info(
        "Workspace soft deleted",
        extra={"workspace_id": str(workspace.id), "user_id": user_id},
    )

    # Send confirmation email
    try:
        recovery_date = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%B %d, %Y")
        
        await send_workspace_email(
            db=db,
            email_type="workspace_deleted",
            workspace_id=workspace.id,
            recipient_email=db_user.email,
            user_id=UUID(user_id),
            # Template Context
            user_name=db_user.display_name or db_user.email,
            workspace_name=workspace.name,
            recovery_deadline=recovery_date,
            remaining_workspaces=remaining_after_delete
        )
    except Exception as e:
        logger.error(f"Failed to send deletion confirmation email: {str(e)}")

    return {
        "message": "Workspace deleted successfully. You have 30 days to recover it if needed.",
        "recovery_period_days": 30,
        "remaining_workspaces": remaining_after_delete,
        "is_last_workspace": remaining_after_delete == 0
    }


