"""
Tests for data retention cleanup service (payment-related features).

Tests the new cleanup methods added for Phase 4.3.3:
- cleanup_webhook_events()
- anonymize_cancelled_subscriptions()
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.services.data_cleanup_service import DataCleanupService


@pytest.mark.asyncio
async def test_cleanup_webhook_events_uses_config_default(db_session, monkeypatch):
    monkeypatch.setattr(
        "src.config.cleanup_config.cleanup_config.WEBHOOK_EVENT_RETENTION_DAYS",
        45,
        raising=False,
    )
    service = DataCleanupService(db=db_session, dry_run=True)
    result = await service.cleanup_webhook_events(retention_days=None)
    assert isinstance(result, int)


@pytest.mark.asyncio
async def test_anonymize_subscriptions_uses_config_default(db_session, monkeypatch):
    monkeypatch.setattr(
        "src.config.cleanup_config.cleanup_config.CANCELLED_SUBSCRIPTION_RETENTION_DAYS",
        60,
        raising=False,
    )
    service = DataCleanupService(db=db_session, dry_run=True)
    result = await service.anonymize_cancelled_subscriptions(retention_days=None)
    assert isinstance(result, int)


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

    async def test_anonymize_old_cancelled_subscriptions(self, db_session, test_user):
        """Should anonymize user_id from old cancelled subscriptions."""
        # Create old cancelled subscription (100 days old)
        old_subscription = UserSubscription(
            id=uuid4(),
            user_id=test_user.id,
            subscription_id="sub_old_cancelled_123",
            customer_id="cus_123",
            variant_id="var_123",
            plan_id=uuid4(),
            status="cancelled",
            updated_at=datetime.now(timezone.utc) - timedelta(days=100),
        )
        db_session.add(old_subscription)

        # Create recent cancelled subscription (30 days old)
        recent_subscription = UserSubscription(
            id=uuid4(),
            user_id=test_user.id,
            subscription_id="sub_recent_cancelled_456",
            customer_id="cus_456",
            variant_id="var_456",
            plan_id=uuid4(),
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
        assert old_subscription.subscription_id == "sub_old_cancelled_123"  # Other data kept

        # Verify recent subscription NOT anonymized
        await db_session.refresh(recent_subscription)
        assert recent_subscription.user_id == test_user.id

    async def test_anonymize_old_expired_subscriptions(self, db_session, test_user):
        """Should anonymize expired subscriptions as well as cancelled."""
        # Create old expired subscription (100 days old)
        expired_subscription = UserSubscription(
            id=uuid4(),
            user_id=test_user.id,
            subscription_id="sub_old_expired_789",
            customer_id="cus_789",
            variant_id="var_789",
            plan_id=uuid4(),
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

    async def test_keep_active_subscriptions(self, db_session, test_user):
        """Should NOT anonymize active subscriptions."""
        # Create old active subscription (100 days old)
        active_subscription = UserSubscription(
            id=uuid4(),
            user_id=test_user.id,
            subscription_id="sub_old_active_999",
            customer_id="cus_999",
            variant_id="var_999",
            plan_id=uuid4(),
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

    async def test_skip_already_anonymized_subscriptions(self, db_session):
        """Should skip subscriptions that are already anonymized."""
        # Create old cancelled subscription with user_id already NULL
        anonymized_subscription = UserSubscription(
            id=uuid4(),
            user_id=None,  # Already anonymized
            subscription_id="sub_already_anonymized",
            customer_id="cus_anon",
            variant_id="var_anon",
            plan_id=uuid4(),
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

    async def test_dry_run_mode_anonymization(self, db_session, test_user):
        """Should count but not anonymize in dry-run mode."""
        # Create old cancelled subscription
        old_subscription = UserSubscription(
            id=uuid4(),
            user_id=test_user.id,
            subscription_id="sub_dryrun_anon",
            customer_id="cus_dryrun",
            variant_id="var_dryrun",
            plan_id=uuid4(),
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


@pytest.mark.asyncio
class TestCleanupAll:
    """Test cleanup_all() method with new payment features."""

    async def test_cleanup_all_includes_payment_data(self, db_session, test_user):
        """Should run all cleanup tasks including new payment-related ones."""
        # Create old webhook event
        old_webhook = WebhookEvent(
            id=uuid4(),
            event_id="evt_cleanup_all",
            event_name="subscription_created",
            payload={"test": "data"},
            processed=True,
            created_at=datetime.now(timezone.utc) - timedelta(days=100),
        )
        db_session.add(old_webhook)

        # Create old cancelled subscription
        old_subscription = UserSubscription(
            id=uuid4(),
            user_id=test_user.id,
            subscription_id="sub_cleanup_all",
            customer_id="cus_cleanup",
            variant_id="var_cleanup",
            plan_id=uuid4(),
            status="cancelled",
            updated_at=datetime.now(timezone.utc) - timedelta(days=100),
        )
        db_session.add(old_subscription)
        await db_session.commit()

        # Run cleanup_all()
        cleanup_service = DataCleanupService(db=db_session, dry_run=False)
        results = await cleanup_service.cleanup_all()

        # Verify results include new cleanup tasks
        assert "webhook_events" in results
        assert "cancelled_subscriptions_anonymized" in results

        # Verify cleanup was performed
        assert results["webhook_events"] == 1
        assert results["cancelled_subscriptions_anonymized"] == 1

        # Verify webhook deleted
        webhook_check = await db_session.get(WebhookEvent, old_webhook.id)
        assert webhook_check is None

        # Verify subscription anonymized
        await db_session.refresh(old_subscription)
        assert old_subscription.user_id is None
