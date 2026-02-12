from fastapi import APIRouter, Depends, Request, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
import uuid
import os
from datetime import datetime, timezone

from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import require_permissions, db_transaction_handler
from src.api.schema.user_schema import UpdateUser, DataExportRequest, DataExportResponse
from src.services.email_service import EmailService
from src.api.database.async_database import get_async_db
from src.services.user_service import UserService
from src.api.middleware.exceptions import ResourceNotFoundException, RextValidationException, RextAuthorizationException
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.config import get_settings, settings
from sqlalchemy import select, delete

router = APIRouter()


# Get settings instance
settings = get_settings()

async def send_data_export_email_task(
    email: str,
    name: str,
    export_id: str,
    export_json: str,
    export_request,
    frontend_url: str,
    user_id: str
):
    """
    Background task to send data export email using EmailService.

    Args:
        email: Recipient email address
        name: User's name for personalization
        export_id: Unique export ID
        export_json: JSON export data
        export_request: Export request details
        frontend_url: Frontend URL for links
        user_id: User ID for email tracking
    """
    from src.api.database.async_database import get_async_db_context

    try:
        async with get_async_db_context() as async_db:
            email_service = EmailService(async_db)

            body_html = f"""
            <h2>Your Data Export is Ready</h2>
            <p>Hello {name},</p>
            <p>Your requested data export has been generated.</p>
            <p><strong>Export ID:</strong> {export_id}</p>
            <p><strong>Generated at:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>

            <h3>Export Contents:</h3>
            <ul>
                <li>Profile Information: {'✓' if export_request.include_profile else '✗'}</li>
                <li>Role Assignments: {'✓' if export_request.include_roles else '✗'}</li>
                <li>Workspace Memberships: {'✓' if export_request.include_workspaces else '✗'}</li>
                <li>Activity Logs: {'✓' if export_request.include_activity else '✗'}</li>
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


@router.get("/users")
@require_permissions("user.read", workspace_scoped=False)
async def get_users(
    request: Request,
    workspace_id: str = None,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Retrieve users, optionally filtered by workspace. Supports pagination.

    Requires authentication.
    """
    try:
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
    except Exception as e:
        logger.error(f"Failed to retrieve users: {str(e)}")
        raise


@router.delete("/delete/{user_id}")
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
    Thin controller - permission check inline, deletion logic simple.

    Requires user.delete permission (super_admin only).
    """
    service = UserService(db)
    current_user_id = UUID(current_user.get("identity"))

    try:
        service = UserService(db)
        current_user_id = UUID(current_user.get("identity"))

        # Check permission via service
        has_permission = await service.check_user_permission(
            user_id=current_user_id,
            permission_name="user.delete"
        )

        if not has_permission:
            return error(
                message="Missing required permission: user.delete",
                code=ErrorCode.FORBIDDEN,
                status_code=403,
                severity=ErrorSeverity.HIGH,
                context={"required_permission": "user.delete"},
                request=request
            )

        # Delete workspace memberships if any
        memberships = await db.execute(
            select(WorkspaceMembers).where(WorkspaceMembers.user_id == UUID(user_id))
        )
        membership_list = memberships.scalars().all()
        if membership_list:
            await db.execute(
                delete(WorkspaceMembers).where(WorkspaceMembers.user_id == UUID(user_id))
            )
            logger.info(f"Deleted {len(membership_list)} workspace memberships for user {user_id}")
            await db.flush()

        # Delete user via service (includes validation)
        db_user = await service.delete_user(UUID(user_id))
        return success(
            data={"id": str(db_user.id)},
            request=request,
            message="User deleted successfully"
        )

    except ResourceNotFoundException:
        return error(
            message="User not found",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except RextValidationException:
        return error(
            message="Validation failed",
            code=ErrorCode.DEPENDENCY_ERROR,
            status_code=400,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        logger.error(f"Failed to delete user {user_id}: {str(e)}")
        raise


@router.put("/update/{user_id}")
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("update user", auto_commit=True)
async def update_user(
    user_id: str,
    user: UpdateUser,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update user details.
    Thin controller - uses UserService for updates.
    """
    service = UserService(db)

    # Update user via service (handles all validation and updates)
    db_user = await service.update_user(
        user_id=UUID(user_id),
        update_data=user
    )

    # Return updated user data (excluding password)
    return {
        "user": {
            "id": str(db_user.id),
            "email": db_user.email,
            "full_name": db_user.full_name,
            "display_name": db_user.display_name,
            "language": db_user.language,
            "timezone": db_user.timezone,
            "status": db_user.status,
            "updated_at": db_user.updated_at.isoformat() if db_user.updated_at else None
        }
    }


