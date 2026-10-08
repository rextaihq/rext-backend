"""
Tests for the data retention cleanup service.

- cleanup_all() on old and recent rows in every table it cleans, and with a step that fails
- the batched deletes, and the dry run the nightly job starts in (its counts)
- cleanup_webhook_events()
- anonymize_cancelled_subscriptions(), which cleanup_all() doesn't run yet
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.base import Base
from src.api.models.admin_models.error_log import ErrorLog, ErrorLogSeverity
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.email_models.email_event import EmailEvent
from src.api.models.email_models.email_log import EmailLog
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.api.models.user_models.user_sessions import UserSession
from src.api.models.user_models.users import Users
from src.config.cleanup_config import CleanupConfig
from src.services.data_cleanup_service import DataCleanupIncomplete, DataCleanupService
from src.services.plan_change_charges import PAID, REFUNDED
from tests.conftest import TEST_DATABASE_URL

Subscription = UserSubscription


def _with_parents(*tables):
    """The tables, and every table their foreign keys reach."""
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


def _tables_for_an_unmigrated_database(sync, tables) -> None:
    """Make the tables on an empty test database only. A migrated one (CI's) is tested as
    its migrations built it, so a table a migration lacks fails here instead of being made
    from the models."""
    if inspect(sync).has_table("alembic_version"):
        return
    Base.metadata.create_all(sync, tables=tables, checkfirst=True)


@pytest_asyncio.fixture
async def db_session():
    """The tables these tests need, inside a transaction that is rolled back.

    The service and the tests commit: each commit only releases a savepoint, so
    nothing is left behind, on an empty test database or a migrated one.
    """
    tables = _with_parents(
        Users.__table__,
        SubscriptionPlan.__table__,
        UserSubscription.__table__,
        WebhookEvent.__table__,
        AuditLog.__table__,
        EmailLog.__table__,
        EmailEvent.__table__,
        ErrorLog.__table__,
        UserSession.__table__,
        TokenBlacklist.__table__,
    )
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(lambda sync: _tables_for_an_unmigrated_database(sync, tables))
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def test_user(db_session):
    user = Users(email=f"{uuid4().hex[:12]}@example.com", full_name="Retention Test")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def plan(db_session):
    plan = SubscriptionPlan(
        name=f"pro-{uuid4().hex[:8]}", display_name="Pro", price_monthly=29.99, price_yearly=299.99
    )
    db_session.add(plan)
    await db_session.flush()
    return plan


def _days_ago(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _webhook_event(
    days_old: int, processed: bool = True, name: str = "subscription_updated"
) -> WebhookEvent:
    return WebhookEvent(
        id=uuid4(),
        event_id=f"evt_{uuid4().hex[:12]}",
        event_name=name,
        payload={"test": "data"},
        processed=processed,
        created_at=_days_ago(days_old),
    )


@pytest.mark.asyncio
async def test_cleanup_webhook_events_uses_config_default(db_session, monkeypatch):
    monkeypatch.setattr("src.config.cleanup_config.cleanup_config.WEBHOOK_EVENT_RETENTION_DAYS", 45)
    event = _webhook_event(days_old=50)
    db_session.add(event)
    await db_session.commit()

    service = DataCleanupService(db=db_session, dry_run=False)
    result = await service.cleanup_webhook_events(retention_days=None)

    assert result >= 1
    assert await db_session.get(WebhookEvent, event.id) is None


@pytest.mark.asyncio
async def test_anonymize_subscriptions_uses_config_default(db_session, monkeypatch):
    monkeypatch.setattr(
        "src.config.cleanup_config.cleanup_config.CANCELLED_SUBSCRIPTION_RETENTION_DAYS", 60
    )
    service = DataCleanupService(db=db_session, dry_run=True)
    result = await service.anonymize_cancelled_subscriptions(retention_days=None)
    assert isinstance(result, int)


def test_the_nightly_cleanup_starts_as_a_dry_run():
    """Its deletes never ran before, so the first nights count and log only."""
    assert CleanupConfig.model_fields["CLEANUP_DRY_RUN"].default is True


@pytest.mark.asyncio
async def test_deletes_run_in_batches_and_commit_each(db_session, monkeypatch):
    """PostgreSQL has no DELETE ... LIMIT: each batch deletes the ids a limited select picks."""
    monkeypatch.setattr("src.config.cleanup_config.cleanup_config.CLEANUP_BATCH_SIZE", 2)
    events = [_webhook_event(days_old=100) for _ in range(5)]
    kept = _webhook_event(days_old=100)
    db_session.add_all([*events, kept])
    await db_session.commit()

    commits = 0
    commit = db_session.commit

    async def counted_commit():
        nonlocal commits
        commits += 1
        await commit()

    monkeypatch.setattr(db_session, "commit", counted_commit)
    service = DataCleanupService(db=db_session, dry_run=False)
    deleted = await service._delete_in_batches(
        WebhookEvent, WebhookEvent.id.in_([event.id for event in events])
    )

    assert deleted == 5
    assert commits == 3  # 2, 2, then the last 1; the pick that finds nothing commits nothing
    remaining = (
        await db_session.execute(
            select(WebhookEvent.id).where(WebhookEvent.id.in_([e.id for e in [*events, kept]]))
        )
    ).scalars()
    assert list(remaining) == [kept.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("reported", [1, 0])
async def test_a_batch_that_deletes_few_or_none_is_not_the_end(db_session, monkeypatch, reported):
    """A batch deletes fewer rows than it picked, or none, when rows were refreshed meanwhile
    and kept, while more wait beyond its limit: the run goes on until a pick finds nothing."""
    monkeypatch.setattr("src.config.cleanup_config.cleanup_config.CLEANUP_BATCH_SIZE", 2)
    events = [_webhook_event(days_old=100) for _ in range(5)]
    db_session.add_all(events)
    await db_session.commit()

    execute = db_session.execute
    deletes = 0

    async def first_batch_reports_fewer(statement, *args, **kwargs):
        nonlocal deletes
        result = await execute(statement, *args, **kwargs)
        if getattr(statement, "is_delete", False):
            deletes += 1
            if deletes == 1:
                return SimpleNamespace(rowcount=reported)
        return result

    monkeypatch.setattr(db_session, "execute", first_batch_reports_fewer)
    service = DataCleanupService(db=db_session, dry_run=False)
    await service._delete_in_batches(
        WebhookEvent, WebhookEvent.id.in_([event.id for event in events])
    )
    monkeypatch.undo()

    remaining = await db_session.execute(
        select(WebhookEvent.id).where(WebhookEvent.id.in_([event.id for event in events]))
    )
    assert list(remaining.scalars()) == []


@pytest.mark.asyncio
async def test_a_batch_size_of_zero_ends_at_once(db_session, monkeypatch):
    """The setting can't be below 1, but a caller can put anything there: a pick of no rows
    finds nothing, and that ends the run."""
    monkeypatch.setattr("src.config.cleanup_config.cleanup_config.CLEANUP_BATCH_SIZE", 0)
    event = _webhook_event(days_old=100)
    db_session.add(event)
    await db_session.commit()

    service = DataCleanupService(db=db_session, dry_run=False)
    deleted = await asyncio.wait_for(
        service._delete_in_batches(WebhookEvent, WebhookEvent.id == event.id), timeout=10
    )

    assert deleted == 0
    assert await _exists(db_session, event)


@pytest.mark.asyncio
class TestWebhookEventCleanup:
    """Test webhook event cleanup functionality."""

    async def test_cleanup_old_processed_webhook_events(self, db_session):
        """Should delete processed webhook events older than retention period."""
        # Create old processed event (100 days old)
        old_event = WebhookEvent(
            id=uuid4(),
            event_id="evt_old_processed_123",
            event_name="subscription_created",
            payload={"test": "data"},
            processed=True,
            created_at=datetime.now(timezone.utc) - timedelta(days=100),
        )
        db_session.add(old_event)

        # Create recent processed event (30 days old)
        recent_event = WebhookEvent(
            id=uuid4(),
            event_id="evt_recent_processed_456",
            event_name="subscription_updated",
            payload={"test": "data"},
            processed=True,
            created_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
        db_session.add(recent_event)

        await db_session.commit()

        # Run cleanup with 90-day retention
        cleanup_service = DataCleanupService(db=db_session, dry_run=False)
        deleted_count = await cleanup_service.cleanup_webhook_events(retention_days=90)

        # Should delete only old event
        assert deleted_count == 1

        # Verify old event deleted
        old_event_check = await db_session.get(WebhookEvent, old_event.id)
        assert old_event_check is None

        # Verify recent event kept
        recent_event_check = await db_session.get(WebhookEvent, recent_event.id)
        assert recent_event_check is not None
        assert recent_event_check.event_id == "evt_recent_processed_456"

    async def test_keep_unprocessed_webhook_events(self, db_session):
        """Should NOT delete unprocessed webhook events (may indicate issues)."""
        # Create old UNPROCESSED event (100 days old)
        unprocessed_event = WebhookEvent(
            id=uuid4(),
            event_id="evt_old_unprocessed_789",
            event_name="subscription_payment_failed",
            payload={"test": "data"},
            processed=False,  # Not processed
            created_at=datetime.now(timezone.utc) - timedelta(days=100),
        )
        db_session.add(unprocessed_event)
        await db_session.commit()

        # Run cleanup
        cleanup_service = DataCleanupService(db=db_session, dry_run=False)
        deleted_count = await cleanup_service.cleanup_webhook_events(retention_days=90)

        # Should NOT delete unprocessed event
        assert deleted_count == 0

        # Verify event still exists
        event_check = await db_session.get(WebhookEvent, unprocessed_event.id)
        assert event_check is not None
        assert event_check.processed is False

    async def test_dry_run_mode_webhook_cleanup(self, db_session):
        """Should count but not delete in dry-run mode."""
        # Create old processed event
        old_event = WebhookEvent(
            id=uuid4(),
            event_id="evt_dryrun_123",
            event_name="subscription_created",
            payload={"test": "data"},
            processed=True,
            created_at=datetime.now(timezone.utc) - timedelta(days=100),
        )
        db_session.add(old_event)
        await db_session.commit()

        # Run cleanup in dry-run mode
        cleanup_service = DataCleanupService(db=db_session, dry_run=True)
        would_delete_count = await cleanup_service.cleanup_webhook_events(retention_days=90)

        # Should report 1 event would be deleted
        assert would_delete_count == 1

        # Verify event still exists (not actually deleted)
        event_check = await db_session.get(WebhookEvent, old_event.id)
        assert event_check is not None

    async def test_no_webhook_events_to_cleanup(self, db_session):
        """Should handle case when no events need cleanup."""
        # No events in database

        cleanup_service = DataCleanupService(db=db_session, dry_run=False)
        deleted_count = await cleanup_service.cleanup_webhook_events(retention_days=90)

        # Should return 0
        assert deleted_count == 0


@pytest.mark.asyncio
class TestSubscriptionAnonymization:
    """Test cancelled subscription anonymization functionality."""

    async def test_anonymize_old_cancelled_subscriptions(self, db_session, test_user, plan):
        """Should anonymize user_id from old cancelled subscriptions."""
        # Create old cancelled subscription (100 days old)
        old_subscription = Subscription(
            id=uuid4(),
            user_id=test_user.id,
            lemonsqueezy_subscription_id="sub_old_cancelled_123",
            lemonsqueezy_customer_id="cus_123",
            lemonsqueezy_variant_id="var_123",
            plan_id=plan.id,
            status="cancelled",
            updated_at=datetime.now(timezone.utc) - timedelta(days=100),
        )
        db_session.add(old_subscription)

        # Create recent cancelled subscription (30 days old)
        recent_subscription = Subscription(
            id=uuid4(),
            user_id=test_user.id,
            lemonsqueezy_subscription_id="sub_recent_cancelled_456",
            lemonsqueezy_customer_id="cus_456",
            lemonsqueezy_variant_id="var_456",
            plan_id=plan.id,
            status="cancelled",
            updated_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
        db_session.add(recent_subscription)

        await db_session.commit()

        # Run anonymization with 90-day retention
        cleanup_service = DataCleanupService(db=db_session, dry_run=False)
        anonymized_count = await cleanup_service.anonymize_cancelled_subscriptions(
            retention_days=90
        )

        # Should anonymize only old subscription
        assert anonymized_count == 1

        # Verify old subscription anonymized (user_id set to NULL)
        await db_session.refresh(old_subscription)
        assert old_subscription.user_id is None
        assert (
            old_subscription.lemonsqueezy_subscription_id == "sub_old_cancelled_123"
        )  # Other data kept

        # Verify recent subscription NOT anonymized
        await db_session.refresh(recent_subscription)
        assert recent_subscription.user_id == test_user.id

    async def test_anonymize_old_expired_subscriptions(self, db_session, test_user, plan):
        """Should anonymize expired subscriptions as well as cancelled."""
        # Create old expired subscription (100 days old)
        expired_subscription = Subscription(
            id=uuid4(),
            user_id=test_user.id,
            lemonsqueezy_subscription_id="sub_old_expired_789",
            lemonsqueezy_customer_id="cus_789",
            lemonsqueezy_variant_id="var_789",
            plan_id=plan.id,
            status="expired",
            updated_at=datetime.now(timezone.utc) - timedelta(days=100),
        )
        db_session.add(expired_subscription)
        await db_session.commit()

        # Run anonymization
        cleanup_service = DataCleanupService(db=db_session, dry_run=False)
        anonymized_count = await cleanup_service.anonymize_cancelled_subscriptions(
            retention_days=90
        )

        # Should anonymize expired subscription
        assert anonymized_count == 1

        await db_session.refresh(expired_subscription)
        assert expired_subscription.user_id is None

    async def test_keep_active_subscriptions(self, db_session, test_user, plan):
        """Should NOT anonymize active subscriptions."""
        # Create old active subscription (100 days old)
        active_subscription = Subscription(
            id=uuid4(),
            user_id=test_user.id,
            lemonsqueezy_subscription_id="sub_old_active_999",
            lemonsqueezy_customer_id="cus_999",
            lemonsqueezy_variant_id="var_999",
            plan_id=plan.id,
            status="active",
            updated_at=datetime.now(timezone.utc) - timedelta(days=100),
        )
        db_session.add(active_subscription)
        await db_session.commit()

        # Run anonymization
        cleanup_service = DataCleanupService(db=db_session, dry_run=False)
        anonymized_count = await cleanup_service.anonymize_cancelled_subscriptions(
            retention_days=90
        )

        # Should NOT anonymize active subscription
        assert anonymized_count == 0

        await db_session.refresh(active_subscription)
        assert active_subscription.user_id == test_user.id  # User link kept

    async def test_skip_already_anonymized_subscriptions(self, db_session, plan):
        """Should skip subscriptions that are already anonymized."""
        # Create old cancelled subscription with user_id already NULL
        anonymized_subscription = Subscription(
            id=uuid4(),
            user_id=None,  # Already anonymized
            lemonsqueezy_subscription_id="sub_already_anonymized",
            lemonsqueezy_customer_id="cus_anon",
            lemonsqueezy_variant_id="var_anon",
            plan_id=plan.id,
            status="cancelled",
            updated_at=datetime.now(timezone.utc) - timedelta(days=100),
        )
        db_session.add(anonymized_subscription)
        await db_session.commit()

        # Run anonymization
        cleanup_service = DataCleanupService(db=db_session, dry_run=False)
        anonymized_count = await cleanup_service.anonymize_cancelled_subscriptions(
            retention_days=90
        )

        # Should NOT count already-anonymized subscription
        assert anonymized_count == 0

    async def test_dry_run_mode_anonymization(self, db_session, test_user, plan):
        """Should count but not anonymize in dry-run mode."""
        # Create old cancelled subscription
        old_subscription = Subscription(
            id=uuid4(),
            user_id=test_user.id,
            lemonsqueezy_subscription_id="sub_dryrun_anon",
            lemonsqueezy_customer_id="cus_dryrun",
            lemonsqueezy_variant_id="var_dryrun",
            plan_id=plan.id,
            status="cancelled",
            updated_at=datetime.now(timezone.utc) - timedelta(days=100),
        )
        db_session.add(old_subscription)
        await db_session.commit()

        # Run anonymization in dry-run mode
        cleanup_service = DataCleanupService(db=db_session, dry_run=True)
        would_anonymize_count = await cleanup_service.anonymize_cancelled_subscriptions(
            retention_days=90
        )

        # Should report 1 subscription would be anonymized
        assert would_anonymize_count == 1

        # Verify subscription NOT actually anonymized
        await db_session.refresh(old_subscription)
        assert old_subscription.user_id == test_user.id

    async def test_no_subscriptions_to_anonymize(self, db_session):
        """Should handle case when no subscriptions need anonymization."""
        # No subscriptions in database

        cleanup_service = DataCleanupService(db=db_session, dry_run=False)
        anonymized_count = await cleanup_service.anonymize_cancelled_subscriptions(
            retention_days=90
        )

        # Should return 0
        assert anonymized_count == 0


async def _old_and_recent_rows(db: AsyncSession, user: Users) -> dict:
    """One row past each default retention period and one inside it, in every table
    cleanup_all() cleans. Returns the rows by whether they should be deleted."""
    old_log = EmailLog(
        provider="resend", to_email="a@example.com", from_email="b@example.com", subject="old"
    )
    old_log.created_at = _days_ago(40)
    recent_log = EmailLog(
        provider="resend", to_email="a@example.com", from_email="b@example.com", subject="new"
    )
    recent_log.created_at = _days_ago(20)
    db.add_all([old_log, recent_log])
    await db.flush()

    def email_event(days_old: int, log: EmailLog | None) -> EmailEvent:
        return EmailEvent(
            email_log_id=log.id if log else None,
            provider="resend",
            provider_event_id=f"evt_{uuid4().hex}",
            provider_message_id=f"msg_{uuid4().hex}",
            event_type="delivered",
            created_at=_days_ago(days_old),
        )

    def session(**dates) -> UserSession:
        return UserSession(
            user_id=user.id,
            jti=uuid4().hex,
            last_activity_at=dates.get("last_activity_at", _days_ago(1)),
            expires_at=dates.get("expires_at", datetime.now(timezone.utc) + timedelta(days=7)),
            revoked_at=dates.get("revoked_at"),
        )

    def token(expires_at: datetime) -> TokenBlacklist:
        return TokenBlacklist(
            jti=uuid4().hex, token_type="refresh", user_id=user.id, expires_at=expires_at
        )

    def audit(days_old: int) -> AuditLog:
        return AuditLog(action="test", resource_type="test", created_at=_days_ago(days_old))

    def error(days_old: int) -> ErrorLog:
        return ErrorLog(
            severity=ErrorLogSeverity.ERROR, message="test", timestamp=_days_ago(days_old)
        )

    now = datetime.now(timezone.utc)
    rows = {
        "deleted": {
            "audit_logs": [audit(400)],
            "email_logs": [old_log],
            # an old orphan, and an old event whose log is deleted in the same run
            "email_events": [email_event(40, None), email_event(40, old_log)],
            "error_logs": [error(100)],
            "user_sessions": [
                session(last_activity_at=_days_ago(10)),
                session(expires_at=now - timedelta(hours=1)),
                session(revoked_at=now - timedelta(hours=1)),
            ],
            "webhook_events": [_webhook_event(days_old=100)],
            "cleanup_expired_tokens": [token(now - timedelta(hours=1))],
        },
        "kept": {
            "audit_logs": [audit(300)],
            "email_logs": [recent_log],
            "email_events": [email_event(20, None), email_event(40, recent_log)],
            "error_logs": [error(60)],
            "user_sessions": [session()],
            "webhook_events": [
                _webhook_event(days_old=30),
                _webhook_event(days_old=100, processed=False),
                # what a customer paid and was refunded: the admin's refund rows read these
                _webhook_event(days_old=400, name=PAID),
                _webhook_event(days_old=400, name=REFUNDED),
            ],
            "cleanup_expired_tokens": [token(now + timedelta(hours=1))],
        },
    }
    for group in rows.values():
        for table_rows in group.values():
            db.add_all([row for row in table_rows if row not in (old_log, recent_log)])
    await db.commit()
    return rows


async def _exists(db: AsyncSession, row) -> bool:
    model = type(row)
    found = await db.execute(select(model.id).where(model.id == row.id))
    return found.scalar_one_or_none() is not None


@pytest.mark.asyncio
class TestCleanupAll:
    """cleanup_all() over every table it cleans."""

    async def test_cleanup_all_deletes_exactly_what_is_past_each_period(
        self, db_session, test_user
    ):
        rows = await _old_and_recent_rows(db_session, test_user)

        results = await DataCleanupService(db=db_session, dry_run=False).cleanup_all()

        for table, deleted in rows["deleted"].items():
            assert results[table] >= len(deleted), table
            for row in deleted:
                assert not await _exists(db_session, row), table
        for table, kept in rows["kept"].items():
            for row in kept:
                assert await _exists(db_session, row), table

    async def test_dry_run_counts_what_the_real_run_deletes(self, db_session, test_user):
        """The dry run is the preview the nightly job starts with: it deletes nothing, and
        its count for every table is what the real run then deletes. That includes the old
        events of email logs the real run deletes first."""
        rows = await _old_and_recent_rows(db_session, test_user)

        preview = await DataCleanupService(db=db_session, dry_run=True).cleanup_all()

        for group in rows.values():
            for table, table_rows in group.items():
                for row in table_rows:
                    assert await _exists(db_session, row), table

        results = await DataCleanupService(db=db_session, dry_run=False).cleanup_all()

        assert preview == results
        for table, deleted in rows["deleted"].items():
            assert preview[table] >= len(deleted), table

    async def test_a_step_that_fails_does_not_stop_the_steps_after_it(
        self, db_session, test_user, monkeypatch
    ):
        """The nightly run once stopped at the webhook events, every night, and the steps
        after it never ran. Now each step runs whatever the one before it did, and the run
        says at its end which steps failed."""
        rows = await _old_and_recent_rows(db_session, test_user)
        # Read now: the rollback after the failed step expires every loaded row.
        old = {
            table: [(type(row), row.id) for row in table_rows]
            for table, table_rows in rows["deleted"].items()
        }
        service = DataCleanupService(db=db_session, dry_run=False)

        async def there(model, row_id) -> bool:
            found = await db_session.execute(select(model.id).where(model.id == row_id))
            return found.scalar_one_or_none() is not None

        async def a_statement_that_fails() -> int:
            # A failed statement leaves the transaction unusable until it is rolled back.
            await db_session.execute(text("SELECT 1 / 0"))
            return 0

        monkeypatch.setattr(service, "cleanup_webhook_events", a_statement_that_fails)

        with pytest.raises(DataCleanupIncomplete) as incomplete:
            await service.cleanup_all()

        assert incomplete.value.failed == ["webhook_events"]
        assert "webhook_events" not in incomplete.value.results
        for table in ("audit_logs", "user_sessions", "cleanup_expired_tokens"):
            assert incomplete.value.results[table] >= len(old[table]), table
            for model, row_id in old[table]:
                assert not await there(model, row_id), table
        for model, row_id in old["webhook_events"]:
            assert await there(model, row_id)

    async def test_events_of_logs_that_could_not_be_deleted_are_kept(
        self, db_session, test_user, monkeypatch
    ):
        """An event goes when its log has gone. When the logs' step fails, its logs are still
        there, and so are their events; an old event with no log is deleted as before."""
        rows = await _old_and_recent_rows(db_session, test_user)
        orphan, of_the_old_log = rows["deleted"]["email_events"]
        orphan_id, linked_id = orphan.id, of_the_old_log.id
        service = DataCleanupService(db=db_session, dry_run=False)

        async def the_logs_step_fails() -> int:
            await db_session.execute(text("SELECT 1 / 0"))
            return 0

        monkeypatch.setattr(service, "cleanup_email_logs", the_logs_step_fails)

        with pytest.raises(DataCleanupIncomplete) as incomplete:
            await service.cleanup_all()

        assert incomplete.value.failed == ["email_logs"]
        kept = await db_session.execute(
            select(EmailEvent.id).where(EmailEvent.id.in_([orphan_id, linked_id]))
        )
        assert list(kept.scalars()) == [linked_id]

    async def test_cleanup_all_reaches_its_last_step_with_the_settings_as_they_are(
        self, db_session, test_user
    ):
        """No setting a step reads is missing: with nothing patched in, the run ends and
        every step has a count."""
        results = await DataCleanupService(db=db_session, dry_run=True).cleanup_all()

        assert list(results) == [
            "audit_logs",
            "email_logs",
            "email_events",
            "error_logs",
            "user_sessions",
            "webhook_events",
            "cleanup_expired_tokens",
        ]

    async def test_cleanup_all_leaves_cancelled_subscriptions_linked(
        self, db_session, test_user, plan
    ):
        """Anonymization isn't part of the nightly run until it is designed: the user_id
        column is NOT NULL."""
        old_webhook = _webhook_event(days_old=100)
        db_session.add(old_webhook)
        old_subscription = Subscription(
            id=uuid4(),
            user_id=test_user.id,
            lemonsqueezy_subscription_id="sub_cleanup_all",
            lemonsqueezy_customer_id="cus_cleanup",
            lemonsqueezy_variant_id="var_cleanup",
            plan_id=plan.id,
            status="cancelled",
            updated_at=datetime.now(timezone.utc) - timedelta(days=100),
        )
        db_session.add(old_subscription)
        await db_session.commit()

        results = await DataCleanupService(db=db_session, dry_run=False).cleanup_all()

        assert "cancelled_subscriptions_anonymized" not in results
        assert results["webhook_events"] >= 1
        assert await db_session.get(WebhookEvent, old_webhook.id) is None
        await db_session.refresh(old_subscription)
        assert old_subscription.user_id == test_user.id
