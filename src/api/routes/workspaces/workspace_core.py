from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.api.models.user_models.roles import Role
from uuid import UUID

from src.utils.logger import logger
from src.utils.response_utils import success, error, created
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.auth_utils import verify_current_user
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.schema.workspace_schema import WorkspaceSchema,WorkspaceUpdateSchema
from src.api.middleware.usage_limiter import check_workspace_limit
from src.services.workspace_service import WorkspaceService



router = APIRouter()


# -------------------------
# Health Check
# -------------------------
@router.get("/")
@db_transaction_handler("get workspace status", success_message="Workspace service is operational")
async def get_status(request: Request) -> dict:
    """Health check for workspace service"""
    return {"status": "operational", "service": "workspace_service"}


# -------------------------
# Create workspace
# -------------------------
@router.post("/")
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
@router.get("/all")
@require_permissions("workspace.read", workspace_scoped=False)
@db_transaction_handler("get all workspaces", success_message="Workspaces retrieved successfully")
async def get_workspaces(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
) -> dict:
    user_id = user.get("identity")
    await verify_current_user(db, user_id)

    # Use workspace service
    workspace_service = WorkspaceService(db)
    workspace_data = await workspace_service.get_user_workspaces(UUID(user_id))

    # Return raw data - decorator handles success response
    return {"workspaces": workspace_data, "total_count": len(workspace_data)}

# -------------------------
# Get workspace by ID
# -------------------------
@router.get("/detail")
@require_permissions("workspace.read")
@db_transaction_handler("get workspace details", success_message="Workspace details retrieved successfully")
async def get_workspace_by_id(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
) -> dict:
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
# Get workspace by slug
# -------------------------
@router.get("/slug/{workspace_slug}")
@require_permissions("workspace.read", workspace_scoped=False)
@db_transaction_handler("get workspace by slug", success_message="Workspace retrieved by slug")
async def get_workspace_by_slug(
    workspace_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
) -> dict:
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
# Get workspace by ID (RESTful endpoint)
# -------------------------
@router.get("/{workspace_id}")
@require_permissions("workspace.read")
@db_transaction_handler("get workspace by id or slug", success_message="Workspace retrieved successfully")
async def get_workspace_by_id_path(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
) -> dict:
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

    return {"workspace": workspace_data}



# -------------------------
# Update workspace
# -------------------------
@router.put("/{workspace_id}")
@require_permissions("workspace.update", workspace_scoped=True)
@db_transaction_handler("update workspace", auto_commit=True)
async def update_workspace(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Update workspace details (name, timezone, url).

    Args:
        workspace_id: Workspace UUID or slug

    Body:
        {
          "name": "New Workspace Name",
          "timezone": "America/New_York",
          "url": "https://example.com"
        }
    """
    from src.api.schema.workspace_schema import WorkspaceUpdateSchema

    user_id = user.get("identity")
    await verify_current_user(db, user_id)

    # Parse and validate request body using Pydantic
    body = await request.json()
    update_data = WorkspaceUpdateSchema(**body)

    # Use workspace service — call the user-facing method with correct parameter names
    workspace_service = WorkspaceService(db)
    from src.utils.workspace_utils import resolve_and_verify_workspace
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Map frontend field names: frontend sends "title", backend uses "name"
    name = update_data.name or body.get("title")

    updated_workspace = await workspace_service.update_workspace_for_user(
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        name=name,
        timezone=update_data.timezone,
        url=update_data.url,
    )

    logger.info(
        "Workspace updated",
        extra={"workspace_id": str(workspace.id), "user_id": user_id}
    )

    return {"workspace": updated_workspace}

# -------------------------
# Delete workspace
# -------------------------
@router.delete("/{workspace_id}")
@require_permissions("workspace.delete", workspace_scoped=True)
@db_transaction_handler("delete workspace", success_message="Workspace deleted successfully")
async def delete_workspace_endpoint(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
) -> dict:
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace_by_id_or_slug_for_user(workspace_id, UUID(user_id))
    await workspace_service.verify_user_is_workspace_owner(workspace.id, UUID(user_id))

    remaining_count = await workspace_service.count_user_workspaces(UUID(user_id))
    remaining_after_delete = remaining_count - 1

    await workspace_service.delete_workspace(workspace.id, UUID(user_id))

    logger.info(
        "Workspace soft deleted",
        extra={"workspace_id": str(workspace.id), "user_id": user_id},
    )

    # Send confirmation email
    try:
        from datetime import datetime, timedelta, timezone

        email_service = EmailService(db)
        recovery_date = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%B %d, %Y")

        await email_service.send_email(
            to_email=db_user.email,
            subject=f"Workspace '{workspace.name}' deleted",
            template_type="workspace_deleted",
            template_data={
                "user_name": db_user.display_name or db_user.email,
                "workspace_name": workspace.name,
                "recovery_deadline": recovery_date,
                "remaining_workspaces": remaining_after_delete
            }
        )
        logger.info(
            "Deletion confirmation email sent",
            extra={"recipient_email": db_user.email},
        )
    except Exception as e:
        # Don't fail the deletion if email fails
        logger.error(
            "Failed to send deletion confirmation email",
            extra={"error": str(e)},
            exc_info=True,
        )

    return {
        "message": "Workspace deleted successfully. You have 30 days to recover it if needed.",
        "recovery_period_days": 30,
        "remaining_workspaces": remaining_after_delete,
        "is_last_workspace": remaining_after_delete == 0
    }


# -------------------------
# Get available roles
# -------------------------
@router.get("/available-roles")
@db_transaction_handler("get available roles", auto_commit=False)
async def get_available_roles(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get available roles for workspace member invitations.

    Returns workspace roles that can be assigned to workspace members.
    Uses is_workspace_role flag for proper role classification.
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