@router.post("/export-data", response_model=DataExportResponse)
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("export user data", auto_commit=False) # Added transaction handler
async def export_user_data(
    request: Request,
    export_request: DataExportRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Request export of user's data.
    Thin controller - data collection logic kept in route for now.

    Generates a comprehensive data export including:
    - Profile information
    - Role assignments
    - Workspace memberships
    - Activity logs (if available)

    Export will be generated in the background and sent via email.

    Returns export request confirmation.
    """
    try:
        user_id = UUID(current_user.get("identity"))
        logger.info(f"Data export requested for user: {user_id}")

        service = UserService(db)

        # Get user from database
        db_user = await service.get_user_by_id(user_id)

        # Generate export ID
        export_id = str(uuid.uuid4())

        # Collect user data based on request
        export_data = {}

        if export_request.include_profile:
            export_data["profile"] = {
                "id": str(db_user.id),
                "email": db_user.email,
                "full_name": db_user.full_name,
                "display_name": db_user.display_name,
                "language": db_user.language,
                "timezone": db_user.timezone,
                "status": db_user.status,
                "email_verified": db_user.email_verified,
                "email_verified_at": db_user.email_verified_at.isoformat() if db_user.email_verified_at else None,
                "created_at": db_user.created_at.isoformat() if db_user.created_at else None,
                "last_login_at": db_user.last_login_at.isoformat() if db_user.last_login_at else None,
                "login_count": db_user.login_count
            }

        if export_request.include_roles:
            roles = []
            for user_role in db_user.user_roles:
                roles.append({
                    "role_name": user_role.role.name if user_role.role else None,
                    "role_display_name": user_role.role.display_name if user_role.role else None,
                    "is_primary": user_role.is_primary,
                    "workspace_id": str(user_role.workspace_id) if user_role.workspace_id else None,
                    "assigned_at": user_role.assigned_at.isoformat() if user_role.assigned_at else None
                })
            export_data["roles"] = roles

        if export_request.include_workspaces:
            workspaces = []
            for membership in db_user.workspace_memberships:
                workspaces.append({
                    "workspace_id": str(membership.workspace_id),
                    "workspace_name": membership.workspace.name if membership.workspace else None,
                    "role": membership.role,
                    "status": membership.status,
                    "joined_at": membership.joined_at.isoformat() if membership.joined_at else None
                })
            export_data["workspaces"] = workspaces

        # Note: Activity logs would require audit_logs table access
        if export_request.include_activity:
            export_data["activity"] = {
                "note": "Activity logs export will be available once audit log system is queried"
            }
        
        # Get frontend URL
        frontend_url = settings.FRONTEND_URL

        # NEW: Export billing/subscription data
        if export_request.include_billing:
            from src.api.models.subscription_models.subscriptions import UserSubscription

            # Get all user subscriptions
            subscriptions = []
            subscriptions_result = await db.execute(
                select(UserSubscription)
                .where(UserSubscription.user_id == user_id)
                .order_by(UserSubscription.created_at.desc())
            )

            for sub in subscriptions_result.scalars():
                subscription_data = {
                    "subscription_id": str(sub.id),
                    "plan_id": str(sub.plan_id),
                    "plan_name": sub.plan.name if sub.plan else None,
                    "status": sub.status,
                    "billing_period": sub.billing_period,
                    "current_period_start": sub.current_period_start.isoformat() if sub.current_period_start else None,
                    "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
                    "trial_ends_at": sub.trial_ends_at.isoformat() if sub.trial_ends_at else None,
                    "canceled_at": sub.canceled_at.isoformat() if sub.canceled_at else None,
                    "created_at": sub.created_at.isoformat() if sub.created_at else None,
                    "lemonsqueezy_id": sub.lemonsqueezy_id
                }
                subscriptions.append(subscription_data)

            export_data["subscriptions"] = subscriptions
            export_data["billing_info"] = {
                "total_subscriptions": len(subscriptions),
                "note": "Complete invoice history can be accessed via the LemonSqueezy customer portal",
                "customer_portal": f"{frontend_url}/settings/subscription"
            }

        # NEW: Export usage metrics
        if export_request.include_usage:
            # Basic usage stats - can be expanded based on your usage tracking
            export_data["usage"] = {
                "workspaces_count": len(db_user.workspace_memberships) if hasattr(db_user, 'workspace_memberships') else 0,
                "roles_count": len(db_user.user_roles) if hasattr(db_user, 'user_roles') else 0,
                "login_count": db_user.login_count if hasattr(db_user, 'login_count') else 0,
                "last_login": db_user.last_login_at.isoformat() if hasattr(db_user, 'last_login_at') and db_user.last_login_at else None,
                "account_age_days": (datetime.now(timezone.utc) - db_user.created_at).days if db_user.created_at else 0,
                "note": "Detailed usage metrics available upon request"
            }

        # Convert to JSON for email
        import json
        export_json = json.dumps(export_data, indent=2)

        # Send email with data export in background using EmailService
        background_tasks.add_task(
            send_data_export_email_task,
            email=db_user.email,
            name=db_user.full_name or "User",
            export_id=export_id,
            export_json=export_json,
            export_request=export_request,
            frontend_url=frontend_url,
            user_id=str(user_id)
        )

        logger.info(f"Data export {export_id} generated for user {user_id}")

        response_data = DataExportResponse(
            export_id=export_id,
            user_id=str(user_id),
            status="completed",
            requested_at=datetime.now(timezone.utc).isoformat(),
            message="Data export has been sent to your email address"
        )

        return success(
            data=response_data.model_dump(),
            request=request,
            message="Data export request completed successfully"
        )

    except ResourceNotFoundException:
        return error(
            message="User not found",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        logger.error(f"Error exporting data for user {current_user.get('identity')}: {str(e)}")
        return error(
            message="Failed to export user data",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )
