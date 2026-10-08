"""A super admin changes a user's plan or extends a trial (FB2.29, revnix/rext-control#710).

The change is the customer's own (SubscriptionService.upgrade) made by an admin: Lemon
Squeezy first, the row only once it agreed, the balance by the plan-change rule, and an
audit entry with the admin and the reason. Checked on the test PostgreSQL inside a
rolled-back transaction, with Lemon Squeezy and the cache stubbed.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import event, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.services.admin_plan_changes as module
import src.services.subscription_service as subscription_service_module
from src.api.database.base import Base
from src.api.middleware.exceptions import BusinessRuleViolationException, RextValidationException
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
    subscription_grants_access,
)
from src.api.models.user_models.users import Users
from src.providers.payment.base_provider import PaymentChangeUnconfirmed
from src.providers.payment.providers.lemonsqueezy import LemonSqueezyAPIError
from src.services.audit_logger import audit_logger
from src.services.subscription_service import SubscriptionService
from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.asyncio

NOW = datetime.now(timezone.utc)
REASON = "Moved up as agreed on the call"
MONTHLY, YEARLY = BillingPeriod.MONTHLY, BillingPeriod.YEARLY


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
    tables = _with_parents(UserSubscription.__table__, AuditLog.__table__)
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


@pytest.fixture
def lemon(monkeypatch):
    """Lemon Squeezy, the cache and the usage count, outside the database."""
    # Lemon Squeezy answers with the subscription as it is afterwards: on the new variant.
    provider = MagicMock(
        update_subscription=AsyncMock(
            side_effect=lambda **sent: SimpleNamespace(plan_id=sent["price_id"])
        )
    )
    monkeypatch.setattr(
        subscription_service_module, "get_payment_provider_singleton", lambda: provider
    )
    monkeypatch.setattr(module, "trigger_payment_alert", MagicMock())
    monkeypatch.setattr(subscription_service_module, "trigger_payment_alert", MagicMock())
    monkeypatch.setattr(subscription_service_module, "invalidate_cache", AsyncMock(return_value=0))
    monkeypatch.setattr(module, "invalidate_cache", AsyncMock(return_value=0))
    monkeypatch.setattr(
        SubscriptionService,
        "calculate_usage",
        AsyncMock(return_value={"workspaces": 0, "members": 0}),
    )
    return provider


async def _plan(db, name, *, price, credits, trial=False, variants=True, active=True, public=True):
    tag = uuid4().hex[:8]
    plan = SubscriptionPlan(
        name=f"{name}-{tag}",
        display_name=name.title(),
        price_monthly=Decimal(price),
        price_yearly=Decimal(price) * 10,
        credits_per_month=credits,
        is_trial_plan=trial,
        is_active=active,
        is_public=public,
        lemonsqueezy_variant_id_monthly=f"v-{name}-m-{tag}" if variants else None,
        lemonsqueezy_variant_id_yearly=f"v-{name}-y-{tag}" if variants else None,
    )
    db.add(plan)
    await db.flush()
    return plan


async def _user(db) -> Users:
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    db.add(user)
    await db.flush()
    return user


async def _subscribed(
    db,
    plan,
    *,
    left,
    billed=True,
    status=SubscriptionStatus.ACTIVE,
    period=MONTHLY,
    user=None,
    **fields,
) -> tuple[Users, UserSubscription]:
    """A customer on `plan` with `left` of the month's credits, in a period ending in 20 days."""
    user = user or await _user(db)
    row = UserSubscription(
        **{
            "user_id": user.id,
            "plan_id": plan.id,
            "status": status,
            "billing_period": period,
            "lemonsqueezy_subscription_id": f"ls-{uuid4().hex[:8]}" if billed else None,
            "start_date": NOW - timedelta(days=10),
            "renews_at": NOW + timedelta(days=20),
            "credits_reset_date": NOW + timedelta(days=20),
            "current_credits": left,
            "subscription_metadata": {"start_month_given": True},
            **fields,
        }
    )
    db.add(row)
    await db.flush()
    return user, row


async def _world(db):
    """Starter (400 a month), Growth (1,000) and Pro (2,500), as the plans table would hold."""
    starter = await _plan(db, "starter", price=39, credits=400)
    growth = await _plan(db, "growth", price=89, credits=1000)
    pro = await _plan(db, "pro", price=189, credits=2500)
    return starter, growth, pro


