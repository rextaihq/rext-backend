"""
Unit tests for EmailEventService.

Tests cover:
- process_webhook_event: Event processing and deduplication
- Email log status updates based on event types
- Idempotency (duplicate event handling)
- get_events_for_email_log: Query events for specific email
- Error handling for malformed webhooks
"""

import pytest
from uuid import uuid4
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from src.services.email_event_service import EmailEventService
from src.api.models.email_models.email_event import EmailEvent
from src.api.models.email_models.email_log import EmailLog
from src.api.schema.webhook_schema import WebhookProcessingResult


class TestEmailEventServiceProcessWebhook:
    """Test process_webhook_event method"""

    @pytest.mark.asyncio
    async def test_process_webhook_delivered_event(self):
        """Should process delivered event and update email log status"""
        mock_db = AsyncMock()

        # Mock email log (existing sent email)
        email_log = EmailLog(
            id=uuid4(),
            provider_message_id="msg_abc123",
            to_email="test@example.com",
            subject="Test",
            status="sent",
            provider="resend",
            from_email="noreply@wrext.com"
        )

        # Mock database queries
        mock_log_result = Mock()
        mock_log_result.scalar_one_or_none.return_value = email_log

        mock_event_result = Mock()
        mock_event_result.scalar_one_or_none.return_value = None  # No duplicate

        mock_db.execute.side_effect = [
            mock_event_result,  # First call: check for duplicate
            mock_log_result,    # Second call: find email log
        ]

        service = EmailEventService(mock_db)

        # Webhook payload for delivered event
        webhook_payload = {
            "type": "email.delivered",
            "created_at": "2025-10-12T12:00:00Z",
            "data": {
                "email_id": "msg_abc123",
                "to": "test@example.com",
                "subject": "Test"
            }
        }

        result = await service.process_webhook_event(webhook_payload)

        # Verify result
        assert result.success is True
        assert result.event_type == "email.delivered"
        assert result.event_id is not None

        # Verify email log status updated
        assert email_log.status == "delivered"
        assert email_log.delivered_at is not None

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_webhook_bounced_event(self):
        """Should process bounced event and mark email as failed"""
        mock_db = AsyncMock()

        email_log = EmailLog(
            id=uuid4(),
            provider_message_id="msg_bounced",
            to_email="invalid@example.com",
            subject="Test",
            status="sent",
            provider="resend",
            from_email="noreply@wrext.com"
        )

        mock_log_result = Mock()
        mock_log_result.scalar_one_or_none.return_value = email_log

        mock_event_result = Mock()
        mock_event_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_event_result, mock_log_result]

        service = EmailEventService(mock_db)

        webhook_payload = {
            "type": "email.bounced",
            "created_at": "2025-10-12T12:00:00Z",
            "data": {
                "email_id": "msg_bounced",
                "to": "invalid@example.com",
                "bounce_type": "hard"
            }
        }

        result = await service.process_webhook_event(webhook_payload)

        assert result.success is True
        assert result.event_type == "email.bounced"

        # Verify status updated to bounced
        assert email_log.status == "bounced"
        assert email_log.failed_at is not None

    @pytest.mark.asyncio
    async def test_process_webhook_complained_event(self):
        """Should process spam complaint event"""
        mock_db = AsyncMock()

        email_log = EmailLog(
            id=uuid4(),
            provider_message_id="msg_spam",
            to_email="complainer@example.com",
            subject="Test",
            status="delivered",
            provider="resend",
            from_email="noreply@wrext.com"
        )

        mock_log_result = Mock()
        mock_log_result.scalar_one_or_none.return_value = email_log

        mock_event_result = Mock()
        mock_event_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_event_result, mock_log_result]

        service = EmailEventService(mock_db)

        webhook_payload = {
            "type": "email.complained",
            "created_at": "2025-10-12T12:00:00Z",
            "data": {
                "email_id": "msg_spam",
                "to": "complainer@example.com"
            }
        }

        result = await service.process_webhook_event(webhook_payload)

        assert result.success is True
        assert result.event_type == "email.complained"

        # Verify status updated to complained
        assert email_log.status == "complained"

    @pytest.mark.asyncio
    async def test_process_webhook_opened_event(self):
        """Should process opened event without changing status"""
        mock_db = AsyncMock()

        email_log = EmailLog(
            id=uuid4(),
            provider_message_id="msg_opened",
            to_email="reader@example.com",
            subject="Test",
            status="delivered",
            provider="resend",
            from_email="noreply@wrext.com"
        )

        original_status = email_log.status

        mock_log_result = Mock()
        mock_log_result.scalar_one_or_none.return_value = email_log

        mock_event_result = Mock()
        mock_event_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_event_result, mock_log_result]

        service = EmailEventService(mock_db)

        webhook_payload = {
            "type": "email.opened",
            "created_at": "2025-10-12T12:00:00Z",
            "data": {
                "email_id": "msg_opened",
                "to": "reader@example.com"
            }
        }

        result = await service.process_webhook_event(webhook_payload)

        assert result.success is True
        assert result.event_type == "email.opened"

        # Status should NOT change (just tracking)
        assert email_log.status == original_status

    @pytest.mark.asyncio
    async def test_process_webhook_clicked_event(self):
        """Should process clicked event without changing status"""
        mock_db = AsyncMock()

        email_log = EmailLog(
            id=uuid4(),
            provider_message_id="msg_clicked",
            to_email="clicker@example.com",
            subject="Test",
            status="delivered",
            provider="resend",
            from_email="noreply@wrext.com"
        )

        original_status = email_log.status

        mock_log_result = Mock()
        mock_log_result.scalar_one_or_none.return_value = email_log

        mock_event_result = Mock()
        mock_event_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_event_result, mock_log_result]

        service = EmailEventService(mock_db)

        webhook_payload = {
            "type": "email.clicked",
            "created_at": "2025-10-12T12:00:00Z",
            "data": {
                "email_id": "msg_clicked",
                "to": "clicker@example.com",
                "link": "https://wrext.com/verify"
            }
        }

        result = await service.process_webhook_event(webhook_payload)

        assert result.success is True
        assert result.event_type == "email.clicked"

        # Status should NOT change
        assert email_log.status == original_status


