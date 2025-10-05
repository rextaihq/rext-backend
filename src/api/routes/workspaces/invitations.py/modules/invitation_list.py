from fastapi import APIRouter, Depends, Request, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from src.utils.logger import logger
from src.utils.response_utils import success, error
from src.utils.invitation_utils import is_invitation_expired, get_invitation_with_details
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.models.user_models.users import Users
from src.api.models.user_models.invitations import UserInvitations


router = APIRouter()


@router.get("/sent")
async def list_sent_invitations(
    request: Request,
    status_filter: Optional[str] = Query(None, description="Filter by status (pending, accepted, revoked, expired)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List invitations sent by the current user.

    - **status_filter**: Optional filter by invitation status
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"User {user_id} listing sent invitations")

        # Build query
        query = select(UserInvitations).where(
            UserInvitations.invited_by_user_id == user_id
        )

        # Apply status filter
        if status_filter:
            query = query.where(UserInvitations.status == status_filter)

        # Get invitations
        result = await db.execute(query.order_by(UserInvitations.created_at.desc()))
        invitations = result.scalars().all()

        # Format response with details
        invitations_data = []
        for inv in invitations:
            details = get_invitation_with_details(db, str(inv.id))
            if details:
                invitations_data.append(details)

        return success(
            data={
                "invitations": invitations_data,
                "total_count": len(invitations_data),
                "status_filter": status_filter
            },
            request=request,
            message=f"Retrieved {len(invitations_data)} sent invitation(s)"
        )

    except Exception as e:
        logger.error(f"Error listing sent invitations: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve sent invitations"
        )


@router.get("/received")
async def list_received_invitations(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List pending invitations for the current user's email.

    Only shows pending, non-expired invitations.
    """
    try:
        user_id = current_user.get("identity")

        # Get user email
        result = await db.execute(select(Users).where(Users.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
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

        # Filter out expired and add details
        invitations_data = []
        for inv in invitations:
            if not is_invitation_expired(inv):
                details = get_invitation_with_details(db, str(inv.id))
                if details:
                    invitations_data.append(details)
            else:
                # Mark as expired
                inv.status = "expired"

        # Commit any expiry status updates
        await db.commit()

        return success(
            data={
                "invitations": invitations_data,
                "total_count": len(invitations_data)
            },
            request=request,
            message=f"Retrieved {len(invitations_data)} pending invitation(s)"
        )

    except Exception as e:
        logger.error(f"Error listing received invitations: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve received invitations"
        )
