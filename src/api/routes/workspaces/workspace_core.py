from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import (
    RextValidationException,
)
from src.api.middleware.usage_limiter import check_workspace_limit
from src.api.models.user_models.roles import Role
from src.api.schema.response.workspace_responses import (
    AvailableRolesResponse,
    DeletedWorkspaceListResponse,
    SingleWorkspaceResponse,
    WorkspaceDeleteResponse,
    WorkspaceListResponse,
    WorkspacePermanentDeleteResponse,
    WorkspacePipelineRetryResponse,
    WorkspaceRestoreResponse,
    WorkspaceStatusResponse,
    WorkspaceTransferOwnershipResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.workspace_schema import (
    DESCRIPTION_MAX_LENGTH,
    DESCRIPTION_MIN_LENGTH,
    WorkspaceResponseSchema,
    WorkspaceSchema,
    WorkspaceTransferOwnershipSchema,
    WorkspaceUpdateSchema,
)
from src.api.security.dependencies import get_current_user
from src.services import account_events
from src.services.email_helpers import send_workspace_email
from src.services.workspace_service import WorkspaceService, pipeline_state
from src.utils.auth_utils import verify_current_user
from src.utils.fast_scraper import WebsiteUnreachableError, check_website_reachable
from src.utils.logger import logger
from src.utils.name_utils import validate_workspace_name
from src.utils.response_utils import created, success
from src.utils.route_decorators import db_transaction_handler, require_permissions

router = APIRouter()


# -------------------------
# Health Check
# -------------------------
@router.get("/", response_model=SuccessResponse[WorkspaceStatusResponse])
@db_transaction_handler("get workspace status", success_message="Workspace service is operational")
async def get_status(request: Request):
    """Health check for workspace service"""
    return success(
        data={"status": "operational", "service": "workspace_service"},
        request=request,
        message="Workspace service is operational",
    )


# -------------------------
# Create workspace
# -------------------------
@router.post(
    "/",
    response_model=SuccessResponse[WorkspaceResponseSchema],
)
# No permission gate: every authenticated account may create workspaces.
# Access control here is the plan's workspace limit (check_workspace_limit(), the
# one gate: its 429 is what the dashboard shows) and authentication itself — the former
# workspace.create permission was redundant because every user held it via the
# irrevocable platform-floor "user" role.
@db_transaction_handler("create workspace", auto_commit=True)
async def create_workspace(
    data: WorkspaceSchema,
    request: Request,
    background_tasks: BackgroundTasks,
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

    # A website, or for a business that has none yet, its owner's description of it: the brand
    # voice is drafted from one or the other (rext-control#853).
    url = str(data.url) if data.url else None
    description = None if url else data.description
    if not url and not description:
        raise RextValidationException(
            message="Workspace URL is required",
            field_errors={"url": ["URL must be provided and valid"]},
        )
    if description and len(description) < DESCRIPTION_MIN_LENGTH:
        short = (
            "Your description is too short. Say in a sentence or two what the business sells, "
            "and to whom."
        )
        raise RextValidationException(message=short, field_errors={"description": [short]})
    if description and len(description) > DESCRIPTION_MAX_LENGTH:
        long = f"Your description is too long. Keep it to {DESCRIPTION_MAX_LENGTH:,} characters."
        raise RextValidationException(message=long, field_errors={"description": [long]})

    if url:
        # Reject dead or made-up domains before any workspace row or pipeline exists.
        try:
            await check_website_reachable(url)
        except WebsiteUnreachableError as exc:
            raise RextValidationException(message=str(exc), field_errors={"url": [str(exc)]})

    user_id = UUID(str(current_user.get("identity")))
    service = WorkspaceService(db)
    result = await service.create_workspace_for_user(
        user_id=user_id,
        name=data.name,
        timezone=data.timezone,
        url=url,
        description=description,
    )

    from src.utils.audit_helper import create_audit_log_async

    workspace_id = result["workspace"]["id"]
    await create_audit_log_async(
        db=db,
        user_id=user_id,
        action="workspace.create",
        resource_type="workspace",
        resource_id=str(workspace_id),
        workspace_id=UUID(str(workspace_id)),
        new_values={"name": data.name, "url": url},
        request=request,
    )

    # A background task runs once the response is sent, so after this route's commit.
    background_tasks.add_task(
        account_events.workspace_created,
        user_id,
        UUID(str(workspace_id)),
        datetime.now(timezone.utc),
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
# No permission gate: these return ONLY the caller's own workspaces
# (WorkspaceService.*_for_user filters on workspace_members for this user),
# so authentication is the check. Gating them on a GLOBAL workspace.read
# only worked while the global "user" role carried that permission.
@db_transaction_handler("get all workspaces", success_message="Workspaces retrieved successfully")
async def get_workspaces(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    sort_by: Literal["created_at", "name"] = Query("created_at"),
):
    """List workspaces, newest first by default or alphabetically by name."""
    user_id = user.get("identity")
    await verify_current_user(db, user_id)

    # Use workspace service
    workspace_service = WorkspaceService(db)
    workspace_data = await workspace_service.get_user_workspaces(UUID(user_id), sort_by=sort_by)

    return success(
        data={"workspaces": workspace_data, "total_count": len(workspace_data)},
        request=request,
        message="Workspaces retrieved successfully",
    )


# -------------------------
# Get workspace by slug
# -------------------------
@router.get("/slug/{workspace_slug}", response_model=SuccessResponse[SingleWorkspaceResponse])
# No permission gate: these return ONLY the caller's own workspaces
# (WorkspaceService.*_for_user filters on workspace_members for this user),
# so authentication is the check. Gating them on a GLOBAL workspace.read
# only worked while the global "user" role carried that permission.
@db_transaction_handler("get workspace by slug", success_message="Workspace retrieved by slug")
async def get_workspace_by_slug(
    workspace_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Fetch workspace details by its URL slug."""
    user_id = user.get("identity")
    await verify_current_user(db, user_id)

    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace_by_slug_for_user(
        workspace_slug, UUID(user_id)
    )
    workspace_data = await workspace_service.get_workspace_with_brand_voice(workspace.id)

    analytics = await workspace_service.get_workspace_analytics(workspace.id)

    # Merge analytics into workspace data
    workspace_data["analytics"] = analytics
    # Outside the cached brand-voice payload: the dashboard polls it while a run is going.
    workspace_data["pipeline"] = pipeline_state(workspace)

    return success(
        data={"workspace": workspace_data}, request=request, message="Workspace retrieved by slug"
    )


# -------------------------
# Get workspace by ID (Query Param)
# -------------------------
@router.get("/detail", response_model=SuccessResponse[SingleWorkspaceResponse])
# workspace_scoped=True: the decorator defaults to False, which checks only
# GLOBAL permissions. A member's workspace.read is workspace-scoped, so these
# routes 403'd for every non-owner once the global "user" role stopped
# carrying workspace.read.
@require_permissions("workspace.read", workspace_scoped=True)
@db_transaction_handler(
    "get workspace details",
    success_message="Workspace details retrieved successfully",
)
async def get_workspace_by_id(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    user_id = user.get("identity")
    await verify_current_user(db, user_id)

    workspace_service = WorkspaceService(db)
    # Resolves the ID (or slug) and verifies membership, raising a 404
    # ResourceNotFoundException for malformed/non-existent/unauthorized IDs
    # instead of letting a bare UUID() ValueError surface as a 500.
    workspace = await workspace_service.get_workspace_by_id_or_slug_for_user(
        workspace_id, UUID(user_id)
    )
    workspace_data = await workspace_service.get_workspace_with_brand_voice(workspace.id)
    analytics = await workspace_service.get_workspace_analytics(workspace.id)

    # Merge analytics into workspace data
    workspace_data["analytics"] = analytics
    # Outside the cached brand-voice payload: the dashboard polls it while a run is going.
    workspace_data["pipeline"] = pipeline_state(workspace)

    return success(
        data={"workspace": workspace_data},
        request=request,
        message="Workspace details retrieved successfully",
    )


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
    # Fetch all workspace roles ordered by hierarchy, excluding workspace_owner
    query = (
        select(Role)
        .where(Role.is_workspace_role, Role.name != "workspace_owner")
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
# List deleted (soft-deleted, still-recoverable) workspaces
# -------------------------
@router.get("/deleted", response_model=SuccessResponse[DeletedWorkspaceListResponse])
# No permission gate: these return ONLY the caller's own workspaces
# (WorkspaceService.*_for_user filters on workspace_members for this user),
# so authentication is the check. Gating them on a GLOBAL workspace.read
# only worked while the global "user" role carried that permission.
@db_transaction_handler(
    "list deleted workspaces",
    success_message="Deleted workspaces retrieved successfully",
)
async def list_deleted_workspaces(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    List the current user's soft-deleted workspaces that are still within
    the 30-day recovery window, for a "Trash" / "Recently Deleted" UI.
    """
    user_id = user.get("identity")
    await verify_current_user(db, user_id)

    workspace_service = WorkspaceService(db)
    deleted_workspaces = await workspace_service.get_deleted_workspaces_for_user(UUID(user_id))

    now = datetime.now(timezone.utc)
    items = []
    for workspace in deleted_workspaces:
        recovery_deadline = workspace.deleted_at + timedelta(days=30)
        items.append(
            {
                **workspace_service._serialize_workspace(workspace),
                "deleted_at": workspace.deleted_at.isoformat(),
                "recovery_deadline": recovery_deadline.isoformat(),
                "days_remaining": max(0, (recovery_deadline - now).days),
            }
        )

    return success(
        data={"workspaces": items, "total_count": len(items)},
        request=request,
        message="Deleted workspaces retrieved successfully",
    )


# -------------------------
# Get workspace by ID or slug (RESTful)
# -------------------------
@router.get("/{workspace_id}", response_model=SuccessResponse[SingleWorkspaceResponse])
# workspace_scoped=True: the decorator defaults to False, which checks only
# GLOBAL permissions. A member's workspace.read is workspace-scoped, so these
# routes 403'd for every non-owner once the global "user" role stopped
# carrying workspace.read.
@require_permissions("workspace.read", workspace_scoped=True)
@db_transaction_handler("get workspace", success_message="Workspace retrieved successfully")
async def get_workspace_detail(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
) -> SuccessResponse[SingleWorkspaceResponse]:
    """
    Fetch comprehensive workspace details by ID or slug.

    Includes brand voice data and aggregated analytics.
    """
    user_id = user.get("identity")
    await verify_current_user(db, user_id)

    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace_by_id_or_slug_for_user(
        workspace_id, UUID(user_id)
    )
    workspace_data = await workspace_service.get_workspace_with_brand_voice(workspace.id)

    analytics = await workspace_service.get_workspace_analytics(workspace.id)

    # Merge analytics into workspace data
    workspace_data["analytics"] = analytics
    # Outside the cached brand-voice payload: the dashboard polls it while a run is going.
    workspace_data["pipeline"] = pipeline_state(workspace)

    return success(data={"workspace": workspace_data}, request=request)


# -------------------------
# Retry the workspace pipeline
# -------------------------
@router.post(
    "/{workspace_id}/pipeline/retry",
    response_model=SuccessResponse[WorkspacePipelineRetryResponse],
)
@db_transaction_handler(
    "retry workspace pipeline", "Workspace pipeline restarted", auto_commit=True
)
@require_permissions("brand_voice.update", workspace_scoped=True)
async def retry_workspace_pipeline(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Read the website again after the last run failed or was interrupted (the pipeline runs
    inside the API process, so a restart or a deploy ends it). Returns the new run's operation
    id for the SSE stream; GET /workspaces/{id} shows its status as `pipeline`."""
    user_id = UUID(str(user.get("identity")))
    service = WorkspaceService(db)
    workspace = await service.get_workspace_by_id_or_slug_for_user(workspace_id, user_id)
    operation_id = await service.retry_pipeline_for_user(workspace.id, user_id)
    return success(
        data={"operation_id": operation_id},
        request=request,
        message="Workspace pipeline restarted",
    )


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
    user: dict = Depends(get_current_user),
):
    """Update workspace metadata (name, timezone, url)."""
    user_id = user.get("identity")
    await verify_current_user(db, user_id)

    workspace_service = WorkspaceService(db)
    from src.utils.workspace_utils import resolve_and_verify_workspace

    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    old_values = {
        "name": workspace.name,
        "timezone": workspace.timezone,
        "url": workspace.url,
    }

    # A changed URL must be a live site, the same rule as on create. Re-sending
    # the current URL unchanged skips the network check.
    if data.url and str(data.url).rstrip("/").lower() != (workspace.url or "").rstrip("/").lower():
        try:
            await check_website_reachable(str(data.url))
        except WebsiteUnreachableError as exc:
            raise RextValidationException(message=str(exc), field_errors={"url": [str(exc)]})

    # Support 'title' fallback from raw body for legacy frontend compatibility
    name = data.name
    if not name:
        try:
            body = await request.json()
            name = body.get("title")
        except Exception:
            pass
        if name is not None:
            name = validate_workspace_name(name)

    updated_workspace = await workspace_service.update_workspace_for_user(
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        name=name,
        timezone=data.timezone,
        url=str(data.url) if data.url else None,
    )

    from src.utils.audit_helper import create_audit_log_async

    await create_audit_log_async(
        db=db,
        user_id=UUID(user_id),
        action="workspace.update",
        resource_type="workspace",
        resource_id=str(workspace.id),
        workspace_id=workspace.id,
        old_values=old_values,
        new_values={
            "name": name or old_values["name"],
            "timezone": data.timezone or old_values["timezone"],
            "url": str(data.url) if data.url else old_values["url"],
        },
        request=request,
    )

    logger.info("Workspace updated", extra={"workspace_id": str(workspace.id), "user_id": user_id})

    return success(
        data={"workspace": updated_workspace},
        request=request,
        message="Workspace updated successfully",
    )


# -------------------------
# Transfer ownership
# -------------------------
@router.post(
    "/{workspace_id}/transfer-ownership",
    response_model=SuccessResponse[WorkspaceTransferOwnershipResponse],
)
@require_permissions("workspace.delete", workspace_scoped=True)
@db_transaction_handler("transfer workspace ownership", auto_commit=True)
async def transfer_workspace_ownership(
    workspace_id: str,
    data: WorkspaceTransferOwnershipSchema,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Hand the workspace to another active member. Owner only."""
    user_id = UUID(user.get("identity"))
    await verify_current_user(db, str(user_id))

    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace_by_id_or_slug_for_user(workspace_id, user_id)

    await workspace_service.transfer_ownership(workspace.id, user_id, data.new_owner_user_id)

    from src.utils.audit_helper import create_audit_log_async

    await create_audit_log_async(
        db=db,
        user_id=user_id,
        action="workspace.transfer_ownership",
        resource_type="workspace",
        resource_id=str(workspace.id),
        workspace_id=workspace.id,
        old_values={"owner_user_id": str(user_id)},
        new_values={"owner_user_id": str(data.new_owner_user_id)},
        request=request,
    )

    return success(
        data={
            "workspace_id": workspace.id,
            "new_owner_user_id": data.new_owner_user_id,
            "previous_owner_user_id": user_id,
        },
        request=request,
        message="Workspace ownership transferred",
    )


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
    user: dict = Depends(get_current_user),
):
    """
    Soft-delete a workspace (30-day recovery period).

    Marks the workspace as deleted and sends a confirmation email to the owner.
    """
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace_by_id_or_slug_for_user(
        workspace_id, UUID(user_id)
    )

    # Verify ownership for deletion
    await workspace_service.verify_user_is_workspace_owner(workspace.id, UUID(user_id))

    # Count before deletion for stats
    remaining_count = await workspace_service.count_user_workspaces(UUID(user_id))
    remaining_after_delete = remaining_count - 1

    # Perform soft delete
    await workspace_service.delete_workspace(workspace.id, UUID(user_id))

    from src.utils.audit_helper import create_audit_log_async

    await create_audit_log_async(
        db=db,
        user_id=UUID(user_id),
        action="workspace.delete",
        resource_type="workspace",
        resource_id=str(workspace.id),
        workspace_id=workspace.id,
        old_values={"name": workspace.name},
        request=request,
    )

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
            remaining_workspaces=remaining_after_delete,
        )
    except Exception as e:
        logger.error(f"Failed to send deletion confirmation email: {str(e)}")

    return success(
        data={
            "workspace_id": workspace.id,
            "message": "Workspace deleted successfully. You have 30 days to recover it if needed.",
            "recovery_period_days": 30,
            "remaining_workspaces": remaining_after_delete,
            "is_last_workspace": remaining_after_delete == 0,
        },
        request=request,
        message="Workspace deleted successfully",
    )


# -------------------------
# Permanently delete workspace
# -------------------------
@router.delete(
    "/{workspace_id}/permanent",
    response_model=SuccessResponse[WorkspacePermanentDeleteResponse],
)
@require_permissions("workspace.delete", workspace_scoped=True)
@db_transaction_handler(
    "permanently delete workspace",
    success_message="Workspace permanently deleted",
)
async def permanently_delete_workspace_endpoint(
    workspace_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Permanently delete a workspace that is already in the trash.

    Irreversible — there is no restore afterwards. Returns 404 if the workspace
    does not exist or has not been soft-deleted first, so this route can never
    destroy a live workspace.

    workspace_id is typed UUID rather than str (the convention elsewhere in this
    file) so FastAPI rejects a malformed id with a 422 before the handler runs.
    That also means this route takes a UUID only, never a slug — which is what
    it already required, it just used to answer a slug with a 500.
    """
    user_id = user.get("identity")

    workspace_service = WorkspaceService(db)

    # Audit after the delete, which needs the name the delete returns. The log
    # is written in the same transaction, so it commits with the delete or not
    # at all. It carries the workspace only as resource_id, never as
    # audit_logs.workspace_id: that column is a real FK (ON DELETE SET NULL, so
    # logs written earlier survive the delete), and setting it here — after the
    # row is gone — would violate the FK on flush.
    from src.utils.audit_helper import create_audit_log_async

    workspace_name = await workspace_service.permanently_delete_workspace(
        workspace_id, UUID(user_id)
    )

    await create_audit_log_async(
        db=db,
        user_id=UUID(user_id),
        action="workspace.permanent_delete",
        resource_type="workspace",
        resource_id=str(workspace_id),
        old_values={"name": workspace_name},
        request=request,
    )

    logger.info(
        "Workspace permanently deleted",
        extra={"workspace_id": str(workspace_id), "user_id": user_id},
    )

    return success(
        data={
            "workspace_id": workspace_id,
            "message": f'Workspace "{workspace_name}" was permanently deleted.',
        },
        request=request,
        message="Workspace permanently deleted",
    )


# -------------------------
# Restore workspace
# -------------------------
@router.post("/{workspace_id}/restore", response_model=SuccessResponse[WorkspaceRestoreResponse])
@require_permissions("workspace.delete", workspace_scoped=True)
@db_transaction_handler("restore workspace", success_message="Workspace restored successfully")
async def restore_workspace_endpoint(
    workspace_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    _: None = Depends(check_workspace_limit()),
):
    """
    Restore a soft-deleted workspace within its 30-day recovery period.

    Only the workspace owner can restore it.
    """
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.restore_workspace(workspace_id, UUID(user_id))

    from src.utils.audit_helper import create_audit_log_async

    await create_audit_log_async(
        db=db,
        user_id=UUID(user_id),
        action="workspace.restore",
        resource_type="workspace",
        resource_id=str(workspace.id),
        workspace_id=workspace.id,
        new_values={"name": workspace.name},
        request=request,
    )

    logger.info(
        "Workspace restored",
        extra={"workspace_id": str(workspace.id), "user_id": user_id},
    )

    try:
        await send_workspace_email(
            db=db,
            email_type="workspace_restored",
            workspace_id=workspace.id,
            recipient_email=db_user.email,
            user_id=UUID(user_id),
            user_name=db_user.display_name or db_user.email,
            workspace_name=workspace.name,
        )
    except Exception as e:
        logger.error(f"Failed to send restoration confirmation email: {str(e)}")

    return success(
        data={
            "message": "Workspace restored successfully.",
            "workspace": workspace_service._serialize_workspace(workspace),
        },
        request=request,
        message="Workspace restored successfully",
    )
