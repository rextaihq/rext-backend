"""The nightly reconciler re-reads unfinished subscriptions from Lemon Squeezy (F11, #336).

Lemon Squeezy retries a webhook only three times, so a missed change is caught up
here with the webhook handlers' rules. Checked on the test PostgreSQL inside a
rolled-back transaction, with the API replaced by a mock.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.services.subscription_reconciler as module
from src.api.database.base import Base
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from tests.conftest import TEST_DATABASE_URL

T1, T2 = (datetime(2026, 10, 6, h, 0, tzinfo=timezone.utc) for h in (8, 9))


@pytest_asyncio.fixture
async def session(monkeypatch):
    monkeypatch.setattr(module, "_PAUSE_BETWEEN_READS_SECONDS", 0)
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=[
                    Users.__table__,
                    SubscriptionPlan.__table__,
                    UserSubscription.__table__,
                    WorkspaceModel.__table__,
                    AuditLog.__table__,
                ],
                checkfirst=True,
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


async def _subscription(db, status, *, stored_at=T1, metadata=None):
    plan = SubscriptionPlan(
        name=f"growth-{uuid4().hex[:8]}", display_name="Growth", credits_per_month=1000
    )
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    db.add_all([plan, user])
    await db.flush()
    row = UserSubscription(
        user_id=user.id,
        plan_id=plan.id,
        status=status,
        lemonsqueezy_subscription_id=f"ls-{uuid4().hex[:8]}",
        provider_updated_at=stored_at,
        subscription_metadata=metadata or {},
    )
    db.add(row)
    await db.flush()
    return row


def _api(states):
    async def read(ls_id):
        state = states[ls_id]
        if isinstance(state, Exception):
            raise state
        return state

    return SimpleNamespace(get_subscription_attributes=AsyncMock(side_effect=read))


@pytest.mark.asyncio
async def test_a_missed_change_is_caught_up_with_its_email(session):
    missed = await _subscription(session, SubscriptionStatus.PAST_DUE)
    same = await _subscription(session, SubscriptionStatus.ACTIVE)
    api = _api(
        {
            missed.lemonsqueezy_subscription_id: {"status": "unpaid", "updated_at": T2.isoformat()},
            same.lemonsqueezy_subscription_id: {"status": "active", "updated_at": T1.isoformat()},
        }
    )

    result = await module.reconcile_subscriptions(session, api)

    assert missed.status == SubscriptionStatus.UNPAID
    assert same.status == SubscriptionStatus.ACTIVE
    assert {k: result[k] for k in ("checked", "changed", "failed")} == {
        "checked": 2,
        "changed": 1,
        "failed": 0,
    }
    assert [email["email_type"] for email in result["emails"]] == ["subscription_unpaid"]


@pytest.mark.asyncio
async def test_an_older_api_state_changes_nothing(session):
    row = await _subscription(session, SubscriptionStatus.ACTIVE, stored_at=T2)

    result = await module.reconcile_subscriptions(
        session,
        _api(
            {row.lemonsqueezy_subscription_id: {"status": "past_due", "updated_at": T1.isoformat()}}
        ),
    )

    assert row.status == SubscriptionStatus.ACTIVE
    assert result["changed"] == 0


@pytest.mark.asyncio
async def test_one_unreadable_subscription_does_not_stop_the_others(session):
    broken = await _subscription(session, SubscriptionStatus.ACTIVE)
    fine = await _subscription(session, SubscriptionStatus.PAST_DUE)
    api = _api(
        {
            broken.lemonsqueezy_subscription_id: RuntimeError("404"),
            fine.lemonsqueezy_subscription_id: {"status": "active", "updated_at": T2.isoformat()},
        }
    )

    result = await module.reconcile_subscriptions(session, api)

    assert fine.status == SubscriptionStatus.ACTIVE
    assert result["failed"] == 1 and result["checked"] == 1


@pytest.mark.asyncio
async def test_expired_and_settled_duplicates_are_not_read(session):
    await _subscription(session, SubscriptionStatus.EXPIRED)
    await _subscription(session, SubscriptionStatus.CANCELLED, metadata={"duplicate_of": "x"})
    api = _api({})

    result = await module.reconcile_subscriptions(session, api)

    api.get_subscription_attributes.assert_not_called()
    assert result["checked"] == 0


@pytest.mark.asyncio
async def test_settled_duplicates_never_take_the_batch(session):
    """Left out before the limit, so a pile of them can't push the real ones out for good."""
    for _ in range(2):
        await _subscription(session, SubscriptionStatus.CANCELLED, metadata={"duplicate_of": "x"})
    real = await _subscription(session, SubscriptionStatus.PAST_DUE)
    api = _api(
        {real.lemonsqueezy_subscription_id: {"status": "active", "updated_at": T2.isoformat()}}
    )

    result = await module.reconcile_subscriptions(session, api, limit=1)

    assert result["checked"] == 1
    assert real.status == SubscriptionStatus.ACTIVE


@pytest.mark.asyncio
async def test_every_read_is_paced_a_failed_one_too(session, monkeypatch):
    broken = await _subscription(session, SubscriptionStatus.ACTIVE)
    fine = await _subscription(session, SubscriptionStatus.ACTIVE)
    pause = AsyncMock()
    monkeypatch.setattr(module, "_pause", pause)

    await module.reconcile_subscriptions(
        session,
        _api(
            {
                broken.lemonsqueezy_subscription_id: RuntimeError("429"),
                fine.lemonsqueezy_subscription_id: {
                    "status": "active",
                    "updated_at": T2.isoformat(),
                },
            }
        ),
    )

    assert pause.await_count == 2


