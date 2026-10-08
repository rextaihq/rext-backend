"""A super admin adds, deducts or resets a user's credits (FB2.28, revnix/rext-control#709).

Added credits are a grant of their own: spent after the month's credits unless they
expire, never taken back by a refund and never counted as used by the refund rule. A
deduction or a reset changes the month's credits without changing what was used.
Checked on the test PostgreSQL inside a rolled-back transaction.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.base import Base
from src.api.middleware.exceptions import BusinessRuleViolationException, RextValidationException
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.credit_grants import CreditGrant
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.promotions import Promotion
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.user_models.users import Users
from src.api.schema.subscription.admin_schemas import AdminCreditAdjustment
from src.services.admin_credits import (
    SUPPORT_NAME,
    adjust_credits,
    credit_breakdown,
    credit_history,
)
from src.services.audit_logger import audit_logger
from src.services.credit_grants import (
    change_plan_credits,
    forfeit_grants,
    grant_credits_used,
    grant_promotion_bonus,
    period_admin_adjustment,
    record_period_admin_adjustment,
)
from src.services.refund_request_service import RefundRequestService
from src.services.usage_tracking_service import UsageTrackingService
from tests.conftest import TEST_DATABASE_URL

NOW = datetime.now(timezone.utc)
PLAN_CREDITS = 1000
REASON = "Compensation for the outage"


def _with_parents(*tables):
    found = []

    def visit(table):
        if table in found:
            return
        found.append(table)
        for key in table.foreign_keys:
            visit(key.column.table)

    for table in tables:
        visit(table)
    return found


@pytest_asyncio.fixture
async def session():
    tables = _with_parents(
        UserSubscription.__table__,
        Promotion.__table__,
        CreditGrant.__table__,
        AuditLog.__table__,
    )
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()

        def tables_unless_migrated(sync):
            if not inspect(sync).has_table("alembic_version"):
                Base.metadata.create_all(sync, tables=tables, checkfirst=True)

        await connection.run_sync(tables_unless_migrated)
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


async def _user(db) -> Users:
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    db.add(user)
    await db.flush()
    return user


async def _subscription(
    db, credits=600, *, plan_credits=PLAN_CREDITS, trial=False
) -> tuple[Users, UserSubscription]:
    """A customer on a paid plan with ``credits`` of the month's credits left."""
    plan = SubscriptionPlan(
        name=f"growth-{uuid4().hex[:8]}",
        display_name="Growth",
        credits_per_month=plan_credits,
        is_trial_plan=trial,
    )
    db.add(plan)
    user = await _user(db)
    subscription = UserSubscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.TRIAL if trial else SubscriptionStatus.ACTIVE,
        start_date=NOW - timedelta(days=10),
        current_credits=credits,
        credits_reset_date=NOW + timedelta(days=20),
        subscription_metadata={},
    )
    db.add(subscription)
    await db.flush()
    return user, subscription


async def _admin_grant(db, subscription, amount, *, admin, created_at, expires_at=None):
    grant = CreditGrant(
        subscription_id=subscription.id,
        source="admin",
        amount=amount,
        remaining=amount,
        forfeited=0,
        reason=REASON,
        granted_by=admin.id,
        expires_at=expires_at,
        created_at=created_at,
    )
    db.add(grant)
    await db.flush()
    return grant


async def _promotion(db) -> Promotion:
    promotion = Promotion(
        code=f"launch-{uuid4().hex[:8]}",
        label="Launch bonus",
        credit_multiplier=2,
        starts_at=NOW - timedelta(days=1),
        ends_at=NOW + timedelta(days=6),
    )
    db.add(promotion)
    await db.flush()
    return promotion


async def _bonus(db, subscription, amount, *, expires_in=timedelta(days=5)):
    """A promotion's bonus on the subscription, as the webhook would grant it."""
    promotion = await _promotion(db)
    grant = CreditGrant(
        subscription_id=subscription.id,
        source="promotion",
        promotion_id=promotion.id,
        amount=amount,
        remaining=amount,
        forfeited=0,
        expires_at=NOW + expires_in,
    )
    db.add(grant)
    await db.flush()
    return grant


async def _adjust(db, user, admin, action, amount=None, **kwargs):
    return await adjust_credits(
        db,
        user_id=user.id,
        admin_id=admin.id,
        action=action,
        amount=amount,
        reason=kwargs.pop("reason", REASON),
        **kwargs,
    )


async def _admin_grants(db, subscription):
    return list(
        (
            await db.execute(
                select(CreditGrant)
                .where(
                    CreditGrant.subscription_id == subscription.id, CreditGrant.source == "admin"
                )
                .order_by(CreditGrant.created_at)
            )
        )
        .scalars()
        .all()
    )


