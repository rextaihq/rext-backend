"""
Credits a super admin adds to, deducts from or resets on a user's account
(FB2.28, revnix/rext-control#709).

Support's tool for compensation and corrections, outside what a plan or a
payment gives. Every change is made on the user's current subscription, under
the same row lock ``consume_credits`` takes. What is added follows the user:
when a later subscription replaces this one (a trial that subscribes), the
credits are spent from the new one (``credit_grants._spendable_by``).

- add: a grant of its own (``source = 'admin'``) with the admin's reason and,
  optionally, an expiry. Without one it lasts and is spent after the monthly
  credits; with one it is spent before them, soonest expiry first.
- deduct: from the credits admins added first, newest first (moved to
  ``forfeited``), then from the period's monthly credits, never below 0. When
  less is there than asked for, what there is is deducted and the result says so.
- reset: the period's monthly credits back to the plan's amount.

A change to the monthly credits is also kept as the period's admin adjustment
(``record_period_admin_adjustment``), so the refund rule's "credits used" stays
what the user actually used. A refund never takes back what an admin added, and
spending it is not "used". Each change is written to the audit log against the
user, with the balance before and after and the reason; without that entry the
change is not made.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.middleware.exceptions import (
    BusinessRuleViolationException,
    RextValidationException,
)
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.credit_grants import (
    ADMIN_CREDIT_MAX_AMOUNT,
    ADMIN_CREDIT_REASON_MAX_LENGTH,
    ADMIN_CREDIT_REASON_MIN_LENGTH,
    CreditGrant,
)
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    subscription_grants_access,
)
from src.api.models.user_models.users import Users
from src.services.audit_logger import AuditEventType, audit_logger
from src.services.credit_grants import (
    ADMIN_SOURCE,
    admin_credit_summary,
    as_utc,
    bonus_summary,
    live_grants,
    period_admin_adjustment,
    record_period_admin_adjustment,
)
from src.services.usage_tracking_service import replenish_if_due
from src.utils.logger import logger

ACTIONS = ("add", "deduct", "reset")
HISTORY_LIMIT = 100
# Who the customer is told made a change: never the admin's name or email.
SUPPORT_NAME = "Rext support"
# What a change may ask for, as the admin's read sends it to the dashboard's form.
ADJUSTMENT_LIMITS = {
    "amount_max": ADMIN_CREDIT_MAX_AMOUNT,
    "reason_min": ADMIN_CREDIT_REASON_MIN_LENGTH,
    "reason_max": ADMIN_CREDIT_REASON_MAX_LENGTH,
}


def clean_reason(reason: Optional[str]) -> str:
    """The reason without surrounding spaces, or a validation error."""
    reason = (reason or "").strip()
    if not ADMIN_CREDIT_REASON_MIN_LENGTH <= len(reason) <= ADMIN_CREDIT_REASON_MAX_LENGTH:
        raise RextValidationException(
            message="A reason is required",
            field_errors={
                "reason": [
                    f"Between {ADMIN_CREDIT_REASON_MIN_LENGTH} and "
                    f"{ADMIN_CREDIT_REASON_MAX_LENGTH} characters, "
                    "shown to the customer"
                ]
            },
        )
    return reason


def _check_amount(amount: Optional[int]) -> int:
    if amount is None or isinstance(amount, bool) or not 1 <= amount <= ADMIN_CREDIT_MAX_AMOUNT:
        raise RextValidationException(
            message="Invalid amount",
            field_errors={
                "amount": [f"A whole number of credits from 1 to {ADMIN_CREDIT_MAX_AMOUNT:,}"]
            },
        )
    return amount


async def _current_subscription(
    db: AsyncSession, user_id: UUID, *, lock: bool
) -> Optional[UserSubscription]:
    """The user's newest subscription that grants access, the one credits are spent from."""
    query = (
        select(UserSubscription)
        .options(selectinload(UserSubscription.plan))
        .where(and_(UserSubscription.user_id == user_id, subscription_grants_access()))
        .order_by(UserSubscription.start_date.desc())
        .limit(1)
    )
    if lock:
        # The same row lock as consume_credits: the balance and the grants change
        # under it only.
        query = query.with_for_update()
    return (await db.execute(query)).scalar_one_or_none()


