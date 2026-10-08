"""
A super admin changes a user's plan, or moves a trial's end to a later date
(FB2.29, revnix/rext-control#710).

The plan change is the customer's own (``SubscriptionService.upgrade``), made by
an admin: Lemon Squeezy takes the new variant first and the row changes only
once it agreed, the balance follows the plan-change rule (the new plan's month
minus what was used this period), and the plan changes at once. What the admin
chooses is the money:

- ``next_renewal`` (the default): nothing is charged or credited now, and the
  new price applies from the next renewal.
- ``charge_now``: Lemon Squeezy invoices the prorated difference now. Offered
  for an upgrade only: what Lemon Squeezy does with a downgrade's prorated
  credit isn't something to promise.
- ``not_billed``: a user without a Lemon Squeezy subscription (a seeded or
  older row); only the row changes.

A trial is not moved to a paid plan here: that would be a paid plan nobody pays
for. Its end can be moved later instead, and credits added
(src/services/admin_credits.py). Every change carries the admin's reason and is
written to the audit log against the user; the reason is for that record, the
customer's activity shows the change without it.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.cache.decorators import invalidate_cache
from src.api.lib.sentry_config import trigger_payment_alert
from src.api.middleware.exceptions import (
    BusinessRuleViolationException,
    RextValidationException,
)
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    FAILED_PAYMENT_STATUSES,
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
    subscription_grants_access,
)
from src.services.audit_logger import audit_logger
from src.services.credit_grants import as_utc, change_plan_credits
from src.services.subscription_service import SubscriptionService
from src.services.webhook_handlers.subscription_handlers import _start_month_given
from src.utils.datetime_utils import add_months
from src.utils.logger import logger

NEXT_RENEWAL, CHARGE_NOW, NOT_BILLED = "next_renewal", "charge_now", "not_billed"
UPGRADE, DOWNGRADE, PERIOD_CHANGE = "upgrade", "downgrade", "period_change"
CURRENCY = "USD"
REASON_MIN_LENGTH = 3
REASON_MAX_LENGTH = 500
# How far ahead of now one extension may put a trial's end.
TRIAL_EXTENSION_MAX_DAYS = 30
TRIAL_AT_ITS_LIMIT = (
    f"This trial already ends more than {TRIAL_EXTENSION_MAX_DAYS} days from now, "
    "the furthest a trial can be moved."
)
# The billing periods a plan can be changed to: lifetime is not sold this way.
_PERIODS = (BillingPeriod.MONTHLY, BillingPeriod.YEARLY)

_NOTHING_CHANGED = " Nothing was changed."
_ON_TRIAL = (
    "This user is on a trial. Extend the trial or add credits instead: "
    "a trial isn't moved to a paid plan from here."
)
_NO_SUBSCRIPTION = "This user has no plan that grants access, so there is no plan to change."
_TRIAL_ENDED = "This user's trial has ended, so there is no plan to change and no trial to extend."
_PROTECTED = "A Super Admin's account is managed outside this screen: nothing is changed from here."


@dataclass(frozen=True)
class _Standing:
    """Where the user's subscription stands for an admin: what may be done, or why not."""

    subscription: Optional[UserSubscription]
    billed_by_provider: bool
    change_refused: Optional[str]
    extension_refused: Optional[str]


def clean_reason(reason: Optional[str]) -> str:
    """The reason without surrounding spaces, or a validation error."""
    reason = (reason or "").strip()
    if not REASON_MIN_LENGTH <= len(reason) <= REASON_MAX_LENGTH:
        raise RextValidationException(
            message="A reason is required",
            field_errors={
                "reason": [
                    f"Between {REASON_MIN_LENGTH} and {REASON_MAX_LENGTH} characters, "
                    "kept with the audit entry"
                ]
            },
        )
    return reason


async def _current_subscription(db: AsyncSession, user_id: UUID) -> Optional[UserSubscription]:
    """The user's subscription that grants access (the one the customer's own change reads)."""
    return await SubscriptionService(db).get_subscription_by_user(user_id)


def _is_trial(subscription: UserSubscription) -> bool:
    plan = subscription.plan
    return subscription.status == SubscriptionStatus.TRIAL or bool(plan and plan.is_trial_plan)