def _order(user, subscription):
    """The payment the period's monthly credits came with."""
    return SimpleNamespace(
        subscription_id=subscription.id,
        user_id=user.id,
        total=8900,
        lemonsqueezy_order_id=f"order-{uuid4().hex[:8]}",
        ordered_at=NOW - timedelta(days=5),
        created_at=NOW - timedelta(days=5),
    )


async def _used(db, order) -> int:
    return (await RefundRequestService(db)._get_credit_usage_details(order))["used"]


# --- add -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_add_is_a_lasting_grant_of_its_own_with_the_reason(session):
    user, subscription = await _subscription(session)
    admin = await _user(session)

    result = await _adjust(session, user, admin, "add", 150, reason="  Outage on 6 October  ")

    [grant] = await _admin_grants(session, subscription)
    assert (grant.amount, grant.remaining, grant.forfeited) == (150, 150, 0)
    assert grant.promotion_id is None and grant.expires_at is None
    assert grant.reason == "Outage on 6 October"
    assert grant.granted_by == admin.id
    assert result["grant_id"] == grant.id
    assert (result["balance_before"], result["balance_after"]) == (600, 750)
    assert (result["amount"], result["monthly_credits"], result["admin_credits"]) == (150, 600, 150)
    assert subscription.current_credits == 600


@pytest.mark.asyncio
async def test_an_add_can_expire(session):
    user, subscription = await _subscription(session)
    admin = await _user(session)
    expires = NOW + timedelta(days=10)

    await _adjust(session, user, admin, "add", 40, expires_at=expires)

    [grant] = await _admin_grants(session, subscription)
    assert grant.expires_at == expires


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expires_at",
    [NOW - timedelta(minutes=1), (NOW - timedelta(days=1)).replace(tzinfo=None)],
)
async def test_an_add_cannot_expire_in_the_past(session, expires_at):
    user, _ = await _subscription(session)
    admin = await _user(session)

    with pytest.raises(RextValidationException):
        await _adjust(session, user, admin, "add", 40, expires_at=expires_at)


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["", "   ", "ab", " ab ", "x" * 501])
async def test_a_reason_is_required(session, reason):
    user, subscription = await _subscription(session)
    admin = await _user(session)

    with pytest.raises(RextValidationException):
        await _adjust(session, user, admin, "add", 10, reason=reason)

    assert await _admin_grants(session, subscription) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["add", "deduct"])
@pytest.mark.parametrize("amount", [None, 0, -5, 100_001, True])
async def test_an_add_or_deduct_takes_1_to_100000_credits(session, action, amount):
    user, _ = await _subscription(session)
    admin = await _user(session)

    with pytest.raises(RextValidationException):
        await _adjust(session, user, admin, action, amount)


@pytest.mark.asyncio
async def test_the_largest_add_is_100000(session):
    user, _ = await _subscription(session)
    admin = await _user(session)

    assert (await _adjust(session, user, admin, "add", 100_000))["amount"] == 100_000


@pytest.mark.asyncio
async def test_only_an_add_can_expire_and_a_reset_takes_no_amount(session):
    user, _ = await _subscription(session)
    admin = await _user(session)

    with pytest.raises(RextValidationException):
        await _adjust(session, user, admin, "deduct", 10, expires_at=NOW + timedelta(days=1))
    with pytest.raises(RextValidationException):
        await _adjust(session, user, admin, "reset", 10)
    with pytest.raises(RextValidationException):
        await _adjust(session, user, admin, "refund", 10)


@pytest.mark.asyncio
async def test_a_user_without_a_subscription_cannot_be_adjusted(session):
    user = await _user(session)
    admin = await _user(session)

    with pytest.raises(BusinessRuleViolationException):
        await _adjust(session, user, admin, "add", 10)


# --- deduct ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_deduction_takes_added_credits_first_newest_first(session):
    user, subscription = await _subscription(session)
    admin = await _user(session)
    older = await _admin_grant(
        session, subscription, 50, admin=admin, created_at=NOW - timedelta(days=2)
    )
    newer = await _admin_grant(
        session, subscription, 30, admin=admin, created_at=NOW - timedelta(days=1)
    )

    result = await _adjust(session, user, admin, "deduct", 40)

    assert (newer.remaining, newer.forfeited) == (0, 30)
    assert (older.remaining, older.forfeited) == (40, 10)
    assert subscription.current_credits == 600
    assert period_admin_adjustment(subscription) == 0
    assert (result["amount"], result["balance_before"], result["balance_after"]) == (40, 680, 640)
    assert result["admin_credits"] == 40


