"""
Unit tests for EmailService.

Tests cover:
- send_email: Email sending with database logging
- Retry logic with fallback provider
- Email disabled handling
- Query methods (get_email_log, get_emails_for_user, get_emails_for_workspace)
- retry_failed_email: Retry mechanism
- Error handling and logging
"""

import pytest
from uuid import uuid4, UUID
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from src.services.email_service import EmailService
from src.api.models.email_models.email_log import EmailLog
from src.providers.email.base import EmailMessage, EmailRecipient, EmailResult
from src.providers.email.mock_provider import MockEmailProvider


class TestEmailServiceInitialization:
    """Test EmailService initialization"""

    @pytest.mark.asyncio
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_initialization(self, mock_get_fallback, mock_get_provider):
        """Should initialize with primary and fallback providers"""
        mock_db = AsyncMock()
        mock_primary = MockEmailProvider()
        mock_fallback = MockEmailProvider()

        mock_get_provider.return_value = mock_primary
        mock_get_fallback.return_value = mock_fallback

        service = EmailService(mock_db)

        assert service.db == mock_db
        assert service.primary_provider == mock_primary
        assert service.fallback_provider == mock_fallback

    @pytest.mark.asyncio
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_initialization_no_fallback(self, mock_get_fallback, mock_get_provider):
        """Should initialize without fallback provider"""
        mock_db = AsyncMock()
        mock_primary = MockEmailProvider()

        mock_get_provider.return_value = mock_primary
        mock_get_fallback.return_value = None  # No fallback

        service = EmailService(mock_db)

        assert service.primary_provider == mock_primary
        assert service.fallback_provider is None


class TestEmailServiceSendEmail:
    """Test send_email method"""

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_send_email_success(self, mock_get_fallback, mock_get_provider, mock_config):
        """Should send email successfully and log to database"""
        # Setup
        mock_db = AsyncMock()
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        mock_config.email_enabled = True
        mock_config.resend_from_email = "noreply@rext.com"
        mock_config.resend_from_name = "REXT"

        service = EmailService(mock_db)

        # Execute
        email_log = await service.send_email(
            to="test@example.com",
            subject="Test Subject",
            html="<p>Test Body</p>",
            workspace_id=uuid4(),
            template_type="test",
            tags={"type": "test"}
        )

        # Verify
        assert email_log is not None
        assert email_log.to_email == "test@example.com"
        assert email_log.subject == "Test Subject"
        assert email_log.status == "sent"
        assert email_log.provider == "mock"
        assert email_log.provider_message_id is not None

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_called_once()
        # Note: refresh() removed to fix transaction issues in integration tests

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_send_email_with_cc_bcc(self, mock_get_fallback, mock_get_provider, mock_config):
        """Should handle CC and BCC recipients"""
        mock_db = AsyncMock()
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        mock_config.email_enabled = True
        mock_config.resend_from_email = "noreply@rext.com"
        mock_config.resend_from_name = "REXT"

        service = EmailService(mock_db)

        email_log = await service.send_email(
            to="to@example.com",
            subject="Test",
            html="<p>Test</p>",
            cc=["cc@example.com"],
            bcc=["bcc@example.com"]
        )

        assert email_log.status == "sent"

        # Verify email was sent with CC/BCC
        last_email = mock_provider.get_last_email()
        assert last_email["cc"] == ["cc@example.com"]
        assert last_email["bcc"] == ["bcc@example.com"]

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_send_email_disabled(self, mock_get_fallback, mock_get_provider, mock_config):
        """Should raise exception when email sending is disabled"""
        mock_db = AsyncMock()
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        mock_config.email_enabled = False

        service = EmailService(mock_db)

        with pytest.raises(Exception, match="Email sending is disabled"):
            await service.send_email(
                to="test@example.com",
                subject="Test",
                html="<p>Test</p>"
            )

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_send_email_provider_failure_with_fallback(
        self, mock_get_fallback, mock_get_provider, mock_config
    ):
        """Should use fallback provider when primary fails"""
        mock_db = AsyncMock()

        # Primary provider that fails
        mock_primary = MockEmailProvider(simulate_failures=True, failure_rate=1.0)

        # Fallback provider that succeeds
        mock_fallback = MockEmailProvider(simulate_failures=False)

        mock_get_provider.return_value = mock_primary
        mock_get_fallback.return_value = mock_fallback

        mock_config.email_enabled = True
        mock_config.resend_from_email = "noreply@rext.com"
        mock_config.resend_from_name = "REXT"

        service = EmailService(mock_db)

        email_log = await service.send_email(
            to="test@example.com",
            subject="Test",
            html="<p>Test</p>",
            retry_on_failure=True
        )

        # Should succeed with fallback
        assert email_log.status == "sent"
        assert email_log.provider == "mock"  # Fallback provider name

        # Verify fallback was used
        assert mock_fallback.get_sent_count() == 1
        assert mock_primary.get_sent_count() == 0  # Primary failed

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_send_email_provider_failure_no_retry(
        self, mock_get_fallback, mock_get_provider, mock_config
    ):
        """Should not retry when retry_on_failure=False"""
        mock_db = AsyncMock()

        # Primary provider that fails
        mock_primary = MockEmailProvider(simulate_failures=True, failure_rate=1.0)
        mock_fallback = MockEmailProvider(simulate_failures=False)

        mock_get_provider.return_value = mock_primary
        mock_get_fallback.return_value = mock_fallback

        mock_config.email_enabled = True
        mock_config.resend_from_email = "noreply@rext.com"
        mock_config.resend_from_name = "REXT"

        service = EmailService(mock_db)

        email_log = await service.send_email(
            to="test@example.com",
            subject="Test",
            html="<p>Test</p>",
            retry_on_failure=False  # Don't retry
        )

        # Should fail (no fallback attempted)
        assert email_log.status == "failed"
        assert email_log.error_message is not None

        # Verify fallback was NOT used
        assert mock_fallback.get_sent_count() == 0

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_send_email_both_providers_fail(
        self, mock_get_fallback, mock_get_provider, mock_config
    ):
        """Should log failure when both providers fail"""
        mock_db = AsyncMock()

        # Both providers fail
        mock_primary = MockEmailProvider(simulate_failures=True, failure_rate=1.0)
        mock_fallback = MockEmailProvider(simulate_failures=True, failure_rate=1.0)

        mock_get_provider.return_value = mock_primary
        mock_get_fallback.return_value = mock_fallback

        mock_config.email_enabled = True
        mock_config.resend_from_email = "noreply@rext.com"
        mock_config.resend_from_name = "REXT"

        service = EmailService(mock_db)

        email_log = await service.send_email(
            to="test@example.com",
            subject="Test",
            html="<p>Test</p>",
            retry_on_failure=True
        )

        # Should fail
        assert email_log.status == "failed"
        assert email_log.error_message is not None
        assert email_log.failed_at is not None
        assert email_log.sent_at is None


