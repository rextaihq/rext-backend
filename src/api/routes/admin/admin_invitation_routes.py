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

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import ResourceNotFoundException, RextValidationException
from src.api.middleware.rate_limiter import admin_invitation_rate_limit
from src.api.schema.admin_invitation_schema import (
    AdminInvitationListResponse,
    AdminInvitationResponse,
    CreateAdminInvitationRequest,
    DeclineAdminInvitationRequest,
    ResendAdminInvitationRequest,
    RevokeAdminInvitationRequest,
    ValidateAdminInvitationResponse,
)
from src.api.schema.response_schemas import GenericResponse, SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.admin_invitation_emails import person_name, send_admin_invitation_email
from src.services.admin_invitation_service import AdminInvitationService
from src.utils.audit_helper import create_audit_log_async
from src.utils.logger import logger
from src.utils.response_utils import created, success
from src.utils.route_decorators import db_transaction_handler, require_permissions

# Admin routes (authenticated, super_admin only)
admin_router = APIRouter(
    prefix="/admin/platform/invitations", tags=["Admin - Platform Invitations"]
)

# Public routes (no auth required)
public_router = APIRouter(prefix="/admin-invitations", tags=["Public - Admin Invitations"])


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _invitation_to_response(invitation) -> AdminInvitationResponse:
    """Convert invitation model to response schema.

    The invitation is one the service read whole (its three people loaded): nothing
    can be read from the database here.
    """
    now = datetime.now(timezone.utc)
    days_until_expiry = None

    if invitation.status == "pending" and not invitation.is_expired():
        time_diff = invitation.expires_at - now
        days_until_expiry = max(0, time_diff.days)

    return AdminInvitationResponse(
        id=str(invitation.id),
        email=invitation.email,
        admin_role=invitation.admin_role,
        status=invitation.status,
        message=invitation.message,
        permissions=invitation.permissions,
        invited_by_admin_id=str(invitation.invited_by_admin_id)
        if invitation.invited_by_admin_id
        else None,
        invited_by_name=person_name(invitation.invited_by),
        invited_by_email=invitation.invited_by.email if invitation.invited_by else None,
        created_at=invitation.created_at.isoformat(),
        expires_at=invitation.expires_at.isoformat(),
        accepted_at=invitation.accepted_at.isoformat() if invitation.accepted_at else None,
        declined_at=invitation.declined_at.isoformat() if invitation.declined_at else None,
        revoked_at=invitation.revoked_at.isoformat() if invitation.revoked_at else None,
        accepted_by_user_id=str(invitation.accepted_by_user_id)
        if invitation.accepted_by_user_id
        else None,
        accepted_by_name=person_name(invitation.accepted_by),
        declined_reason=invitation.declined_reason,
        revoked_by_admin_id=str(invitation.revoked_by_admin_id)
        if invitation.revoked_by_admin_id
        else None,
        revoked_by_name=person_name(invitation.revoked_by),
        revoked_reason=invitation.revoked_reason,
        is_expired=invitation.is_expired(),
        can_be_accepted=invitation.can_be_accepted(),
        days_until_expiry=days_until_expiry,
    )


def _invalid_invitation_validation_response() -> ValidateAdminInvitationResponse:
    """Return a client-safe response for invalid/unavailable admin invitation tokens."""
    return ValidateAdminInvitationResponse(
        valid=False,
        email="",
        admin_role="",
        expires_at=datetime.now(timezone.utc).isoformat(),
        is_expired=True,
        status="invalid",
        error_message="Invitation is invalid or expired",
    )


# ============================================================================
# ADMIN ENDPOINTS (super_admin only)
# ============================================================================


@admin_router.post(
    "", response_model=SuccessResponse[AdminInvitationResponse], status_code=status.HTTP_201_CREATED
)
@db_transaction_handler("create admin invitation", auto_commit=True)
@require_permissions("user.invite", workspace_scoped=False)
async def create_admin_invitation(
    request: Request,
    data: CreateAdminInvitationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(admin_invitation_rate_limit()),  # Add rate limiting
):
    """
    Create a new platform admin invitation.

    **Requirements:**
    - Caller must be super_admin
    - Email must not have existing pending invitation
    - Admin role must be valid (super_admin, admin, support)

    **Process:**
    1. Validates caller is super_admin
    2. Creates invitation with secure token
    3. Sends the invitation email. If it can't be sent, nothing is saved and the
       caller is told (502), so "created" always means the person has the link
    4. Returns invitation details

    **Security:**
    - Only super_admin can create admin invitations
    - All actions are audit logged
    """
    service = AdminInvitationService(db)

    invitation = await service.create_admin_invitation(
        email=data.email,
        admin_role=data.admin_role,
        invited_by_admin_id=UUID(current_user["identity"]),
        message=data.message,
        permissions=data.permissions,
        expiry_days=data.expiry_days or 7,
    )

    await create_audit_log_async(
        db=db,
        user_id=UUID(current_user["identity"]),
        action="admin_invitation.create",
        resource_type="admin_invitation",
        resource_id=str(invitation.id),
        new_values={"email": invitation.email, "admin_role": invitation.admin_role},
        request=request,
    )

    # Before the commit: an invitation whose email didn't go out is not kept.
    await send_admin_invitation_email(db, invitation)

    return created(data=_invitation_to_response(invitation), request=request)