# --- revnix/rext-control#529, part B -----------------------------------------------------


@pytest.mark.asyncio
async def test_each_subscription_is_its_own_transaction(session, monkeypatch):
    """Committed one by one, so no row stays locked while the batch reads the others."""
    rows = [await _subscription(session, SubscriptionStatus.ACTIVE) for _ in range(3)]
    commit = AsyncMock()
    monkeypatch.setattr(session, "commit", commit)

    await module.reconcile_subscriptions(
        session,
        _api(
            {
                row.lemonsqueezy_subscription_id: {"status": "active", "updated_at": T2.isoformat()}
                for row in rows
            }
        ),
    )

    assert commit.await_count == 3


@pytest.mark.asyncio
async def test_a_subscription_that_fails_to_read_goes_to_the_back(session):
    broken = await _subscription(session, SubscriptionStatus.ACTIVE)
    waiting = await _subscription(session, SubscriptionStatus.ACTIVE)
    api = _api(
        {
            broken.lemonsqueezy_subscription_id: RuntimeError("404"),
            waiting.lemonsqueezy_subscription_id: {
                "status": "active",
                "updated_at": T2.isoformat(),
            },
        }
    )

    first = await module.reconcile_subscriptions(session, api, limit=1)
    second = await module.reconcile_subscriptions(session, api, limit=1)

    read = [call.args[0] for call in api.get_subscription_attributes.await_args_list]
    assert read == [broken.lemonsqueezy_subscription_id, waiting.lemonsqueezy_subscription_id]
    assert first["failed"] == 1 and second["checked"] == 1
    assert "reconciled_at" in broken.subscription_metadata


@pytest.mark.asyncio
async def test_a_revived_older_subscription_gets_the_duplicate_check(session, monkeypatch):
    """A missed recovery brings an older one back while a newer one runs: a person is told."""
    import src.services.duplicate_subscriptions as duplicates

    alert = MagicMock()
    monkeypatch.setattr(duplicates, "trigger_payment_alert", alert)
    monkeypatch.delenv("BILLING_AUTO_SETTLE_DUPLICATES", raising=False)
    older = await _subscription(session, SubscriptionStatus.UNPAID)
    older.created_at = T1
    newer = UserSubscription(
        user_id=older.user_id,
        plan_id=older.plan_id,
        status=SubscriptionStatus.ACTIVE,
        lemonsqueezy_subscription_id=f"ls-{uuid4().hex[:8]}",
        provider_updated_at=T1,
        created_at=T2,
    )
    session.add(newer)
    await session.flush()

    await module.reconcile_subscriptions(
        session,
        _api(
            {
                older.lemonsqueezy_subscription_id: {
                    "status": "active",
                    "updated_at": T2.isoformat(),
                },
                newer.lemonsqueezy_subscription_id: {
                    "status": "active",
                    "updated_at": T1.isoformat(),
                },
            }
        ),
    )

    assert older.subscription_metadata["duplicate_found_of"] == str(newer.id)
    assert alert.call_args.kwargs["severity"] == "critical"


@pytest.mark.asyncio
async def test_a_cancellation_it_finds_sends_the_cancellation_email(session):
    row = await _subscription(session, SubscriptionStatus.ACTIVE)

    result = await module.reconcile_subscriptions(
        session,
        _api(
            {
                row.lemonsqueezy_subscription_id: {
                    "status": "cancelled",
                    "ends_at": (T2 + timedelta(days=20)).isoformat(),
                    "updated_at": T2.isoformat(),
                }
            }
        ),
    )

    assert row.status == SubscriptionStatus.CANCELLED
    assert [email["email_type"] for email in result["emails"]] == ["subscription_cancelled"]


@pytest.mark.asyncio
async def test_the_notice_goes_out_when_the_email_fails():
    from src.api.tasks import subscription_reconcile_task as task

    db = AsyncMock()
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = db
    email = {"send_email": True, "email_type": "subscription_unpaid", "email_data": {}}
    notify = AsyncMock()

    with (
        patch.object(task, "AsyncSessionLocal", lambda: session_cm),
        patch.object(
            task,
            "reconcile_subscriptions",
            AsyncMock(return_value={"checked": 1, "changed": 1, "failed": 0, "emails": [email]}),
        ),
        patch(
            "src.api.routes.subscriptions.webhook_routes._send_webhook_email",
            AsyncMock(side_effect=RuntimeError("email provider down")),
        ),
        patch("src.api.routes.subscriptions.webhook_routes._send_webhook_notification", notify),
    ):
        await task.run_subscription_reconcile_task()

    notify.assert_awaited_once_with(email)


@pytest.mark.asyncio
async def test_the_job_commits_then_sends_the_emails():
    from src.api.tasks import subscription_reconcile_task as task

    db = AsyncMock()
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = db
    email = {"send_email": True, "email_type": "subscription_unpaid", "email_data": {}}
    order = []
    db.commit.side_effect = lambda: order.append("commit")
    send = AsyncMock(side_effect=lambda *_a: order.append("email"))

    with (
        patch.object(task, "AsyncSessionLocal", lambda: session_cm),
        patch.object(
            task,
            "reconcile_subscriptions",
            AsyncMock(return_value={"checked": 1, "changed": 1, "failed": 0, "emails": [email]}),
        ),
        patch("src.api.routes.subscriptions.webhook_routes._send_webhook_email", send),
        patch(
            "src.api.routes.subscriptions.webhook_routes._send_webhook_notification", AsyncMock()
        ),
    ):
        result = await task.run_subscription_reconcile_task()

    assert order == ["commit", "email"]
    assert result == {"checked": 1, "changed": 1, "failed": 0}
