"""
Admin Account Recovery API endpoints.

Back the "Account Recovery" tab in admin User Management: list recovery requests
by status (pending / approved / rejected) and approve or reject a pending one.
Approving restores the account; either outcome emails the requester.

All endpoints require the admin or super_admin role.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.permissions import is_admin
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.account_recovery_service import AccountRecoveryService
from src.utils.audit_helper import create_audit_log_async
from src.utils.logger import logger
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler

router = APIRouter(prefix="/account-recovery", tags=["Admin - Account Recovery"])


class RecoveryReviewRequest(BaseModel):
    """Optional note the admin attaches when approving or rejecting."""
    note: Optional[str] = Field(None, max_length=2000)


async def _send_recovery_outcome_email(
    email_type: str, email: str, first_name: str, user_id: str, review_note: Optional[str]
):
    """Background task: tell the requester their recovery request was approved/rejected."""
    from src.api.config import get_settings
    from src.api.database.async_database import get_async_db_context
    from src.services.email_helpers import send_auth_email

    try:
        async with get_async_db_context() as async_db:
            await send_auth_email(
                db=async_db,
                email_type=email_type,
                recipient_email=email,
                user_name=first_name,
                user_id=UUID(user_id),
                frontend_url=get_settings().FRONTEND_URL,
                review_note=review_note,
            )
            logger.info(f"Recovery {email_type} email sent to {email}")
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to send recovery {email_type} email to {email}: {exc}", exc_info=True)


@router.get("/requests", response_model=SuccessResponse)
@db_transaction_handler("list account recovery requests", auto_commit=False)
async def list_recovery_requests(
    request: Request,
    status: str = Query("all", description="pending | approved | rejected | all"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by email"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin),
):
    """List account recovery requests, optionally filtered by status."""
    service = AccountRecoveryService(db)
    result = await service.list_requests(
        status=status, page=page, per_page=per_page, search=search
    )
    counts = await service.status_counts()

    return success(
        data={
            "requests": result["requests"],
            "pagination": result["pagination"],
            "counts": counts,
        },
        request=request,
        message=f"Retrieved {len(result['requests'])} recovery requests",
    )


@router.post("/requests/{request_id}/approve", response_model=SuccessResponse)
@db_transaction_handler("approve account recovery request", auto_commit=True)
async def approve_recovery_request(
    request_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    body: RecoveryReviewRequest = RecoveryReviewRequest(),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin),
):
    """Approve a pending recovery request and restore the account."""
    admin_id = UUID(str(current_user.get("identity")))
    service = AccountRecoveryService(db)

    req = await service.approve(request_id, admin_id, review_note=body.note)

    await create_audit_log_async(
        db=db,
        user_id=admin_id,
        action="user.account_recovery.approve",
        resource_type="account_recovery_request",
        resource_id=str(request_id),
        new_values={"status": "approved"},
        request=request,
        metadata={"target_user_email": req.email, "review_note": body.note},
    )

    if req.user_id:
        background_tasks.add_task(
            _send_recovery_outcome_email,
            email_type="account_recovery_approved",
            email=req.email,
            first_name=(req.user.full_name or req.user.display_name or "there") if req.user else "there",
            user_id=str(req.user_id),
            review_note=body.note,
        )

    return success(
        data=service._serialize(req),
        request=request,
        message="Recovery request approved and account restored",
    )


@router.post("/requests/{request_id}/reject", response_model=SuccessResponse)
@db_transaction_handler("reject account recovery request", auto_commit=True)
async def reject_recovery_request(
    request_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    body: RecoveryReviewRequest = RecoveryReviewRequest(),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin),
):
    """Reject a pending recovery request. The account stays deleted."""
    admin_id = UUID(str(current_user.get("identity")))
    service = AccountRecoveryService(db)

    req = await service.reject(request_id, admin_id, review_note=body.note)

    await create_audit_log_async(
        db=db,
        user_id=admin_id,
        action="user.account_recovery.reject",
        resource_type="account_recovery_request",
        resource_id=str(request_id),
        new_values={"status": "rejected"},
        request=request,
        metadata={"target_user_email": req.email, "review_note": body.note},
    )

    if req.user_id:
        background_tasks.add_task(
            _send_recovery_outcome_email,
            email_type="account_recovery_rejected",
            email=req.email,
            first_name=(req.user.full_name or req.user.display_name or "there") if req.user else "there",
            user_id=str(req.user_id),
            review_note=body.note,
        )

    return success(
        data=service._serialize(req),
        request=request,
        message="Recovery request rejected",
    )
