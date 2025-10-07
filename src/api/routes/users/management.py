from fastapi import APIRouter, Depends, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import uuid
import os
from datetime import datetime

from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.schema.user_schema import UpdateUser, DataExportRequest, DataExportResponse
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.tasks.send_mail import send_email
from src.api.database.async_database import get_async_db
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.services.user_service import UserService
from src.api.middleware.exceptions import ResourceNotFoundException, WrextValidationException

router = APIRouter()


@router.get("/users")
async def get_users(
    request: Request,
    workspace_id: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Retrieve users, optionally filtered by workspace.
    Thin controller - business logic could be extracted to service.

    Requires authentication.
    """
    try:
        logger.info(f"Fetching users for workspace: {workspace_id or 'all'}")

        # Base query
        query = select(Users)

        if workspace_id:
            # Filter by workspace membership
            query = query.join(WorkspaceMembers).where(
                WorkspaceMembers.workspace_id == workspace_id,
                WorkspaceMembers.status == "active"
            )
            logger.info(f"Filtering users by workspace_id: {workspace_id}")

        result = await db.execute(query)
        users = result.scalars().all()

        # Convert users to dict format (excluding passwords)
        user_data = [user.to_dict() for user in users]

        return success(
            data={
                "users": user_data,
                "total_count": len(user_data),
                "workspace_id": workspace_id
            },
            request=request,
            message=f"Retrieved {len(user_data)} users successfully"
        )
    except Exception as e:
        logger.error(f"Failed to retrieve users: {str(e)}")
        return error(
            message="Failed to retrieve users",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.delete("/delete/{user_id}")
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
    try:
        # Check if user has permission to delete users
        from src.api.models.user_models.permissions import Permission
        from src.api.models.user_models.role_permissions import RolePermission
        from src.api.models.user_models.user_roles import UserRole

        user_uuid = UUID(current_user.get("identity"))

        # Check user.delete permission
        permission_result = await db.execute(
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_uuid)
            .where(Permission.name == "user.delete")
        )
        permission_check = permission_result.scalar_one_or_none()

        if not permission_check:
            return error(
                message="Missing required permission: user.delete",
                code=ErrorCode.AUTHORIZATION_ERROR,
                status_code=403,
                severity=ErrorSeverity.HIGH,
                context={"required_permission": "user.delete"},
                request=request
            )

        service = UserService(db)

        # Get user to delete
        db_user = await service.get_user_by_id(UUID(user_id))

        # Prevent deleting an already deleted user
        if db_user.deleted_at:
            return error(
                message="User already deleted",
                code=ErrorCode.DEPENDENCY_ERROR,
                status_code=400,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Soft delete
        db_user.deleted_at = datetime.utcnow()
        await db.commit()

        return success(
            data={"id": str(db_user.id)},
            request=request,
            message="User deleted successfully"
        )

    except ResourceNotFoundException:
        return error(
            message="User not found",
            code=ErrorCode.NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete user {user_id}: {str(e)}")
        return error(
            message="Failed to delete user",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.put("/update/{user_id}")
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
    try:
        service = UserService(db)

        # Get user
        db_user = await service.get_user_by_id(UUID(user_id))

        # Check for duplicate email
        if user.email:
            email_result = await db.execute(
                select(Users).where(
                    Users.email == user.email,
                    Users.id != UUID(user_id)
                )
            )
            if email_result.scalar_one_or_none():
                return error(
                    message="Email already exists",
                    code=ErrorCode.DUPLICATE_RESOURCE,
                    status_code=400,
                    severity=ErrorSeverity.MEDIUM,
                    request=request
                )

        # Check for duplicate username
        if user.username:
            username_result = await db.execute(
                select(Users).where(
                    Users.username == user.username,
                    Users.id != UUID(user_id)
                )
            )
            if username_result.scalar_one_or_none():
                return error(
                    message="Username already exists",
                    code=ErrorCode.DUPLICATE_RESOURCE,
                    status_code=400,
                    severity=ErrorSeverity.MEDIUM,
                    request=request
                )

        # Update fields using service
        update_kwargs = {}
        if user.first_name is not None:
            update_kwargs["first_name"] = user.first_name
        if user.last_name is not None:
            update_kwargs["last_name"] = user.last_name
        if user.display_name is not None:
            update_kwargs["display_name"] = user.display_name
        if user.language is not None:
            update_kwargs["language"] = user.language
        if user.timezone is not None:
            update_kwargs["timezone"] = user.timezone

        # Email and username need direct update (not in update_profile)
        if user.email is not None:
            db_user.email = user.email
        if user.username is not None:
            db_user.username = user.username

        # Update other fields via service
        if update_kwargs:
            db_user = await service.update_profile(user_id=UUID(user_id), **update_kwargs)
        else:
            db_user.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(db_user)

        # Return updated user data (excluding password)
        user_data = {
            "id": str(db_user.id),
            "username": db_user.username,
            "email": db_user.email,
            "first_name": db_user.first_name,
            "last_name": db_user.last_name,
            "display_name": db_user.display_name,
            "language": db_user.language,
            "timezone": db_user.timezone,
            "status": db_user.status,
            "updated_at": db_user.updated_at.isoformat() if db_user.updated_at else None
        }

        return success(
            data={"user": user_data},
            request=request,
            message="User updated successfully"
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
        await db.rollback()
        logger.error(f"Failed to update user {user_id}: {str(e)}")
        return error(
            message="Failed to update user",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.post("/export-data", response_model=DataExportResponse)
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
                "username": db_user.username,
                "first_name": db_user.first_name,
                "last_name": db_user.last_name,
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

        # Convert to JSON for email
        import json
        export_json = json.dumps(export_data, indent=2)

        # Get frontend URL
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

        # Send email with data export in background
        background_tasks.add_task(
            send_email,
            to=db_user.email,
            subject="Your WREXT Data Export",
            body=f"""
            <h2>Your Data Export is Ready</h2>
            <p>Hello {db_user.first_name or db_user.username},</p>
            <p>Your requested data export has been generated.</p>
            <p><strong>Export ID:</strong> {export_id}</p>
            <p><strong>Generated at:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>

            <h3>Export Contents:</h3>
            <ul>
                <li>Profile Information: {'✓' if export_request.include_profile else '✗'}</li>
                <li>Role Assignments: {'✓' if export_request.include_roles else '✗'}</li>
                <li>Workspace Memberships: {'✓' if export_request.include_workspaces else '✗'}</li>
                <li>Activity Logs: {'✓' if export_request.include_activity else '✗'}</li>
            </ul>

            <p>Your data is attached as a JSON file to this email.</p>
            <p><a href="{frontend_url}">Return to WREXT</a></p>

            <hr>
            <pre style="background: #f4f4f4; padding: 15px; border-radius: 5px; overflow-x: auto;">
{export_json}
            </pre>
            """
        )

        logger.info(f"Data export {export_id} generated for user {user_id}")

        response_data = DataExportResponse(
            export_id=export_id,
            user_id=str(user_id),
            status="completed",
            requested_at=datetime.utcnow().isoformat(),
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
            context={"error_details": str(e)},
            request=request
        )
