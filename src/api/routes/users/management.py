from fastapi import APIRouter, Depends, Request, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_
from sqlalchemy.orm import selectinload
from uuid import UUID
import uuid
import json
from datetime import datetime, timezone

from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import require_permissions, db_transaction_handler
from src.api.schema.user_schema import UpdateUser, DataExportRequest, DataExportResponse
from src.services.email_service import EmailService
from src.api.database.async_database import get_async_db
from src.services.user_service import UserService
from src.api.middleware.exceptions import ResourceNotFoundException, RextValidationException
from src.utils.response_utils import success
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.admin_responses import UserListResponse, UserResponseSchema, UserDeleteResponse
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.user_models.users import Users
from src.api.models.user_models.user_roles import UserRole
from src.api.config import get_settings

router = APIRouter()
settings = get_settings()

async def send_data_export_email_task(
    email: str,
    name: str,
    export_id: str,
    export_json: str,
    export_request_details: dict,
    frontend_url: str,
    user_id: str
):
    """
    Background task to send data export email.
    """
    from src.api.database.async_database import get_async_db_context

    try:
        async with get_async_db_context() as async_db:
            email_service = EmailService(async_db)

            check_sym = '\u2713'
            cross_sym = '\u2717'
            body_html = f"""
            <h2>Your Data Export is Ready</h2>
            <p>Hello {name},</p>
            <p>Your requested data export has been generated.</p>
            <p><strong>Export ID:</strong> {export_id}</p>
            <p><strong>Generated at:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>

            <h3>Export Contents:</h3>
            <ul>
                <li>Profile Information: {check_sym if export_request_details.get('include_profile') else cross_sym}</li>
                <li>Role Assignments: {check_sym if export_request_details.get('include_roles') else cross_sym}</li>
                <li>Workspace Memberships: {check_sym if export_request_details.get('include_workspaces') else cross_sym}</li>
                <li>Activity Logs: {check_sym if export_request_details.get('include_activity') else cross_sym}</li>
            </ul>

            <p>Your data is included below as JSON.</p>
            <p><a href="{frontend_url}">Return to REXT</a></p>

            <hr>
            <pre style="background: #f4f4f4; padding: 15px; border-radius: 5px; overflow-x: auto;">
{export_json}
            </pre>
            """

            await email_service.send_email(
                to=email,
                subject="Your REXT Data Export",
                html=body_html,
                user_id=UUID(user_id),
                template_type="data_export",
                tags={"type": "user_management", "action": "data_export"}
            )
            logger.info(f"Data export email sent successfully to {email}")
    except Exception as e:
        logger.error(f"Failed to send data export email to {email}: {str(e)}", exc_info=True)


@router.get("/users", response_model=SuccessResponse[UserListResponse])
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("get users", auto_commit=False)
async def get_users(
    request: Request,
    workspace_id: str = Query(None, description="Filter by workspace ID"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Retrieve users, optionally filtered by workspace.
    """
    service = UserService(db)
    workspace_uuid = UUID(workspace_id) if workspace_id else None

    result = await service.get_users(
        workspace_id=workspace_uuid,
        page=page,
        per_page=per_page,
    )

    user_data = [user.to_dict() for user in result["users"]]

    return success(
        data={
            "users": user_data,
            "total_count": result["pagination"]["total"],
            "workspace_id": workspace_id,
            "pagination": result["pagination"],
        },
        request=request,
        message=f"Retrieved {len(user_data)} users successfully"
    )


@router.delete("/delete/{user_id}", response_model=SuccessResponse[UserDeleteResponse])
@require_permissions("user.delete", workspace_scoped=False)
@db_transaction_handler("delete user", auto_commit=True)
async def delete_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Soft delete a user by setting deleted_at timestamp.
    """
    service = UserService(db)
    target_uuid = UUID(user_id)

    # Delete workspace memberships first to prevent orphaned records if not handled by cascades
    await db.execute(
        delete(WorkspaceMembers).where(WorkspaceMembers.user_id == target_uuid)
    )
    await db.flush()

    # Delete user via service
    db_user = await service.delete_user(target_uuid)
    
    logger.info(f"User {user_id} soft deleted by admin {current_user.get('identity')}")

    return success(
        data={"id": str(db_user.id)},
        request=request,
        message="User deleted successfully"
    )


@router.put("/update/{user_id}", response_model=SuccessResponse[UserResponseSchema])
@db_transaction_handler("update user", auto_commit=True)
async def update_user(
    user_id: UUID,  # Changed from str to UUID for auto-validation (returns 422 on bad ID)
    update_data: UpdateUser,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update user details.
    """
    service = UserService(db)

    db_user = await service.update_user(
        user_id=user_id,
        **update_data.model_dump(exclude_unset=True)
    )

    return success(
        data=db_user.to_dict(),
        request=request,
        message="User updated successfully"
    )


@router.post("/export-data", response_model=SuccessResponse[DataExportResponse])
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("export user data", auto_commit=False)
async def export_user_data(
    request: Request,
    export_request: DataExportRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Request export of user's data.
    """
    user_id = UUID(current_user.get("identity"))
    # Get user with relationships eagerly loaded to avoid MissingGreenlet error
    stmt = (
        select(Users)
        .where(Users.id == user_id)
        .options(
            selectinload(Users.user_roles).selectinload(UserRole.role),
            selectinload(Users.workspace_memberships)
        )
    )
    result = await db.execute(stmt)
    db_user = result.scalar_one_or_none()
    
    if not db_user:
        raise ResourceNotFoundException(resource_type="User", resource_id=str(user_id))
    
    export_data = {
        "profile": {
            "id": str(db_user.id),
            "email": db_user.email,
            "full_name": db_user.full_name,
            "display_name": db_user.display_name,
            "status": db_user.status,
            "created_at": db_user.created_at.isoformat() if db_user.created_at else None
        } if export_request.include_profile else {}
    }

    if export_request.include_roles:
        roles = []
        for user_role in getattr(db_user, 'user_roles', []):
            roles.append({
                "role_name": user_role.role.name if user_role.role else None,
                "is_primary": user_role.is_primary,
                "workspace_id": str(user_role.workspace_id) if user_role.workspace_id else None
            })
        export_data["roles"] = roles

    if export_request.include_workspaces:
        workspaces = []
        for membership in getattr(db_user, 'workspace_memberships', []):
            workspaces.append({
                "workspace_id": str(membership.workspace_id),
                "role": membership.role,
                "status": membership.status,
                "joined_at": membership.joined_at.isoformat() if membership.joined_at else None
            })
        export_data["workspaces"] = workspaces

    if export_request.include_usage:
        export_data["usage"] = {
            "account_age_days": (datetime.now(timezone.utc) - db_user.created_at.replace(tzinfo=timezone.utc)).days if db_user.created_at else 0
        }

    export_id = str(uuid.uuid4())
    export_json = json.dumps(export_data, indent=2)

    # Queue background task
    background_tasks.add_task(
        send_data_export_email_task,
        email=db_user.email,
        name=db_user.full_name or "User",
        export_id=export_id,
        export_json=export_json,
        export_request_details=export_request.model_dump(),
        frontend_url=settings.FRONTEND_URL,
        user_id=str(user_id)
    )

    response_data = DataExportResponse(
        export_id=export_id,
        user_id=str(user_id),
        status="pending",
        requested_at=datetime.now(timezone.utc).isoformat(),
        message="Data export has been requested and will be sent to your email."
    )

    return success(
        data=response_data,
        request=request,
        message="Data export requested successfully"
    )