async def _change(db, user, admin, plan, billing="next_renewal", period=MONTHLY, reason=REASON):
    return await module.change_plan(
        db,
        user_id=user.id,
        admin_id=admin.id,
        plan_id=plan.id,
        billing_period=period,
        billing=billing,
        reason=reason,
    )


def _fields(refused) -> set[str]:
    """The fields a validation refusal names."""
    return {detail["field"] for detail in refused.value.details}


async def _audit(db, user) -> list[AuditLog]:
    return list(
        (
            await db.execute(
                select(AuditLog)
                .where(AuditLog.user_id == user.id)
                .order_by(AuditLog.created_at.asc())
            )
        )
        .scalars()
        .all()
    )


# --- the change ------------------------------------------------------------------------


async def test_an_upgrade_is_billed_from_the_next_renewal_unless_the_admin_says_now(session, lemon):
    starter, growth, _ = await _world(session)
    user, row = await _subscribed(session, starter, left=100)  # 300 of 400 used
    admin = await _user(session)

    result = await _change(session, user, admin, growth)

    # Lemon Squeezy takes the new variant with no proration: nothing charged now.
    lemon.update_subscription.assert_awaited_once_with(
        subscription_id=row.lemonsqueezy_subscription_id,
        price_id=growth.lemonsqueezy_variant_id_monthly,
        prorate=False,
    )
    assert row.plan_id == growth.id
    # The new plan's month minus what was used this period.
    assert row.current_credits == 700
    assert (result["monthly_credits_before"], result["monthly_credits_after"]) == (100, 700)
    assert (result["old_plan"]["id"], result["new_plan"]["id"]) == (starter.id, growth.id)
    assert (result["billing"], result["new_billing_period"]) == ("next_renewal", "monthly")


async def test_charge_now_has_lemon_squeezy_invoice_the_difference(session, lemon):
    starter, growth, _ = await _world(session)
    user, row = await _subscribed(session, starter, left=400)
    admin = await _user(session)

    await _change(session, user, admin, growth, billing="charge_now")

    lemon.update_subscription.assert_awaited_once_with(
        subscription_id=row.lemonsqueezy_subscription_id,
        price_id=growth.lemonsqueezy_variant_id_monthly,
        prorate=True,
    )
    assert (row.plan_id, row.billing_period) == (growth.id, MONTHLY)


async def test_a_billed_subscription_keeps_its_billing_cycle(session, lemon):
    # Another cycle can move Lemon Squeezy's billing date or charge at once, so "nothing
    # is charged now" couldn't be promised for it.
    starter, growth, _ = await _world(session)
    user, row = await _subscribed(session, starter, left=100)
    unbilled, other = await _subscribed(session, starter, left=100, billed=False)
    admin = await _user(session)

    with pytest.raises(BusinessRuleViolationException) as refused:
        await _change(session, user, admin, growth, period=YEARLY)
    assert "billed monthly" in refused.value.message
    assert (row.plan_id, row.billing_period) == (starter.id, MONTHLY)
    lemon.update_subscription.assert_not_awaited()

    # Nobody bills this one, so its period is only what the row says.
    await _change(session, unbilled, admin, growth, billing="not_billed", period=YEARLY)
    assert (other.plan_id, other.billing_period) == (growth.id, YEARLY)


async def test_a_subscription_lemon_squeezy_left_as_it_was_is_not_changed_here(session, lemon):
    # Paid through PayPal: Lemon Squeezy answers 200 and changes nothing.
    starter, growth, _ = await _world(session)
    user, row = await _subscribed(session, starter, left=100)
    admin = await _user(session)
    lemon.update_subscription.side_effect = lambda **sent: SimpleNamespace(
        plan_id=starter.lemonsqueezy_variant_id_monthly
    )

    with pytest.raises(BusinessRuleViolationException) as refused:
        await _change(session, user, admin, growth)

    assert "PayPal" in refused.value.message and "Nothing was changed" in refused.value.message
    assert (row.plan_id, row.current_credits) == (starter.id, 100)
    assert await _audit(session, user) == []


