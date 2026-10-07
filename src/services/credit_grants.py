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
from src.api.models.subscription_models.subscriptions import UserSubscription
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


async def live_grants(
    db: AsyncSession, subscription_id: UUID, now: Optional[datetime] = None
) -> list[CreditGrant]:
    """The subscription's grants with credits left and not expired: those with an
    expiry, soonest first, then those without, oldest first (``split_cost``'s order
    around the monthly credits).

    Callers that spend lock the subscription row first (``consume_credits``),
    which serialises every change to its grants.
    """
    now = now or datetime.now(timezone.utc)
    result = await db.execute(
        select(CreditGrant)
        .where(CreditGrant.subscription_id == subscription_id, _usable(now))
        .order_by(CreditGrant.expires_at.asc().nulls_last(), CreditGrant.created_at.asc())
    )
    return list(result.scalars().all())


async def grant_balance(
    db: AsyncSession, subscription_id: UUID, now: Optional[datetime] = None
) -> int:
    """Credits left in the subscription's unexpired grants."""
    now = now or datetime.now(timezone.utc)
    result = await db.execute(
        select(func.coalesce(func.sum(CreditGrant.remaining), 0)).where(
            CreditGrant.subscription_id == subscription_id, _usable(now)
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
