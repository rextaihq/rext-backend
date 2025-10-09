import os
from typing import Dict, List, Optional, Set
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import (
    BusinessRuleViolationException,
    DuplicateResourceException,
    ResourceNotFoundException,
    WrextValidationException,
)
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.user_models.roles import Role
from src.api.models.user_models.users import Users
from src.api.schema.invitation_schema import (
    RevokeInvitationRequest,
    WorkspaceInvitationBulkRequest,
    WorkspaceInvitationCreateRequest,
)
from src.api.security.dependencies import get_current_user
from src.api.tasks.send_mail import send_email
from src.services.invitation_service import InvitationService
from src.utils.audit_helper import create_audit_log
from src.utils.auth_utils import verify_current_user
from src.utils.invitation_utils import is_invitation_expired
from src.utils.logger import logger
from src.utils.response_utils import created, success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.utils.email_template_utils import render_workspace_email


router = APIRouter(tags=["workspace-invitations"])


async def _load_role_map(db: AsyncSession, role_ids: Set[UUID]) -> Dict[UUID, Role]:
    if not role_ids:
        return {}
    result = await db.execute(select(Role).where(Role.id.in_(role_ids)))
    roles = result.scalars().all()
    return {role.id: role for role in roles}


async def _load_user_map(db: AsyncSession, user_ids: Set[UUID]) -> Dict[UUID, Users]:
    if not user_ids:
        return {}
    result = await db.execute(select(Users).where(Users.id.in_(user_ids)))
    users = result.scalars().all()
    return {user.id: user for user in users}


def _serialize_invitation(
    invitation: UserInvitations,
    role: Optional[Role],
    invited_by: Optional[Users],
) -> Dict[str, Optional[str]]:
    expires_at = (
        invitation.expires_at.isoformat() if invitation.expires_at else None
    )
    return {
        "id": str(invitation.id),
        "workspace_id": str(invitation.workspace_id),
        "email": invitation.email,
        "role_id": str(invitation.role_id) if invitation.role_id else None,
        "role_name": role.display_name if role else None,
        "status": invitation.status,
        "expires_at": expires_at,
        "created_at": invitation.created_at.isoformat()
        if invitation.created_at
        else None,
        "invited_by_user_id": str(invitation.invited_by_user_id)
        if invitation.invited_by_user_id
        else None,
        "invited_by_name": invited_by.display_name if invited_by else None,
        "is_expired": is_invitation_expired(invitation),
    }