async def test_a_downgrade_is_only_from_the_next_renewal_and_never_below_zero(session, lemon):
    starter, growth, _ = await _world(session)
    user, row = await _subscribed(session, growth, left=250)  # 750 of 1,000 used
    admin = await _user(session)

    with pytest.raises(RextValidationException) as refused:
        await _change(session, user, admin, starter, billing="charge_now")
    assert "billing" in _fields(refused)
    lemon.update_subscription.assert_not_awaited()
    assert row.plan_id == growth.id

    await _change(session, user, admin, starter)

    assert (row.plan_id, row.current_credits) == (starter.id, 0)
    assert lemon.update_subscription.await_args.kwargs["prorate"] is False


async def test_nothing_changes_when_lemon_squeezy_does_not_accept_it(session, lemon, monkeypatch):
    starter, growth, _ = await _world(session)
    user, row = await _subscribed(session, starter, left=100)
    admin = await _user(session)
    lemon.update_subscription.side_effect = LemonSqueezyAPIError(422, "variant not in the store")
    # Where a customer's change falls back to a local one, an admin's never does.
    monkeypatch.setattr(subscription_service_module.payment_settings, "payment_sandbox_mode", True)

    with pytest.raises(BusinessRuleViolationException) as refused:
        await _change(session, user, admin, growth)

    message = refused.value.message
    assert "status 422" in message and "Nothing was changed" in message
    assert "variant not in the store" not in message  # the status, never Lemon Squeezy's words
    assert (row.plan_id, row.current_credits) == (starter.id, 100)
    assert await _audit(session, user) == []


async def test_a_change_lemon_squeezy_took_but_did_not_confirm_is_not_called_refused(
    session, lemon
):
    # The PATCH went through and reading the subscription back failed: Lemon Squeezy has
    # changed and can't be rolled back, so the admin isn't told that nothing changed.
    starter, growth, _ = await _world(session)
    user, row = await _subscribed(session, starter, left=100)
    admin = await _user(session)
    lemon.update_subscription.side_effect = PaymentChangeUnconfirmed("read back failed")

    with pytest.raises(BusinessRuleViolationException) as refused:
        await _change(session, user, admin, growth)

    assert "Lemon Squeezy took the change" in refused.value.message
    assert "Nothing was changed" not in refused.value.message
    alert = subscription_service_module.trigger_payment_alert.call_args.kwargs
    assert alert["alert_type"] == "admin_plan_change_unconfirmed"
    # Nothing is recorded here: Lemon Squeezy's own update brings the plan in line.
    assert row.plan_id == starter.id
    assert await _audit(session, user) == []


async def test_a_user_lemon_squeezy_does_not_bill_is_changed_here_only(session, lemon):
    starter, growth, _ = await _world(session)
    user, row = await _subscribed(session, starter, left=100, billed=False)
    admin = await _user(session)

    with pytest.raises(RextValidationException) as refused:
        await _change(session, user, admin, growth)  # next_renewal: there is no renewal to bill
    assert "billing" in _fields(refused)

    result = await _change(session, user, admin, growth, billing="not_billed")

    lemon.update_subscription.assert_not_awaited()
    assert (row.plan_id, row.current_credits, result["billing"]) == (growth.id, 700, "not_billed")


# --- what is refused --------------------------------------------------------------------


async def test_a_trial_is_not_moved_to_a_paid_plan(session, lemon):
    _, growth, _ = await _world(session)
    trial = await _plan(session, "trial", price=0, credits=60, trial=True, variants=False)
    user, row = await _subscribed(
        session,
        trial,
        left=60,
        billed=False,
        status=SubscriptionStatus.TRIAL,
        trial_end_date=NOW + timedelta(days=3),
        end_date=NOW + timedelta(days=3),
    )
    admin = await _user(session)

    with pytest.raises(BusinessRuleViolationException) as refused:
        await _change(session, user, admin, growth, billing="not_billed")

    assert "Extend the trial or add credits" in refused.value.message
    assert row.plan_id == trial.id


@pytest.mark.parametrize(
    ("fields", "says"),
    [
        ({"status": SubscriptionStatus.PAST_DUE}, "renewal payment has failed"),
        (
            {"status": SubscriptionStatus.CANCELLED, "end_date": NOW + timedelta(days=5)},
            "cancelled",
        ),
        ({"period": BillingPeriod.LIFETIME}, "lifetime"),
    ],
)
async def test_a_subscription_that_is_not_running_normally_is_refused(session, lemon, fields, says):
    starter, growth, _ = await _world(session)
    user, row = await _subscribed(session, starter, left=100, **fields)
    admin = await _user(session)

    with pytest.raises(BusinessRuleViolationException) as refused:
        await _change(session, user, admin, growth)

    assert says in refused.value.message and "Nothing was changed" in refused.value.message
    assert row.plan_id == starter.id
    lemon.update_subscription.assert_not_awaited()


