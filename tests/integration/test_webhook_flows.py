"""
Integration tests for webhook flows.

Tests webhook event processing with real database interactions.
Covers complete webhook lifecycle from receipt to database update.

Tests cover:
- Webhook event processing end-to-end
- Email log status updates from webhooks
- Event deduplication (idempotency)
- Multiple events for same email (delivered -> opened -> clicked)
- Error scenarios
"""

import pytest
from uuid import uuid4
from datetime import datetime
from unittest.mock import patch

from src.services.email_service import EmailService
from src.services.email_event_service import EmailEventService
from src.api.models.email_models.email_log import EmailLog
from src.api.models.email_models.email_event import EmailEvent
from src.providers.email.mock_provider import MockEmailProvider
from sqlalchemy import select


class TestWebhookEventProcessing:
    """Test webhook event processing flows"""

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_delivered_webhook_updates_status(
        self,
        mock_get_fallback,
        mock_get_provider,
        mock_config,
        db_session
    ):
        """Should process delivered webhook and update email status"""
        # Setup
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        mock_config.email_enabled = True
        mock_config.resend_from_email = "noreply@wrext.com"
        mock_config.resend_from_name = "WREXT"

        # Send an email first
        email_service = EmailService(db_session)
        email_log = await email_service.send_email(
            to="test@example.com",
            subject="Test",
            html="<p>Test</p>"
        )

        assert email_log.status == "sent"
        provider_message_id = email_log.provider_message_id

        # Process delivered webhook
        event_service = EmailEventService(db_session)

        webhook_payload = {
            "type": "email.delivered",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "data": {
                "email_id": provider_message_id,
                "to": "test@example.com",
                "subject": "Test"
            }
        }

        result = await event_service.process_webhook_event(webhook_payload)

        # Verify processing successful
        assert result.success is True
        assert result.event_type == "email.delivered"
        assert result.event_id is not None

        # Verify email log status updated
        await db_session.refresh(email_log)
        assert email_log.status == "delivered"
        assert email_log.delivered_at is not None

        # Verify event created in database
        events_result = await db_session.execute(
            select(EmailEvent).where(EmailEvent.email_log_id == email_log.id)
        )
        events = events_result.scalars().all()

        assert len(events) == 1
        assert events[0].event_type == "email.delivered"
        assert events[0].provider_message_id == provider_message_id

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_bounced_webhook_marks_failure(
        self,
        mock_get_fallback,
        mock_get_provider,
        mock_config,
        db_session
    ):
        """Should process bounced webhook and mark email as bounced"""
        # Setup and send email
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        mock_config.email_enabled = True
        mock_config.resend_from_email = "noreply@wrext.com"
        mock_config.resend_from_name = "WREXT"

        email_service = EmailService(db_session)
        email_log = await email_service.send_email(
            to="invalid@example.com",
            subject="Test",
            html="<p>Test</p>"
        )

        provider_message_id = email_log.provider_message_id

        # Process bounced webhook
        event_service = EmailEventService(db_session)

        webhook_payload = {
            "type": "email.bounced",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "data": {
                "email_id": provider_message_id,
                "to": "invalid@example.com",
                "bounce_type": "hard",
                "reason": "Mailbox does not exist"
            }
        }

        result = await event_service.process_webhook_event(webhook_payload)

        # Verify processing successful
        assert result.success is True

        # Verify email log status updated to bounced
        await db_session.refresh(email_log)
        assert email_log.status == "bounced"
        assert email_log.failed_at is not None


class TestWebhookIdempotency:
    """Test webhook event deduplication"""

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_duplicate_webhook_ignored(
        self,
        mock_get_fallback,
        mock_get_provider,
        mock_config,
        db_session
    ):
        """Should ignore duplicate webhook events"""
        # Setup and send email
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        mock_config.email_enabled = True
        mock_config.resend_from_email = "noreply@wrext.com"
        mock_config.resend_from_name = "WREXT"

        email_service = EmailService(db_session)
        email_log = await email_service.send_email(
            to="test@example.com",
            subject="Test",
            html="<p>Test</p>"
        )

        provider_message_id = email_log.provider_message_id

        event_service = EmailEventService(db_session)

        # Same webhook payload
        webhook_payload = {
            "type": "email.delivered",
            "created_at": "2025-10-12T12:00:00Z",
            "data": {
                "email_id": provider_message_id,
                "to": "test@example.com"
            }
        }

        # Process webhook first time
        result1 = await event_service.process_webhook_event(webhook_payload)
        assert result1.success is True

        # Process same webhook again (duplicate)
        result2 = await event_service.process_webhook_event(webhook_payload)

        # Should recognize as duplicate
        assert result2.success is True
        assert "duplicate" in result2.message.lower()
        assert result2.event_id == result1.event_id  # Same event ID

        # Verify only ONE event created in database
        events_result = await db_session.execute(
            select(EmailEvent).where(EmailEvent.email_log_id == email_log.id)
        )
        events = events_result.scalars().all()

        assert len(events) == 1  # Only one event, not two