@admin_router.get("", response_model=SuccessResponse[AdminInvitationListResponse])
@db_transaction_handler("list admin invitations", auto_commit=False)
@require_permissions("user.invite", workspace_scoped=False)
async def list_admin_invitations(
    request: Request,
    status: Optional[str] = Query(
        None, description="Filter by status (pending/accepted/revoked/expired/declined)"
    ),
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

    invitations, total_count = await service.get_all_invitations_paginated(
        status=status,
        limit=limit,
        offset=offset,
    )

    invitation_responses = [_invitation_to_response(inv) for inv in invitations]

    return success(
        data=AdminInvitationListResponse(
            invitations=invitation_responses,
            total_count=total_count,
            status_filter=status,
            limit=limit,
            offset=offset,
        ),
        request=request,
    )


@admin_router.get("/{invitation_id}", response_model=SuccessResponse[AdminInvitationResponse])
@db_transaction_handler("get admin invitation", auto_commit=False)
@require_permissions("user.invite", workspace_scoped=False)
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

    return success(data=_invitation_to_response(invitation), request=request)


@admin_router.post(
    "/{invitation_id}/resend", response_model=SuccessResponse[AdminInvitationResponse]
)
@db_transaction_handler("resend admin invitation", auto_commit=True)
@require_permissions("user.invite", workspace_scoped=False)
async def resend_admin_invitation(
    request: Request,
    invitation_id: UUID,
    data: ResendAdminInvitationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    __: None = Depends(admin_invitation_rate_limit()),
):
    """
    Resend (refresh) an admin invitation with new token and expiry.

    **Requirements:**
    - Caller must be super_admin
    - Invitation must be pending or expired

    **Process:**
    1. Generates new token
    2. Updates expiry date
    3. Sends the invitation email again. If it can't be sent, the old link stays
       as it was and the caller is told (502)
    """
    service = AdminInvitationService(db)

    invitation = await service.resend_admin_invitation(
        invitation_id=invitation_id,
        resent_by_admin_id=UUID(current_user["identity"]),
        expiry_days=data.expiry_days or 7,
    )

    await create_audit_log_async(
        db=db,
        user_id=UUID(current_user["identity"]),
        action="admin_invitation.resend",
        resource_type="admin_invitation",
        resource_id=str(invitation.id),
        new_values={"email": invitation.email, "expiry_days": data.expiry_days or 7},
        request=request,
    )

    # Before the commit: a new link nobody received must not replace the old one.
    await send_admin_invitation_email(db, invitation)

    return success(data=_invitation_to_response(invitation), request=request)


@admin_router.delete("/{invitation_id}", response_model=SuccessResponse[GenericResponse])
@db_transaction_handler("revoke admin invitation", auto_commit=True)
@require_permissions("user.invite", workspace_scoped=False)
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
        revoked_by_admin_id=UUID(current_user["identity"]),
        reason=data.reason,
    )

    await create_audit_log_async(
        db=db,
        user_id=UUID(current_user["identity"]),
        action="admin_invitation.revoke",
        resource_type="admin_invitation",
        resource_id=str(invitation.id),
        new_values={"email": invitation.email, "reason": data.reason},
        request=request,
    )

    # TODO: Optionally send revocation email
    # await send_admin_invitation_revoked_email(invitation)

    return success(
        data=GenericResponse(
            success=True,
            message=f"Admin invitation for {invitation.email} has been revoked",
        ),
        request=request,
    )


# ============================================================================
# PUBLIC ENDPOINTS (no auth required)
# ============================================================================


@public_router.get(
    "/{token}/validate", response_model=SuccessResponse[ValidateAdminInvitationResponse]
)
async def validate_admin_invitation_token(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_async_db),
):
    """Validate an admin invitation token (public endpoint)."""
    service = AdminInvitationService(db)

    try:
        invitation = await service.get_invitation_by_token(token)

        return success(
            data=ValidateAdminInvitationResponse(
                valid=invitation.can_be_accepted(),
                invitation_id=str(invitation.id),
                email=invitation.email,
                admin_role=invitation.admin_role,
                message=invitation.message,
                invited_by_name=person_name(invitation.invited_by),
                expires_at=invitation.expires_at.isoformat(),
                is_expired=invitation.is_expired(),
                status=invitation.status,
                error_message=None
                if invitation.can_be_accepted()
                else (
                    "Invitation has expired"
                    if invitation.is_expired()
                    else "Invitation is no longer pending"
                ),
            ),
            request=request,
        )
    except (ResourceNotFoundException, RextValidationException):
        logger.info(
            "Admin invitation token validation failed", extra={"reason": "invalid_or_not_found"}
        )
        return success(data=_invalid_invitation_validation_response(), request=request)
    except Exception:
        logger.exception("Unexpected error validating admin invitation token")
        return success(data=_invalid_invitation_validation_response(), request=request)


@public_router.post("/{token}/accept", response_model=SuccessResponse[AdminInvitationResponse])
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
        user_id=UUID(current_user["identity"]),
    )

    await create_audit_log_async(
        db=db,
        user_id=UUID(current_user["identity"]),
        action="admin_invitation.accept",
        resource_type="admin_invitation",
        resource_id=str(invitation.id),
        new_values={"email": invitation.email, "admin_role": invitation.admin_role},
        request=request,
    )

    # TODO: Send acceptance notification to inviter
    # await send_admin_invitation_accepted_email(invitation)

    return success(data=_invitation_to_response(invitation), request=request)


@public_router.post("/{token}/decline", response_model=SuccessResponse[GenericResponse])
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

    await create_audit_log_async(
        db=db,
        user_id=None,
        action="admin_invitation.decline",
        resource_type="admin_invitation",
        resource_id=str(invitation.id),
        new_values={"email": invitation.email, "reason": data.reason},
        request=request,
    )

    # TODO: Send decline notification to inviter
    # await send_admin_invitation_declined_email(invitation)

    return success(
        data=GenericResponse(
            success=True,
            message="Admin invitation declined successfully",
        ),
        request=request,
    )