async def test_a_user_without_a_subscription_is_refused(session, lemon):
    _, growth, _ = await _world(session)
    user, admin = await _user(session), await _user(session)

    with pytest.raises(BusinessRuleViolationException):
        await _change(session, user, admin, growth)


async def test_the_same_plan_is_refused_and_so_is_a_period_alone(session, lemon):
    starter, _, _ = await _world(session)
    user, row = await _subscribed(session, starter, left=100)
    admin = await _user(session)

    with pytest.raises(BusinessRuleViolationException) as same:
        await _change(session, user, admin, starter)
    with pytest.raises(BusinessRuleViolationException) as period_alone:
        await _change(session, user, admin, starter, period=YEARLY)

    assert "plan now" in same.value.message
    assert "billing period can't be changed alone" in period_alone.value.message
    assert row.billing_period == MONTHLY
    lemon.update_subscription.assert_not_awaited()


async def test_a_plan_with_no_price_at_lemon_squeezy_is_refused_for_a_billed_user(session, lemon):
    starter, _, _ = await _world(session)
    unsold = await _plan(session, "scale", price=389, credits=6000, variants=False)
    user, row = await _subscribed(session, starter, left=100)
    admin = await _user(session)

    with pytest.raises(BusinessRuleViolationException) as refused:
        await _change(session, user, admin, unsold)

    assert "no monthly price at Lemon Squeezy" in refused.value.message
    assert row.plan_id == starter.id


@pytest.mark.parametrize(
    "target",
    [
        {"trial": True, "variants": False},
        {"active": False},
        {"public": False},
        {"credits": None},
    ],
)
async def test_only_a_plan_on_offer_can_be_chosen(session, lemon, target):
    starter, _, _ = await _world(session)
    other = await _plan(session, "other", **{"price": 99, "credits": 1200, **target})
    user, row = await _subscribed(session, starter, left=100)
    admin = await _user(session)

    with pytest.raises(RextValidationException) as refused:
        await _change(session, user, admin, other)

    assert "plan_id" in _fields(refused)
    assert row.plan_id == starter.id


@pytest.mark.parametrize("reason", ["", "  ", "ab", "x" * 501])
async def test_a_reason_is_required(session, lemon, reason):
    starter, growth, _ = await _world(session)
    user, row = await _subscribed(session, starter, left=100)
    admin = await _user(session)

    with pytest.raises(RextValidationException) as refused:
        await _change(session, user, admin, growth, reason=reason)

    assert "reason" in _fields(refused)
    assert row.plan_id == starter.id
    lemon.update_subscription.assert_not_awaited()


# --- the audit entry --------------------------------------------------------------------


async def test_the_change_is_audited_against_the_user_with_the_admin_and_the_reason(session, lemon):
    starter, growth, _ = await _world(session)
    user, row = await _subscribed(session, starter, left=100)
    admin = await _user(session)

    result = await _change(session, user, admin, growth, billing="charge_now")

    (entry,) = await _audit(session, user)  # one entry: not the customer's own "upgraded" too
    assert entry.id == result["audit_id"]
    assert entry.action == "admin.plan_changed"
    assert entry.resource_id == str(row.id)
    assert entry.old_values == {"plan": starter.name, "billing_period": "monthly"}
    assert entry.new_values == {"plan": growth.name, "billing_period": "monthly"}
    meta = entry.audit_metadata
    assert meta["admin_id"] == str(admin.id)
    assert (meta["billing"], meta["kind"]) == ("charge_now", "upgrade")
    assert (meta["credits_before"], meta["credits_after"]) == (100, 700)
    assert meta["reason"] == REASON


async def test_the_reason_is_kept_out_of_the_application_log(session, lemon, monkeypatch):
    starter, growth, _ = await _world(session)
    user, _ = await _subscribed(session, starter, left=100)
    admin = await _user(session)
    logged = []
    monkeypatch.setattr(
        audit_logger.logger,
        "info",
        lambda message, *args, **kwargs: logged.append((message, kwargs)),
    )

    await _change(session, user, admin, growth, reason="As promised to jane@example.com")

    (line,) = [entry for entry in logged if "admin.plan_changed" in entry[0]]
    assert "jane@example.com" not in line[0] and "jane@example.com" not in str(line[1])
    (entry,) = await _audit(session, user)
    assert entry.audit_metadata["reason"] == "As promised to jane@example.com"


