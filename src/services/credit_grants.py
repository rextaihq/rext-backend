"""
Credit grants: credits on top of a subscription's monthly credits.

A grant is a promotion's bonus (the launch offer: double credits for the first
month of a plan started in launch week) or credits a super admin added
(src/services/admin_credits.py). Promotions are data (the ``promotions`` table);
the Lemon Squeezy webhook reads the one that applies when a subscription is
created and grants its bonus once. Every spend takes grants with an expiry
first, soonest expiry first, then the monthly credits, then grants without an
expiry, oldest first; a grant is no longer counted once it expires. Spending
goes through ``UsageTrackingService.consume_credits``, which
``src/utils/credit_manager.py`` calls; this module only gives, reads and splits.

Admin grants are kept apart from the purchase: a refund forfeits only promotion
grants, and only promotion grants count as credits used for the refund rule.
They also follow the user, not the subscription row they were added on
(``_spendable_by``): a checkout or a new start replaces that row, and what
support gave must not stay behind on the old one.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.subscription_models.credit_grants import CreditGrant
from src.api.models.subscription_models.promotions import Promotion
from src.api.models.subscription_models.refunds import Refund, RefundStatus
from src.api.models.subscription_models.subscriptions import (
    FAILED_PAYMENT_STATUSES,
    UserSubscription,
)
from src.utils.datetime_utils import add_months
from src.utils.logger import logger

PROMOTION_SOURCE = "promotion"
ADMIN_SOURCE = "admin"


def as_utc(value: datetime) -> datetime:
    """The same instant as an aware UTC datetime (the provider's dates are naive UTC)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def promotion_applies(
    promotion: Any, started_at: datetime, plan_name: Optional[str], billing_period: Optional[str]
) -> bool:
    """Whether a subscription started at ``started_at`` on this plan and period qualifies."""
    started_at = as_utc(started_at)
    return (
        bool(promotion.is_active)
        and as_utc(promotion.starts_at) <= started_at < as_utc(promotion.ends_at)
        and (not promotion.plan_names or plan_name in promotion.plan_names)
        and (not promotion.billing_periods or billing_period in promotion.billing_periods)
    )


@dataclass(frozen=True)
class Bonus:
    amount: int
    expires_at: datetime


def promotion_bonus(
    promotion: Any,
    monthly_credits: Optional[int],
    paid_from: datetime,
    first_period_end: Optional[datetime],
) -> Optional[Bonus]:
    """The bonus a promotion gives a plan, or None when there is nothing to give.

    A multiplier of 2 doubles the first month: the bonus is one month's credits
    on top. A fixed bonus is that many credits. Either expires at the end of the
    first paid period, and never later than a month after the paid period began
    (a yearly plan's period is a year; its first month is what the offer covers).
    ``paid_from`` is when the paid period began, which for a trial that converts
    is later than the subscription's start.
    """
    if promotion.credit_multiplier:
        if not monthly_credits or monthly_credits <= 0 or promotion.credit_multiplier <= 1:
            return None
        amount = monthly_credits * (promotion.credit_multiplier - 1)
    elif promotion.bonus_credits and promotion.bonus_credits > 0:
        amount = promotion.bonus_credits
    else:
        return None
    paid_from = as_utc(paid_from)
    month_end = add_months(paid_from, 1)
    expires_at = month_end if first_period_end is None else min(as_utc(first_period_end), month_end)
    return Bonus(amount=amount, expires_at=expires_at)


# The credits used in the billing period at its last plan change and the balance left then,
# kept in the subscription's metadata with the period's end (its credits_reset_date).
_PLAN_CHANGE = "plan_change_credits"


