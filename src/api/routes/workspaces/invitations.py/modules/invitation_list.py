from fastapi import APIRouter, Depends, Request, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from uuid import UUID

from src.utils.logger import logger
from src.utils.response_utils import success, error
from src.utils.invitation_utils import is_invitation_expired, get_invitation_with_details
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import ResourceNotFoundException, WrextAPIException
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.models.user_models.users import Users
from src.api.models.user_models.invitations import UserInvitations
from src.services.invitation_service import InvitationService


router = APIRouter()


@router.get("/sent")
@require_permissions("member.read", workspace_scoped=True)
@db_transaction_handler("list sent invitations", auto_commit=False)
async def list_sent_invitations(
    request: Request,
    status_filter: Optional[str] = Query(None, description="Filter by status (pending, accepted, revoked, expired)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List invitations sent by the current user - Using InvitationService
    Note: Presentation logic (get_invitation_with_details) stays in route
    """
    user_id = current_user.get("identity")
    logger.info(f"User {user_id} listing sent invitations")

    # Use service to get invitations (could be enhanced to add invited_by filter)
    # For now, we'll filter in the route since the service doesn't have this method yet
    query = select(UserInvitations).where(
        UserInvitations.invited_by_user_id == user_id
    )

    if status_filter:
        query = query.where(UserInvitations.status == status_filter)

    result = await db.execute(query.order_by(UserInvitations.created_at.desc()))
    invitations = result.scalars().all()

    # Format response with details (presentation layer concern)
    invitations_data = []
    for inv in invitations:
        details = get_invitation_with_details(db, str(inv.id))
        if details:
            invitations_data.append(details)

    return {
        "data": {
            "invitations": invitations_data,
            "total_count": len(invitations_data),
            "status_filter": status_filter
        },
        "message": f"Retrieved {len(invitations_data)} sent invitation(s)"
    }


@router.get("/received")
@require_permissions("member.read")
@db_transaction_handler("list received invitations", auto_commit=True)
async def list_received_invitations(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List pending invitations for the current user's email
    Note: Expiry checking and marking stays in route as it's presentation/cleanup logic
    """
    user_id = current_user.get("identity")

    # Get user email
    result = await db.execute(select(Users).where(Users.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ResourceNotFoundException(
            message="User not found",
            resource_type="user",
            resource_id=str(user_id)
        )

    logger.info(f"User {user_id} listing received invitations for email {user.email}")

    # Get pending invitations for user's email
    result = await db.execute(
        select(UserInvitations).where(
            UserInvitations.email == user.email,
            UserInvitations.status == "pending"
        ).order_by(UserInvitations.created_at.desc())
    )
    invitations = result.scalars().all()

    # Filter out expired and add details (presentation layer concern)
    invitations_data = []
    for inv in invitations:
        if not is_invitation_expired(inv):
            details = get_invitation_with_details(db, str(inv.id))
            if details:
                invitations_data.append(details)
        else:
            # Mark as expired
            inv.status = "expired"

    # Flush any expiry status updates
    await db.flush()

    return {
        "data": {
            "invitations": invitations_data,
            "total_count": len(invitations_data)
        },
        "message": f"Retrieved {len(invitations_data)} pending invitation(s)"
    }