async def adjust_credits(
    db: AsyncSession,
    *,
    user_id: UUID,
    admin_id: UUID,
    action: str,
    amount: Optional[int] = None,
    reason: str,
    expires_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Add, deduct or reset a user's credits as a super admin, and audit it.

    The caller checks that ``admin_id`` is a super admin and may act on the user,
    and commits. Returns what was done: the action, the credits asked for and
    applied (for a reset, the change to the monthly credits), the balance before
    and after, the monthly and added credits after, the grant made (add) and the
    audit entry's id.

    Raises:
        RextValidationException: An unknown action, a missing or out-of-range
            amount, a reason too short or too long, or an expiry that is not in
            the future or not on an add.
        BusinessRuleViolationException: The user has no subscription that grants
            access, or a reset on a plan without monthly credits (a trial).
    """
    if action not in ACTIONS:
        raise RextValidationException(
            message="Invalid action",
            field_errors={"action": [f"One of {', '.join(ACTIONS)}"]},
        )
    reason = clean_reason(reason)
    if action == "reset":
        if amount is not None:
            raise RextValidationException(
                message="A reset takes no amount",
                field_errors={"amount": ["Leave it out: a reset sets the plan's monthly credits"]},
            )
    else:
        amount = _check_amount(amount)
    now = datetime.now(timezone.utc)
    if expires_at is not None:
        if action != "add":
            raise RextValidationException(
                message="Only added credits can expire",
                field_errors={"expires_at": ["Only for an add"]},
            )
        expires_at = as_utc(expires_at)
        if expires_at <= now:
            raise RextValidationException(
                message="The expiry must be in the future",
                field_errors={"expires_at": ["Must be in the future"]},
            )

    subscription = await _current_subscription(db, user_id, lock=True)
    if subscription is None:
        raise BusinessRuleViolationException(
            message="This user has no active subscription whose credits can be changed.",
            rule_name="admin_credits_subscription",
        )
    # A period that has ended starts its new month first, as consume_credits
    # would at the next spend, so the change lands on the period it is meant for.
    replenish_if_due(subscription)

    grants = await live_grants(db, subscription.id, now, lock=True)
    monthly_before = subscription.current_credits or 0
    balance_before = monthly_before + sum(g.remaining for g in grants)
    grant: Optional[CreditGrant] = None
    details: Dict[str, Any] = {"requested_amount": amount, "monthly_before": monthly_before}

    if action == "add":
        grant = CreditGrant(
            subscription_id=subscription.id,
            source=ADMIN_SOURCE,
            promotion_id=None,
            amount=amount,
            remaining=amount,
            forfeited=0,
            reason=reason,
            granted_by=admin_id,
            expires_at=expires_at,
        )
        db.add(grant)
        applied = amount
    elif action == "deduct":
        left = amount
        # What admins added is taken back first, the newest first.
        for added in sorted(
            (g for g in grants if g.source == ADMIN_SOURCE),
            key=lambda g: g.created_at,
            reverse=True,
        ):
            step = min(added.remaining, left)
            added.remaining -= step
            added.forfeited = (added.forfeited or 0) + step
            left -= step
            if not left:
                break
        from_added = amount - left
        from_monthly = min(max(monthly_before, 0), left)
        if from_monthly:
            subscription.current_credits = monthly_before - from_monthly
            record_period_admin_adjustment(subscription, -from_monthly)
        applied = from_added + from_monthly
        details.update(
            {
                "from_added": from_added,
                "from_monthly": from_monthly,
                "shortfall": amount - applied,
            }
        )
    else:
        plan = subscription.plan
        if not can_reset(plan):
            raise BusinessRuleViolationException(
                message="This plan has no monthly credits to reset to.",
                rule_name="admin_credits_reset",
            )
        subscription.current_credits = plan.credits_per_month
        applied = plan.credits_per_month - monthly_before
        if applied:
            record_period_admin_adjustment(subscription, applied)
        details["reset_to"] = plan.credits_per_month

    await db.flush()
    grants_after = await live_grants(db, subscription.id, now)
    monthly_after = subscription.current_credits or 0
    balance_after = monthly_after + sum(g.remaining for g in grants_after)
    added_after = admin_credit_summary(grants_after)

    audit = await audit_logger.log_admin_credits_adjusted(
        admin_id=admin_id,
        user_id=user_id,
        subscription_id=subscription.id,
        action=action,
        amount=applied,
        balance_before=balance_before,
        balance_after=balance_after,
        reason=reason,
        grant_id=grant.id if grant else None,
        expires_at=expires_at,
        metadata={**details, "monthly_after": monthly_after},
        db=db,
    )
    if audit is None:
        # A credit change nobody can trace is not made: the caller rolls back.
        raise RuntimeError("The credit change could not be written to the audit log")

    logger.info(
        "Admin credits adjusted: action=%s amount=%d subscription=%s",
        action,
        applied,
        subscription.id,
    )
    return {
        "action": action,
        "requested_amount": amount,
        "amount": applied,
        "balance_before": balance_before,
        "balance_after": balance_after,
        "monthly_credits": monthly_after,
        "admin_credits": added_after["credits"] if added_after else 0,
        "subscription_id": subscription.id,
        "grant_id": grant.id if grant else None,
        "audit_id": audit.id,
    }


def can_reset(plan: Any) -> bool:
    """Whether the month's credits can be reset: the plan has some, and isn't a trial
    (a trial's credits come once and don't renew)."""
    return bool(plan is not None and not plan.is_trial_plan and (plan.credits_per_month or 0) > 0)


def _as_a_change_would_find_it(subscription: UserSubscription) -> SimpleNamespace:
    """The month's credits as a spend or an adjustment would find them now.

    Both start the new month first when its reset date has passed
    (``replenish_if_due``). A read that reported the stored numbers would show last
    month's balance and period until the first of them ran. Worked out on a copy:
    a read writes nothing.
    """
    month = SimpleNamespace(
        plan=subscription.plan,
        plan_id=subscription.plan_id,
        status=subscription.status,
        current_credits=subscription.current_credits,
        credits_reset_date=subscription.credits_reset_date,
        subscription_metadata=subscription.subscription_metadata,
    )
    replenish_if_due(month)
    return month


async def credit_breakdown(db: AsyncSession, user_id: UUID) -> Dict[str, Any]:
    """What the user can spend now: the monthly credits, a promotion's bonus and the
    credits support added."""
    subscription = await _current_subscription(db, user_id, lock=False)
    if subscription is None:
        return {
            "subscription_id": None,
            "plan_name": None,
            "current_credits": 0,
            "monthly_credits": 0,
            "credits_per_month": None,
            "credits_reset_date": None,
            "can_reset": False,
            "bonus": None,
            "added_credits": None,
            "period_adjustment": 0,
        }
    grants = await live_grants(db, subscription.id)
    month = _as_a_change_would_find_it(subscription)
    monthly = month.current_credits or 0
    plan = subscription.plan
    return {
        "subscription_id": subscription.id,
        "plan_name": plan.display_name if plan else None,
        "current_credits": monthly + sum(g.remaining for g in grants),
        "monthly_credits": monthly,
        "credits_per_month": plan.credits_per_month if plan else None,
        "credits_reset_date": month.credits_reset_date.isoformat()
        if month.credits_reset_date is not None
        else None,
        "can_reset": can_reset(plan),
        "bonus": bonus_summary(grants),
        "added_credits": admin_credit_summary(grants),
        "period_adjustment": period_admin_adjustment(month),
    }


def _as_uuid(value: Any) -> Optional[UUID]:
    """An id read back from audit metadata (stored as text), or None."""
    if not value or isinstance(value, UUID):
        return value or None
    try:
        return UUID(str(value))
    except ValueError:
        return None


async def _emails(db: AsyncSession, user_ids: Iterable[Optional[UUID]]) -> Dict[UUID, str]:
    ids = {i for i in user_ids if i}
    if not ids:
        return {}
    rows = await db.execute(select(Users.id, Users.email).where(Users.id.in_(ids)))
    return {row.id: row.email for row in rows}


async def credit_history(
    db: AsyncSession, user_id: UUID, *, for_admin: bool, limit: int = HISTORY_LIMIT
) -> Dict[str, List[Dict[str, Any]]]:
    """The credits admins added to the user (``grants``) and every admin change to
    their credits (``adjustments``, from the audit log), newest first.

    ``for_admin`` adds who made each one; the customer's own view names
    SUPPORT_NAME instead and never an admin's id or email.
    """
    grants = (
        (
            await db.execute(
                select(CreditGrant)
                .join(UserSubscription, UserSubscription.id == CreditGrant.subscription_id)
                .where(UserSubscription.user_id == user_id, CreditGrant.source == ADMIN_SOURCE)
                .order_by(CreditGrant.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    entries = (
        (
            await db.execute(
                select(AuditLog)
                .where(
                    AuditLog.user_id == user_id,
                    AuditLog.action == AuditEventType.ADMIN_CREDITS_ADJUSTED.value,
                )
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    emails = (
        await _emails(
            db,
            [g.granted_by for g in grants]
            + [_as_uuid((e.audit_metadata or {}).get("admin_id")) for e in entries],
        )
        if for_admin
        else {}
    )

    grant_rows = []
    for g in grants:
        row = {
            "id": g.id,
            "amount": g.amount,
            "remaining": g.remaining,
            "forfeited": g.forfeited or 0,
            "reason": g.reason,
            "expires_at": g.expires_at,
            "created_at": g.created_at,
        }
        if for_admin:
            row.update(
                {
                    "subscription_id": g.subscription_id,
                    "granted_by": g.granted_by,
                    "granted_by_email": emails.get(g.granted_by),
                }
            )
        else:
            row["granted_by"] = SUPPORT_NAME
        grant_rows.append(row)

    adjustment_rows = []
    for e in entries:
        meta = e.audit_metadata or {}
        row = {
            "id": e.id,
            "action": meta.get("action"),
            "amount": meta.get("amount"),
            "balance_before": meta.get("balance_before"),
            "balance_after": meta.get("balance_after"),
            "reason": meta.get("reason"),
            "expires_at": meta.get("expires_at"),
            # The grant an add made: both views list it, so the two are shown as one.
            "grant_id": meta.get("grant_id"),
            "created_at": e.created_at,
        }
        if for_admin:
            admin_id = _as_uuid(meta.get("admin_id"))
            row.update(
                {
                    "requested_amount": meta.get("requested_amount"),
                    "adjusted_by": admin_id,
                    "adjusted_by_email": emails.get(admin_id),
                }
            )
        else:
            row["adjusted_by"] = SUPPORT_NAME
        adjustment_rows.append(row)

    return {"grants": grant_rows, "adjustments": adjustment_rows}
