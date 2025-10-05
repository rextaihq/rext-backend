from fastapi import APIRouter, Depends, Request, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, timedelta
import uuid
import os

from src.utils.logger import logger
from src.utils.response_utils import success, created
from src.utils.invitation_utils import is_invitation_expired
from src.utils.audit_helper import create_audit_log
from src.utils.email_template_utils import render_workspace_email
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    WrextAuthenticationException
)
from src.api.schema.invitation_schema import (
    CreateInvitationRequest,
    BulkCreateInvitationRequest,
    BulkInvitationResult,
)
from src.api.models.user_models.users import Users
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.tasks.send_mail import send_email
from src.utils.workspace_utils import verify_workspace_membership
from src.utils.db_utils import get_or_404
from src.api.models.user_models.roles import Role


router = APIRouter()


@router.get("/status")
async def get_invitation_status(request: Request):
    """Qa
    Endpoint to check the invitation service status.
    """
    return success(
        message="Invitation service is up and running.",
        data={"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    )


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    request: Request,
    invitation_data: CreateInvitationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new invitation for a user to join a workspace.

    - **email**: Email address of the user to invite
    - **workspace_id**: ID of the workspace
    - **role_id**: Role to assign to the invited user
    - **expiry_days**: Days until invitation expires (1-30, default 7)

    Requires: workspace admin/owner OR user.invite permission
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"User {user_id} creating invitation for {invitation_data.email}")

        # Verify workspace exists and user has access
        workspace, membership = await verify_workspace_membership(db, invitation_data.workspace_id, user_id)

        # TODO: Add permission check for user.invite or workspace admin role

        # Verify role exists
        role = await get_or_404(db, Role, invitation_data.role_id, "role")

        # Check if invitation already exists for this email + workspace
        result = await db.execute(
            select(UserInvitations).where(
                UserInvitations.email == invitation_data.email.lower(),
                UserInvitations.workspace_id == invitation_data.workspace_id,
                UserInvitations.status == "pending"
            )
        )
        existing_invitation = result.scalar_one_or_none()

        if existing_invitation:
            # Check if expired - if so, revoke it and create new one
            if is_invitation_expired(existing_invitation):
                existing_invitation.status = "expired"
                await db.commit()
            else:
                raise DuplicateResourceException(
                    message="An active invitation already exists for this email and workspace",
                    resource_type="invitation",
                    conflicting_field="email",
                    conflicting_value=invitation_data.email
                )

        # Check if user is already a member
        # First find if user exists with this email
        result = await db.execute(
            select(Users).where(Users.email == invitation_data.email.lower())
        )
        existing_user = result.scalar_one_or_none()
        if existing_user:
            result = await db.execute(
                select(WorkspaceMembers).where(
                    WorkspaceMembers.user_id == existing_user.id,
                    WorkspaceMembers.workspace_id == invitation_data.workspace_id
                )
            )
            existing_membership = result.scalar_one_or_none()

            if existing_membership:
                raise DuplicateResourceException(
                    message="User is already a member of this workspace",
                    resource_type="workspace_member",
                    conflicting_field="user_id",
                    conflicting_value=str(existing_user.id)
                )

        # Generate invitation token
        invitation_token = str(uuid.uuid4())

        # Calculate expiry
        expires_at = datetime.utcnow() + timedelta(days=invitation_data.expiry_days)

        # Create invitation
        invitation = UserInvitations(
            email=invitation_data.email.lower(),
            workspace_id=invitation_data.workspace_id,
            role_id=invitation_data.role_id,
            invited_by_user_id=user_id,
            invitation_token=invitation_token,
            status="pending",
            expires_at=expires_at
        )

        db.add(invitation)
        await db.commit()
        await db.refresh(invitation)

        # Get inviter details for email
        result = await db.execute(select(Users).where(Users.id == user_id))
        inviter = result.scalar_one_or_none()

        # Send invitation email in background using custom or default template
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        invitation_link = f"{frontend_url}/invitations/accept?token={invitation_token}"

        # Render email template
        email_content = render_workspace_email(
            db=db,
            workspace_id=invitation_data.workspace_id,
            template_type="workspace_invitation",
            variables={
                "workspace_name": workspace.name,
                "inviter_name": inviter.display_name or inviter.username,
                "recipient_email": invitation_data.email,
                "role_name": role.display_name or role.name,
                "invitation_url": invitation_link,
                "expiry_days": str(invitation_data.expiry_days)
            }
        )

        background_tasks.add_task(
            send_email,
            to=invitation_data.email,
            subject=email_content["subject"],
            body=email_content["body"]
        )

        logger.info(f"Invitation created: {invitation.id} for {invitation_data.email} to workspace {workspace.name}")

        # Create audit log
        create_audit_log(
            db=db,
            user_id=user_id,
            action="invitation.create",
            resource_type="invitation",
            resource_id=str(invitation.id),
            new_values={
                "email": invitation_data.email,
                "workspace_id": str(invitation_data.workspace_id),
                "role_id": str(invitation_data.role_id)
            },
            request=request,
            workspace_id=invitation_data.workspace_id,
            username=inviter.username if inviter else None,
            user_email=inviter.email if inviter else None
        )

        return created(
            data={
                "invitation": {
                    "id": str(invitation.id),
                    "email": invitation.email,
                    "workspace_id": str(invitation.workspace_id),
                    "workspace_name": workspace.name,
                    "role_id": str(invitation.role_id),
                    "role_name": role.name,
                    "status": invitation.status,
                    "expires_at": invitation.expires_at.isoformat(),
                    "created_at": invitation.created_at.isoformat()
                }
            },
            request=request,
            message=f"Invitation sent to {invitation_data.email}"
        )

    except (DuplicateResourceException, ResourceNotFoundException, WrextAuthenticationException):
        raise
    except Exception as e:
        logger.error(f"Error creating invitation: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create invitation"
        )


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
async def create_bulk_invitations(
    request: Request,
    invitation_data: BulkCreateInvitationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create multiple invitations at once for users to join a workspace.

    - **emails**: List of email addresses (max 50)
    - **workspace_id**: ID of the workspace
    - **role_id**: Role to assign to all invited users
    - **expiry_days**: Days until invitations expire (1-30, default 7)

    Returns a detailed report of successful and failed invitations.
    Requires: workspace admin/owner OR user.invite permission
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"User {user_id} creating bulk invitations for {len(invitation_data.emails)} emails")

        # Verify workspace exists
        workspace = await verify_workspace_exists(db, invitation_data.workspace_id)

        # Check if user has permission to invite to this workspace
        await verify_workspace_membership(db, invitation_data.workspace_id, user_id)

        # Verify role exists
        role = await verify_role_exists(db, invitation_data.role_id)

        # Get inviter details for email
        result = await db.execute(select(Users).where(Users.id == user_id))
        inviter = result.scalar_one_or_none()
        inviter_name = inviter.display_name if inviter else "A workspace member"

        # Process each email
        results = []
        successful = 0
        failed = 0

        for email in invitation_data.emails:
            try:
                email_lower = email.lower()

                # Check if invitation already exists for this email + workspace
                result = await db.execute(
                    select(UserInvitations).where(
                        UserInvitations.email == email_lower,
                        UserInvitations.workspace_id == invitation_data.workspace_id,
                        UserInvitations.status == "pending"
                    )
                )
                existing_invitation = result.scalar_one_or_none()

                if existing_invitation:
                    # Check if expired - if so, revoke it and create new one
                    if is_invitation_expired(existing_invitation):
                        existing_invitation.status = "expired"
                        await db.commit()
                    else:
                        results.append(BulkInvitationResult(
                            email=email,
                            success=False,
                            error_message="An active invitation already exists for this email"
                        ))
                        failed += 1
                        continue

                # Check if user is already a member
                result = await db.execute(select(Users).where(Users.email == email_lower))
                existing_user = result.scalar_one_or_none()
                if existing_user:
                    result = await db.execute(
                        select(WorkspaceMembers).where(
                            WorkspaceMembers.user_id == existing_user.id,
                            WorkspaceMembers.workspace_id == invitation_data.workspace_id
                        )
                    )
                    existing_membership = result.scalar_one_or_none()

                    if existing_membership:
                        results.append(BulkInvitationResult(
                            email=email,
                            success=False,
                            error_message="User is already a member of this workspace"
                        ))
                        failed += 1
                        continue

                # Generate invitation token
                invitation_token = str(uuid.uuid4())

                # Calculate expiry
                expires_at = datetime.utcnow() + timedelta(days=invitation_data.expiry_days)

                # Create invitation
                invitation = UserInvitations(
                    email=email_lower,
                    workspace_id=invitation_data.workspace_id,
                    role_id=invitation_data.role_id,
                    invited_by_user_id=user_id,
                    invitation_token=invitation_token,
                    status="pending",
                    expires_at=expires_at
                )

                db.add(invitation)
                await db.flush()  # Get the ID without committing

                # Send invitation email asynchronously
                frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
                invitation_url = f"{frontend_url}/accept-invitation?token={invitation_token}"

                background_tasks.add_task(
                    send_email,
                    to_email=email,
                    subject=f"You're invited to join {workspace.name}",
                    body=f"""
                    Hi there,

                    {inviter_name} has invited you to join the "{workspace.name}" workspace.

                    Role: {role.display_name}

                    Click the link below to accept the invitation:
                    {invitation_url}

                    This invitation will expire in {invitation_data.expiry_days} days.

                    If you don't want to join this workspace, you can ignore this email.

                    Best regards,
                    The Wrext Team
                    """
                )

                # Audit log for each invitation
                create_audit_log(
                    db=db,
                    user_id=user_id,
                    action="invitation.created",
                    resource_type="invitation",
                    resource_id=str(invitation.id),
                    details={
                        "email": email,
                        "workspace_id": str(invitation_data.workspace_id),
                        "role_id": str(invitation_data.role_id),
                        "expires_at": expires_at.isoformat()
                    }
                )

                results.append(BulkInvitationResult(
                    email=email,
                    success=True,
                    invitation_id=str(invitation.id)
                ))
                successful += 1

            except Exception as e:
                logger.error(f"Error creating invitation for {email}: {str(e)}")
                results.append(BulkInvitationResult(
                    email=email,
                    success=False,
                    error_message=str(e)
                ))
                failed += 1

        # Commit all successful invitations
        await db.commit()

        logger.info(f"Bulk invitation completed: {successful} successful, {failed} failed")

        return created(
            data={
                "total_requested": len(invitation_data.emails),
                "successful": successful,
                "failed": failed,
                "results": [r.dict() for r in results]
            },
            request=request,
            message=f"Bulk invitation completed: {successful} sent, {failed} failed"
        )

    except (ResourceNotFoundException, WrextAuthenticationException):
        raise
    except Exception as e:
        logger.error(f"Error in bulk invitation: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process bulk invitations"
        )