@pytest.mark.asyncio
async def test_a_deduction_then_takes_the_months_credits_and_records_it(session):
    user, subscription = await _subscription(session)
    admin = await _user(session)
    added = await _admin_grant(session, subscription, 30, admin=admin, created_at=NOW)

    result = await _adjust(session, user, admin, "deduct", 100)

    assert (added.remaining, added.forfeited) == (0, 30)
    assert subscription.current_credits == 530
    assert period_admin_adjustment(subscription) == -70
    assert (result["amount"], result["balance_after"]) == (100, 530)


@pytest.mark.asyncio
async def test_a_deduction_never_goes_below_zero_and_leaves_the_bonus(session):
    # 20 monthly credits and a 500-credit launch bonus; 50 asked for: the bonus
    # is not support's to take, so 20 are deducted and 30 reported missing.
    user, subscription = await _subscription(session, credits=20)
    admin = await _user(session)
    bonus = await _bonus(session, subscription, 500)

    result = await _adjust(session, user, admin, "deduct", 50)

    assert subscription.current_credits == 0
    assert bonus.remaining == 500
    assert (result["requested_amount"], result["amount"]) == (50, 20)
    assert (result["balance_before"], result["balance_after"]) == (520, 500)
    entry = await session.get(AuditLog, result["audit_id"])
    assert entry.audit_metadata["shortfall"] == 30


# --- reset -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_reset_sets_the_plans_credits_and_records_the_change(session):
    user, subscription = await _subscription(session, credits=600)
    admin = await _user(session)

    result = await _adjust(session, user, admin, "reset")

    assert subscription.current_credits == PLAN_CREDITS
    assert period_admin_adjustment(subscription) == 400
    assert (result["amount"], result["balance_before"], result["balance_after"]) == (
        400,
        600,
        1000,
    )
    # Kept for this month on this plan.
    assert subscription.subscription_metadata["admin_credit_adjustment"]["period"] == (
        f"{subscription.credits_reset_date.isoformat()}|{subscription.plan_id}"
    )


@pytest.mark.asyncio
async def test_a_deduction_and_a_reset_add_up_in_the_period(session):
    user, subscription = await _subscription(session, credits=600)
    admin = await _user(session)

    await _adjust(session, user, admin, "deduct", 100)
    await _adjust(session, user, admin, "reset")

    assert period_admin_adjustment(subscription) == -100 + 500


@pytest.mark.asyncio
@pytest.mark.parametrize(("trial", "plan_credits"), [(True, 100), (False, None)])
async def test_a_reset_is_refused_without_monthly_credits(session, trial, plan_credits):
    user, subscription = await _subscription(
        session, credits=20, trial=trial, plan_credits=plan_credits
    )
    admin = await _user(session)

    with pytest.raises(BusinessRuleViolationException):
        await _adjust(session, user, admin, "reset")
    assert subscription.current_credits == 20


@pytest.mark.asyncio
async def test_a_new_period_starts_without_the_last_ones_adjustment(session):
    user, subscription = await _subscription(session, credits=600)
    admin = await _user(session)
    await _adjust(session, user, admin, "reset")

    subscription.credits_reset_date = subscription.credits_reset_date + timedelta(days=30)

    assert period_admin_adjustment(subscription) == 0


@pytest.mark.asyncio
async def test_an_adjustment_is_read_only_on_the_plan_it_was_recorded_for(session):
    # A row whose plan is set by hand, with no plan change's credits worked out: the 300
    # deducted on the old plan is not read on the new one.
    user, subscription = await _subscription(session, credits=600)
    admin = await _user(session)
    await _adjust(session, user, admin, "deduct", 300)
    assert period_admin_adjustment(subscription) == -300

    bigger = SubscriptionPlan(
        name=f"pro-{uuid4().hex[:8]}", display_name="Pro", credits_per_month=2000
    )
    session.add(bigger)
    await session.flush()
    subscription.plan_id = bigger.id
    subscription.current_credits = 2000

    assert period_admin_adjustment(subscription) == 0
    await session.refresh(subscription, ["plan"])
    await _adjust(session, user, admin, "deduct", 50)
    assert period_admin_adjustment(subscription) == -50


# --- a plan change inside the period (F8g, rext-control #849) --------------------------


_AS_STORED = object()