class TestWebhookEventSequence:
    """Test multiple webhook events for same email"""

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_email_lifecycle_events(
        self,
        mock_get_fallback,
        mock_get_provider,
        mock_config,
        db_session
    ):
        """Should handle complete email lifecycle: sent -> delivered -> opened -> clicked"""
        # Setup and send email
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        mock_config.email_enabled = True
        mock_config.resend_from_email = "noreply@wrext.com"
        mock_config.resend_from_name = "WREXT"

        email_service = EmailService(db_session)
        email_log = await email_service.send_email(
            to="engaged@example.com",
            subject="Test",
            html='<p>Test with <a href="https://wrext.com">link</a></p>'
        )

        provider_message_id = email_log.provider_message_id
        event_service = EmailEventService(db_session)

        # Event 1: Delivered
        delivered_payload = {
            "type": "email.delivered",
            "created_at": "2025-10-12T12:00:00Z",
            "data": {
                "email_id": provider_message_id,
                "to": "engaged@example.com"
            }
        }
        await event_service.process_webhook_event(delivered_payload)

        # Event 2: Opened
        opened_payload = {
            "type": "email.opened",
            "created_at": "2025-10-12T12:05:00Z",
            "data": {
                "email_id": provider_message_id,
                "to": "engaged@example.com"
            }
        }
        await event_service.process_webhook_event(opened_payload)

        # Event 3: Clicked
        clicked_payload = {
            "type": "email.clicked",
            "created_at": "2025-10-12T12:10:00Z",
            "data": {
                "email_id": provider_message_id,
                "to": "engaged@example.com",
                "link": "https://wrext.com"
            }
        }
        await event_service.process_webhook_event(clicked_payload)

        # Verify final status
        await db_session.refresh(email_log)
        assert email_log.status == "delivered"  # Final status

        # Verify all events stored
        events_result = await db_session.execute(
            select(EmailEvent)
            .where(EmailEvent.email_log_id == email_log.id)
            .order_by(EmailEvent.created_at.asc())
        )
        events = events_result.scalars().all()

        assert len(events) == 3
        assert events[0].event_type == "email.delivered"
        assert events[1].event_type == "email.opened"
        assert events[2].event_type == "email.clicked"


class TestWebhookErrorHandling:
    """Test webhook error scenarios"""

    @pytest.mark.asyncio
    async def test_webhook_for_unknown_email(self, db_session):
        """Should handle webhook for email that doesn't exist in our system"""
        event_service = EmailEventService(db_session)

        webhook_payload = {
            "type": "email.delivered",
            "created_at": "2025-10-12T12:00:00Z",
            "data": {
                "email_id": "unknown_message_id_12345",
                "to": "unknown@example.com"
            }
        }

        result = await event_service.process_webhook_event(webhook_payload)

        # Should still process (create orphan event for tracking)
        assert result.success is True
        assert result.email_log_id is None  # No linked email log

        # Verify event created
        events_result = await db_session.execute(
            select(EmailEvent).where(
                EmailEvent.provider_message_id == "unknown_message_id_12345"
            )
        )
        events = events_result.scalars().all()

        assert len(events) == 1
        assert events[0].email_log_id is None  # Orphan event

    @pytest.mark.asyncio
    async def test_webhook_missing_email_id(self, db_session):
        """Should reject webhook missing required email_id"""
        event_service = EmailEventService(db_session)

        webhook_payload = {
            "type": "email.delivered",
            "created_at": "2025-10-12T12:00:00Z",
            "data": {
                # Missing email_id
                "to": "test@example.com"
            }
        }

        result = await event_service.process_webhook_event(webhook_payload)

        # Should fail gracefully
        assert result.success is False
        assert "Missing email_id" in result.message

        # No event should be created
        events_result = await db_session.execute(select(EmailEvent))
        events = events_result.scalars().all()

        assert len(events) == 0
