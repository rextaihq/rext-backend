"""
Admin Invitation API endpoints.

This module provides API endpoints for managing platform-level administrator invitations.
Only super_admin can access these endpoints.

Endpoints:
- POST   /admin/platform/invitations           - Create admin invitation
- GET    /admin/platform/invitations           - List all admin invitations
- GET    /admin/platform/invitations/{id}      - Get specific invitation
- POST   /admin/platform/invitations/{id}/resend - Resend invitation
- DELETE /admin/platform/invitations/{id}      - Revoke invitation
- GET    /admin/platform/invitations/stats     - Invitation statistics

Public Endpoints (no auth):
- GET    /admin-invitations/{token}/validate   - Validate invitation token
- POST   /admin-invitations/{token}/accept     - Accept invitation
- POST   /admin-invitations/{token}/decline    - Decline invitation
"""

from typing import Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.admin_invitation_service import AdminInvitationService
from src.api.schema.admin_invitation_schema import (
    CreateAdminInvitationRequest,
    AcceptAdminInvitationRequest,
    DeclineAdminInvitationRequest,
    RevokeAdminInvitationRequest,
    ResendAdminInvitationRequest,
    AdminInvitationResponse,
    AdminInvitationListResponse,
    ValidateAdminInvitationResponse,
    AdminInvitationStatsResponse,
)
from src.api.schema.response_schemas import GenericResponse
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.logger import logger


# Admin routes (authenticated, super_admin only)
admin_router = APIRouter(
    prefix="/admin/platform/invitations",
    tags=["Admin - Platform Invitations"]
)

# Public routes (no auth required)
public_router = APIRouter(
    prefix="/admin-invitations",
    tags=["Public - Admin Invitations"]
)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _invitation_to_response(invitation) -> AdminInvitationResponse:
    """Convert invitation model to response schema."""
    now = datetime.utcnow()
    days_until_expiry = None

    if invitation.status == 'pending' and not invitation.is_expired():
        time_diff = invitation.expires_at - now
        days_until_expiry = max(0, time_diff.days)

    return AdminInvitationResponse(
        id=str(invitation.id),
        email=invitation.email,
        admin_role=invitation.admin_role,
        status=invitation.status,
        message=invitation.message,
        permissions=invitation.permissions,
        invited_by_admin_id=str(invitation.invited_by_admin_id) if invitation.invited_by_admin_id else None,
        invited_by_name=(
            f"{invitation.invited_by.first_name} {invitation.invited_by.last_name}"
            if invitation.invited_by else None
        ),
        invited_by_email=invitation.invited_by.email if invitation.invited_by else None,
        created_at=invitation.created_at.isoformat(),
        expires_at=invitation.expires_at.isoformat(),
        accepted_at=invitation.accepted_at.isoformat() if invitation.accepted_at else None,
        declined_at=invitation.declined_at.isoformat() if invitation.declined_at else None,
        revoked_at=invitation.revoked_at.isoformat() if invitation.revoked_at else None,
        accepted_by_user_id=str(invitation.accepted_by_user_id) if invitation.accepted_by_user_id else None,
        accepted_by_name=(
            f"{invitation.accepted_by.first_name} {invitation.accepted_by.last_name}"
            if invitation.accepted_by else None
        ),
        declined_reason=invitation.declined_reason,
        revoked_by_admin_id=str(invitation.revoked_by_admin_id) if invitation.revoked_by_admin_id else None,
        revoked_by_name=(
            f"{invitation.revoked_by.first_name} {invitation.revoked_by.last_name}"
            if invitation.revoked_by else None
        ),
        revoked_reason=invitation.revoked_reason,
        is_expired=invitation.is_expired(),
        can_be_accepted=invitation.can_be_accepted(),
        days_until_expiry=days_until_expiry,
    )


# ============================================================================
# ADMIN ENDPOINTS (super_admin only)
# ============================================================================


