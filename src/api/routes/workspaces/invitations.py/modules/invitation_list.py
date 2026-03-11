from fastapi import APIRouter, Depends, Request, HTTPException, Query,BackgroundTasks
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
from src.api.middleware.exceptions import ResourceNotFoundException, RextAPIException
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity, SuccessResponse
from src.api.schema.response.invitation_responses import InvitationListResponse
from src.api.models.user_models.users import Users
from src.api.models.user_models.invitations import UserInvitations
from src.services.invitation_service import InvitationService
from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.services.notifications_services import notification_service
from src.api.services.notification_helper import schedule_if_allowed

router = APIRouter()


@router.get("/sent", response_model=SuccessResponse[InvitationListResponse])
@require_permissions("member.read", workspace_scoped=True)
@db_transaction_handler("list sent invitations", auto_commit=False)
async def list_sent_invitations(
    request: Request,
    status_filter: Optional[str] = Query(None, description="Filter by status (pending, accepted, revoked, expired)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
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
        details = await get_invitation_with_details(db, str(inv.id))
        if details:
            invitations_data.append(details)

   
    return success(
        data={
            "invitations": invitations_data,
            "total_count": len(invitations_data),
            "status_filter": status_filter
        },
        message=f"Retrieved {len(invitations_data)} sent invitation(s)"
    )

@router.get("/received", response_model=SuccessResponse[InvitationListResponse])
@require_permissions("member.read")
@db_transaction_handler("list received invitations", auto_commit=True)
async def list_received_invitations(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = Depends(BackgroundTasks),
):
    """
    List pending invitations for the current user's email.
    Expiry checking and marking stays in route as it's presentation/cleanup logic.
    """
    user_id = current_user.get("identity")

    # ------------------------------------------------------------------
    # 1️⃣ Load the user & their email
    # ------------------------------------------------------------------
    result = await db.execute(select(Users).where(Users.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ResourceNotFoundException(
            message="User not found",
            resource_type="user",
            resource_id=str(user_id),
        )

    logger.info(f"User {user_id} listing received invitations for email {user.email}")

    # ------------------------------------------------------------------
    # 2️⃣ Pull pending invitations for that email
    # ------------------------------------------------------------------
    result = await db.execute(
        select(UserInvitations)
        .where(UserInvitations.email == user.email, UserInvitations.status == "pending")
        .order_by(UserInvitations.created_at.desc())
    )
    invitations = result.scalars().all()

    # ------------------------------------------------------------------
    # 3️⃣ Filter out expired ones & build detailed payload
    # ------------------------------------------------------------------
    invitations_data = []
    expired_count = 0
    for inv in invitations:
        if not is_invitation_expired(inv):
            details = await get_invitation_with_details(db, str(inv.id))
            if details:
                invitations_data.append(details)
        else:
            inv.status = "expired"
            expired_count += 1

    if expired_count:
        logger.info(f"Marked {expired_count} invitation(s) as expired.")
    await db.flush()   # persist any status changes

    # ------------------------------------------------------------------
    # 4️⃣ Load the user's notification preferences
    # ------------------------------------------------------------------
    result = await db.execute(
        select(NotificationPreferences).where(NotificationPreferences.user_id == UUID(user_id))
    )
    pref = result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # 5️⃣ Schedule notification **iff** the preference allows it
    # ------------------------------------------------------------------
    await schedule_if_allowed(
        db=db,
        user_id=user_id,
        background_tasks=background_tasks,
        pref_flag="ws_invite_received",
        message="You have new pending invitations.",
        payload={
            "invitations": invitations_data,
            "total_count": len(invitations_data),
        },
        # workspace_id=str(workspace_id),
    )

    # ------------------------------------------------------------------
    # 6️⃣ Return the API response
    # ------------------------------------------------------------------
    return success(
        data={
            "invitations": invitations_data,
            "total_count": len(invitations_data),
        },
        message=f"Retrieved {len(invitations_data)} pending invitation(s)"
    )