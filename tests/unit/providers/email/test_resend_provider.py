"""
Unit tests for ResendEmailProvider.

Tests cover:
- Provider initialization and API key validation
- Email sending via Resend API
- Parameter building for Resend API
- Error handling for API failures
- Connection verification
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.providers.email.resend_provider import ResendEmailProvider
from src.providers.email.base import EmailMessage, EmailRecipient, EmailResult


class TestResendEmailProviderInitialization:
    """Test ResendEmailProvider initialization"""

    @patch('src.providers.email.resend_provider.email_config')
    def test_initialization_success(self, mock_config):
        """Should initialize with valid API key"""
        mock_config.resend_api_key = "re_test_key_123"
        mock_config.resend_from_email = "noreply@wrext.com"
        mock_config.resend_from_name = "WREXT"

        with patch('src.providers.email.resend_provider.resend') as mock_resend:
            provider = ResendEmailProvider()

            assert provider.get_provider_name() == "resend"
            assert mock_resend.api_key == "re_test_key_123"

    @patch('src.providers.email.resend_provider.email_config')
    def test_initialization_missing_api_key(self, mock_config):
        """Should raise ValueError if API key not configured"""
        mock_config.resend_api_key = None

        with pytest.raises(ValueError, match="RESEND_API_KEY not configured"):
            ResendEmailProvider()

    @patch('src.providers.email.resend_provider.email_config')
    def test_initialization_empty_api_key(self, mock_config):
        """Should raise ValueError if API key is empty string"""
        mock_config.resend_api_key = ""

        with pytest.raises(ValueError, match="RESEND_API_KEY not configured"):
            ResendEmailProvider()


class TestResendEmailProviderSendEmail:
    """Test send_email method"""

    @pytest.mark.asyncio
    @patch('src.providers.email.resend_provider.email_config')
    @patch('src.providers.email.resend_provider.resend')
    async def test_send_email_success(self, mock_resend, mock_config):
        """Should send email successfully via Resend API"""
        # Setup
        mock_config.resend_api_key = "re_test_key"
        mock_config.resend_from_email = "noreply@wrext.com"
        mock_config.resend_from_name = "WREXT"

        mock_resend.Emails.send.return_value = {
            "id": "msg_abc123",
            "from": "WREXT <noreply@wrext.com>",
            "to": ["test@example.com"],
            "created_at": "2025-10-12T00:00:00Z"
        }

        provider = ResendEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="test@example.com", name="Test User")],
            subject="Test Email",
            html="<p>Test Body</p>",
            from_email="noreply@wrext.com",
            from_name="WREXT"
        )

        # Execute
        result = await provider.send_email(message)

        # Verify
        assert result.success is True
        assert result.message_id == "msg_abc123"
        assert result.error is None
        assert result.provider_response["id"] == "msg_abc123"

        # Verify Resend API was called correctly
        mock_resend.Emails.send.assert_called_once()
        call_args = mock_resend.Emails.send.call_args[0][0]
        assert call_args["from"] == "WREXT <noreply@wrext.com>"
        assert call_args["to"] == ["Test User <test@example.com>"]
        assert call_args["subject"] == "Test Email"
        assert call_args["html"] == "<p>Test Body</p>"

    @pytest.mark.asyncio
    @patch('src.providers.email.resend_provider.email_config')
    @patch('src.providers.email.resend_provider.resend')
    async def test_send_email_with_multiple_recipients(self, mock_resend, mock_config):
        """Should handle multiple recipients"""
        mock_config.resend_api_key = "re_test_key"
        mock_resend.Emails.send.return_value = {"id": "msg_123"}

        provider = ResendEmailProvider()

        message = EmailMessage(
            to=[
                EmailRecipient(email="user1@example.com", name="User One"),
                EmailRecipient(email="user2@example.com", name="User Two")
            ],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@wrext.com"
        )

        result = await provider.send_email(message)

        assert result.success is True
        call_args = mock_resend.Emails.send.call_args[0][0]
        assert call_args["to"] == [
            "User One <user1@example.com>",
            "User Two <user2@example.com>"
        ]

    @pytest.mark.asyncio
    @patch('src.providers.email.resend_provider.email_config')
    @patch('src.providers.email.resend_provider.resend')
    async def test_send_email_with_cc_bcc(self, mock_resend, mock_config):
        """Should handle CC and BCC recipients"""
        mock_config.resend_api_key = "re_test_key"
        mock_resend.Emails.send.return_value = {"id": "msg_123"}

        provider = ResendEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="to@example.com")],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@wrext.com",
            cc=[EmailRecipient(email="cc@example.com", name="CC User")],
            bcc=[EmailRecipient(email="bcc@example.com")]
        )

        result = await provider.send_email(message)

        assert result.success is True
        call_args = mock_resend.Emails.send.call_args[0][0]
        assert call_args["cc"] == ["CC User <cc@example.com>"]
        assert call_args["bcc"] == ["bcc@example.com"]

    @pytest.mark.asyncio
    @patch('src.providers.email.resend_provider.email_config')
    @patch('src.providers.email.resend_provider.resend')
    async def test_send_email_with_reply_to(self, mock_resend, mock_config):
        """Should handle reply_to address"""
        mock_config.resend_api_key = "re_test_key"
        mock_resend.Emails.send.return_value = {"id": "msg_123"}

        provider = ResendEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="to@example.com")],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@wrext.com",
            reply_to="reply@wrext.com"
        )

        result = await provider.send_email(message)

        assert result.success is True
        call_args = mock_resend.Emails.send.call_args[0][0]
        assert call_args["reply_to"] == "reply@wrext.com"

    @pytest.mark.asyncio
    @patch('src.providers.email.resend_provider.email_config')
    @patch('src.providers.email.resend_provider.resend')
    async def test_send_email_with_tags(self, mock_resend, mock_config):
        """Should handle email tags"""
        mock_config.resend_api_key = "re_test_key"
        mock_resend.Emails.send.return_value = {"id": "msg_123"}

        provider = ResendEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="to@example.com")],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@wrext.com",
            tags={"type": "auth", "action": "verify"}
        )

        result = await provider.send_email(message)

        assert result.success is True
        call_args = mock_resend.Emails.send.call_args[0][0]
        # Tags should be converted to Resend format: list of {"name": key, "value": val}
        expected_tags = [
            {"name": "type", "value": "auth"},
            {"name": "action", "value": "verify"}
        ]
        assert len(call_args["tags"]) == 2
        assert all(tag in call_args["tags"] for tag in expected_tags)

    @pytest.mark.asyncio
    @patch('src.providers.email.resend_provider.email_config')
    @patch('src.providers.email.resend_provider.resend')
    async def test_send_email_recipient_without_name(self, mock_resend, mock_config):
        """Should format recipient without name correctly"""
        mock_config.resend_api_key = "re_test_key"
        mock_resend.Emails.send.return_value = {"id": "msg_123"}

        provider = ResendEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="test@example.com")],  # No name
            subject="Test",
            html="<p>Test</p>",
            from_email="from@wrext.com"
        )

        result = await provider.send_email(message)

        assert result.success is True
        call_args = mock_resend.Emails.send.call_args[0][0]
        assert call_args["to"] == ["test@example.com"]  # No name formatting


class TestResendEmailProviderErrorHandling:
    """Test error handling for API failures"""

    @pytest.mark.asyncio
    @patch('src.providers.email.resend_provider.email_config')
    @patch('src.providers.email.resend_provider.resend')
    async def test_send_email_api_error(self, mock_resend, mock_config):
        """Should handle Resend API errors gracefully"""
        mock_config.resend_api_key = "re_test_key"
        mock_resend.Emails.send.side_effect = Exception("API Error: Invalid email")

        provider = ResendEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="invalid@example.com")],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@wrext.com"
        )

        result = await provider.send_email(message)

        assert result.success is False
        assert "API Error: Invalid email" in result.error
        assert result.message_id is None

    @pytest.mark.asyncio
    @patch('src.providers.email.resend_provider.email_config')
    @patch('src.providers.email.resend_provider.resend')
    async def test_send_email_network_error(self, mock_resend, mock_config):
        """Should handle network errors"""
        mock_config.resend_api_key = "re_test_key"
        mock_resend.Emails.send.side_effect = Exception("Network timeout")

        provider = ResendEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="test@example.com")],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@wrext.com"
        )

        result = await provider.send_email(message)

        assert result.success is False
        assert "Network timeout" in result.error

    @pytest.mark.asyncio
    @patch('src.providers.email.resend_provider.email_config')
    @patch('src.providers.email.resend_provider.resend')
    async def test_send_email_non_dict_response(self, mock_resend, mock_config):
        """Should handle non-dict responses from Resend API"""
        mock_config.resend_api_key = "re_test_key"
        mock_resend.Emails.send.return_value = "string_response"  # Unexpected format

        provider = ResendEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="test@example.com")],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@wrext.com"
        )

        result = await provider.send_email(message)

        # Should still succeed but handle gracefully
        assert result.success is True
        assert result.message_id is None
        assert result.provider_response == {"raw": "string_response"}


class TestResendEmailProviderConnectionVerification:
    """Test connection verification"""

    @pytest.mark.asyncio
    @patch('src.providers.email.resend_provider.email_config')
    @patch('src.providers.email.resend_provider.resend')
    async def test_verify_connection_success(self, mock_resend, mock_config):
        """Should verify connection when API key is set"""
        mock_config.resend_api_key = "re_test_key"
        mock_resend.api_key = "re_test_key"

        provider = ResendEmailProvider()
        result = await provider.verify_connection()

        assert result is True

    @pytest.mark.asyncio
    @patch('src.providers.email.resend_provider.email_config')
    @patch('src.providers.email.resend_provider.resend')
    async def test_verify_connection_no_key(self, mock_resend, mock_config):
        """Should fail verification if API key not set"""
        mock_config.resend_api_key = None  # No API key in config

        # The provider will fail to initialize if API key is not set
        with pytest.raises(ValueError, match="RESEND_API_KEY not configured"):
            ResendEmailProvider()


class TestResendEmailProviderFeatureSupport:
    """Test feature support checking"""

    @pytest.mark.asyncio
    @patch('src.providers.email.resend_provider.email_config')
    @patch('src.providers.email.resend_provider.resend')
    async def test_supports_feature(self, mock_resend, mock_config):
        """Should support documented features"""
        mock_config.resend_api_key = "re_test_key"

        provider = ResendEmailProvider()

        # Should support all documented features
        assert provider.supports_feature('basic_email') is True
        assert provider.supports_feature('webhooks') is True
        assert provider.supports_feature('tags') is True
        assert provider.supports_feature('cc_bcc') is True
        assert provider.supports_feature('reply_to') is True
        assert provider.supports_feature('html') is True

        # Should not support unknown features
        assert provider.supports_feature('unknown_feature') is False