@admin_router.post("", response_model=AdminInvitationResponse, status_code=status.HTTP_201_CREATED)
@db_transaction_handler("create admin invitation", auto_commit=True)
@require_permissions("admin.invite", workspace_scoped=False)
async def create_admin_invitation(
    request: Request,
    data: CreateAdminInvitationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a new platform admin invitation.

    **Requirements:**
    - Caller must be super_admin
    - Email must not have existing pending invitation
    - Admin role must be valid (super_admin, support_admin, platform_admin)

    **Process:**
    1. Validates caller is super_admin
    2. Creates invitation with secure token
    3. Sends invitation email (background task)
    4. Returns invitation details

    **Security:**
    - Only super_admin can create admin invitations
    - All actions are audit logged
    """
    service = AdminInvitationService(db)

    invitation = await service.create_admin_invitation(
        email=data.email,
        admin_role=data.admin_role,
        invited_by_admin_id=UUID(current_user["id"]),
        message=data.message,
        permissions=data.permissions,
        expiry_days=data.expiry_days or 7,
    )

    logger.info(
        f"Admin invitation created: {data.email} for {data.admin_role} "
        f"by {current_user['email']}"
    )

    # TODO: Send invitation email in background task
    # await send_admin_invitation_email(invitation)

    return _invitation_to_response(invitation)


@admin_router.get("", response_model=AdminInvitationListResponse)
@db_transaction_handler("list admin invitations", auto_commit=False)
@require_permissions("audit.read", workspace_scoped=False)
async def list_admin_invitations(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status (pending/accepted/revoked/expired/declined)"),
    limit: int = Query(50, ge=1, le=100, description="Results per page"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List all platform admin invitations.

    **Requirements:**
    - Caller must be super_admin

    **Filters:**
    - status: pending, accepted, revoked, expired, declined
    - limit: max 100 results
    - offset: for pagination
    """
    service = AdminInvitationService(db)

    invitations = await service.get_all_invitations(
        status=status,
        limit=limit,
        offset=offset,
    )

    invitation_responses = [_invitation_to_response(inv) for inv in invitations]

    return AdminInvitationListResponse(
        invitations=invitation_responses,
        total_count=len(invitation_responses),
        status_filter=status,
        limit=limit,
        offset=offset,
    )


@admin_router.get("/{invitation_id}", response_model=AdminInvitationResponse)
@db_transaction_handler("get admin invitation", auto_commit=False)
@require_permissions("audit.read", workspace_scoped=False)
async def get_admin_invitation(
    request: Request,
    invitation_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get details of a specific admin invitation.

    **Requirements:**
    - Caller must be super_admin
    - Invitation must exist
    """
    service = AdminInvitationService(db)
    invitation = await service.get_invitation_by_id(invitation_id)

    return _invitation_to_response(invitation)


@admin_router.post("/{invitation_id}/resend", response_model=AdminInvitationResponse)
@db_transaction_handler("resend admin invitation", auto_commit=True)
@require_permissions("admin.invite", workspace_scoped=False)
async def resend_admin_invitation(
    request: Request,
    invitation_id: UUID,
    data: ResendAdminInvitationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Resend (refresh) an admin invitation with new token and expiry.

    **Requirements:**
    - Caller must be super_admin
    - Invitation must be pending or expired

    **Process:**
    1. Generates new token
    2. Updates expiry date
    3. Sends new invitation email
    """
    service = AdminInvitationService(db)

    invitation = await service.resend_admin_invitation(
        invitation_id=invitation_id,
        resent_by_admin_id=UUID(current_user["id"]),
        expiry_days=data.expiry_days or 7,
    )

    logger.info(
        f"Admin invitation resent: {invitation.email} by {current_user['email']}"
    )

    # TODO: Send invitation email in background task
    # await send_admin_invitation_email(invitation)

    return _invitation_to_response(invitation)


@admin_router.delete("/{invitation_id}", response_model=GenericResponse)
@db_transaction_handler("revoke admin invitation", auto_commit=True)
@require_permissions("admin.invite", workspace_scoped=False)
async def revoke_admin_invitation(
    request: Request,
    invitation_id: UUID,
    data: RevokeAdminInvitationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Revoke (cancel) an admin invitation.

    **Requirements:**
    - Caller must be super_admin
    - Invitation must be pending

    **Process:**
    1. Marks invitation as revoked
    2. Records revoker and reason
    3. Optionally notifies invitee
    """
    service = AdminInvitationService(db)

    invitation = await service.revoke_admin_invitation(
        invitation_id=invitation_id,
        revoked_by_admin_id=UUID(current_user["id"]),
        reason=data.reason,
    )

    logger.info(
        f"Admin invitation revoked: {invitation.email} by {current_user['email']}"
    )

    # TODO: Optionally send revocation email
    # await send_admin_invitation_revoked_email(invitation)

    return GenericResponse(
        success=True,
        message=f"Admin invitation for {invitation.email} has been revoked",
    )


# ============================================================================
# PUBLIC ENDPOINTS (no auth required)
# ============================================================================


@public_router.get("/{token}/validate", response_model=ValidateAdminInvitationResponse)
async def validate_admin_invitation_token(
    token: str,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Validate an admin invitation token (public endpoint).

    **Purpose:**
    - Show invitation details before acceptance
    - Check if invitation is still valid
    - Used by frontend to display invitation info

    **No authentication required** - token serves as proof of invitation.
    """
    try:
        service = AdminInvitationService(db)
        invitation = await service.get_invitation_by_token(token)

        return ValidateAdminInvitationResponse(
            valid=invitation.can_be_accepted(),
            invitation_id=str(invitation.id),
            email=invitation.email,
            admin_role=invitation.admin_role,
            message=invitation.message,
            invited_by_name=(
                f"{invitation.invited_by.first_name} {invitation.invited_by.last_name}"
                if invitation.invited_by else None
            ),
            expires_at=invitation.expires_at.isoformat(),
            is_expired=invitation.is_expired(),
            status=invitation.status,
            error_message=None if invitation.can_be_accepted() else (
                "Invitation has expired" if invitation.is_expired()
                else f"Invitation is {invitation.status}"
            ),
        )
    except Exception as e:
        return ValidateAdminInvitationResponse(
            valid=False,
            email="",
            admin_role="",
            expires_at=datetime.utcnow().isoformat(),
            is_expired=True,
            status="invalid",
            error_message=str(e),
        )


@public_router.post("/{token}/accept", response_model=AdminInvitationResponse)
@db_transaction_handler("accept admin invitation", auto_commit=True)
async def accept_admin_invitation(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Accept an admin invitation (requires authentication).

    **Requirements:**
    - User must be logged in
    - Token must be valid and not expired
    - User's email must match invitation email
    - User must not already have admin role

    **Process:**
    1. Validates invitation token
    2. Checks email match
    3. Assigns admin role to user
    4. Marks invitation as accepted
    5. Notifies inviter of acceptance
    """
    service = AdminInvitationService(db)

    invitation = await service.accept_admin_invitation(
        token=token,
        user_id=UUID(current_user["id"]),
    )

    logger.info(
        f"Admin invitation accepted: {invitation.email} is now {invitation.admin_role}"
    )

    # TODO: Send acceptance notification to inviter
    # await send_admin_invitation_accepted_email(invitation)

    return _invitation_to_response(invitation)


@public_router.post("/{token}/decline", response_model=GenericResponse)
@db_transaction_handler("decline admin invitation", auto_commit=True)
async def decline_admin_invitation(
    request: Request,
    token: str,
    data: DeclineAdminInvitationRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Decline an admin invitation (no auth required).

    **Requirements:**
    - Token must be valid
    - Invitation must be pending

    **Process:**
    1. Marks invitation as declined
    2. Records decline reason
    3. Notifies inviter of decline
    """
    service = AdminInvitationService(db)

    invitation = await service.decline_admin_invitation(
        token=token,
        reason=data.reason,
    )

    logger.info(
        f"Admin invitation declined: {invitation.email}"
    )

    # TODO: Send decline notification to inviter
    # await send_admin_invitation_declined_email(invitation)

    return GenericResponse(
        success=True,
        message="Admin invitation declined successfully",
    )
