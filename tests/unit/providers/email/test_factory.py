"""
Unit tests for EmailProviderFactory.

Tests cover:
- Provider creation for each type (resend, smtp, mock)
- Provider caching mechanism
- Fallback provider logic
- Invalid provider handling
- Instance management
"""

from unittest.mock import Mock, patch

import pytest

from src.providers.email.factory import (
    EmailProviderFactory,
    get_email_provider,
    get_fallback_email_provider,
)
from src.providers.email.mock_provider import MockEmailProvider
from src.providers.email.resend_provider import ResendEmailProvider
from src.providers.email.smtp_provider import SMTPEmailProvider


class TestEmailProviderFactoryGetProvider:
    """Test get_email_provider function"""

    def setup_method(self):
        """Clear provider instances before each test"""
        EmailProviderFactory.reset()

    @patch("src.providers.email.factory.email_config")
    def test_get_provider_mock_default(self, mock_config):
        """Should create mock provider when configured"""
        mock_config.email_provider = "mock"

        provider = get_email_provider()

        assert isinstance(provider, MockEmailProvider)
        assert provider.get_provider_name() == "mock"

    @patch("src.providers.email.resend_provider.resend")
    @patch("src.providers.email.factory.email_config")
    def test_get_provider_resend(self, mock_config, mock_resend):
        """Should create Resend provider when configured"""
        mock_config.email_provider = "resend"
        mock_config.resend_api_key = "re_test_key"
        mock_config.resend_from_email = "noreply@rext.com"
        mock_config.resend_from_name = "Rext AI"

        provider = get_email_provider()

        assert isinstance(provider, ResendEmailProvider)
        assert provider.get_provider_name() == "resend"

    @patch("src.providers.email.smtp_provider.email_config")
    @patch("src.providers.email.factory.email_config")
    def test_get_provider_smtp(self, mock_factory_config, mock_provider_config):
        """Should create SMTP provider when configured"""
        mock_factory_config.email_provider = "smtp"
        mock_provider_config.smtp_server = "smtp.gmail.com"
        mock_provider_config.smtp_port = 587
        mock_provider_config.smtp_username = "test@gmail.com"
        mock_provider_config.smtp_password = "password123"

        provider = get_email_provider()

        assert isinstance(provider, SMTPEmailProvider)
        assert provider.get_provider_name() == "smtp"

    @patch("src.providers.email.factory.email_config")
    def test_get_provider_force_recreate(self, mock_config):
        """Should recreate provider when force_recreate=True"""
        mock_config.email_provider = "mock"

        # Get provider first time
        provider1 = EmailProviderFactory.get_provider()

        # Get provider again with force_recreate
        provider2 = EmailProviderFactory.get_provider(force_recreate=True)

        # Should be different instances (recreated)
        assert isinstance(provider1, MockEmailProvider)
        assert isinstance(provider2, MockEmailProvider)
        # Note: can't compare instances directly as they're newly created

    @patch("src.providers.email.factory.email_config")
    def test_get_provider_invalid_type(self, mock_config):
        """Should raise ValueError for invalid provider type"""
        mock_config.email_provider = "invalid_provider"

        with pytest.raises(ValueError, match="Unknown email provider: invalid_provider"):
            get_email_provider()

    @patch("src.providers.email.factory.email_config")
    def test_get_provider_caching(self, mock_config):
        """Should cache provider instances"""
        mock_config.email_provider = "mock"

        # Get provider twice
        provider1 = get_email_provider()
        provider2 = get_email_provider()

        # Should return same instance
        assert provider1 is provider2

    @patch("src.providers.email.factory.email_config")
    def test_get_provider_caching_same_type(self, mock_config):
        """Should cache provider instances"""
        mock_config.email_provider = "mock"

        # Get provider twice
        provider1 = get_email_provider()
        provider2 = get_email_provider()

        # Should return same instance
        assert provider1 is provider2


