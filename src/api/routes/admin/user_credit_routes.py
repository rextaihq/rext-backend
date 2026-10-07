"""
Admin User Credits API endpoints (FB2.28, revnix/rext-control#709).

A super admin adds credits to, deducts credits from or resets the monthly
credits of any user, with a reason the customer sees, and reads the user's
credits and the history of those changes. The rules are in
src/services/admin_credits.py.

All endpoints require the super admin role; a change also needs billing.manage
and is refused on a Super Admin's own account.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.models.user_models.users import Users
from src.api.routes.subscriptions.admin.shared.auth import require_super_admin
from src.api.schema.response.credit_responses import (
    AdminCreditAdjustmentResult,
    AdminUserCreditsResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.subscription.admin_schemas import AdminCreditAdjustment
from src.api.security.dependencies import get_current_user
from src.services.admin_credits import adjust_credits, credit_breakdown, credit_history
from src.utils.rbac_utils import assert_target_manageable_by
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions

router = APIRouter(prefix="/users", tags=["Admin - User Credits"])

_DONE = {
    "add": "Credits added.",
    "deduct": "Credits deducted.",
    "reset": "Monthly credits reset.",
}


async def _existing_user(db: AsyncSession, user_id: UUID) -> Users:
    user = await db.get(Users, user_id)
    if user is None:
        raise ResourceNotFoundException(resource_type="user", resource_id=str(user_id))
    return user


@router.get("/{user_id}/credits", response_model=SuccessResponse[AdminUserCreditsResponse])
@require_permissions("billing.read")
@db_transaction_handler("get user credits", auto_commit=False)
async def get_user_credits(
    request: Request,
    user_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    A user's credits and the history of admin changes to them (super admin only).

    Returns:
    - credits: what the user can spend now: the month's credits, a promotion's
      bonus and the credits admins added
    - grants: the credits admins added, with what is left, what a deduction
      took back, the reason, who added them and the expiry
    - adjustments: every add, deduct and reset from the audit log, with the
      balance before and after; newest first, at most 100 of each
    """
    await require_super_admin(db, current_user.get("identity"))
    await _existing_user(db, user_id)

    history = await credit_history(db, user_id, for_admin=True)
    return success(
        data={
            "user_id": user_id,
            "credits": await credit_breakdown(db, user_id),
            **history,
        },
        request=request,
        message="Credits retrieved successfully",
    )


@router.post("/{user_id}/credits", response_model=SuccessResponse[AdminCreditAdjustmentResult])
@require_permissions("billing.manage")
@db_transaction_handler("adjust user credits")
async def adjust_user_credits(
    request: Request,
    user_id: UUID,
    body: AdminCreditAdjustment,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Add, deduct or reset a user's credits (super admin only).

    Request Body:
    - action: add, deduct or reset
    - amount: credits to add or deduct, 1 to 100,000; left out for a reset
    - reason: why, 3 to 500 characters, shown to the customer
    - expires_at: only for an add: when the credits expire. Left out, they
      last and are spent after the month's credits; with it, before them.

    A deduction takes what admins added first, then the month's credits, never
    below 0; when less is there than asked for, it takes what there is and
    says so in ``amount``. A reset sets the month's credits to the plan's
    amount (not on a trial). Every change is in the audit log.
    """
    admin_user_id = UUID(str(current_user.get("identity")))
    await require_super_admin(db, admin_user_id)
    await _existing_user(db, user_id)
    await assert_target_manageable_by(db, admin_user_id, user_id, action="change the credits of")

    result = await adjust_credits(
        db,
        user_id=user_id,
        admin_id=admin_user_id,
        action=body.action,
        amount=body.amount,
        reason=body.reason,
        expires_at=body.expires_at,
    )
    await db.commit()

    return success(
        data=result,
        request=request,
        message=_DONE[body.action],
    )