def change_plan_credits(
    subscription: UserSubscription,
    old_monthly: Optional[int],
    new_monthly: int,
    period_before: Optional[datetime] = None,
    old_plan_id: Optional[UUID] = None,
) -> None:
    """Set the balance for a plan change within a billing period (F8a, the founder's rule,
    2026-10-07): the new plan's monthly credits minus the credits already used this period,
    never below 0. Call it once the subscription's credits_reset_date is the period's end.

    What was used is the old plan's monthly credits minus what is left. After an earlier change
    in the same period it is what was used then plus what was spent since, so switching down to
    a smaller plan and back gives nothing back. With the old plan's credits unknown, nothing
    counts as used. Grants (an offer's bonus) are apart and stay.

    The period's end can come from Lemon Squeezy's renews_at or from the stored reset date, so
    a change is in the earlier change's period when that period is the end it found
    (`period_before`, before the change moved it) or the end it leaves.

    A period that had ended is refilled lazily, by the next spend or the renewal's invoice
    (UsageTrackingService.consume_credits, not while a payment has failed). When neither has
    come yet the balance is still last period's: the change opens the new period, in which
    nothing was used, and an earlier change in the ended period doesn't count.

    What a super admin deducted from the month, or reset, stands through the change: the
    balance carries it as it carries what was used, so switching plans undoes no deduction and
    takes back no reset. That adjustment is recorded for the plan it was made on (it is not
    usage, and the readings of "credits used" add it back), so with `old_plan_id` the record
    moves to the new plan with the balance, as much of it as the new balance still shows
    (_carry_admin_adjustment). Call this once the subscription's plan_id is the new plan's. A
    change that opens a new period carries none.
    """

    def key(moment: Optional[datetime]) -> Optional[str]:
        return as_utc(moment).isoformat() if moment else None

    period = key(subscription.credits_reset_date)
    left = subscription.current_credits or 0
    # The period's ends, as they were found, before a period that had ended is put aside.
    ends_found = (period, key(period_before))
    opens_a_period = (
        period_before is not None
        and as_utc(period_before) <= datetime.now(timezone.utc)
        and subscription.status not in FAILED_PAYMENT_STATUSES
        and old_monthly is not None
    )
    if opens_a_period:
        left, period_before = old_monthly, None
    earlier = (subscription.subscription_metadata or {}).get(_PLAN_CHANGE) or {}
    if earlier.get("period") and earlier.get("period") in (period, key(period_before)):
        used = max(0, earlier["used"] + earlier["left"] - left)
    elif old_monthly is not None:
        used = max(0, old_monthly - left)
    else:
        used = 0
    subscription.current_credits = max(0, new_monthly - used)
    # Reassigned, not mutated in place: SQLAlchemy doesn't track a plain JSONB's insides.
    subscription.subscription_metadata = {
        **(subscription.subscription_metadata or {}),
        _PLAN_CHANGE: {"period": period, "used": used, "left": subscription.current_credits},
    }
    if old_plan_id is not None and not opens_a_period:
        _carry_admin_adjustment(subscription, old_plan_id, ends_found, used, new_monthly)


def split_cost(
    cost: int, expiring: Sequence[int], monthly: int, lasting: Sequence[int]
) -> Optional[tuple[list[int], int, list[int]]]:
    """How a cost is taken: from each grant with an expiry in order (soonest
    first), then from the monthly credits, then from each grant without an
    expiry in order (oldest first). Credits that expire go first, so none is
    lost while lasting ones are spent.

    Returns the amount taken from each expiring grant, from the monthly credits
    and from each lasting grant, or None when everything together is not enough.
    """
    monthly = max(monthly, 0)
    if cost < 0 or cost > sum(expiring) + monthly + sum(lasting):
        return None
    left = cost

    def take(remaining: int) -> int:
        nonlocal left
        step = min(remaining, left)
        left -= step
        return step

    from_expiring = [take(remaining) for remaining in expiring]
    from_monthly = take(monthly)
    from_lasting = [take(remaining) for remaining in lasting]
    return from_expiring, from_monthly, from_lasting


def _usable(now: datetime):
    return and_(
        CreditGrant.remaining > 0,
        or_(CreditGrant.expires_at.is_(None), CreditGrant.expires_at > now),
    )


def _spendable_by(subscription_id: UUID):
    """The grants a subscription spends: its own, and the credits an admin added on
    any of the same user's subscriptions.

    A promotion's bonus belongs to the purchase that earned it, so it stays with
    its subscription. Credits support added belong to the user: subscription_created
    replaces the row (a trial that subscribes, a new start after a cancellation),
    and they are still there to spend from the new one.
    """
    owner = (
        select(UserSubscription.user_id)
        .where(UserSubscription.id == subscription_id)
        .scalar_subquery()
    )
    return or_(
        CreditGrant.subscription_id == subscription_id,
        and_(
            CreditGrant.source == ADMIN_SOURCE,
            CreditGrant.subscription_id.in_(
                select(UserSubscription.id).where(UserSubscription.user_id == owner)
            ),
        ),
    )