async def _changed_to_a_plan_of(db, subscription, monthly, *, period_before=_AS_STORED):
    """What a plan change does to the row: the new plan's id, then the credits worked out
    from what was used (change_plan_credits, as the webhook and the dashboard call it)."""
    other = SubscriptionPlan(
        name=f"other-{uuid4().hex[:8]}", display_name="Other", credits_per_month=monthly
    )
    db.add(other)
    await db.flush()
    old_plan_id = subscription.plan_id
    old_monthly = (await db.get(SubscriptionPlan, old_plan_id)).credits_per_month
    subscription.plan_id = other.id
    change_plan_credits(
        subscription,
        old_monthly,
        monthly,
        period_before=(
            subscription.credits_reset_date if period_before is _AS_STORED else period_before
        ),
        old_plan_id=old_plan_id,
    )
    await db.flush()
    await db.refresh(subscription, ["plan"])


async def _changed_to_a_plan_of_2000(db, subscription, *, period_before=_AS_STORED):
    await _changed_to_a_plan_of(db, subscription, 2000, period_before=period_before)


@pytest.mark.asyncio
async def test_a_deduction_stands_through_a_plan_change_and_is_not_read_as_used(session):
    # 1,000 a month and 600 left: 400 used. Support deducts 300, so 300 are left. The change
    # to 2,000 a month keeps what was used and the deduction: 2,000 - 400 - 300.
    user, subscription = await _subscription(session, credits=600)
    admin = await _user(session)
    await _adjust(session, user, admin, "deduct", 300)

    await _changed_to_a_plan_of_2000(session, subscription)

    assert subscription.current_credits == 1300
    assert period_admin_adjustment(subscription) == -300
    assert await _used(session, _order(user, subscription)) == 400


@pytest.mark.asyncio
async def test_a_reset_stays_through_a_plan_change_and_what_was_spent_is_still_used(session):
    # 400 used, then support resets the month: 1,000 again. The change to 2,000 a month takes
    # nothing of the reset back, and the 400 are still what the customer used.
    user, subscription = await _subscription(session, credits=600)
    admin = await _user(session)
    await _adjust(session, user, admin, "reset")

    await _changed_to_a_plan_of_2000(session, subscription)

    assert subscription.current_credits == 2000
    assert period_admin_adjustment(subscription) == 400
    assert await _used(session, _order(user, subscription)) == 400


@pytest.mark.asyncio
async def test_the_adjustment_follows_a_plan_change_whose_period_end_moved(session):
    # Lemon Squeezy's renews_at and the stored reset date can differ by the time the change
    # arrives: the same period under another end. The deduction was recorded under the end
    # stored then, and is found by it.
    user, subscription = await _subscription(session, credits=600)
    admin = await _user(session)
    await _adjust(session, user, admin, "deduct", 300)
    stored_end = subscription.credits_reset_date
    subscription.credits_reset_date = stored_end + timedelta(hours=3)

    await _changed_to_a_plan_of_2000(session, subscription, period_before=stored_end)

    assert subscription.current_credits == 1300
    assert period_admin_adjustment(subscription) == -300


@pytest.mark.asyncio
async def test_a_plan_change_that_opens_a_new_period_carries_no_adjustment(session):
    # The period ended and nothing has refilled it yet: the change opens the next one, in
    # which nothing was used and nothing was deducted.
    user, subscription = await _subscription(session, credits=300)
    ended = NOW - timedelta(days=1)
    subscription.credits_reset_date = ended
    record_period_admin_adjustment(subscription, -300)
    assert period_admin_adjustment(subscription) == -300
    subscription.credits_reset_date = NOW + timedelta(days=29)

    await _changed_to_a_plan_of_2000(session, subscription, period_before=ended)

    assert subscription.current_credits == 2000
    assert period_admin_adjustment(subscription) == 0


@pytest.mark.asyncio
async def test_a_deduction_a_downgrade_swallows_is_not_carried(session):
    # 500 used of 1,000, then support deducts 400: 100 left. On a plan of 400 a month the
    # 500 used leave nothing with or without the deduction, so none of it is carried: the 500
    # must not read as unused (the refund rule would then take the month for untouched).
    user, subscription = await _subscription(session, credits=500)
    admin = await _user(session)
    await _adjust(session, user, admin, "deduct", 400)
    assert subscription.current_credits == 100

    await _changed_to_a_plan_of(session, subscription, 400)

    assert subscription.current_credits == 0
    assert period_admin_adjustment(subscription) == 0
    assert "admin_credit_adjustment" not in subscription.subscription_metadata
    assert await _used(session, _order(user, subscription)) == 400


