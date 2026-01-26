"""
Unit tests for SMTPEmailProvider.

Tests cover:
- Provider initialization and SMTP configuration validation
- Email sending via SMTP
- MIME message building
- Error handling for SMTP failures
- Connection verification
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from email.mime.multipart import MIMEMultipart
from src.providers.email.smtp_provider import SMTPEmailProvider
from src.providers.email.base import EmailMessage, EmailRecipient


class TestSMTPEmailProviderInitialization:
    """Test SMTPEmailProvider initialization"""

    @patch('src.providers.email.smtp_provider.email_config')
    def test_initialization_success(self, mock_config):
        """Should initialize with valid SMTP configuration"""
        mock_config.smtp_server = "smtp.gmail.com"
        mock_config.smtp_port = 587
        mock_config.smtp_username = "test@gmail.com"
        mock_config.smtp_password = "password123"
        mock_config.smtp_use_tls = True

        provider = SMTPEmailProvider()

        assert provider.get_provider_name() == "smtp"

    @patch('src.providers.email.smtp_provider.email_config')
    def test_initialization_missing_server(self, mock_config):
        """Should raise ValueError if SMTP server not configured"""
        mock_config.smtp_server = None
        mock_config.smtp_username = "test@gmail.com"
        mock_config.smtp_password = "password123"

        with pytest.raises(ValueError, match="SMTP_SERVER not configured"):
            SMTPEmailProvider()

    @patch('src.providers.email.smtp_provider.email_config')
    def test_initialization_missing_credentials(self, mock_config):
        """Should raise ValueError if SMTP credentials not configured"""
        mock_config.smtp_server = "smtp.gmail.com"
        mock_config.smtp_port = 587
        mock_config.smtp_username = None
        mock_config.smtp_password = None

        with pytest.raises(ValueError, match="SMTP_USERNAME and SMTP_PASSWORD required"):
            SMTPEmailProvider()


class TestSMTPEmailProviderSendEmail:
    """Test send_email method"""

    @pytest.mark.asyncio
    @patch('src.providers.email.smtp_provider.email_config')
    @patch('src.providers.email.smtp_provider.smtplib.SMTP')
    async def test_send_email_success(self, mock_smtp_class, mock_config):
        """Should send email successfully via SMTP"""
        # Setup config
        mock_config.smtp_server = "smtp.gmail.com"
        mock_config.smtp_port = 587
        mock_config.smtp_username = "test@gmail.com"
        mock_config.smtp_password = "password123"
        mock_config.smtp_use_tls = True

        # Setup SMTP mock
        mock_smtp_instance = MagicMock()
        mock_smtp_instance.sendmail.return_value = {}  # Empty dict = success
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

        provider = SMTPEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="recipient@example.com", name="Recipient")],
            subject="Test Email",
            html="<p>Test Body</p>",
            from_email="sender@rext.com",
            from_name="Sender"
        )

        # Execute
        result = await provider.send_email(message)

        # Verify
        assert result.success is True
        assert result.message_id is not None
        assert result.error is None

        # Verify SMTP operations
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.login.assert_called_once_with("test@gmail.com", "password123")
        mock_smtp_instance.sendmail.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.providers.email.smtp_provider.email_config')
    @patch('src.providers.email.smtp_provider.smtplib.SMTP')
    async def test_send_email_with_cc_bcc(self, mock_smtp_class, mock_config):
        """Should handle CC and BCC recipients"""
        mock_config.smtp_server = "smtp.gmail.com"
        mock_config.smtp_port = 587
        mock_config.smtp_username = "test@gmail.com"
        mock_config.smtp_password = "password123"
        mock_config.smtp_use_tls = True

        mock_smtp_instance = MagicMock()
        mock_smtp_instance.sendmail.return_value = {}  # Empty dict = success
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

        provider = SMTPEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="to@example.com")],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@rext.com",
            cc=[EmailRecipient(email="cc@example.com")],
            bcc=[EmailRecipient(email="bcc@example.com")]
        )

        result = await provider.send_email(message)

        assert result.success is True
        # Verify sendmail was called with all recipients
        mock_smtp_instance.sendmail.assert_called_once()
        call_args = mock_smtp_instance.sendmail.call_args[0]
        assert call_args[0] == "from@rext.com"  # from_email
        assert set(call_args[1]) == {"to@example.com", "cc@example.com", "bcc@example.com"}  # all recipients

    @pytest.mark.asyncio
    @patch('src.providers.email.smtp_provider.email_config')
    @patch('src.providers.email.smtp_provider.smtplib.SMTP')
    async def test_send_email_with_reply_to(self, mock_smtp_class, mock_config):
        """Should handle reply_to address"""
        mock_config.smtp_server = "smtp.gmail.com"
        mock_config.smtp_port = 587
        mock_config.smtp_username = "test@gmail.com"
        mock_config.smtp_password = "password123"
        mock_config.smtp_use_tls = True

        mock_smtp_instance = MagicMock()
        mock_smtp_instance.sendmail.return_value = {}  # Empty dict = success
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

        provider = SMTPEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="to@example.com")],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@rext.com",
            reply_to="reply@rext.com"
        )

        result = await provider.send_email(message)

        assert result.success is True


class TestSMTPEmailProviderErrorHandling:
    """Test error handling for SMTP failures"""

    @pytest.mark.asyncio
    @patch('src.providers.email.smtp_provider.email_config')
    @patch('src.providers.email.smtp_provider.smtplib.SMTP')
    async def test_send_email_connection_error(self, mock_smtp_class, mock_config):
        """Should handle SMTP connection errors"""
        mock_config.smtp_server = "smtp.gmail.com"
        mock_config.smtp_port = 587
        mock_config.smtp_username = "test@gmail.com"
        mock_config.smtp_password = "password123"
        mock_config.smtp_use_tls = True

        # Simulate connection error
        mock_smtp_class.side_effect = Exception("Connection refused")

        provider = SMTPEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="to@example.com")],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@rext.com"
        )

        result = await provider.send_email(message)

        assert result.success is False
        assert "Connection refused" in result.error
        assert result.message_id is None

    @pytest.mark.asyncio
    @patch('src.providers.email.smtp_provider.email_config')
    @patch('src.providers.email.smtp_provider.smtplib.SMTP')
    async def test_send_email_authentication_error(self, mock_smtp_class, mock_config):
        """Should handle SMTP authentication errors"""
        mock_config.smtp_server = "smtp.gmail.com"
        mock_config.smtp_port = 587
        mock_config.smtp_username = "test@gmail.com"
        mock_config.smtp_password = "wrong_password"
        mock_config.smtp_use_tls = True

        mock_smtp_instance = MagicMock()
        mock_smtp_instance.login.side_effect = Exception("Authentication failed")
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

        provider = SMTPEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="to@example.com")],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@rext.com"
        )

        result = await provider.send_email(message)

        assert result.success is False
        assert "Authentication failed" in result.error

    @pytest.mark.asyncio
    @patch('src.providers.email.smtp_provider.email_config')
    @patch('src.providers.email.smtp_provider.smtplib.SMTP')
    async def test_send_email_send_error(self, mock_smtp_class, mock_config):
        """Should handle errors during email sending"""
        mock_config.smtp_server = "smtp.gmail.com"
        mock_config.smtp_port = 587
        mock_config.smtp_username = "test@gmail.com"
        mock_config.smtp_password = "password123"
        mock_config.smtp_use_tls = True

        mock_smtp_instance = MagicMock()
        mock_smtp_instance.sendmail.side_effect = Exception("Send failed")
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

        provider = SMTPEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="to@example.com")],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@rext.com"
        )

        result = await provider.send_email(message)

        assert result.success is False
        assert "Send failed" in result.error


class TestSMTPEmailProviderConnectionVerification:
    """Test connection verification"""

    @pytest.mark.asyncio
    @patch('src.providers.email.smtp_provider.email_config')
    @patch('src.providers.email.smtp_provider.smtplib.SMTP')
    async def test_verify_connection_success(self, mock_smtp_class, mock_config):
        """Should verify SMTP connection successfully"""
        mock_config.smtp_server = "smtp.gmail.com"
        mock_config.smtp_port = 587
        mock_config.smtp_username = "test@gmail.com"
        mock_config.smtp_password = "password123"
        mock_config.smtp_use_tls = True

        mock_smtp_instance = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

        provider = SMTPEmailProvider()
        result = await provider.verify_connection()

        assert result is True
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.login.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.providers.email.smtp_provider.email_config')
    @patch('src.providers.email.smtp_provider.smtplib.SMTP')
    async def test_verify_connection_failure(self, mock_smtp_class, mock_config):
        """Should handle connection verification failures"""
        mock_config.smtp_server = "smtp.gmail.com"
        mock_config.smtp_port = 587
        mock_config.smtp_username = "test@gmail.com"
        mock_config.smtp_password = "password123"
        mock_config.smtp_use_tls = True

        # Simulate connection failure
        mock_smtp_class.side_effect = Exception("Connection timeout")

        provider = SMTPEmailProvider()
        result = await provider.verify_connection()

        assert result is False


class TestSMTPEmailProviderFeatureSupport:
    """Test feature support checking"""

    @pytest.mark.asyncio
    @patch('src.providers.email.smtp_provider.email_config')
    async def test_supports_feature(self, mock_config):
        """Should support documented features"""
        mock_config.smtp_server = "smtp.gmail.com"
        mock_config.smtp_port = 587
        mock_config.smtp_username = "test@gmail.com"
        mock_config.smtp_password = "password123"
        mock_config.smtp_use_tls = True

        provider = SMTPEmailProvider()

        # Should support basic features
        assert provider.supports_feature('basic_email') is True
        assert provider.supports_feature('cc_bcc') is True
        assert provider.supports_feature('reply_to') is True
        assert provider.supports_feature('html') is True

        # Should NOT support Resend-specific features or attachments (not implemented yet)
        assert provider.supports_feature('webhooks') is False
        assert provider.supports_feature('tags') is False
        assert provider.supports_feature('attachments') is False  # Not implemented yet

        # Should not support unknown features
        assert provider.supports_feature('unknown_feature') is False