async def test_no_change_is_kept_without_its_audit_entry(session, lemon, monkeypatch):
    starter, growth, _ = await _world(session)
    user, _ = await _subscribed(session, starter, left=100)
    unbilled, _ = await _subscribed(session, starter, left=100, billed=False)
    admin = await _user(session)
    monkeypatch.setattr(
        "src.services.admin_plan_changes.audit_logger.log_admin_plan_changed",
        AsyncMock(return_value=None),
    )

    # Nobody bills this one: the caller's rollback undoes everything.
    with pytest.raises(RuntimeError):
        await _change(session, unbilled, admin, growth, billing="not_billed")
    module.trigger_payment_alert.assert_not_called()

    # Lemon Squeezy has changed already and can't be rolled back: the admin isn't told
    # "nothing was changed", and a person is alerted to record who and why.
    with pytest.raises(BusinessRuleViolationException) as refused:
        await _change(session, user, admin, growth)
    assert "Lemon Squeezy has changed the plan" in refused.value.message
    assert "Nothing was changed" not in refused.value.message
    alert = module.trigger_payment_alert.call_args.kwargs
    assert alert["alert_type"] == "admin_plan_change_unrecorded"
    assert alert["context"]["admin_id"] == str(admin.id)


# --- what the admin is shown first --------------------------------------------------------


def _choice(options, plan, period="monthly"):
    (row,) = [p for p in options["plans"] if p["id"] == plan.id]
    (found,) = [p for p in row["periods"] if p["billing_period"] == period]
    return found


async def test_the_options_say_how_each_choice_is_billed_and_what_it_leaves(session, lemon):
    starter, growth, pro = await _world(session)
    user, row = await _subscribed(session, growth, left=250)  # 750 of 1,000 used

    options = await module.plan_options(session, user.id)

    assert options["currency"] == "USD"
    assert options["subscription"]["plan_id"] == growth.id
    assert options["subscription"]["billed_by_provider"] is True
    assert options["change"] == {
        "allowed": True,
        "refused_reason": None,
        "default_billing": "next_renewal",
    }
    assert options["trial_extension"]["allowed"] is False
    assert options["limits"] == {"reason_min": 3, "reason_max": 500}
    # In the list by price, with the list prices.
    assert [p["id"] for p in options["plans"]][:3] == [starter.id, growth.id, pro.id]
    assert options["plans"][0]["price_monthly"] == "39.00"

    up = _choice(options, pro)
    assert (up["kind"], up["allowed"]) == ("upgrade", True)
    assert [(m["billing"], m["plan_changes"]) for m in up["modes"]] == [
        ("next_renewal", "now"),
        ("charge_now", "now"),
    ]
    assert {m["monthly_credits_after"] for m in up["modes"]} == {1750}
    down = _choice(options, starter)
    assert (down["kind"], [m["billing"] for m in down["modes"]]) == ("downgrade", ["next_renewal"])
    assert down["modes"][0]["monthly_credits_after"] == 0
    own = _choice(options, growth)
    assert (own["allowed"], own["modes"]) == (False, [])
    other_period = _choice(options, growth, "yearly")
    assert (other_period["kind"], other_period["allowed"]) == ("period_change", False)
    other_cycle = _choice(options, pro, "yearly")
    assert other_cycle["allowed"] is False and "billed monthly" in other_cycle["refused_reason"]
    # Reading the options changes nothing.
    assert (row.plan_id, row.current_credits) == (growth.id, 250)


@pytest.mark.parametrize(("target", "left"), [("pro", 250), ("starter", 250), ("pro", 0)])
async def test_the_credits_shown_are_the_credits_the_change_leaves(session, lemon, target, left):
    starter, growth, pro = await _world(session)
    plan = {"pro": pro, "starter": starter}[target]
    user, row = await _subscribed(session, growth, left=left)
    admin = await _user(session)
    shown = _choice(await module.plan_options(session, user.id), plan)["modes"][0]

    result = await _change(session, user, admin, plan, billing=shown["billing"])

    assert result["monthly_credits_after"] == shown["monthly_credits_after"] == row.current_credits