class TestEmailServiceQueryMethods:
    """Test query methods"""

    @pytest.mark.asyncio
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_get_email_log(self, mock_get_fallback, mock_get_provider):
        """Should retrieve email log by ID"""
        mock_db = AsyncMock()
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        # Mock database query
        email_log_id = uuid4()
        mock_email_log = EmailLog(
            id=email_log_id,
            to_email="test@example.com",
            subject="Test",
            status="sent",
            provider="mock",
            from_email="noreply@rext.com"
        )

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_email_log
        mock_db.execute.return_value = mock_result

        service = EmailService(mock_db)
        result = await service.get_email_log(email_log_id)

        assert result == mock_email_log
        assert result.id == email_log_id

    @pytest.mark.asyncio
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_get_email_log_not_found(self, mock_get_fallback, mock_get_provider):
        """Should return None when email log not found"""
        mock_db = AsyncMock()
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = EmailService(mock_db)
        result = await service.get_email_log(uuid4())

        assert result is None

    @pytest.mark.asyncio
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_get_emails_for_user(self, mock_get_fallback, mock_get_provider):
        """Should retrieve emails for specific user"""
        mock_db = AsyncMock()
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        user_id = uuid4()
        mock_emails = [
            EmailLog(id=uuid4(), user_id=user_id, to_email="test1@example.com", subject="Email 1", status="sent", provider="mock", from_email="noreply@rext.com"),
            EmailLog(id=uuid4(), user_id=user_id, to_email="test2@example.com", subject="Email 2", status="sent", provider="mock", from_email="noreply@rext.com"),
        ]

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_emails
        mock_db.execute.return_value = mock_result

        service = EmailService(mock_db)
        results = await service.get_emails_for_user(user_id, limit=50, offset=0)

        assert len(results) == 2
        assert all(email.user_id == user_id for email in results)

    @pytest.mark.asyncio
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_get_emails_for_workspace(self, mock_get_fallback, mock_get_provider):
        """Should retrieve emails for specific workspace"""
        mock_db = AsyncMock()
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        workspace_id = uuid4()
        mock_emails = [
            EmailLog(id=uuid4(), workspace_id=workspace_id, to_email="test1@example.com", subject="Email 1", status="sent", provider="mock", from_email="noreply@rext.com"),
            EmailLog(id=uuid4(), workspace_id=workspace_id, to_email="test2@example.com", subject="Email 2", status="sent", provider="mock", from_email="noreply@rext.com"),
        ]

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_emails
        mock_db.execute.return_value = mock_result

        service = EmailService(mock_db)
        results = await service.get_emails_for_workspace(workspace_id, limit=50, offset=0)

        assert len(results) == 2
        assert all(email.workspace_id == workspace_id for email in results)

    @pytest.mark.asyncio
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_get_recent_failures(self, mock_get_fallback, mock_get_provider):
        """Should retrieve recent failed emails"""
        mock_db = AsyncMock()
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        mock_failed_emails = [
            EmailLog(id=uuid4(), to_email="failed1@example.com", subject="Failed 1", status="failed", provider="mock", from_email="noreply@rext.com", error_message="Error 1"),
            EmailLog(id=uuid4(), to_email="failed2@example.com", subject="Failed 2", status="failed", provider="mock", from_email="noreply@rext.com", error_message="Error 2"),
        ]

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_failed_emails
        mock_db.execute.return_value = mock_result

        service = EmailService(mock_db)
        results = await service.get_recent_failures(hours=24, limit=100)

        assert len(results) == 2
        assert all(email.status == "failed" for email in results)