class TestEmailEventServiceIdempotency:
    """Test event deduplication (idempotency)"""

    @pytest.mark.asyncio
    async def test_duplicate_event_ignored(self):
        """Should ignore duplicate webhook events"""
        mock_db = AsyncMock()

        # Existing event (already processed)
        existing_event = EmailEvent(
            id=uuid4(),
            email_log_id=uuid4(),
            provider="resend",
            provider_event_id="msg_123_email.delivered_2025-10-12T12:00:00Z",
            provider_message_id="msg_123",
            event_type="email.delivered",
            event_data={},
            created_at=datetime.utcnow()
        )

        mock_event_result = Mock()
        mock_event_result.scalar_one_or_none.return_value = existing_event

        mock_db.execute.return_value = mock_event_result

        service = EmailEventService(mock_db)

        webhook_payload = {
            "type": "email.delivered",
            "created_at": "2025-10-12T12:00:00Z",
            "data": {
                "email_id": "msg_123",
                "to": "test@example.com"
            }
        }

        result = await service.process_webhook_event(webhook_payload)

        # Should succeed but recognize duplicate
        assert result.success is True
        assert "duplicate" in result.message.lower()
        assert result.event_id == str(existing_event.id)

        # Should NOT add new event to database
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()


class TestEmailEventServiceErrorHandling:
    """Test error handling for malformed webhooks"""

    @pytest.mark.asyncio
    async def test_missing_email_id(self):
        """Should handle webhook missing email_id"""
        mock_db = AsyncMock()
        service = EmailEventService(mock_db)

        webhook_payload = {
            "type": "email.delivered",
            "created_at": "2025-10-12T12:00:00Z",
            "data": {
                # Missing email_id
                "to": "test@example.com"
            }
        }

        result = await service.process_webhook_event(webhook_payload)

        assert result.success is False
        assert "Missing email_id" in result.message

    @pytest.mark.asyncio
    async def test_email_log_not_found(self):
        """Should handle case where email log doesn't exist"""
        mock_db = AsyncMock()

        # No existing event (not duplicate)
        mock_event_result = Mock()
        mock_event_result.scalar_one_or_none.return_value = None

        # No email log found
        mock_log_result = Mock()
        mock_log_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_event_result, mock_log_result]

        service = EmailEventService(mock_db)

        webhook_payload = {
            "type": "email.delivered",
            "created_at": "2025-10-12T12:00:00Z",
            "data": {
                "email_id": "msg_unknown",
                "to": "unknown@example.com"
            }
        }

        result = await service.process_webhook_event(webhook_payload)

        # Should still create event (for tracking) even without log
        assert result.success is True
        assert result.email_log_id is None  # No email log linked

        # Event should still be created
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_timestamp(self):
        """Should handle invalid timestamp gracefully"""
        mock_db = AsyncMock()

        email_log = EmailLog(
            id=uuid4(),
            provider_message_id="msg_123",
            to_email="test@example.com",
            subject="Test",
            status="sent",
            provider="resend",
            from_email="noreply@wrext.com"
        )

        mock_log_result = Mock()
        mock_log_result.scalar_one_or_none.return_value = email_log

        mock_event_result = Mock()
        mock_event_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_event_result, mock_log_result]

        service = EmailEventService(mock_db)

        webhook_payload = {
            "type": "email.delivered",
            "created_at": "invalid_timestamp",  # Invalid format
            "data": {
                "email_id": "msg_123",
                "to": "test@example.com"
            }
        }

        result = await service.process_webhook_event(webhook_payload)

        # Should succeed (uses current time as fallback)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_database_error(self):
        """Should handle database errors gracefully"""
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("Database connection lost")

        service = EmailEventService(mock_db)

        webhook_payload = {
            "type": "email.delivered",
            "created_at": "2025-10-12T12:00:00Z",
            "data": {
                "email_id": "msg_123",
                "to": "test@example.com"
            }
        }

        result = await service.process_webhook_event(webhook_payload)

        assert result.success is False
        assert "Error processing event" in result.message

        # Should rollback transaction
        mock_db.rollback.assert_called_once()


