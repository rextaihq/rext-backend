"""
Unit tests for SMTPEmailProvider.

Tests cover:
- Provider initialization and SMTP configuration validation
- Email sending via SMTP
- MIME message building
- Error handling for SMTP failures
- Connection verification
"""

from email.mime.multipart import MIMEMultipart
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import aiosmtplib
import pytest

from src.providers.email.base import EmailMessage, EmailRecipient
from src.providers.email.smtp_provider import SMTPEmailProvider


class TestSMTPEmailProviderInitialization:
    """Test SMTPEmailProvider initialization"""

    @patch("src.providers.email.smtp_provider.email_config")
    def test_initialization_success(self, mock_config):
        """Should initialize with valid SMTP configuration"""
        mock_config.smtp_server = "smtp.gmail.com"
        mock_config.smtp_port = 587
        mock_config.smtp_username = "test@gmail.com"
        mock_config.smtp_password = "password123"
        mock_config.smtp_use_tls = True

        provider = SMTPEmailProvider()

        assert provider.get_provider_name() == "smtp"

    @patch("src.providers.email.smtp_provider.email_config")
    def test_initialization_missing_server(self, mock_config):
        """Should raise ValueError if SMTP server not configured"""
        mock_config.smtp_server = None
        mock_config.smtp_username = "test@gmail.com"
        mock_config.smtp_password = "password123"

        with pytest.raises(ValueError, match="SMTP_SERVER not configured"):
            SMTPEmailProvider()

    @patch("src.providers.email.smtp_provider.email_config")
    def test_initialization_missing_credentials(self, mock_config):
        """Should raise ValueError if SMTP credentials not configured"""
        mock_config.smtp_server = "smtp.gmail.com"
        mock_config.smtp_port = 587
        mock_config.smtp_username = None
        mock_config.smtp_password = None

        with pytest.raises(ValueError, match="SMTP_USERNAME and SMTP_PASSWORD required"):
            SMTPEmailProvider()


SMTP = "src.providers.email.smtp_provider.aiosmtplib.SMTP"


def _configure(mock_config, password="password123"):
    mock_config.smtp_server = "smtp.gmail.com"
    mock_config.smtp_port = 587
    mock_config.smtp_username = "test@gmail.com"
    mock_config.smtp_password = password
    mock_config.smtp_use_tls = True