class TestEmailServiceRetryFailedEmail:
    """Test retry_failed_email method"""

    @pytest.mark.asyncio
    @patch('src.services.email_service.email_config')
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_retry_failed_email_success(self, mock_get_fallback, mock_get_provider, mock_config):
        """Should retry failed email successfully"""
        mock_db = AsyncMock()
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        mock_config.email_enabled = True
        mock_config.resend_from_email = "noreply@rext.com"
        mock_config.resend_from_name = "REXT"

        # Create a failed email log
        email_log_id = uuid4()
        failed_email_log = EmailLog(
            id=email_log_id,
            to_email="test@example.com",
            subject="Test",
            status="failed",
            provider="mock",
            from_email="noreply@rext.com",
            error_message="Previous failure",
            failed_at=datetime.now(timezone.utc)
        )

        # Mock get_email_log to return the failed log
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = failed_email_log
        mock_db.execute.return_value = mock_result

        service = EmailService(mock_db)

        # Manually set the failed log in the service's method
        with patch.object(service, 'get_email_log', return_value=failed_email_log):
            retried_log = await service.retry_failed_email(email_log_id)

            # Should succeed on retry
            assert retried_log.status == "sent"
            assert retried_log.error_message is None
            assert retried_log.sent_at is not None
            assert retried_log.failed_at is None

    @pytest.mark.asyncio
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_retry_failed_email_not_found(self, mock_get_fallback, mock_get_provider):
        """Should raise ValueError when email log not found"""
        mock_db = AsyncMock()
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        service = EmailService(mock_db)

        with patch.object(service, 'get_email_log', return_value=None):
            with pytest.raises(ValueError, match="Email log .* not found"):
                await service.retry_failed_email(uuid4())

    @pytest.mark.asyncio
    @patch('src.services.email_service.get_email_provider')
    @patch('src.services.email_service.get_fallback_email_provider')
    async def test_retry_failed_email_wrong_status(self, mock_get_fallback, mock_get_provider):
        """Should raise ValueError when email log is not in failed status"""
        mock_db = AsyncMock()
        mock_provider = MockEmailProvider()
        mock_get_provider.return_value = mock_provider
        mock_get_fallback.return_value = None

        # Email log with 'sent' status (not failed)
        email_log_id = uuid4()
        sent_email_log = EmailLog(
            id=email_log_id,
            to_email="test@example.com",
            subject="Test",
            status="sent",  # Not failed
            provider="mock",
            from_email="noreply@rext.com"
        )

        service = EmailService(mock_db)

        with patch.object(service, 'get_email_log', return_value=sent_email_log):
            with pytest.raises(ValueError, match="is not in failed status"):
                await service.retry_failed_email(email_log_id)
