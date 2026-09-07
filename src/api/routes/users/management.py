from fastapi import APIRouter, Depends, Request, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_
from sqlalchemy.orm import selectinload
from src.api.config import get_settings
from uuid import UUID
import uuid
import json
import base64
from datetime import datetime, timezone
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import require_permissions, db_transaction_handler
from src.api.schema.user_schema import UpdateUser, DataExportRequest, DataExportResponse
from src.services.email_service import EmailService
from src.api.database.async_database import get_async_db
from src.services.user_service import UserService
from src.services.session_service import SessionService
from src.services.audit_service import AuditService
from src.services.subscription_service import SubscriptionService
from src.api.schema.audit_schema import AuditLogExportFormat
from emails.templates.account.data_export_ready import create_data_export_ready_email
from src.utils.audit_helper import create_audit_log_async
from src.api.middleware.exceptions import ResourceNotFoundException, RextValidationException
from src.api.schema.response_schemas import SuccessResponse
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.schema.response.user_management_responses import (
    UserListResponse,
    UserDeleteResponse,
    UserUpdateResponse,
    UserStatsResponse,
    UserSortField,
)
from src.utils.response_utils import success
from src.api.schema.user_schema import DataExportResponse
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole

router = APIRouter()
settings = get_settings()

async def send_data_export_email_task(
    email: str,
    name: str,
    export_id: str,
    export_json: str,
    export_request_details: dict,
    frontend_url: str,
    user_id: str,
    filename: str
):
    """
    Background task to send data export email.
    """
    from src.api.database.async_database import get_async_db_context

    try:
        async with get_async_db_context() as async_db:
            email_service = EmailService(async_db)

            body_html = create_data_export_ready_email(user_name=name)

            b64_content = base64.b64encode(export_json.encode('utf-8')).decode('ascii')
            attachments = [{
                "filename": filename,
                "content": b64_content,
                "content_type": "application/json"
            }]

            await email_service.send_email(
                to=email,
                subject="Your Rext AI Data Export",
                html=body_html,
                user_id=UUID(user_id),
                template_type="data_export",
                tags={"type": "user_management", "action": "data_export"},
                attachments=attachments
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
    search: str = Query(None, description="Search by name or email"),
    status: str = Query(None, description="Filter by account status"),
    role: str = Query(None, description="Filter by role name or display name"),
    sort_by: UserSortField = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort direction"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Retrieve users with optional workspace, search, status, role filtering and sorting.
    """
    service = UserService(db)
    workspace_uuid = UUID(workspace_id) if workspace_id else None

    result = await service.get_users(
        workspace_id=workspace_uuid,
        page=page,
        per_page=per_page,
        search=search,
        status=status,
        role=role,
        sort_by=sort_by,
        sort_order=sort_order,
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

@router.get("/users/stats", response_model=SuccessResponse[UserStatsResponse])
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("get user stats", auto_commit=False)
async def get_user_stats(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Aggregate counts for the User Management stat cards.

    Computed server-side so the cards stay accurate now that the table is
    served one page at a time rather than downloading every user.
    """
    service = UserService(db)
    stats = await service.get_user_stats()

    return success(
        data=stats,
        request=request,
        message="User statistics retrieved successfully"
    )


@router.get("/deleted", response_model=SuccessResponse[UserListResponse])
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("get deleted users", auto_commit=False)
async def get_deleted_users(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Retrieve soft-deleted users.
    """
    from sqlalchemy import func
    from src.api.models.user_models.user_roles import UserRole
    
    base_query = select(Users).options(
        selectinload(Users.user_roles).selectinload(UserRole.role),
        selectinload(Users.user_roles).selectinload(UserRole.workspace),
    ).where(Users.deleted_at.isnot(None), Users.status != "anonymized")

    # Get total count
    count_query = select(func.count()).select_from(base_query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * per_page
    paginated_query = base_query.offset(offset).limit(per_page)
    result = await db.execute(paginated_query)
    users = list(result.scalars().all())

    total_pages = (total + per_page - 1) // per_page if total > 0 else 0

    user_data = [user.to_dict() for user in users]
    
    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }

    return success(
        data={
            "users": user_data,
            "total_count": total,
            "workspace_id": None,
            "pagination": pagination,
        },
        request=request,
        message=f"Retrieved {len(user_data)} deleted users successfully"
    )


@router.get("/detail/{user_id}", response_model=SuccessResponse)
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("get user detail", auto_commit=False)
async def get_user_detail(
    user_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieve user detail by ID.
    """
    service = UserService(db)
    user = await service.get_user_by_id(user_id)
    if not user or user.deleted_at is not None:
        raise ResourceNotFoundException(resource_type="User", resource_id=str(user_id))

    return success(
        data=user.to_dict(),
        request=request,
        message="User details retrieved successfully"
    )


@router.delete("/delete/{user_id}", response_model=SuccessResponse[UserDeleteResponse])
@require_permissions("user.delete", workspace_scoped=False)
@db_transaction_handler("delete user", auto_commit=True)
async def delete_user(
    user_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Soft delete a user by setting deleted_at timestamp.

    Emails the account owner a recovery link, since the login screen tells a
    deleted user to use "the recovery link sent to your email".
    """
    service = UserService(db)
    target_uuid = UUID(user_id)

    # An admin deleting their own account would lock themselves out with no
    # way back, so refuse it explicitly rather than letting it happen.
    if str(target_uuid) == str(current_user.get("identity")):
        raise RextValidationException(
            message="You cannot delete your own account from User Management."
        )

    # Delete user via service
    db_user = await service.delete_user(target_uuid)

    # A soft delete must end the user's access immediately. get_current_user
    # validates the session, not deleted_at, so without this the deleted
    # user's live access token keeps working until it expires.
    await SessionService(db).revoke_all_sessions(target_uuid)

    # Queue the recovery link so the owner can restore the account within the
    # retention window. Queued (not sent inline) so a mail failure can't roll
    # back the deletion.
    from src.api.routes.users.auth import send_recovery_email_task
    from src.api.security.token_utils import create_recovery_token

    background_tasks.add_task(
        send_recovery_email_task,
        email=db_user.email,
        first_name=db_user.full_name or db_user.display_name or "there",
        recovery_token=create_recovery_token(
            {"id": str(db_user.id), "email": db_user.email}
        ),
        user_id=str(db_user.id),
        frontend_url=settings.FRONTEND_URL,
        retention_days=settings.USER_DELETION_RETENTION_DAYS,
    )

    logger.info(f"User {user_id} soft deleted by admin {current_user.get('identity')}")

    return success(
        data={"id": str(db_user.id)},
        request=request,
        message="User deleted successfully"
    )


@router.put("/update/{user_id}", response_model=SuccessResponse[UserUpdateResponse])
@require_permissions("user.update", workspace_scoped=False) # Adding missing permission check
@db_transaction_handler("update user", auto_commit=True)
async def update_user(
    user_id: UUID,  # Changed from str to UUID for auto-validation (returns 422 on bad ID)
    update_data: UpdateUser,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update user details.
    """
    service = UserService(db)

    changes = update_data.model_dump(exclude_unset=True)

    # Snapshot the fields being changed before the update so the audit entry
    # can show old -> new. Password is recorded as changed, never in clear.
    existing = await service.get_user_by_id(user_id)
    audited_fields = [f for f in changes if f != "password"]
    old_values = {field: getattr(existing, field, None) for field in audited_fields}

    db_user = await service.update_user(user_id=user_id, **changes)

    await create_audit_log_async(
        db=db,
        user_id=UUID(str(current_user.get("identity"))),
        action="user.update",
        resource_type="user",
        resource_id=str(user_id),
        old_values=old_values,
        new_values={field: changes[field] for field in audited_fields},
        request=request,
        metadata={
            "password_changed": "password" in changes,
            "updated_fields": sorted(changes.keys()),
            "target_user_email": db_user.email,
        },
    )

    return success(
        data=db_user.to_dict(),
        request=request,
        message="User updated successfully"
    )


@router.post("/export-data", response_model=SuccessResponse[DataExportResponse])
# No permission gate: this exports the *caller's own* data, so authentication
# is sufficient. Gating it on user.read locked out every non-admin.
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
        "export_metadata": {
            "export_id": str(uuid.uuid4()),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "user_id": str(user_id),
        },
        "user": {},
        "roles": [],
        "workspaces": [],
        "usage": {},
        "activity": [],
        "billing": {}
    }

    if export_request.include_profile:
        export_data["user"] = {
            "id": str(db_user.id),
            "email": db_user.email,
            "full_name": db_user.full_name,
            "display_name": db_user.display_name,
            "status": db_user.status,
            "created_at": db_user.created_at.isoformat() if db_user.created_at else None
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
                "status": membership.status,
                "joined_at": membership.joined_at.isoformat() if membership.joined_at else None
            })
        export_data["workspaces"] = workspaces

    if export_request.include_usage:
        export_data["usage"] = {
            "account_age_days": (datetime.now(timezone.utc) - db_user.created_at.replace(tzinfo=timezone.utc)).days if db_user.created_at else 0
        }

    if export_request.include_activity:
        audit_service = AuditService(db)
        # Fetch up to 1000 logs for the user's export to avoid immense payloads
        logs = await audit_service.fetch_logs(user_id=str(user_id), limit=1000)
        logs_payload = await audit_service.format_export_payload(
            logs, 
            format=AuditLogExportFormat.JSON, 
            requested_by=str(user_id)
        )
        export_data["activity"] = logs_payload.get("logs", [])

    if export_request.include_billing:
        sub_service = SubscriptionService(db)
        subscription = await sub_service.get_subscription_by_user(user_id)
        if subscription:
            export_data["billing"] = {
                "subscription_id": str(subscription.id),
                "status": subscription.status.value if subscription.status else None,
                "billing_period": subscription.billing_period.value if subscription.billing_period else None,
                "plan_name": subscription.plan.name if subscription.plan else None,
                "start_date": subscription.start_date.isoformat() if subscription.start_date else None,
                "end_date": subscription.end_date.isoformat() if subscription.end_date else None,
                "current_credits": subscription.current_credits,
            }

    export_id = export_data["export_metadata"]["export_id"]
    export_json = json.dumps(export_data, indent=2)
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"rext_export_{user_id}_{timestamp_str}.json"

    # Queue background task
    background_tasks.add_task(
        send_data_export_email_task,
        email=db_user.email,
        name=db_user.full_name or "User",
        export_id=export_id,
        export_json=export_json,
        export_request_details=export_request.model_dump(),
        frontend_url=settings.FRONTEND_URL,
        user_id=str(user_id),
        filename=filename
    )

    return success(
        data=DataExportResponse(
            export_id=export_id,
            user_id=str(user_id),
            status="completed",
            format="json",
            filename=filename,
            generated_at=datetime.now(timezone.utc).isoformat(),
            export_payload=export_data,
            requested_at=datetime.now(timezone.utc).isoformat(),
            message="Data export completed and sent to your email."
        ),
        request=request,
        message="Data export generated successfully"
    )