@router.get(
    "/{workspace_id}/invitations",
    summary="List invitations for a workspace",
)
@db_transaction_handler("list workspace invitations", auto_commit=False)
@require_permissions("member.invite", workspace_scoped=True)
async def list_workspace_invitations(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Return invitations created for the workspace."""
    user_uuid = UUID(str(user.get("identity")))
    await verify_current_user(db, str(user_uuid))
    workspace, _membership = await resolve_and_verify_workspace(
        db,
        workspace_id,
        user_uuid,
    )

    query = (
        select(UserInvitations)
        .where(UserInvitations.workspace_id == workspace.id)
        .order_by(UserInvitations.created_at.desc())
    )
    result = await db.execute(query)
    invitations: List[UserInvitations] = result.scalars().all()

    role_ids = {inv.role_id for inv in invitations if inv.role_id}
    inviter_ids = {
        inv.invited_by_user_id for inv in invitations if inv.invited_by_user_id
    }

    roles = await _load_role_map(db, role_ids)
    inviters = await _load_user_map(db, inviter_ids)

    payload = [
        _serialize_invitation(inv, roles.get(inv.role_id), inviters.get(inv.invited_by_user_id))
        for inv in invitations
    ]

    return success(
        data={
            "invitations": payload,
            "total_count": len(payload),
        },
        request=request,
        message=f"Retrieved {len(payload)} invitation(s)",
    )


@router.post(
    "/{workspace_id}/invitations",
    status_code=status.HTTP_201_CREATED,
    summary="Create workspace invitation",
)
@db_transaction_handler("create workspace invitation", auto_commit=True)
@require_permissions("member.invite", workspace_scoped=True)
async def create_workspace_invitation(
    workspace_id: str,
    payload: WorkspaceInvitationCreateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Create an invitation tied to the workspace."""
    user_uuid = UUID(str(user.get("identity")))
    await verify_current_user(db, str(user_uuid))
    workspace, _membership = await resolve_and_verify_workspace(
        db,
        workspace_id,
        user_uuid,
    )

    result = await db.execute(select(Role).where(Role.id == UUID(payload.role_id)))
    role = result.scalar_one_or_none()
    if not role:
        raise ResourceNotFoundException(
            resource_type="role",
            resource_id=payload.role_id,
        )

    service = InvitationService(db)
    try:
        invitation = await service.create_invitation(
            email=payload.email,
            workspace_id=workspace.id,
            role_id=role.id,
            invited_by_user_id=user_uuid,
            expiry_days=payload.expiry_days or 7,
        )
    except DuplicateResourceException:
        raise
    except BusinessRuleViolationException:
        raise

    result = await db.execute(select(Users).where(Users.id == user_uuid))
    inviter = result.scalar_one_or_none()

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

    invitation_link = f"{frontend_url}/invitations/accept?token={invitation.invitation_token}"

    email_content = render_workspace_email(
        db=db,
        workspace_id=workspace.id,
        template_type="workspace_invitation",
        variables={
            "workspace_name": workspace.name,
            "inviter_name": inviter.display_name if inviter else "A teammate",
            "recipient_email": invitation.email,
            "role_name": role.display_name or role.name,
            "invitation_url": invitation_link,
            "expiry_days": str(payload.expiry_days or 7),
        },
    )

    background_tasks.add_task(
        send_email,
        to=invitation.email,
        subject=email_content["subject"],
        body=email_content["body"],
    )

    create_audit_log(
        db=db,
        user_id=str(user_uuid),
        action="invitation.create",
        resource_type="invitation",
        resource_id=str(invitation.id),
        new_values={
            "email": invitation.email,
            "workspace_id": str(workspace.id),
            "role_id": str(role.id),
        },
        request=request,
        workspace_id=workspace.id,
        username=inviter.username if inviter else None,
        user_email=inviter.email if inviter else None,
    )

    logger.info(
        "Workspace invitation created",
        extra={
            "workspace_id": str(workspace.id),
            "invitation_id": str(invitation.id),
            "invited_email": invitation.email,
            "invited_by": str(user_uuid),
        },
    )

    return created(
        data={
            "invitation": _serialize_invitation(
                invitation, role, inviter
            )
        },
        request=request,
        message="Invitation created successfully",
    )


@router.post(
    "/{workspace_id}/invitations/bulk",
    status_code=status.HTTP_201_CREATED,
    summary="Create multiple workspace invitations",
)
@db_transaction_handler("create bulk workspace invitations", auto_commit=True)
@require_permissions("member.invite", workspace_scoped=True)
async def create_bulk_workspace_invitations(
    workspace_id: str,
    payload: WorkspaceInvitationBulkRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Create invitations for multiple recipients."""
    user_uuid = UUID(str(user.get("identity")))
    await verify_current_user(db, str(user_uuid))
    workspace, _membership = await resolve_and_verify_workspace(
        db,
        workspace_id,
        user_uuid,
    )

    result = await db.execute(select(Role).where(Role.id == UUID(payload.role_id)))
    role = result.scalar_one_or_none()
    if not role:
        raise ResourceNotFoundException(
            resource_type="role",
            resource_id=payload.role_id,
        )

    result = await db.execute(select(Users).where(Users.id == user_uuid))
    inviter = result.scalar_one_or_none()

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

    service = InvitationService(db)
    created_invitations = []
    failures = []

    for email in payload.emails:
        try:
            invitation = await service.create_invitation(
                email=email,
                workspace_id=workspace.id,
                role_id=role.id,
                invited_by_user_id=user_uuid,
                expiry_days=payload.expiry_days or 7,
            )
            created_invitations.append(invitation)

            invitation_url = (
                f"{frontend_url}/invitations/accept?token={invitation.invitation_token}"
            )
            email_content = render_workspace_email(
                db=db,
                workspace_id=workspace.id,
                template_type="workspace_invitation",
                variables={
                    "workspace_name": workspace.name,
                    "inviter_name": inviter.display_name if inviter else "A teammate",
                    "recipient_email": email,
                    "role_name": role.display_name or role.name,
                    "invitation_url": invitation_url,
                    "expiry_days": str(payload.expiry_days or 7),
                },
            )
            background_tasks.add_task(
                send_email,
                to=email,
                subject=email_content["subject"],
                body=email_content["body"],
            )
        except (DuplicateResourceException, BusinessRuleViolationException) as exc:
            failures.append({"email": email, "error": str(exc)})

    create_audit_log(
        db=db,
        user_id=str(user_uuid),
        action="invitation.bulk_create",
        resource_type="invitation",
        resource_id="bulk",
        new_values={
            "workspace_id": str(workspace.id),
            "emails": payload.emails,
            "role_id": payload.role_id,
        },
        request=request,
        workspace_id=workspace.id,
        username=inviter.username if inviter else None,
        user_email=inviter.email if inviter else None,
    )

    return created(
        data={
            "total_requested": len(payload.emails),
            "successful": len(created_invitations),
            "failed": len(failures),
            "results": [
                {
                    "email": inv.email,
                    "success": True,
                    "invitation_id": str(inv.id),
                }
                for inv in created_invitations
            ]
            + [
                {"email": failure["email"], "success": False, "error_message": failure["error"]}
                for failure in failures
            ],
        },
        request=request,
        message="Bulk invitations processed",
    )


@router.delete(
    "/{workspace_id}/invitations/{invitation_id}",
    summary="Revoke workspace invitation",
)
@db_transaction_handler("revoke workspace invitation", auto_commit=True)
@require_permissions("member.invite", workspace_scoped=True)
async def revoke_workspace_invitation(
    workspace_id: str,
    invitation_id: str,
    request: Request,
    payload: Optional[RevokeInvitationRequest] = None,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Revoke a pending invitation for the workspace."""
    user_uuid = UUID(str(user.get("identity")))
    await verify_current_user(db, str(user_uuid))
    workspace, _membership = await resolve_and_verify_workspace(
        db,
        workspace_id,
        user_uuid,
    )

    service = InvitationService(db)
    invitation = await service.get_invitation_by_id(UUID(invitation_id))
    if invitation.workspace_id != workspace.id:
        raise ResourceNotFoundException(
            resource_type="invitation",
            resource_id=invitation_id,
        )

    if invitation.status != "pending":
        raise WrextValidationException(
            message="Only pending invitations can be revoked",
            field_errors={"status": ["Invitation is not pending"]},
        )

    await service.revoke_invitation(
        invitation_id=UUID(invitation_id),
        revoked_by_user_id=user_uuid,
    )

    create_audit_log(
        db=db,
        user_id=str(user_uuid),
        action="invitation.revoke",
        resource_type="invitation",
        resource_id=invitation_id,
        old_values={"status": "pending"},
        new_values={
            "status": "revoked",
            "reason": payload.reason if payload else None,
        },
        request=request,
        workspace_id=workspace.id,
    )

    logger.info(
        "Workspace invitation revoked",
        extra={
            "workspace_id": str(workspace.id),
            "invitation_id": invitation_id,
            "revoked_by": str(user_uuid),
        },
    )

    return success(
        data={"invitation_id": invitation_id, "status": "revoked"},
        request=request,
        message="Invitation revoked successfully",
    )