class TestEmailEventServiceQueryMethods:
    """Test query methods"""

    @pytest.mark.asyncio
    async def test_get_events_for_email_log(self):
        """Should retrieve all events for specific email log"""
        mock_db = AsyncMock()

        email_log_id = uuid4()
        mock_events = [
            EmailEvent(id=uuid4(), email_log_id=email_log_id, event_type="email.delivered", provider="resend", provider_message_id="msg_1", event_data={}, created_at=datetime.utcnow()),
            EmailEvent(id=uuid4(), email_log_id=email_log_id, event_type="email.opened", provider="resend", provider_message_id="msg_1", event_data={}, created_at=datetime.utcnow()),
        ]

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_events
        mock_db.execute.return_value = mock_result

        service = EmailEventService(mock_db)
        events = await service.get_events_for_email_log(email_log_id, limit=50)

        assert len(events) == 2
        assert all(event.email_log_id == email_log_id for event in events)

    @pytest.mark.asyncio
    async def test_get_recent_events(self):
        """Should retrieve recent events within time window"""
        mock_db = AsyncMock()

        mock_events = [
            EmailEvent(id=uuid4(), email_log_id=uuid4(), event_type="email.delivered", provider="resend", provider_message_id="msg_1", event_data={}, created_at=datetime.utcnow()),
            EmailEvent(id=uuid4(), email_log_id=uuid4(), event_type="email.bounced", provider="resend", provider_message_id="msg_2", event_data={}, created_at=datetime.utcnow()),
        ]

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_events
        mock_db.execute.return_value = mock_result

        service = EmailEventService(mock_db)
        events = await service.get_recent_events(hours=24, limit=100)

        assert len(events) == 2