async def _trial_has_ended(db: AsyncSession, user_id: UUID) -> bool:
    """Whether the user's newest subscription is a trial: asked only when none grants
    access, so the admin reads why there is nothing to change."""
    newest = (
        await db.execute(
            select(UserSubscription)
            .options(selectinload(UserSubscription.plan))
            .where(UserSubscription.user_id == user_id)
            .order_by(UserSubscription.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return newest is not None and _is_trial(newest)


async def _standing_of(
    db: AsyncSession,
    user_id: UUID,
    subscription: Optional[UserSubscription],
    protected: bool = False,
) -> _Standing:
    if protected:
        billed = bool(
            subscription
            and (subscription.lemonsqueezy_subscription_id or subscription.provider_subscription_id)
        )
        return _Standing(subscription, billed, _PROTECTED, _PROTECTED)
    if subscription is None and await _trial_has_ended(db, user_id):
        return _Standing(None, False, _TRIAL_ENDED, _TRIAL_ENDED)
    return _standing(subscription)


def _standing(subscription: Optional[UserSubscription]) -> _Standing:
    if subscription is None:
        return _Standing(None, False, _NO_SUBSCRIPTION, _NO_SUBSCRIPTION)
    billed = bool(
        subscription.lemonsqueezy_subscription_id or subscription.provider_subscription_id
    )
    if _is_trial(subscription):
        extension = (
            "This trial is run by Lemon Squeezy, which ends or converts it: "
            "its end can't be moved from here."
            if billed
            else None
        )
        return _Standing(subscription, billed, _ON_TRIAL, extension)
    not_a_trial = "This user isn't on a trial."
    if subscription.status in FAILED_PAYMENT_STATUSES:
        refused = "A renewal payment has failed. The plan can be changed once it is paid."
    elif subscription.status != SubscriptionStatus.ACTIVE:
        refused = "This subscription is cancelled and runs to its end; its plan can't be changed."
    elif subscription.billing_period == BillingPeriod.LIFETIME:
        refused = "A lifetime plan can't be changed from here."
    else:
        refused = None
    return _Standing(subscription, billed, refused, not_a_trial)


async def _one_change_at_a_time(db: AsyncSession, user_id: UUID) -> None:
    """One change per user at a time, from before their plan is read.

    Two requests for one user (two admins, or one sent twice) would otherwise both
    check the same plan and both reach Lemon Squeezy, the second on what the first
    had made of it, with its billing, its credits and its audit entry worked out from
    a plan that is no longer theirs. The lock is the user's checkout lock, held until
    the transaction ends, so a checkout of theirs waits too.
    """
    await SubscriptionService(db)._lock_checkout(user_id)


def _variant(plan: SubscriptionPlan, period: BillingPeriod) -> Optional[str]:
    if period == BillingPeriod.MONTHLY:
        return plan.lemonsqueezy_variant_id_monthly
    return plan.lemonsqueezy_variant_id_yearly


def _kind(current: SubscriptionPlan, new: SubscriptionPlan) -> str:
    """An upgrade costs more a month by the list price; anything else is a downgrade."""
    if new.id == current.id:
        return PERIOD_CHANGE
    return UPGRADE if (new.price_monthly or 0) > (current.price_monthly or 0) else DOWNGRADE


def _over_the_limits(
    service: SubscriptionService,
    current: SubscriptionPlan,
    plan: SubscriptionPlan,
    usage: Dict[str, int],
) -> Optional[str]:
    """Why the user's usage rules the plan out (more workspaces than it allows), in the
    words the change itself refuses with, or None."""
    if not service._is_downgrade(current, plan, usage):
        return None
    try:
        service._validate_downgrade_limits(plan, usage)
    except RextValidationException as over:
        return over.message
    return None


def _period_refusal(
    standing: _Standing, current: SubscriptionPlan, plan: SubscriptionPlan, period: BillingPeriod
) -> Optional[str]:
    """Why this plan and period can't be chosen for the user, or None."""
    subscription = standing.subscription
    if plan.id == current.id:
        if subscription.billing_period == period:
            return "This is the user's plan now."
        return "A billing period can't be changed alone yet: choose another plan."
    if standing.billed_by_provider:
        # Another billing cycle can move Lemon Squeezy's billing date or charge at once,
        # so "nothing is charged now" couldn't be promised for it.
        if subscription.billing_period and subscription.billing_period != period:
            return (
                f"This subscription is billed {subscription.billing_period.value}: "
                "its billing period can't be changed from here yet."
            )
        if not _variant(plan, period):
            return f"{plan.display_name} has no {period.value} price at Lemon Squeezy."
    return None


def _modes(standing: _Standing, kind: str) -> List[str]:
    if not standing.billed_by_provider:
        return [NOT_BILLED]
    return [NEXT_RENEWAL, CHARGE_NOW] if kind == UPGRADE else [NEXT_RENEWAL]


def _credits_after(
    subscription: UserSubscription, current: SubscriptionPlan, plan: SubscriptionPlan
) -> Optional[int]:
    """The month's credits the change would leave: SubscriptionService.upgrade's own
    steps, run on a copy of what they read (tests hold the two together)."""
    if plan.credits_per_month is None:
        return None
    now = datetime.now(timezone.utc)
    copy = SimpleNamespace(
        status=subscription.status,
        trial_end_date=subscription.trial_end_date,
        subscription_metadata=dict(subscription.subscription_metadata or {}),
        current_credits=subscription.current_credits,
        credits_reset_date=subscription.credits_reset_date,
        renews_at=subscription.renews_at,
    )
    if not _start_month_given(copy):
        # Its first payment brings the plan's month: until then the balance stays.
        return copy.current_credits or 0
    period_before = copy.credits_reset_date
    copy.credits_reset_date = next(
        (end for end in (copy.credits_reset_date, copy.renews_at) if end and as_utc(end) > now),
        add_months(now, 1),
    )
    change_plan_credits(
        copy, current.credits_per_month, plan.credits_per_month, period_before=period_before
    )
    return copy.current_credits


async def _offered_plans(db: AsyncSession, current_id: Optional[UUID]) -> List[SubscriptionPlan]:
    """The plans an admin may choose: active, public, with monthly credits, not a trial;
    the user's own plan is listed whatever it is."""
    rows = (
        (
            await db.execute(
                select(SubscriptionPlan).order_by(
                    SubscriptionPlan.price_monthly.asc().nulls_last(), SubscriptionPlan.name.asc()
                )
            )
        )
        .scalars()
        .all()
    )
    return [
        plan
        for plan in rows
        if plan.id == current_id
        or (
            plan.is_active
            and plan.is_public
            and not plan.is_trial_plan
            and plan.credits_per_month is not None
        )
    ]


def _price(amount: Any) -> Optional[str]:
    """A list price as the dashboard shows it: "89.00"."""
    return None if amount is None else f"{amount:.2f}"


def _extension_window(subscription: UserSubscription) -> tuple[datetime, datetime]:
    """The earliest and latest end one extension may give the trial."""
    now = datetime.now(timezone.utc)
    current_end = subscription.trial_end_date
    earliest = max(as_utc(current_end), now) if current_end else now
    return earliest, now + timedelta(days=TRIAL_EXTENSION_MAX_DAYS)


async def plan_options(
    db: AsyncSession, user_id: UUID, *, protected: bool = False
) -> Dict[str, Any]:
    """What an admin sees before changing a user's plan: the plan now, whether it may be
    changed or the trial extended, and each plan and period with how it would be billed
    and the month's credits it would leave. ``protected``: the user is a Super Admin, whose
    account the two changes refuse, so nothing is offered."""
    subscription = await _current_subscription(db, user_id)
    standing = await _standing_of(db, user_id, subscription, protected)
    current = subscription.plan if subscription else None
    service = SubscriptionService(db)
    usable = standing.change_refused is None and current is not None
    # What the change checks a smaller plan against, read once for all of them.
    usage = await service.calculate_usage(user_id) if usable else {}
    plans = []
    for plan in await _offered_plans(db, current.id if current else None):
        over = _over_the_limits(service, current, plan, usage) if usable else None
        periods = []
        for period in _PERIODS:
            refused = (
                (_period_refusal(standing, current, plan, period) or over)
                if usable
                else standing.change_refused
            )
            kind = _kind(current, plan) if current is not None else UPGRADE
            periods.append(
                {
                    "billing_period": period.value,
                    "kind": kind,
                    "allowed": refused is None,
                    "refused_reason": refused,
                    "modes": [
                        {
                            "billing": mode,
                            "plan_changes": "now",
                            "monthly_credits_after": _credits_after(subscription, current, plan),
                        }
                        for mode in (_modes(standing, kind) if refused is None else [])
                    ],
                }
            )
        plans.append(
            {
                "id": plan.id,
                "name": plan.name,
                "display_name": plan.display_name,
                "price_monthly": _price(plan.price_monthly),
                "price_yearly": _price(plan.price_yearly),
                "credits_per_month": plan.credits_per_month,
                "periods": periods,
            }
        )

    extension: Dict[str, Any] = {
        "allowed": standing.extension_refused is None,
        "refused_reason": standing.extension_refused,
        "earliest_ends_at": None,
        "latest_ends_at": None,
    }
    if standing.extension_refused is None:
        earliest, latest = _extension_window(subscription)
        if earliest >= latest:
            # A trial that already runs past the limit (an older or hand-set row): no
            # later end is left to give it, and the change would refuse every one.
            extension.update({"allowed": False, "refused_reason": TRIAL_AT_ITS_LIMIT})
        else:
            extension.update({"earliest_ends_at": earliest, "latest_ends_at": latest})

    return {
        "user_id": user_id,
        "currency": CURRENCY,
        "subscription": None
        if subscription is None
        else {
            "id": subscription.id,
            "plan_id": subscription.plan_id,
            "plan_name": current.name if current else None,
            "plan_display_name": current.display_name if current else None,
            "status": subscription.status.value,
            "is_trial": _is_trial(subscription),
            "billing_period": subscription.billing_period.value
            if subscription.billing_period
            else None,
            "billed_by_provider": standing.billed_by_provider,
            "renews_at": subscription.renews_at,
            "trial_ends_at": subscription.trial_end_date,
            "monthly_credits": subscription.current_credits or 0,
            "credits_per_month": current.credits_per_month if current else None,
        },
        "change": {
            "allowed": standing.change_refused is None,
            "refused_reason": standing.change_refused,
            "default_billing": None
            if standing.change_refused is not None
            else (NEXT_RENEWAL if standing.billed_by_provider else NOT_BILLED),
        },
        "trial_extension": extension,
        "plans": plans,
        "limits": {"reason_min": REASON_MIN_LENGTH, "reason_max": REASON_MAX_LENGTH},
    }


def alert_unrecorded(
    *, user_id: UUID, admin_id: UUID, old_plan: str, new_plan: str, billing: str, failed: str
) -> None:
    """Tell a person that Lemon Squeezy took an admin's plan change and it is not recorded
    here. The plan follows Lemon Squeezy's own update; who changed it and why does not, so
    that is what the alert carries. ``failed`` says what couldn't be done."""
    trigger_payment_alert(
        alert_type="admin_plan_change_unrecorded",
        message=(
            f"An admin's plan change was accepted by Lemon Squeezy, but {failed}: the plan "
            "here follows Lemon Squeezy's update; record who changed it and why"
        ),
        severity="high",
        context={
            "admin_id": str(admin_id),
            "old_plan": old_plan,
            "new_plan": new_plan,
            "billing": billing,
        },
        user_id=str(user_id),
        operation="admin_plan_change",
    )


def _refuse(message: str, rule: str) -> BusinessRuleViolationException:
    return BusinessRuleViolationException(message=message + _NOTHING_CHANGED, rule_name=rule)


async def change_plan(
    db: AsyncSession,
    *,
    user_id: UUID,
    admin_id: UUID,
    plan_id: UUID,
    billing_period: BillingPeriod,
    billing: str,
    reason: str,
) -> Dict[str, Any]:
    """Change a user's plan as a super admin, and audit it.

    The caller checks that ``admin_id`` is a super admin and may act on the user,
    and commits. Returns the old and new plan and period, how it was billed, the
    month's credits before and after, the next renewal and the audit entry's id.

    Raises:
        RextValidationException: A reason too short or too long, a billing period
            or a billing mode this change can't have, or usage above the new
            plan's limits (the customer's own change refuses that too).
        BusinessRuleViolationException: No subscription, a trial, a failed
            payment, a cancelled or lifetime subscription, a plan that isn't
            offered, the same plan, a plan with no price at Lemon Squeezy, or
            Lemon Squeezy not accepting the change.
    """
    reason = clean_reason(reason)
    await _one_change_at_a_time(db, user_id)
    subscription = await _current_subscription(db, user_id)
    standing = await _standing_of(db, user_id, subscription)
    if standing.change_refused:
        raise _refuse(standing.change_refused, "admin_plan_standing")
    current = subscription.plan
    if billing_period not in _PERIODS:
        raise RextValidationException(
            message="Invalid billing period",
            field_errors={"billing_period": ["Monthly or yearly"]},
        )
    offered = {plan.id: plan for plan in await _offered_plans(db, current.id)}
    plan = offered.get(plan_id)
    if plan is None:
        raise RextValidationException(
            message="This plan can't be chosen",
            field_errors={"plan_id": ["Not a plan an admin can move a user to"]},
        )
    refused = _period_refusal(standing, current, plan, billing_period)
    if refused:
        raise _refuse(refused, "admin_plan_choice")
    kind = _kind(current, plan)
    modes = _modes(standing, kind)
    if billing not in modes:
        raise RextValidationException(
            message="This change can't be billed that way",
            field_errors={"billing": [f"One of {', '.join(modes)}"]},
        )

    old_period = subscription.billing_period
    credits_before = subscription.current_credits or 0
    subscription_id = subscription.id
    unrecorded = {
        "user_id": user_id,
        "admin_id": admin_id,
        "old_plan": current.name,
        "new_plan": plan.name,
        "billing": billing,
    }
    # The customer's own change, made by an admin: Lemon Squeezy first, the row after.
    service = SubscriptionService(db)
    try:
        changed = await service.upgrade(
            user_id,
            plan.id,
            billing_period,
            prorate=billing == CHARGE_NOW,
            by_admin=True,
        )
    except (BusinessRuleViolationException, RextValidationException):
        # A refusal, or an outcome upgrade() has told a person about itself.
        raise
    except Exception:
        # Past Lemon Squeezy's yes, the work here failed (the row's lock, its write, the
        # cache): the plan has changed there and nothing of it will be kept here.
        if service.provider_change_accepted:
            alert_unrecorded(**unrecorded, failed="the plan could not be written")
        raise
    credits_after = changed.current_credits or 0

    audit = await audit_logger.log_admin_plan_changed(
        admin_id=admin_id,
        user_id=user_id,
        subscription_id=subscription_id,
        old_plan_name=current.name,
        new_plan_name=plan.name,
        old_billing_period=old_period.value if old_period else None,
        new_billing_period=billing_period.value,
        billing=billing,
        credits_before=credits_before,
        credits_after=credits_after,
        reason=reason,
        metadata={"kind": kind},
        db=db,
    )
    if audit is None:
        # A plan change nobody can trace is not kept: the caller rolls back. Lemon Squeezy
        # has changed already, though, and can't be rolled back with it: its
        # subscription_updated brings the plan here in line, and a person is told, since
        # that update carries neither the admin nor the reason.
        if standing.billed_by_provider:
            alert_unrecorded(**unrecorded, failed="the audit entry could not be written")
            raise BusinessRuleViolationException(
                message=(
                    "Lemon Squeezy has changed the plan, but the change could not be recorded "
                    "here. The plan here follows when Lemon Squeezy's update arrives; the "
                    "team has been alerted."
                ),
                rule_name="admin_plan_unrecorded",
            )
        raise RuntimeError("The plan change could not be written to the audit log")

    logger.info(
        "Admin plan change: %s to %s (%s), subscription=%s",
        current.name,
        plan.name,
        billing,
        subscription_id,
    )
    return {
        "subscription_id": subscription_id,
        "old_plan": {"id": current.id, "name": current.name, "display_name": current.display_name},
        "new_plan": {"id": plan.id, "name": plan.name, "display_name": plan.display_name},
        "old_billing_period": old_period.value if old_period else None,
        "new_billing_period": billing_period.value,
        "billing": billing,
        "monthly_credits_before": credits_before,
        "monthly_credits_after": credits_after,
        "renews_at": changed.renews_at,
        "audit_id": audit.id,
    }


async def extend_trial(
    db: AsyncSession,
    *,
    user_id: UUID,
    admin_id: UUID,
    ends_at: datetime,
    reason: str,
) -> Dict[str, Any]:
    """Move a trial's end to a later date as a super admin, and audit it.

    Only a trial this app runs (no Lemon Squeezy subscription), and no further
    than TRIAL_EXTENSION_MAX_DAYS from now. The caller checks the admin and
    commits.

    Raises:
        RextValidationException: A reason too short or too long, or an end that is
            not later than the trial's own or is too far ahead.
        BusinessRuleViolationException: No subscription, not a trial, or a trial
            Lemon Squeezy runs.
    """
    reason = clean_reason(reason)
    await _one_change_at_a_time(db, user_id)
    # The subscription the options showed (an active one before a trial), then its row
    # under a lock, read again.
    subscription = await _current_subscription(db, user_id)
    if subscription is not None:
        await db.execute(
            select(UserSubscription)
            .options(selectinload(UserSubscription.plan))
            .where(UserSubscription.id == subscription.id)
            .with_for_update(of=UserSubscription)
            .execution_options(populate_existing=True)
        )
    standing = await _standing_of(db, user_id, subscription)
    if standing.extension_refused:
        raise _refuse(standing.extension_refused, "admin_trial_standing")

    ends_at = as_utc(ends_at)
    earliest, latest = _extension_window(subscription)
    if earliest >= latest:
        raise _refuse(TRIAL_AT_ITS_LIMIT, "admin_trial_extension")
    if ends_at <= earliest or ends_at > latest:
        raise RextValidationException(
            message="The new end must be later than the trial's and within the limit",
            field_errors={
                "ends_at": [
                    f"Later than the trial's end, and at most {TRIAL_EXTENSION_MAX_DAYS} "
                    "days from now"
                ]
            },
        )

    before = subscription.trial_end_date
    # A trial's row ends, and its credits' period closes, with the trial.
    for field in ("end_date", "credits_reset_date"):
        held = getattr(subscription, field)
        if held is None or before is None or as_utc(held) == as_utc(before):
            setattr(subscription, field, ends_at)
    subscription.trial_end_date = ends_at
    subscription.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await invalidate_cache(f"user:subscription_tier:{user_id}:*")

    audit = await audit_logger.log_admin_trial_extended(
        admin_id=admin_id,
        user_id=user_id,
        subscription_id=subscription.id,
        ended_at_before=before,
        ends_at=ends_at,
        reason=reason,
        db=db,
    )
    if audit is None:
        raise RuntimeError("The trial extension could not be written to the audit log")

    logger.info("Admin trial extension: subscription=%s", subscription.id)
    return {
        "subscription_id": subscription.id,
        "trial_ended_at_before": before,
        "trial_ends_at": ends_at,
        "audit_id": audit.id,
    }


# A row of the Users list for a user with no subscription that grants access.
NO_PLAN: Dict[str, Any] = {"plan_display_name": None, "is_trial": False, "billing_period": None}


async def plans_of_users(db: AsyncSession, user_ids: Iterable[UUID]) -> Dict[UUID, Dict[str, Any]]:
    """Each user's plan as the admin's Users list shows it: the name, whether it is a
    trial and the billing period, from the newest subscription that grants access.
    One query for the whole page; a user without one is left out (NO_PLAN)."""
    ids = list(user_ids)
    if not ids:
        return {}
    rows = (
        (
            await db.execute(
                select(UserSubscription)
                .options(selectinload(UserSubscription.plan))
                .where(UserSubscription.user_id.in_(ids), subscription_grants_access())
                .order_by(UserSubscription.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    plans: Dict[UUID, Dict[str, Any]] = {}
    # Ascending, so an active row and then the newest one wins, as get_subscription_by_user picks.
    for row in sorted(rows, key=lambda r: r.status == SubscriptionStatus.ACTIVE):
        plans[row.user_id] = {
            "plan_display_name": row.plan.display_name if row.plan else None,
            "is_trial": _is_trial(row),
            "billing_period": row.billing_period.value if row.billing_period else None,
        }
    return plans
