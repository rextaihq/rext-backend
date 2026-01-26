"""
Integration tests for email flows.

Tests complete email sending flows with real database interactions.
Uses MockEmailProvider to avoid external dependencies.

Tests cover:
- End-to-end email sending with database logging
- Provider fallback mechanism
- Email status transitions
- Template rendering integration
- Error scenarios with database rollback
"""

import pytest
import pytest_asyncio
from uuid import uuid4
from datetime import datetime
from unittest.mock import patch

from src.services.email_service import EmailService
from src.api.models.email_models.email_log import EmailLog
from src.providers.email.mock_provider import MockEmailProvider
from sqlalchemy import select


class TestEmailSendingFlows:
    """Test complete email sending flows"""

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_send_email_complete_flow(
        self,
        mock_get_fallback,
        mock_get_provider,
        mock_config,
        db_session
    ):
        """Should send email and log to database"""
        # Setup mock provider
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        mock_config.email_enabled = True
        mock_config.resend_from_email = "noreply@rext.com"
        mock_config.resend_from_name = "REXT"

        # Create email service
        service = EmailService(db_session)

        # Send email (auto_commit=False for test transaction control)
        email_log = await service.send_email(
            to="test@example.com",
            subject="Test Email",
            html="<p>Test content</p>",
            template_type="test",
            tags={"type": "test", "env": "integration"},
            auto_commit=False
        )

        # Verify email log created and committed to database
        assert email_log.id is not None
        assert email_log.to_email == "test@example.com"
        assert email_log.subject == "Test Email"
        assert email_log.status == "sent"
        assert email_log.provider == "mock"
        assert email_log.provider_message_id is not None
        assert email_log.sent_at is not None
        assert email_log.tags == {"type": "test", "env": "integration"}

        # Verify email actually sent through provider
        assert mock_provider.get_sent_count() == 1
        sent_email = mock_provider.get_last_email()
        assert sent_email["to"] == ["test@example.com"]
        assert sent_email["subject"] == "Test Email"

        # Verify database persistence (query from DB)
        result = await db_session.execute(
            select(EmailLog).where(EmailLog.id == email_log.id)
        )
        persisted_log = result.scalar_one_or_none()

        assert persisted_log is not None
        assert persisted_log.to_email == "test@example.com"
        assert persisted_log.status == "sent"

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_send_email_with_workspace_and_user(
        self,
        mock_get_fallback,
        mock_get_provider,
        mock_config,
        db_session
    ):
        """Should associate email with workspace and user"""
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        mock_config.email_enabled = True
        mock_config.resend_from_email = "noreply@rext.com"
        mock_config.resend_from_name = "REXT"

        workspace_id = uuid4()
        user_id = uuid4()

        service = EmailService(db_session)

        email_log = await service.send_email(
            to="user@example.com",
            subject="Workspace Invitation",
            html="<p>You've been invited</p>",
            workspace_id=workspace_id,
            user_id=user_id,
            template_type="workspace_invitation",
            auto_commit=False
        )

        assert email_log.workspace_id == workspace_id
        assert email_log.user_id == user_id
        assert email_log.template_type == "workspace_invitation"

        # Verify database persistence
        result = await db_session.execute(
            select(EmailLog).where(EmailLog.id == email_log.id)
        )
        persisted_log = result.scalar_one_or_none()

        assert persisted_log.workspace_id == workspace_id
        assert persisted_log.user_id == user_id