async def live_grants(
    db: AsyncSession,
    subscription_id: UUID,
    now: Optional[datetime] = None,
    *,
    lock: bool = False,
) -> list[CreditGrant]:
    """The grants the subscription spends (``_spendable_by``) with credits left and
    not expired: those with an expiry, soonest first, then those without, oldest
    first (``split_cost``'s order around the monthly credits).

    Callers that change them lock the subscription row first (``consume_credits``)
    and pass ``lock``: an admin's grant can be reached from two of the user's
    subscription rows while one replaces the other, so the grant rows are locked
    too and read as they are once the lock is held.
    """
    now = now or datetime.now(timezone.utc)
    query = (
        select(CreditGrant)
        .where(_spendable_by(subscription_id), _usable(now))
        .order_by(CreditGrant.expires_at.asc().nulls_last(), CreditGrant.created_at.asc())
    )
    if lock:
        query = query.with_for_update(of=CreditGrant)
    result = await db.execute(query)
    return list(result.scalars().all())


async def grant_balance(
    db: AsyncSession, subscription_id: UUID, now: Optional[datetime] = None
) -> int:
    """Credits left in the unexpired grants the subscription spends."""
    now = now or datetime.now(timezone.utc)
    result = await db.execute(
        select(func.coalesce(func.sum(CreditGrant.remaining), 0)).where(
            _spendable_by(subscription_id), _usable(now)
        )
    )
    return int(result.scalar_one())


async def grant_credits_used(
    db: AsyncSession,
    subscription_id: UUID,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    order_id: Optional[str] = None,
) -> int:
    """Credits spent from the subscription's promotion grants (forfeited credits are
    not spent).

    For a refund, the grants that order earned (``order_id``) count; for a grant
    without a recorded order, ``since`` and ``until`` bound the order's period
    instead (valid at the order's date, made by ``until``). Credits an admin
    added came with no purchase, so spending them is not counted.
    """
    spent = CreditGrant.amount - CreditGrant.remaining - CreditGrant.forfeited
    query = select(func.coalesce(func.sum(spent), 0)).where(
        CreditGrant.subscription_id == subscription_id,
        CreditGrant.source == PROMOTION_SOURCE,
    )
    if order_id:
        return int(
            (
                await db.execute(query.where(CreditGrant.lemonsqueezy_order_id == str(order_id)))
            ).scalar_one()
        ) + int(
            (
                await db.execute(
                    _period_bound(
                        query.where(CreditGrant.lemonsqueezy_order_id.is_(None)), since, until
                    )
                )
            ).scalar_one()
        )
    result = await db.execute(_period_bound(query, since, until))
    return int(result.scalar_one())


def _period_bound(query, since: Optional[datetime], until: Optional[datetime]):
    if since is not None:
        query = query.where(
            or_(CreditGrant.expires_at.is_(None), CreditGrant.expires_at > as_utc(since))
        )
    if until is not None:
        query = query.where(CreditGrant.created_at <= as_utc(until))
    return query


async def order_refunded(db: AsyncSession, order_id: str) -> bool:
    """Whether money was returned on a Lemon Squeezy order, even partly (a failed
    refund returned none, as RefundService counts it)."""
    return bool(
        await db.scalar(
            select(
                exists().where(
                    Refund.lemonsqueezy_order_id == str(order_id),
                    Refund.status != RefundStatus.FAILED,
                )
            )
        )
    )


async def forfeit_grants(
    db: AsyncSession,
    subscription_id: UUID,
    now: Optional[datetime] = None,
    order_id: Optional[str] = None,
) -> int:
    """Zero the subscription's live promotion grants and return the credits forfeited.

    A refund forfeits an unspent promotional bonus: the bonus came with the
    purchase, so money returned on it takes the bonus back. Credits an admin
    added (support's compensation) are not part of the purchase and stay.
    Forfeited credits are kept apart from spent ones. The caller holds the
    subscription's row lock, as ``consume_credits`` does. Safe to call again
    (nothing is left the second time).
    """
    grants = [
        g
        for g in await live_grants(db, subscription_id, now)
        if g.source == PROMOTION_SOURCE
        # The refunded order's grants, and any whose order was not recorded.
        and (not order_id or g.lemonsqueezy_order_id in (None, str(order_id)))
    ]
    forfeited = sum(g.remaining for g in grants)
    for grant in grants:
        grant.forfeited = (grant.forfeited or 0) + grant.remaining
        grant.remaining = 0
    if grants:
        await db.flush()
    return forfeited