async def test_the_options_for_a_user_nobody_bills_and_for_one_without_a_plan(session, lemon):
    starter, growth, _ = await _world(session)
    user, _ = await _subscribed(session, starter, left=100, billed=False)
    nobody = await _user(session)

    unbilled = await module.plan_options(session, user.id)
    none = await module.plan_options(session, nobody.id)

    assert unbilled["change"]["default_billing"] == "not_billed"
    assert [m["billing"] for m in _choice(unbilled, growth)["modes"]] == ["not_billed"]
    assert none["subscription"] is None
    assert (none["change"]["allowed"], none["trial_extension"]["allowed"]) == (False, False)
    assert "no plan" in none["change"]["refused_reason"]
    assert all(not period["allowed"] for plan in none["plans"] for period in plan["periods"])


async def test_a_smaller_plan_the_users_workspaces_do_not_fit_is_not_offered(
    session, lemon, monkeypatch
):
    # The change refuses it (the customer's own change does too), so the options say so.
    starter, growth, pro = await _world(session)
    starter.max_workspaces = 1
    user, _ = await _subscribed(session, growth, left=250)
    admin = await _user(session)
    monkeypatch.setattr(
        SubscriptionService,
        "calculate_usage",
        AsyncMock(return_value={"workspaces": 2, "members": 0}),
    )

    options = await module.plan_options(session, user.id)

    down = _choice(options, starter)
    assert (down["allowed"], down["modes"]) == (False, [])
    assert "2 workspaces" in down["refused_reason"]
    assert _choice(options, pro)["allowed"] is True
    with pytest.raises(RextValidationException):
        await _change(session, user, admin, starter)


async def test_a_super_admins_account_is_offered_nothing(session, lemon):
    starter, growth, _ = await _world(session)
    user, _ = await _subscribed(session, starter, left=100)

    options = await module.plan_options(session, user.id, protected=True)

    assert options["subscription"]["plan_id"] == starter.id
    for standing in (options["change"], options["trial_extension"]):
        assert standing["allowed"] is False
        assert "Super Admin" in standing["refused_reason"]
    assert all(not period["allowed"] for plan in options["plans"] for period in plan["periods"])


async def test_a_plan_read_from_the_cache_still_has_its_monthly_credits(session, monkeypatch):
    # The plan change works the balance out from them: a cached plan without them made
    # the change skip the balance.
    import src.api.cache.redis_client as redis_client

    stored = {}

    class Cache:
        is_enabled = True

        async def get(self, key):
            return stored.get(key)

        async def set(self, key, value, ttl=None):
            stored[key] = value

    monkeypatch.setattr(redis_client, "cache", Cache())
    monkeypatch.setattr(
        subscription_service_module, "get_payment_provider_singleton", lambda: MagicMock()
    )
    trial = await _plan(session, "trial", price=0, credits=60, trial=True, variants=False)
    service = SubscriptionService(session)

    await service._get_plan_or_404(trial.id)
    cached = await service._get_plan_or_404(trial.id)

    assert stored and cached is not trial
    assert (cached.credits_per_month, cached.is_trial_plan) == (60, True)


# --- a trial's end ----------------------------------------------------------------------


async def _statements(db, change) -> list[str]:
    """The SQL one change runs, in order."""
    statements: list[str] = []

    def record(_conn, _cursor, statement, *_rest):
        statements.append(statement)

    connection = db.bind.sync_connection
    event.listen(connection, "before_cursor_execute", record)
    try:
        await change()
    finally:
        event.remove(connection, "before_cursor_execute", record)
    return statements


def _locked_before_the_plan_is_read(statements) -> bool:
    lock = next(i for i, sql in enumerate(statements) if "pg_advisory_xact_lock" in sql)
    read = next(i for i, sql in enumerate(statements) if "FROM user_subscriptions" in sql)
    return lock < read


async def test_a_plan_change_takes_the_users_lock_before_it_reads_their_plan(session, lemon):
    """Two changes for one user would otherwise both check the same plan and both reach
    Lemon Squeezy; the second now waits and reads what the first left."""
    starter, growth, _ = await _world(session)
    user, _ = await _subscribed(session, starter, left=100)
    admin = await _user(session)

    statements = await _statements(session, lambda: _change(session, user, admin, growth))

    assert _locked_before_the_plan_is_read(statements)
    lemon.update_subscription.assert_awaited_once()