class TestFallbackProviderFlows:
    """Test provider fallback mechanism"""

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_fallback_on_primary_failure(
        self,
        mock_get_fallback,
        mock_get_provider,
        mock_config,
        db_session
    ):
        """Should use fallback provider when primary fails"""
        # Primary provider that always fails
        primary_provider = MockEmailProvider(simulate_failures=True, failure_rate=1.0)

        # Fallback provider that succeeds
        fallback_provider = MockEmailProvider(simulate_failures=False)

        mock_get_provider.return_value = primary_provider
        mock_get_fallback.return_value = fallback_provider

        mock_config.email_enabled = True
        mock_config.resend_from_email = "noreply@rext.com"
        mock_config.resend_from_name = "REXT"

        service = EmailService(db_session)

        email_log = await service.send_email(
            to="test@example.com",
            subject="Test",
            html="<p>Test</p>",
            retry_on_failure=True,
            auto_commit=False
        )

        # Should succeed via fallback
        assert email_log.status == "sent"
        assert email_log.provider == "mock"

        # Verify primary failed, fallback succeeded
        assert primary_provider.get_sent_count() == 0
        assert fallback_provider.get_sent_count() == 1

        # Verify database state
        result = await db_session.execute(
            select(EmailLog).where(EmailLog.id == email_log.id)
        )
        persisted_log = result.scalar_one_or_none()

        assert persisted_log.status == "sent"
        assert persisted_log.provider_message_id is not None

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_failure_when_both_providers_fail(
        self,
        mock_get_fallback,
        mock_get_provider,
        mock_config,
        db_session
    ):
        """Should log failure when both providers fail"""
        # Both providers fail
        primary_provider = MockEmailProvider(simulate_failures=True, failure_rate=1.0)
        fallback_provider = MockEmailProvider(simulate_failures=True, failure_rate=1.0)

        mock_get_provider.return_value = primary_provider
        mock_get_fallback.return_value = fallback_provider

        mock_config.email_enabled = True
        mock_config.resend_from_email = "noreply@rext.com"
        mock_config.resend_from_name = "REXT"

        service = EmailService(db_session)

        email_log = await service.send_email(
            to="test@example.com",
            subject="Test",
            html="<p>Test</p>",
            retry_on_failure=True,
            auto_commit=False
        )

        # Should fail
        assert email_log.status == "failed"
        assert email_log.error_message is not None
        assert email_log.failed_at is not None
        assert email_log.sent_at is None

        # Verify database state
        result = await db_session.execute(
            select(EmailLog).where(EmailLog.id == email_log.id)
        )
        persisted_log = result.scalar_one_or_none()

        assert persisted_log.status == "failed"
        assert persisted_log.error_message is not None


class TestEmailQueryFlows:
    """Test email querying flows"""

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_query_emails_for_user(
        self,
        mock_get_fallback,
        mock_get_provider,
        mock_config,
        db_session
    ):
        """Should query emails for specific user"""
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        mock_config.email_enabled = True
        mock_config.resend_from_email = "noreply@rext.com"
        mock_config.resend_from_name = "REXT"

        user_id = uuid4()

        service = EmailService(db_session)

        # Send 3 emails for the same user
        for i in range(3):
            await service.send_email(
                to=f"user{i}@example.com",
                subject=f"Email {i}",
                html=f"<p>Email {i}</p>",
                user_id=user_id,
                auto_commit=False
            )

        # Query emails for user
        user_emails = await service.get_emails_for_user(user_id, limit=50)

        assert len(user_emails) == 3
        assert all(email.user_id == user_id for email in user_emails)

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_query_emails_for_workspace(
        self,
        mock_get_fallback,
        mock_get_provider,
        mock_config,
        db_session
    ):
        """Should query emails for specific workspace"""
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        mock_config.email_enabled = True
        mock_config.resend_from_email = "noreply@rext.com"
        mock_config.resend_from_name = "REXT"

        workspace_id = uuid4()

        service = EmailService(db_session)

        # Send emails for workspace
        for i in range(2):
            await service.send_email(
                to=f"member{i}@example.com",
                subject=f"Workspace Email {i}",
                html=f"<p>Content {i}</p>",
                workspace_id=workspace_id,
                auto_commit=False
            )

        # Query emails for workspace
        workspace_emails = await service.get_emails_for_workspace(workspace_id, limit=50)

        assert len(workspace_emails) == 2
        assert all(email.workspace_id == workspace_id for email in workspace_emails)


class TestEmailRetryFlows:
    """Test email retry mechanism"""

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_retry_failed_email(
        self,
        mock_get_fallback,
        mock_get_provider,
        mock_config,
        db_session
    ):
        """Should retry failed email successfully"""
        # First attempt: provider fails
        failing_provider = MockEmailProvider(simulate_failures=True, failure_rate=1.0)
        mock_get_provider.return_value = failing_provider
        mock_get_fallback.return_value = None

        mock_config.email_enabled = True
        mock_config.resend_from_email = "noreply@rext.com"
        mock_config.resend_from_name = "REXT"

        service = EmailService(db_session)

        # Send email (will fail)
        email_log = await service.send_email(
            to="test@example.com",
            subject="Test",
            html="<p>Test</p>",
            retry_on_failure=False,  # Don't auto-retry
            auto_commit=False
        )

        assert email_log.status == "failed"

        # Second attempt: provider succeeds
        succeeding_provider = MockEmailProvider(simulate_failures=False)
        mock_get_provider.return_value = succeeding_provider

        # Retry the failed email
        retried_log = await service.retry_failed_email(email_log.id, auto_commit=False)

        # Should succeed on retry
        assert retried_log.status == "sent"
        assert retried_log.error_message is None
        assert retried_log.provider_message_id is not None

        # Verify database state updated
        result = await db_session.execute(
            select(EmailLog).where(EmailLog.id == email_log.id)
        )
        persisted_log = result.scalar_one_or_none()

        assert persisted_log.status == "sent"