@pytest.mark.asyncio
async def test_a_downgrade_carries_the_part_of_a_deduction_its_balance_still_shows(session):
    # 100 used of 1,000, then 400 deducted: 500 left. On a plan of 400 a month the 100 used
    # would leave 300; the deduction takes them, so 300 of it is still in the balance.
    user, subscription = await _subscription(session, credits=900)
    admin = await _user(session)
    await _adjust(session, user, admin, "deduct", 400)

    await _changed_to_a_plan_of(session, subscription, 400)

    assert subscription.current_credits == 0
    assert period_admin_adjustment(subscription) == -300
    assert await _used(session, _order(user, subscription)) == 100


@pytest.mark.asyncio
async def test_a_reset_then_a_downgrade_keeps_what_was_used(session):
    # 500 used of 1,000, then a reset: 1,000 again. On a plan of 400 a month the customer
    # has the whole 400, where the 500 used would have left none: all 400 are the reset's.
    user, subscription = await _subscription(session, credits=500)
    admin = await _user(session)
    await _adjust(session, user, admin, "reset")

    await _changed_to_a_plan_of(session, subscription, 400)

    assert subscription.current_credits == 400
    assert period_admin_adjustment(subscription) == 400
    assert await _used(session, _order(user, subscription)) == 400


@pytest.mark.asyncio
async def test_a_swallowed_deduction_stands_again_on_a_larger_plan(session):
    # 50 used of 1,000, then 900 deducted: 50 left. A plan of 400 a month shows 350 of the
    # deduction (0 left where 350 would be). Back on 1,000 a month the whole 900 stand again,
    # and the 50 are still all that was used.
    user, subscription = await _subscription(session, credits=950)
    admin = await _user(session)
    await _adjust(session, user, admin, "deduct", 900)

    await _changed_to_a_plan_of(session, subscription, 400)
    assert subscription.current_credits == 0
    assert period_admin_adjustment(subscription) == -350
    assert await _used(session, _order(user, subscription)) == 50

    await _changed_to_a_plan_of(session, subscription, 1000)
    assert subscription.current_credits == 50
    assert period_admin_adjustment(subscription) == -900
    assert await _used(session, _order(user, subscription)) == 50


@pytest.mark.asyncio
async def test_a_reset_after_a_swallowed_deduction_keeps_used_true_through_the_next_change(
    session,
):
    # As above, but support resets the month on the smaller plan (400 again) before the change
    # back. The reset's 400 stay with the customer; the 50 are still all that was used.
    user, subscription = await _subscription(session, credits=950)
    admin = await _user(session)
    await _adjust(session, user, admin, "deduct", 900)
    await _changed_to_a_plan_of(session, subscription, 400)
    await _adjust(session, user, admin, "reset")
    assert subscription.current_credits == 400
    assert await _used(session, _order(user, subscription)) == 50

    await _changed_to_a_plan_of(session, subscription, 1000)

    assert subscription.current_credits == 450
    assert period_admin_adjustment(subscription) == -500
    assert await _used(session, _order(user, subscription)) == 50


@pytest.mark.asyncio
async def test_an_adjustment_recorded_without_a_reset_date_follows_the_plan_change(session):
    # An old row with no reset date records its adjustment without a period. The change gives
    # the row its first reset date, and finds the adjustment by its missing one.
    user, subscription = await _subscription(session, credits=600)
    admin = await _user(session)
    subscription.credits_reset_date = None
    await session.flush()
    await _adjust(session, user, admin, "deduct", 300)
    assert period_admin_adjustment(subscription) == -300
    subscription.credits_reset_date = NOW + timedelta(days=30)

    await _changed_to_a_plan_of_2000(session, subscription, period_before=None)

    assert subscription.current_credits == 1300
    assert period_admin_adjustment(subscription) == -300


@pytest.mark.asyncio
async def test_a_plan_change_without_an_adjustment_records_none(session):
    user, subscription = await _subscription(session, credits=600)

    await _changed_to_a_plan_of_2000(session, subscription)

    assert subscription.current_credits == 1600
    assert "admin_credit_adjustment" not in subscription.subscription_metadata


# --- the subscription row is replaced ------------------------------------------------


async def _replaced_by_a_paid_plan(db, user, old) -> UserSubscription:
    """What subscription_created does at a checkout: the local trial is cancelled and a
    new row carries the paid plan."""
    old.status = SubscriptionStatus.CANCELLED
    old.end_date = NOW - timedelta(minutes=1)
    plan = SubscriptionPlan(
        name=f"growth-{uuid4().hex[:8]}", display_name="Growth", credits_per_month=PLAN_CREDITS
    )
    db.add(plan)
    await db.flush()
    new = UserSubscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        start_date=NOW,
        current_credits=PLAN_CREDITS,
        credits_reset_date=NOW + timedelta(days=30),
        subscription_metadata={},
    )
    db.add(new)
    await db.flush()
    return new