async def test_a_trials_extension_takes_the_same_lock_first(session, lemon):
    user, _ = await _on_trial(session)
    admin = await _user(session)

    statements = await _statements(
        session,
        lambda: module.extend_trial(
            session,
            user_id=user.id,
            admin_id=admin.id,
            ends_at=NOW + timedelta(days=9),
            reason="A week more to try it",
        ),
    )

    assert _locked_before_the_plan_is_read(statements)


async def _on_trial(db, *, ends_in=timedelta(days=2), billed=False):
    trial = await _plan(db, "trial", price=0, credits=60, trial=True, variants=False)
    end = NOW + ends_in
    return await _subscribed(
        db,
        trial,
        left=40,
        billed=billed,
        status=SubscriptionStatus.TRIAL,
        trial_end_date=end,
        end_date=end,
        credits_reset_date=end,
    )


async def test_a_trials_end_is_moved_later_and_audited(session, lemon):
    user, row = await _on_trial(session)
    admin = await _user(session)
    before = row.trial_end_date
    later = NOW + timedelta(days=9)

    options = await module.plan_options(session, user.id)
    result = await module.extend_trial(
        session, user_id=user.id, admin_id=admin.id, ends_at=later, reason="A week more to try it"
    )

    assert options["change"]["allowed"] is False
    assert options["trial_extension"]["allowed"] is True
    assert options["trial_extension"]["earliest_ends_at"] == before
    # The row and its credits' period end with the trial; the credits are as they were.
    assert (row.trial_end_date, row.end_date, row.credits_reset_date) == (later, later, later)
    assert (row.status, row.current_credits) == (SubscriptionStatus.TRIAL, 40)
    assert (result["trial_ended_at_before"], result["trial_ends_at"]) == (before, later)
    (entry,) = await _audit(session, user)
    assert entry.id == result["audit_id"]
    assert entry.action == "admin.trial_extended"
    assert entry.audit_metadata["admin_id"] == str(admin.id)
    assert entry.audit_metadata["reason"] == "A week more to try it"
    assert entry.new_values == {"trial_end_date": later.isoformat()}


async def test_a_trial_that_is_over_is_not_brought_back_by_an_extension(session, lemon):
    user, row = await _on_trial(session, ends_in=timedelta(hours=-1))
    admin = await _user(session)

    async def grants_access() -> bool:
        found = await session.execute(
            select(UserSubscription.id).where(
                UserSubscription.id == row.id, subscription_grants_access()
            )
        )
        return found.first() is not None

    assert await grants_access() is False
    # A trial that is over grants nothing and is no longer the user's plan: an extension
    # moves the end of a running trial, it doesn't start an ended one again.
    with pytest.raises(BusinessRuleViolationException) as refused:
        await module.extend_trial(
            session,
            user_id=user.id,
            admin_id=admin.id,
            ends_at=NOW + timedelta(days=3),
            reason="Back for three days",
        )
    assert await grants_access() is False
    # The admin is told why, in the one line the dashboard shows.
    assert "trial has ended" in refused.value.message
    options = await module.plan_options(session, user.id)
    assert options["subscription"] is None
    for standing in (options["change"], options["trial_extension"]):
        assert standing["allowed"] is False
        assert standing["refused_reason"].startswith("This user's trial has ended")


@pytest.mark.parametrize(
    "ends_in",
    [timedelta(days=1), timedelta(days=2), timedelta(days=31)],  # earlier, the same, too far
)
async def test_the_new_end_is_later_than_the_trials_and_within_thirty_days(session, lemon, ends_in):
    user, row = await _on_trial(session)
    admin = await _user(session)
    before = row.trial_end_date

    with pytest.raises(RextValidationException) as refused:
        await module.extend_trial(
            session, user_id=user.id, admin_id=admin.id, ends_at=NOW + ends_in, reason=REASON
        )

    assert "ends_at" in _fields(refused)
    assert row.trial_end_date == before


async def test_a_trial_that_already_runs_past_the_limit_is_not_offered_an_extension(session, lemon):
    """An older or hand-set row: no later end is left inside the limit, so the options say
    so instead of offering a window the change would refuse every date of."""
    user, row = await _on_trial(session, ends_in=timedelta(days=45))
    admin = await _user(session)
    before = row.trial_end_date

    extension = (await module.plan_options(session, user.id))["trial_extension"]

    assert extension["allowed"] is False
    assert extension["refused_reason"] == module.TRIAL_AT_ITS_LIMIT
    assert (extension["earliest_ends_at"], extension["latest_ends_at"]) == (None, None)
    with pytest.raises(BusinessRuleViolationException) as refused:
        await module.extend_trial(
            session,
            user_id=user.id,
            admin_id=admin.id,
            ends_at=NOW + timedelta(days=50),
            reason="A little longer",
        )
    assert refused.value.message.startswith(module.TRIAL_AT_ITS_LIMIT)
    assert row.trial_end_date == before