async def grant_promotion_bonus(
    db: AsyncSession,
    subscription_id: UUID,
    plan: Any,
    billing_period: Optional[str],
    started_at: Optional[datetime],
    first_period_end: Optional[datetime],
    paid_from: Optional[datetime] = None,
    order_id: Optional[str] = None,
) -> Optional[int]:
    """Give a promotion's bonus to a subscription started inside its window.

    Called by the Lemon Squeezy webhook handlers for a paid subscription.
    ``started_at`` (the subscription's start) decides the window; the bonus runs
    from ``paid_from`` (when the paid period began; the start if not given). A
    subscription gets one promotional bonus: the subscription row is locked and a
    subscription that already has a promotion grant gets nothing, so a repeated or
    second event grants nothing even when a capped promotion has since filled up
    (credits an admin added do not count: they are no bonus). A
    capped promotion is locked while its grants are counted. ``order_id`` (the
    Lemon Squeezy order that started the subscription) is kept on the grant; no
    grant is made for an order already refunded, even partly (a failed refund
    does not count). Returns the credits
    granted by this call, or None.
    """
    if started_at is None or plan is None or plan.is_trial_plan:
        return None
    await db.execute(
        select(UserSubscription.id).where(UserSubscription.id == subscription_id).with_for_update()
    )
    if await db.scalar(
        select(
            exists().where(
                CreditGrant.subscription_id == subscription_id,
                CreditGrant.source == PROMOTION_SOURCE,
            )
        )
    ):
        return None
    if order_id and await order_refunded(db, order_id):
        logger.info("No promotion bonus for refunded order %s", order_id)
        return None
    candidates = (
        (
            await db.execute(
                select(Promotion)
                .where(
                    Promotion.is_active.is_(True),
                    Promotion.starts_at <= as_utc(started_at),
                    Promotion.ends_at > as_utc(started_at),
                )
                .order_by(Promotion.starts_at.desc())
            )
        )
        .scalars()
        .all()
    )
    # The newest qualifying promotion with redemptions left; a capped one is
    # locked while its grants are counted.
    promotion = bonus = None
    for candidate in candidates:
        if not promotion_applies(candidate, started_at, plan.name, billing_period):
            continue
        candidate_bonus = promotion_bonus(
            candidate, plan.credits_per_month, paid_from or started_at, first_period_end
        )
        if candidate_bonus is None:
            continue
        if candidate.max_redemptions:
            await db.execute(
                select(Promotion.id).where(Promotion.id == candidate.id).with_for_update()
            )
            redeemed = await db.scalar(
                select(func.count())
                .select_from(CreditGrant)
                .where(CreditGrant.promotion_id == candidate.id)
            )
            if redeemed >= candidate.max_redemptions:
                logger.info("Promotion %s is fully redeemed", candidate.code)
                continue
        promotion, bonus = candidate, candidate_bonus
        break
    if promotion is None:
        return None
    result = await db.execute(
        insert(CreditGrant)
        .values(
            subscription_id=subscription_id,
            source=PROMOTION_SOURCE,
            promotion_id=promotion.id,
            lemonsqueezy_order_id=str(order_id) if order_id else None,
            amount=bonus.amount,
            remaining=bonus.amount,
            expires_at=bonus.expires_at,
        )
        .on_conflict_do_nothing(constraint="uq_credit_grants_subscription_promotion")
        .returning(CreditGrant.id)
    )
    if result.scalar_one_or_none() is None:
        return None
    logger.info(
        "Promotion bonus granted: promotion=%s credits=%d expires_at=%s subscription=%s",
        promotion.code,
        bonus.amount,
        bonus.expires_at.isoformat(),
        subscription_id,
    )
    return bonus.amount


def bonus_summary(grants: Sequence[CreditGrant]) -> Optional[Dict[str, Any]]:
    """What the dashboard shows for the live promotion grants: "Launch bonus: +1,000
    credits until ...". Admin grants are left out (``admin_credit_summary``)."""
    grants = [g for g in grants if g.source == PROMOTION_SOURCE]
    if not grants:
        return None
    first = grants[0]
    expiries = [as_utc(g.expires_at) for g in grants if g.expires_at is not None]
    return {
        "label": first.promotion.label if first.promotion else "Bonus credits",
        "promotion": first.promotion.code if first.promotion else None,
        "credits": sum(g.remaining for g in grants),
        "granted": sum(g.amount for g in grants),
        "expires_at": min(expiries).isoformat() if expiries else None,
    }


def admin_credit_summary(grants: Sequence[CreditGrant]) -> Optional[Dict[str, Any]]:
    """The live admin grants among ``grants``: the credits left, the credits added
    and the soonest expiry (None when none expires), or None when there are none."""
    grants = [g for g in grants if g.source == ADMIN_SOURCE]
    if not grants:
        return None
    expiries = [as_utc(g.expires_at) for g in grants if g.expires_at is not None]
    return {
        "credits": sum(g.remaining for g in grants),
        "granted": sum(g.amount for g in grants),
        "expires_at": min(expiries).isoformat() if expiries else None,
    }