@pytest.mark.asyncio
async def test_added_credits_follow_the_user_to_the_subscription_that_replaces_theirs(session):
    user, trial = await _subscription(session, credits=60, plan_credits=60, trial=True)
    admin = await _user(session)
    await _adjust(session, user, admin, "add", 200)
    usage = UsageTrackingService(session)
    assert await usage.get_credit_balance(user.id) == 260

    paid = await _replaced_by_a_paid_plan(session, user, trial)

    # Spendable from the new row, after its month's credits, and shown as added.
    assert await usage.get_credit_balance(user.id) == PLAN_CREDITS + 200
    breakdown = await credit_breakdown(session, user.id)
    assert breakdown["subscription_id"] == paid.id
    assert (breakdown["monthly_credits"], breakdown["added_credits"]["credits"]) == (
        PLAN_CREDITS,
        200,
    )
    assert await usage.consume_credits(user.id, PLAN_CREDITS + 50) is True
    (grant,) = await _admin_grants(session, trial)
    assert (paid.current_credits, grant.remaining) == (0, 150)

    # And an admin can still take them back.
    result = await _adjust(session, user, admin, "deduct", 100)
    assert (result["amount"], result["balance_after"]) == (100, 50)
    assert (grant.remaining, grant.forfeited) == (50, 100)


@pytest.mark.asyncio
async def test_only_added_credits_follow_the_user_and_only_their_own(session):
    user, trial = await _subscription(session, credits=60, plan_credits=60, trial=True)
    admin = await _user(session)
    await _bonus(session, trial, 500)  # a promotion's bonus stays with its purchase
    other, _ = await _subscription(session)
    await _adjust(session, other, admin, "add", 999)  # someone else's added credits

    await _replaced_by_a_paid_plan(session, user, trial)

    assert await UsageTrackingService(session).get_credit_balance(user.id) == PLAN_CREDITS
    assert (await credit_breakdown(session, user.id))["added_credits"] is None


# --- spending order ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_expiring_grants_go_first_then_the_month_then_lasting_grants(session):
    user, subscription = await _subscription(session, credits=20)
    admin = await _user(session)
    bonus = await _bonus(session, subscription, 10, expires_in=timedelta(days=5))
    expiring = await _admin_grant(
        session,
        subscription,
        10,
        admin=admin,
        created_at=NOW,
        expires_at=NOW + timedelta(days=10),
    )
    oldest = await _admin_grant(
        session, subscription, 10, admin=admin, created_at=NOW - timedelta(days=2)
    )
    newest = await _admin_grant(
        session, subscription, 10, admin=admin, created_at=NOW - timedelta(days=1)
    )
    usage = UsageTrackingService(session)

    assert await usage.consume_credits(user.id, 25) is True
    assert (bonus.remaining, expiring.remaining, subscription.current_credits) == (0, 0, 15)
    assert (oldest.remaining, newest.remaining) == (10, 10)

    assert await usage.consume_credits(user.id, 20) is True
    assert (subscription.current_credits, oldest.remaining, newest.remaining) == (0, 5, 10)

    assert await usage.consume_credits(user.id, 8) is True
    assert (oldest.remaining, newest.remaining) == (0, 7)

    assert await usage.consume_credits(user.id, 8) is False
    assert newest.remaining == 7


# --- the refund rule's "credits used" ---------------------------------------------


@pytest.mark.asyncio
async def test_used_credits_stay_the_same_through_add_deduct_and_reset(session):
    # 1,000 a month and 600 left: 400 used, whatever support does to the balance.
    user, subscription = await _subscription(session, credits=600)
    admin = await _user(session)
    order = _order(user, subscription)
    assert await _used(session, order) == 400

    await _adjust(session, user, admin, "add", 100)
    assert await _used(session, order) == 400

    await _adjust(session, user, admin, "deduct", 150)  # 100 added, then 50 monthly
    assert subscription.current_credits == 550
    assert await _used(session, order) == 400

    await _adjust(session, user, admin, "reset")
    assert subscription.current_credits == PLAN_CREDITS
    assert await _used(session, order) == 400


@pytest.mark.asyncio
async def test_spending_added_credits_is_not_used(session):
    user, subscription = await _subscription(session, credits=600)
    admin = await _user(session)
    order = _order(user, subscription)
    await _adjust(session, user, admin, "add", 50, expires_at=NOW + timedelta(days=3))

    assert await UsageTrackingService(session).consume_credits(user.id, 30) is True

    assert subscription.current_credits == 600
    assert await grant_credits_used(session, subscription.id) == 0
    assert await _used(session, order) == 400