async def test_only_a_trial_this_app_runs_is_extended(session, lemon):
    starter, _, _ = await _world(session)
    paying, _ = await _subscribed(session, starter, left=100)
    at_lemon_squeezy, row = await _on_trial(session, billed=True)
    admin = await _user(session)

    for user, says in ((paying, "isn't on a trial"), (at_lemon_squeezy, "run by Lemon Squeezy")):
        with pytest.raises(BusinessRuleViolationException) as refused:
            await module.extend_trial(
                session,
                user_id=user.id,
                admin_id=admin.id,
                ends_at=NOW + timedelta(days=9),
                reason=REASON,
            )
        assert says in refused.value.message

    assert row.trial_end_date == NOW + timedelta(days=2)


async def test_the_extension_reads_the_subscription_the_options_show(session, lemon):
    # A paid plan and a newer trial row that both grant access: the options show the paid
    # plan (active first), so the extension answers for that one and leaves the trial row.
    starter, _, _ = await _world(session)
    user, _ = await _subscribed(session, starter, left=100)
    trial = await _plan(session, "trial", price=0, credits=60, trial=True, variants=False)
    end = NOW + timedelta(days=2)
    _, stray = await _subscribed(
        session,
        trial,
        left=40,
        billed=False,
        user=user,
        status=SubscriptionStatus.TRIAL,
        trial_end_date=end,
        end_date=end,
        credits_reset_date=end,
        created_at=NOW,
    )
    admin = await _user(session)

    options = await module.plan_options(session, user.id)
    with pytest.raises(BusinessRuleViolationException) as refused:
        await module.extend_trial(
            session,
            user_id=user.id,
            admin_id=admin.id,
            ends_at=NOW + timedelta(days=9),
            reason=REASON,
        )

    assert options["subscription"]["plan_id"] == starter.id
    assert options["trial_extension"]["allowed"] is False
    assert "isn't on a trial" in refused.value.message
    assert stray.trial_end_date == end


async def test_a_failed_audit_write_is_logged_without_what_the_entry_held(monkeypatch):
    # SQLAlchemy's error text carries the statement's parameters, and with them the reason.
    from sqlalchemy.exc import IntegrityError

    import src.utils.audit_helper as audit_helper

    logged = []
    monkeypatch.setattr(
        audit_helper.logger, "error", lambda message, *a, **k: logged.append(message)
    )
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    db.flush = AsyncMock(
        side_effect=IntegrityError(
            "INSERT INTO audit_logs ...",
            {"audit_metadata": '{"reason": "As promised to jane@example.com"}'},
            Exception("null value in column violates not-null constraint"),
        )
    )

    entry = await audit_helper.create_audit_log(
        db=db,
        user_id=uuid4(),
        action="admin.plan_changed",
        resource_type="subscription",
        resource_id="s-1",
        metadata={"reason": "As promised to jane@example.com"},
    )

    assert entry is None
    (line,) = logged
    assert "jane@example.com" not in line
    assert "not-null constraint" in line


# --- the Users list ---------------------------------------------------------------------


async def test_each_users_plan_for_the_list_comes_in_one_read(session, lemon):
    starter, growth, _ = await _world(session)
    paying, _ = await _subscribed(session, growth, left=100, period=YEARLY)
    trying, _ = await _on_trial(session)
    nobody = await _user(session)
    # An ended subscription beside the running one doesn't speak for the user.
    await _subscribed(
        session,
        starter,
        left=0,
        user=paying,
        status=SubscriptionStatus.EXPIRED,
        end_date=NOW - timedelta(days=40),
    )

    plans = await module.plans_of_users(session, [paying.id, trying.id, nobody.id])

    assert plans[paying.id] == {
        "plan_display_name": "Growth",
        "is_trial": False,
        "billing_period": "yearly",
    }
    assert plans[trying.id]["is_trial"] is True
    assert nobody.id not in plans
    assert await module.plans_of_users(session, []) == {}