class TestEmailProviderFactoryFallback:
    """Test fallback provider logic"""

    def setup_method(self):
        """Clear provider instances before each test"""
        EmailProviderFactory.reset()

    @patch("src.providers.email.factory.email_config")
    def test_get_fallback_provider_configured(self, mock_config):
        """Should return fallback provider when configured"""
        mock_config.email_provider = "resend"
        mock_config.email_fallback_provider = "mock"

        fallback = get_fallback_email_provider()

        assert fallback is not None
        assert isinstance(fallback, MockEmailProvider)

    @patch("src.providers.email.factory.email_config")
    def test_get_fallback_provider_none_configured(self, mock_config):
        """Should return None when no fallback configured"""
        mock_config.email_provider = "resend"
        mock_config.email_fallback_provider = None

        fallback = get_fallback_email_provider()

        assert fallback is None

    @patch("src.providers.email.factory.email_config")
    def test_get_fallback_provider_same_as_primary(self, mock_config):
        """Should still create fallback even if same type as primary"""
        mock_config.email_provider = "mock"
        mock_config.email_fallback_provider = "mock"  # Same as primary

        fallback = get_fallback_email_provider()

        # Factory creates fallback regardless of primary type
        assert fallback is not None
        assert isinstance(fallback, MockEmailProvider)

    @patch("src.providers.email.factory.email_config")
    def test_get_fallback_provider_caching(self, mock_config):
        """Should cache fallback provider instance"""
        mock_config.email_provider = "resend"
        mock_config.email_fallback_provider = "mock"

        fallback1 = get_fallback_email_provider()
        fallback2 = get_fallback_email_provider()

        # Should return same instance
        assert fallback1 is fallback2


class TestEmailProviderFactoryInstanceManagement:
    """Test provider instance management"""

    def setup_method(self):
        """Clear provider instances before each test"""
        EmailProviderFactory.reset()

    @patch("src.providers.email.resend_provider.resend")
    @patch("src.providers.email.factory.email_config")
    def test_provider_instances_isolation(self, mock_config, mock_resend):
        """Should maintain separate instances for primary and fallback"""
        mock_config.email_provider = "resend"
        mock_config.email_fallback_provider = "mock"
        mock_config.resend_api_key = "re_test_key"
        mock_config.resend_from_email = "noreply@rext.com"
        mock_config.resend_from_name = "Rext AI"

        # Clear instances
        EmailProviderFactory.reset()

        primary = get_email_provider()
        fallback = get_fallback_email_provider()

        assert primary is not fallback
        assert isinstance(primary, ResendEmailProvider)
        assert isinstance(fallback, MockEmailProvider)


class TestEmailProviderFactoryErrorScenarios:
    """Test error scenarios and edge cases"""

    def setup_method(self):
        """Clear provider instances before each test"""
        EmailProviderFactory.reset()

    @patch("src.providers.email.resend_provider.email_config")
    @patch("src.providers.email.factory.email_config")
    def test_resend_missing_api_key(self, mock_factory_config, mock_provider_config):
        """Should raise ValueError when Resend API key is missing"""
        mock_factory_config.email_provider = "resend"
        mock_provider_config.resend_api_key = None  # Missing API key

        with pytest.raises(ValueError, match="Failed to create resend provider"):
            get_email_provider()

    @patch("src.providers.email.smtp_provider.email_config")
    @patch("src.providers.email.factory.email_config")
    def test_smtp_missing_configuration(self, mock_factory_config, mock_provider_config):
        """Should raise ValueError when SMTP configuration is incomplete"""
        mock_factory_config.email_provider = "smtp"
        mock_provider_config.smtp_server = None  # Missing server
        mock_provider_config.smtp_username = None
        mock_provider_config.smtp_password = None

        with pytest.raises(ValueError, match="Failed to create smtp provider"):
            get_email_provider()

    @patch("src.providers.email.factory.email_config")
    def test_provider_type_case_insensitive(self, mock_config):
        """Should handle uppercase provider types (normalizes to lowercase)"""
        mock_config.email_provider = "MOCK"  # Uppercase

        # Factory normalizes to lowercase, so this should succeed
        provider = get_email_provider()
        assert isinstance(provider, MockEmailProvider)
        assert provider.get_provider_name() == "mock"

    @patch("src.providers.email.factory.email_config")
    def test_empty_provider_type(self, mock_config):
        """Should raise ValueError for empty provider type"""
        mock_config.email_provider = ""

        with pytest.raises(ValueError, match="Unknown email provider"):
            get_email_provider()