@pytest.mark.asyncio
async def test_a_partial_refund_after_a_reset_keeps_used_and_the_reset(session, monkeypatch):
    # 400 used, then reset to 1,000; a 10% refund takes 10% of the month: 900 left,
    # and reading it again (a replayed webhook) changes nothing.
    monkeypatch.setattr(
        "src.services.order_service.OrderService.is_latest_order", AsyncMock(return_value=True)
    )
    user, subscription = await _subscription(session, credits=600)
    admin = await _user(session)
    order = _order(user, subscription)
    await _adjust(session, user, admin, "reset")
    usage = UsageTrackingService(session)

    adjustment = await usage.reconcile_partial_refund_credits(
        user_id=user.id,
        lemonsqueezy_order_id=order.lemonsqueezy_order_id,
        refunded_total=890,
        original_amount=8900,
    )

    assert (adjustment["used"], adjustment["credits_after"]) == (400, 900)
    assert subscription.current_credits == 900
    assert await _used(session, order) == 400
    assert (
        await usage.reconcile_partial_refund_credits(
            user_id=user.id,
            lemonsqueezy_order_id=order.lemonsqueezy_order_id,
            refunded_total=890,
            original_amount=8900,
        )
        is None
    )
    assert subscription.current_credits == 900


@pytest.mark.asyncio
async def test_a_partial_refund_after_a_deduction_keeps_it_deducted(session, monkeypatch):
    monkeypatch.setattr(
        "src.services.order_service.OrderService.is_latest_order", AsyncMock(return_value=True)
    )
    user, subscription = await _subscription(session, credits=PLAN_CREDITS)
    admin = await _user(session)
    order = _order(user, subscription)
    await _adjust(session, user, admin, "deduct", 300)

    adjustment = await UsageTrackingService(session).reconcile_partial_refund_credits(
        user_id=user.id,
        lemonsqueezy_order_id=order.lemonsqueezy_order_id,
        refunded_total=890,
        original_amount=8900,
    )

    # 10% of the month back (900 kept), less the 300 deducted.
    assert (adjustment["used"], adjustment["credits_after"]) == (0, 600)
    assert await _used(session, order) == 0


# --- kept apart from promotions and refunds ---------------------------------------


@pytest.mark.asyncio
async def test_a_refund_forfeits_the_bonus_and_not_the_added_credits(session):
    user, subscription = await _subscription(session)
    admin = await _user(session)
    bonus = await _bonus(session, subscription, 500)
    added = await _admin_grant(session, subscription, 100, admin=admin, created_at=NOW)

    assert await forfeit_grants(session, subscription.id) == 500

    assert (bonus.remaining, bonus.forfeited) == (0, 500)
    assert (added.remaining, added.forfeited) == (100, 0)


@pytest.mark.asyncio
async def test_added_credits_do_not_stand_in_for_the_promotions_bonus(session):
    user, subscription = await _subscription(session)
    admin = await _user(session)
    await _admin_grant(session, subscription, 100, admin=admin, created_at=NOW)
    await _promotion(session)
    plan = await session.get(SubscriptionPlan, subscription.plan_id)

    granted = await grant_promotion_bonus(
        session,
        subscription.id,
        plan,
        "monthly",
        started_at=NOW,
        first_period_end=NOW + timedelta(days=30),
    )

    assert granted == PLAN_CREDITS


# --- the audit log and the history ------------------------------------------------


@pytest.mark.asyncio
async def test_every_change_is_audited_against_the_user(session):
    user, subscription = await _subscription(session)
    admin = await _user(session)

    result = await _adjust(session, user, admin, "add", 150)

    entry = await session.get(AuditLog, result["audit_id"])
    assert entry.action == "admin.credits_adjusted"
    assert entry.user_id == user.id
    assert entry.resource_id == str(subscription.id)
    meta = entry.audit_metadata
    assert meta["admin_id"] == str(admin.id)
    assert (meta["action"], meta["amount"]) == ("add", 150)
    assert (meta["balance_before"], meta["balance_after"]) == (600, 750)
    assert meta["reason"] == REASON
    assert meta["grant_id"] == str(result["grant_id"])
    assert (entry.old_values, entry.new_values) == ({"balance": 600}, {"balance": 750})