def _smtp_client():
    """An aiosmtplib.SMTP stand-in: an async context manager with async login and sendmail."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.login = AsyncMock()
    client.sendmail = AsyncMock(return_value=({}, "OK"))
    return client


def _message(**extra):
    return EmailMessage(
        to=[EmailRecipient(email="to@example.com", name="Recipient")],
        subject="Test Email",
        html="<p>Test Body</p>",
        from_email="from@rext.com",
        from_name="Sender",
        **extra,
    )


class TestSMTPEmailProviderSendEmail:
    """Test send_email method"""

    @pytest.mark.asyncio
    @patch("src.providers.email.smtp_provider.email_config")
    async def test_send_email_success(self, mock_config):
        """Should send email via async SMTP: STARTTLS, login, then one sendmail"""
        _configure(mock_config)
        client = _smtp_client()

        with patch(SMTP, return_value=client) as smtp_class:
            result = await SMTPEmailProvider().send_email(_message())

        assert result.success is True
        assert result.message_id is not None
        assert result.error is None
        smtp_class.assert_called_once_with(
            hostname="smtp.gmail.com", port=587, timeout=30, start_tls=True
        )
        client.login.assert_awaited_once_with("test@gmail.com", "password123")
        client.sendmail.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.providers.email.smtp_provider.email_config")
    async def test_send_email_with_cc_bcc(self, mock_config):
        """Should send to every recipient, with BCC kept out of the headers"""
        _configure(mock_config)
        client = _smtp_client()

        with patch(SMTP, return_value=client):
            result = await SMTPEmailProvider().send_email(
                _message(
                    cc=[EmailRecipient(email="cc@example.com")],
                    bcc=[EmailRecipient(email="bcc@example.com")],
                )
            )

        assert result.success is True
        sender, recipients, body = client.sendmail.call_args.args
        assert sender == "from@rext.com"
        assert set(recipients) == {"to@example.com", "cc@example.com", "bcc@example.com"}
        assert "Cc: cc@example.com" in body
        assert "bcc@example.com" not in body

    @pytest.mark.asyncio
    @patch("src.providers.email.smtp_provider.email_config")
    async def test_send_email_with_reply_to(self, mock_config):
        """Should set the Reply-To header"""
        _configure(mock_config)
        client = _smtp_client()

        with patch(SMTP, return_value=client):
            result = await SMTPEmailProvider().send_email(_message(reply_to="reply@rext.com"))

        assert result.success is True
        assert "Reply-To: reply@rext.com" in client.sendmail.call_args.args[2]


class TestSMTPEmailProviderErrorHandling:
    """Test error handling for SMTP failures"""

    @pytest.mark.asyncio
    @patch("src.providers.email.smtp_provider.email_config")
    async def test_send_email_connection_error(self, mock_config):
        """Should report a connection that can't be made"""
        _configure(mock_config)

        with patch(SMTP, side_effect=Exception("Connection refused")):
            result = await SMTPEmailProvider().send_email(_message())

        assert result.success is False
        assert "Connection refused" in result.error
        assert result.message_id is None

    @pytest.mark.asyncio
    @patch("src.providers.email.smtp_provider.email_config")
    async def test_send_email_authentication_error(self, mock_config):
        """Should report refused credentials as an authentication failure"""
        _configure(mock_config, password="wrong_password")
        client = _smtp_client()
        client.login.side_effect = aiosmtplib.SMTPAuthenticationError(535, "Authentication failed")

        with patch(SMTP, return_value=client):
            result = await SMTPEmailProvider().send_email(_message())

        assert result.success is False
        assert result.error.startswith("SMTP authentication failed")
        assert "Authentication failed" in result.error
        assert result.provider_response["error_type"] == "authentication"
        client.sendmail.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("src.providers.email.smtp_provider.email_config")
    async def test_send_email_send_error(self, mock_config):
        """Should report an SMTP error during sending"""
        _configure(mock_config)
        client = _smtp_client()
        client.sendmail.side_effect = aiosmtplib.SMTPException("Send failed")

        with patch(SMTP, return_value=client):
            result = await SMTPEmailProvider().send_email(_message())

        assert result.success is False
        assert result.error == "SMTP error: Send failed"


class TestSMTPEmailProviderConnectionVerification:
    """Test connection verification"""

    @pytest.mark.asyncio
    @patch("src.providers.email.smtp_provider.email_config")
    async def test_verify_connection_success(self, mock_config):
        """Should log in once, with a shorter timeout than sending"""
        _configure(mock_config)
        client = _smtp_client()

        with patch(SMTP, return_value=client) as smtp_class:
            result = await SMTPEmailProvider().verify_connection()

        assert result is True
        assert smtp_class.call_args.kwargs["timeout"] == 10
        client.login.assert_awaited_once_with("test@gmail.com", "password123")

    @pytest.mark.asyncio
    @patch("src.providers.email.smtp_provider.email_config")
    async def test_verify_connection_failure(self, mock_config):
        """Should handle connection verification failures"""
        _configure(mock_config)

        with patch(SMTP, side_effect=Exception("Connection timeout")):
            result = await SMTPEmailProvider().verify_connection()

        assert result is False


class TestSMTPEmailProviderFeatureSupport:
    """Test feature support checking"""

    @pytest.mark.asyncio
    @patch("src.providers.email.smtp_provider.email_config")
    async def test_supports_feature(self, mock_config):
        """Should support documented features"""
        mock_config.smtp_server = "smtp.gmail.com"
        mock_config.smtp_port = 587
        mock_config.smtp_username = "test@gmail.com"
        mock_config.smtp_password = "password123"
        mock_config.smtp_use_tls = True

        provider = SMTPEmailProvider()

        # Should support basic features
        assert provider.supports_feature("basic_email") is True
        assert provider.supports_feature("cc_bcc") is True
        assert provider.supports_feature("reply_to") is True
        assert provider.supports_feature("html") is True

        # Should NOT support Resend-specific features or attachments (not implemented yet)
        assert provider.supports_feature("webhooks") is False
        assert provider.supports_feature("tags") is False
        assert provider.supports_feature("attachments") is False  # Not implemented yet

        # Should not support unknown features
        assert provider.supports_feature("unknown_feature") is False