# --- an admin's changes to the period's monthly credits ----------------------
#
# "Credits used this period" is never stored: it is read as granted - balance -
# (credits a refund cut). An admin who deducts from or resets the monthly
# credits changes the balance without any credit being used, so the sum of
# those changes is kept on the subscription for the period it was made in, and
# the readings add it back (refund_request_service, reconcile_partial_refund_credits).

ADMIN_CREDIT_ADJUSTMENT = "admin_credit_adjustment"


def _period_key(subscription: Any) -> Optional[str]:
    """The period an adjustment belongs to: the month, on the plan it was made on.

    The plan is part of the key: an adjustment is read only on the plan it was
    recorded for. A plan change inside the month keeps the reset date and what
    was used, and moves the record to the new plan itself (change_plan_credits);
    a row whose plan is set any other way starts without it.
    """
    reset_date = subscription.credits_reset_date
    if reset_date is None:
        return None
    return f"{as_utc(reset_date).isoformat()}|{getattr(subscription, 'plan_id', None)}"


def period_admin_adjustment(subscription: Any) -> int:
    """What admins changed the period's monthly credits by (negative for a deduction),
    or 0 when the recorded change belongs to an earlier period."""
    recorded = (subscription.subscription_metadata or {}).get(ADMIN_CREDIT_ADJUSTMENT)
    if not recorded or recorded.get("period") != _period_key(subscription):
        return 0
    return int(recorded.get("delta") or 0)


def record_period_admin_adjustment(subscription: Any, delta: int) -> None:
    """Add ``delta`` to the period's admin adjustment; a new period starts from 0.

    The metadata is reassigned rather than mutated: SQLAlchemy does not track
    in-place changes to a plain JSONB column.
    """
    meta = {**(subscription.subscription_metadata or {})}
    meta[ADMIN_CREDIT_ADJUSTMENT] = {
        "period": _period_key(subscription),
        "delta": period_admin_adjustment(subscription) + delta,
    }
    subscription.subscription_metadata = meta


def _carry_admin_adjustment(
    subscription: Any,
    old_plan_id: UUID,
    period_ends: Sequence[Optional[str]],
    used: int,
    new_monthly: int,
) -> None:
    """Move the period's admin adjustment from the old plan's key to the plan the
    subscription is on now (change_plan_credits).

    ``period_ends`` are the ends the period was found under, as ISO strings: Lemon Squeezy's
    renews_at and the stored reset date can differ by the time a change arrives. A row that
    had no reset date recorded its adjustment without a period, and is found by that.

    What moves is what the admin's change still adds to or takes from the balance on the new
    plan: the balance as it is now, against what it would be had the admin changed nothing.
    ``used`` is what the change counted as used, the admin's change included, so the credits
    really used are ``used`` plus the recorded change. On most changes that is the recorded
    change whole. On a downgrade whose balance stops at 0 it is less: a deduction the smaller
    plan has swallowed is no longer in the balance, and carried whole it would make credits
    that were used read as unused.
    """
    meta = {**(subscription.subscription_metadata or {})}
    recorded = meta.get(ADMIN_CREDIT_ADJUSTMENT)
    if not recorded or not recorded.get("delta"):
        return
    old_keys = {f"{end}|{old_plan_id}" if end else None for end in period_ends}
    if recorded.get("period") not in old_keys:
        return
    without = max(0, new_monthly - max(0, used + int(recorded["delta"])))
    carried = (subscription.current_credits or 0) - without
    if carried:
        meta[ADMIN_CREDIT_ADJUSTMENT] = {"period": _period_key(subscription), "delta": carried}
    else:
        meta.pop(ADMIN_CREDIT_ADJUSTMENT)
    subscription.subscription_metadata = meta


async def active_promotion(db: AsyncSession, now: Optional[datetime] = None) -> Optional[Promotion]:
    """The promotion a subscription started now would receive (for GET /api/v1/plans):
    one for every plan and period, inside its window, with redemptions left."""
    now = now or datetime.now(timezone.utc)
    redeemed = (
        select(func.count())
        .select_from(CreditGrant)
        .where(CreditGrant.promotion_id == Promotion.id)
        .scalar_subquery()
    )
    return await db.scalar(
        select(Promotion)
        .where(
            Promotion.is_active.is_(True),
            Promotion.starts_at <= now,
            Promotion.ends_at > now,
            Promotion.plan_names.is_(None),
            Promotion.billing_periods.is_(None),
            # A promotion whose redemptions are used up is no longer offered.
            or_(Promotion.max_redemptions.is_(None), redeemed < Promotion.max_redemptions),
        )
        .order_by(Promotion.starts_at.desc())
        .limit(1)
    )