@pytest.mark.asyncio
async def test_the_reason_is_kept_in_the_audit_entry_and_out_of_the_application_log(
    session, monkeypatch
):
    # The reason is free text: it may name the customer or an incident.
    user, _ = await _subscription(session)
    admin = await _user(session)
    logged = []
    monkeypatch.setattr(
        audit_logger.logger,
        "info",
        lambda message, *args, **kwargs: logged.append((message, kwargs)),
    )

    result = await _adjust(session, user, admin, "add", 150, reason="Refund for jane@example.com")

    (line,) = [entry for entry in logged if "admin.credits_adjusted" in entry[0]]
    assert "jane@example.com" not in line[0]
    assert "jane@example.com" not in str(line[1])
    assert '"amount":150' in line[0]
    entry = await session.get(AuditLog, result["audit_id"])
    assert entry.audit_metadata["reason"] == "Refund for jane@example.com"


@pytest.mark.asyncio
async def test_no_change_is_made_without_its_audit_entry(session, monkeypatch):
    user, _ = await _subscription(session)
    admin = await _user(session)
    monkeypatch.setattr(
        "src.services.admin_credits.audit_logger.log_admin_credits_adjusted",
        AsyncMock(return_value=None),
    )

    with pytest.raises(RuntimeError):
        await _adjust(session, user, admin, "add", 150)


@pytest.mark.asyncio
async def test_the_customers_history_names_rext_support_and_never_the_admin(session):
    user, subscription = await _subscription(session)
    admin = await _user(session)
    await _adjust(session, user, admin, "add", 150, reason="Outage on 6 October")
    await _adjust(session, user, admin, "deduct", 20, reason="Added twice by mistake")

    history = await credit_history(session, user.id, for_admin=False)

    [grant] = history["grants"]
    assert (grant["amount"], grant["remaining"], grant["forfeited"]) == (150, 130, 20)
    assert grant["reason"] == "Outage on 6 October"
    assert grant["granted_by"] == SUPPORT_NAME
    assert [a["action"] for a in history["adjustments"]] == ["deduct", "add"]
    assert history["adjustments"][0]["reason"] == "Added twice by mistake"
    assert all(a["adjusted_by"] == SUPPORT_NAME for a in history["adjustments"])
    # An add names the grant it made, so the two are shown as one change.
    assert [a["grant_id"] for a in history["adjustments"]] == [None, str(grant["id"])]
    assert str(admin.id) not in repr(history) and admin.email not in repr(history)


@pytest.mark.asyncio
async def test_the_admins_history_names_who_made_each_change(session):
    user, subscription = await _subscription(session)
    admin = await _user(session)
    result = await _adjust(session, user, admin, "add", 150)

    history = await credit_history(session, user.id, for_admin=True)

    [grant] = history["grants"]
    assert (grant["granted_by"], grant["granted_by_email"]) == (admin.id, admin.email)
    assert grant["subscription_id"] == subscription.id
    [entry] = history["adjustments"]
    assert (entry["adjusted_by"], entry["adjusted_by_email"]) == (admin.id, admin.email)
    assert entry["grant_id"] == str(result["grant_id"])
    assert (entry["balance_before"], entry["balance_after"]) == (600, 750)


# --- the request body ---------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"action": "add", "reason": REASON},  # no amount
        {"action": "deduct", "reason": REASON},
        {"action": "reset", "amount": 10, "reason": REASON},
        {"action": "deduct", "amount": 10, "reason": REASON, "expires_at": "2030-01-01T00:00:00Z"},
        {"action": "add", "amount": 0, "reason": REASON},
        {"action": "add", "amount": 100_001, "reason": REASON},
        {"action": "add", "amount": 10, "reason": "  ab  "},
        {"action": "add", "amount": 10},
        {"action": "refund", "amount": 10, "reason": REASON},
        # Not a whole number in the JSON: true would otherwise be read as 1 credit.
        {"action": "add", "amount": True, "reason": REASON},
        {"action": "deduct", "amount": "5", "reason": REASON},
        {"action": "add", "amount": 5.0, "reason": REASON},
    ],
)
def test_the_body_refuses_what_the_action_does_not_take(body):
    with pytest.raises(ValidationError):
        AdminCreditAdjustment(**body)


def test_the_body_takes_each_action():
    add = AdminCreditAdjustment(
        action="add", amount=10, reason="  why  ", expires_at="2030-01-01T00:00:00Z"
    )
    assert add.reason == "why" and add.expires_at.year == 2030
    assert AdminCreditAdjustment(action="deduct", amount=5, reason=REASON).amount == 5
    assert AdminCreditAdjustment(action="reset", reason=REASON).amount is None
