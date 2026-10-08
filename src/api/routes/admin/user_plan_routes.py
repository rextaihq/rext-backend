"""
A super admin changes a user's plan, or moves a trial's end to a later date
(FB2.29, revnix/rext-control#710). The rules are in
src/services/admin_plan_changes.py; these routes check who is asking and who is
asked about, and commit.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.models.subscription_models.subscriptions import BillingPeriod
from src.api.models.user_models.users import Users
from src.api.routes.subscriptions.admin.shared.auth import require_super_admin
from src.api.schema.response.admin_plan_responses import (
    AdminPlanChangeResult,
    AdminTrialExtensionResult,
    AdminUserPlanResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.subscription.admin_schemas import AdminPlanChange, AdminTrialExtension
from src.api.security.dependencies import get_current_user
from src.services.admin_plan_changes import change_plan, extend_trial, plan_options
from src.utils import rbac_utils
from src.utils.rbac_utils import assert_target_manageable_by
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions

router = APIRouter(prefix="/users", tags=["Admin - User Plan"])


async def _existing_user(db: AsyncSession, user_id: UUID) -> Users:
    user = await db.get(Users, user_id)
    if user is None:
        raise ResourceNotFoundException(
            resource_type="User", resource_id=str(user_id), message="User not found"
        )
    return user


@router.get("/{user_id}/plan", response_model=SuccessResponse[AdminUserPlanResponse])
@require_permissions("billing.read")
@db_transaction_handler("get user plan options", auto_commit=False)
async def get_user_plan(
    request: Request,
    user_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    A user's plan and what a super admin may change it to (super admin only).

    Returns:
    - subscription: the plan now, its period, renewal and credits; null without one
    - change: whether the plan may be changed, and how a change is billed by default
    - trial_extension: whether the trial's end may be moved, and between which dates
    - plans: each plan with its list prices and, for each period, whether it can be
      chosen, whether it is an upgrade or a downgrade, and each way it can be billed
      with the month's credits it would leave
    - limits: the reason's shortest and longest length
    """
    await require_super_admin(db, current_user.get("identity"))
    await _existing_user(db, user_id)
    # The two changes refuse a Super Admin's account: the options say so first.
    protected = await rbac_utils.is_user_super_admin(db, user_id)

    return success(
        data=await plan_options(db, user_id, protected=protected),
        request=request,
        message="Plan options retrieved successfully",
    )


@router.post("/{user_id}/plan", response_model=SuccessResponse[AdminPlanChangeResult])
@require_permissions("billing.manage")
@db_transaction_handler("change user plan")
async def change_user_plan(
    request: Request,
    user_id: UUID,
    body: AdminPlanChange,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Change a user's plan (super admin only).

    Request Body:
    - plan_id: the plan to move to
    - billing_period: monthly or yearly
    - billing: next_renewal (nothing charged now, the new price from the next
      renewal), charge_now (Lemon Squeezy invoices the prorated difference now; an
      upgrade only) or not_billed (a user without a Lemon Squeezy subscription)
    - reason: why, kept with the audit entry

    The plan changes at once, through Lemon Squeezy first for a subscription it
    bills, and the month's credits become the new plan's minus what was used this
    period. A trial, a failed renewal, a cancelled or lifetime subscription and a
    Super Admin's account are refused. Every change is in the audit log.
    """
    admin_user_id = UUID(str(current_user.get("identity")))
    await require_super_admin(db, admin_user_id)
    await _existing_user(db, user_id)
    await assert_target_manageable_by(db, admin_user_id, user_id, action="change the plan of")

    result = await change_plan(
        db,
        user_id=user_id,
        admin_id=admin_user_id,
        plan_id=body.plan_id,
        billing_period=BillingPeriod(body.billing_period),
        billing=body.billing,
        reason=body.reason,
    )
    await db.commit()

    return success(data=result, request=request, message="Plan changed.")


@router.post("/{user_id}/trial", response_model=SuccessResponse[AdminTrialExtensionResult])
@require_permissions("billing.manage")
@db_transaction_handler("extend user trial")
async def extend_user_trial(
    request: Request,
    user_id: UUID,
    body: AdminTrialExtension,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Move a user's trial to a later end (super admin only).

    Request Body:
    - ends_at: the new end, later than the trial's own and within the limit the
      plan options give
    - reason: why, kept with the audit entry

    Only a trial this app runs: one Lemon Squeezy runs is ended or converted by it.
    """
    admin_user_id = UUID(str(current_user.get("identity")))
    await require_super_admin(db, admin_user_id)
    await _existing_user(db, user_id)
    await assert_target_manageable_by(db, admin_user_id, user_id, action="extend the trial of")

    result = await extend_trial(
        db,
        user_id=user_id,
        admin_id=admin_user_id,
        ends_at=body.ends_at,
        reason=body.reason,
    )
    await db.commit()

    return success(data=result, request=request, message="Trial extended.")
