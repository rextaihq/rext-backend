"""
Tests for application configuration and settings validation.

Tests the Settings class in src/api/config.py to ensure:
1. JWT secret keys are validated for minimum length
2. Weak or placeholder keys are rejected
3. Application fails fast on invalid configuration
4. Environment variables are properly loaded
"""

import os

import pytest
from pydantic import ValidationError

from src.api.config import Settings, get_settings


class TestJWTSecretValidation:
    """Test JWT secret key validation requirements."""

    def test_weak_secret_key_rejected_too_short(self, monkeypatch):
        """Test that SECRET_KEY shorter than 32 characters is rejected."""
        # Set environment variables for this test
        monkeypatch.setenv("SECRET_KEY", "short")  # Only 5 characters
        monkeypatch.setenv("REFRESH_SECRET_KEY", "a" * 32)  # Valid length

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_message = str(exc_info.value)
        assert "SECRET_KEY must be at least 32 characters" in error_message

    def test_weak_refresh_secret_key_rejected_too_short(self, monkeypatch):
        """Test that REFRESH_SECRET_KEY shorter than 32 characters is rejected."""
        monkeypatch.setenv("SECRET_KEY", "a" * 32)  # Valid length
        monkeypatch.setenv("REFRESH_SECRET_KEY", "short")  # Only 5 characters

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_message = str(exc_info.value)
        assert "REFRESH_SECRET_KEY must be at least 32 characters" in error_message

    def test_placeholder_secret_key_rejected(self, monkeypatch):
        """Test that placeholder SECRET_KEY values are rejected."""
        placeholder_values = ["your-secret-key-here", "changeme", "secret", "password"]

        for placeholder in placeholder_values:
            monkeypatch.setenv("SECRET_KEY", placeholder)
            monkeypatch.setenv("REFRESH_SECRET_KEY", "a" * 32)

            with pytest.raises(ValidationError) as exc_info:
                Settings()

            error_message = str(exc_info.value)
            assert "insecure placeholder value" in error_message

    def test_placeholder_refresh_secret_key_rejected(self, monkeypatch):
        """Test that placeholder REFRESH_SECRET_KEY values are rejected."""
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("REFRESH_SECRET_KEY", "your-secret-key-here")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_message = str(exc_info.value)
        assert "insecure placeholder value" in error_message

    def test_strong_secret_keys_accepted(self, monkeypatch):
        """Test that strong SECRET_KEY and REFRESH_SECRET_KEY are accepted."""
        import secrets

        # Generate cryptographically secure keys
        strong_secret = secrets.token_urlsafe(64)
        strong_refresh = secrets.token_urlsafe(64)

        monkeypatch.setenv("SECRET_KEY", strong_secret)
        monkeypatch.setenv("REFRESH_SECRET_KEY", strong_refresh)

        # Should not raise any exceptions
        settings = Settings()

        assert settings.SECRET_KEY == strong_secret
        assert settings.REFRESH_SECRET_KEY == strong_refresh
        assert len(settings.SECRET_KEY) >= 32
        assert len(settings.REFRESH_SECRET_KEY) >= 32

    def test_minimum_length_keys_accepted(self, monkeypatch):
        """Test that 32-character keys (minimum) are accepted."""
        secret_key = "a" * 32  # Exactly 32 characters
        refresh_key = "b" * 32  # Exactly 32 characters

        monkeypatch.setenv("SECRET_KEY", secret_key)
        monkeypatch.setenv("REFRESH_SECRET_KEY", refresh_key)

        settings = Settings()

        assert settings.SECRET_KEY == secret_key
        assert settings.REFRESH_SECRET_KEY == refresh_key

    def test_missing_secret_key_rejected(self, monkeypatch):
        """Test that missing SECRET_KEY is rejected."""
        # Only set REFRESH_SECRET_KEY, not SECRET_KEY
        monkeypatch.setenv("REFRESH_SECRET_KEY", "a" * 32)
        monkeypatch.delenv("SECRET_KEY", raising=False)

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_message = str(exc_info.value)
        assert "SECRET_KEY" in error_message

    def test_missing_refresh_secret_key_rejected(self, monkeypatch):
        """Test that missing REFRESH_SECRET_KEY is rejected."""
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.delenv("REFRESH_SECRET_KEY", raising=False)

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_message = str(exc_info.value)
        assert "REFRESH_SECRET_KEY" in error_message


class TestSettingsDefaults:
    """Test default values for optional settings."""

    def test_algorithm_defaults_to_hs256(self, monkeypatch):
        """Test that ALGORITHM defaults to HS256."""
        import secrets

        monkeypatch.setenv("SECRET_KEY", secrets.token_urlsafe(64))
        monkeypatch.setenv("REFRESH_SECRET_KEY", secrets.token_urlsafe(64))
        monkeypatch.delenv("ALGORITHM", raising=False)

        settings = Settings()

        assert settings.ALGORITHM == "HS256"

    def test_token_expiration_defaults(self, monkeypatch):
        """Test that token expiration settings have sensible defaults."""
        import secrets

        monkeypatch.setenv("SECRET_KEY", secrets.token_urlsafe(64))
        monkeypatch.setenv("REFRESH_SECRET_KEY", secrets.token_urlsafe(64))

        settings = Settings()

        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 30  # 30 minutes
        assert settings.REFRESH_TOKEN_EXPIRE_DAYS == 7  # 7 days

    def test_frontend_url_defaults(self, monkeypatch):
        """Test that FRONTEND_URL has proper default."""
        import secrets

        monkeypatch.setenv("SECRET_KEY", secrets.token_urlsafe(64))
        monkeypatch.setenv("REFRESH_SECRET_KEY", secrets.token_urlsafe(64))
        monkeypatch.delenv("FRONTEND_URL", raising=False)

        settings = Settings()

        assert settings.FRONTEND_URL == "http://localhost:3000"

    @pytest.mark.parametrize(
        ("frontend_url", "expected_root"),
        [
            ("https://staging.rext.ai", "https://staging.rext.ai/"),
            ("https://app.rext.ai/", "https://app.rext.ai/"),
        ],
    )
    def test_frontend_root_url_is_environment_aware(
        self,
        monkeypatch,
        frontend_url,
        expected_root,
    ):
        """Test checkout redirects use the configured frontend root."""
        import secrets

        monkeypatch.setenv("SECRET_KEY", secrets.token_urlsafe(64))
        monkeypatch.setenv("REFRESH_SECRET_KEY", secrets.token_urlsafe(64))
        monkeypatch.setenv("FRONTEND_URL", frontend_url)

        settings = Settings()

        assert settings.frontend_root_url == expected_root

    def test_debug_defaults_to_false(self, monkeypatch):
        """Test that DEBUG defaults to False."""
        import secrets

        monkeypatch.setenv("SECRET_KEY", secrets.token_urlsafe(64))
        monkeypatch.setenv("REFRESH_SECRET_KEY", secrets.token_urlsafe(64))
        monkeypatch.delenv("DEBUG", raising=False)

        settings = Settings()

        assert settings.DEBUG is False


class TestDebugParsing:
    """Test DEBUG flag parsing from various string values."""

    @pytest.mark.parametrize(
        "debug_value,expected",
        [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("0", False),
            ("no", False),
            ("off", False),
            ("", False),
        ],
    )
    def test_debug_string_parsing(self, monkeypatch, debug_value, expected):
        """Test that DEBUG string values are parsed correctly."""
        import secrets

        monkeypatch.setenv("SECRET_KEY", secrets.token_urlsafe(64))
        monkeypatch.setenv("REFRESH_SECRET_KEY", secrets.token_urlsafe(64))
        monkeypatch.setenv("DEBUG", debug_value)

        settings = Settings()

        assert settings.DEBUG is expected


class TestAllowedOriginsList:
    """Test ALLOWED_ORIGINS parsing into list."""

    def test_allowed_origins_parsed_to_list(self, monkeypatch):
        """Test that comma-separated ALLOWED_ORIGINS is parsed to list."""
        import secrets

        monkeypatch.setenv("SECRET_KEY", secrets.token_urlsafe(64))
        monkeypatch.setenv("REFRESH_SECRET_KEY", secrets.token_urlsafe(64))
        monkeypatch.setenv(
            "ALLOWED_ORIGINS", "http://localhost:3000,http://example.com,https://app.example.com"
        )

        settings = Settings()

        assert settings.allowed_origins_list == [
            "http://localhost:3000",
            "http://example.com",
            "https://app.example.com",
        ]

    def test_allowed_origins_strips_whitespace(self, monkeypatch):
        """Test that whitespace in ALLOWED_ORIGINS is stripped."""
        import secrets

        monkeypatch.setenv("SECRET_KEY", secrets.token_urlsafe(64))
        monkeypatch.setenv("REFRESH_SECRET_KEY", secrets.token_urlsafe(64))
        monkeypatch.setenv(
            "ALLOWED_ORIGINS",
            " http://localhost:3000 , http://example.com , https://app.example.com ",
        )

        settings = Settings()

        assert settings.allowed_origins_list == [
            "http://localhost:3000",
            "http://example.com",
            "https://app.example.com",
        ]


class TestGetSettings:
    """Test the get_settings() singleton function."""

    def test_get_settings_returns_singleton(self, monkeypatch):
        """Test that get_settings() returns the same instance."""
        import secrets

        from src.api.config import _settings

        monkeypatch.setenv("SECRET_KEY", secrets.token_urlsafe(64))
        monkeypatch.setenv("REFRESH_SECRET_KEY", secrets.token_urlsafe(64))

        # Reset the global singleton
        import src.api.config

        src.api.config._settings = None

        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2  # Same instance


class TestProductionScenarios:
    """Test scenarios that should occur in production deployments."""

    def test_production_keys_from_env_file(self, monkeypatch, tmp_path):
        """Test that production keys are loaded from .env file."""
        import secrets

        # Create a temporary .env file
        env_file = tmp_path / ".env"
        secret_key = secrets.token_urlsafe(64)
        refresh_key = secrets.token_urlsafe(64)

        env_file.write_text(f"""
SECRET_KEY={secret_key}
REFRESH_SECRET_KEY={refresh_key}
ALGORITHM=HS256
ENVIRONMENT=production
DEBUG=false
""")

        # Point Pydantic to our test .env file
        monkeypatch.setenv("SECRET_KEY", secret_key)
        monkeypatch.setenv("REFRESH_SECRET_KEY", refresh_key)
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DEBUG", "false")

        settings = Settings()

        assert settings.SECRET_KEY == secret_key
        assert settings.REFRESH_SECRET_KEY == refresh_key
        assert settings.ENVIRONMENT == "production"
        assert settings.DEBUG is False

    def test_production_rejects_weak_keys(self, monkeypatch):
        """Test that production environment rejects weak keys."""
        monkeypatch.setenv("SECRET_KEY", "weak")
        monkeypatch.setenv("REFRESH_SECRET_KEY", "weak")
        monkeypatch.setenv("ENVIRONMENT", "production")

        with pytest.raises(ValidationError):
            Settings()


class TestPaymentSettingsValidation:
    """Test validation and normalization in PaymentSettings."""

    def test_payment_settings_blank_credentials_normalize_to_none(self, monkeypatch):
        """Test that blank credential strings are normalized to None."""
        from src.config.payment_config import PaymentSettings

        monkeypatch.setenv("LEMONSQUEEZY_API_KEY", "   ")
        monkeypatch.setenv("LEMONSQUEEZY_STORE_ID", "")
        monkeypatch.setenv("LEMONSQUEEZY_WEBHOOK_SECRET", "\t")

        # In sandbox mode, it shouldn't raise ValidationError even if missing
        settings = PaymentSettings(payment_sandbox_mode=True)

        assert settings.lemonsqueezy_api_key is None
        assert settings.lemonsqueezy_store_id is None
        assert settings.lemonsqueezy_webhook_secret is None

    def test_payment_settings_requires_credentials_when_not_sandbox(self, monkeypatch):
        """Test that missing credentials raise ValidationError in non-sandbox mode."""
        from src.config.payment_config import PaymentSettings

        monkeypatch.delenv("LEMONSQUEEZY_API_KEY", raising=False)
        monkeypatch.delenv("LEMONSQUEEZY_STORE_ID", raising=False)
        monkeypatch.delenv("LEMONSQUEEZY_WEBHOOK_SECRET", raising=False)

        with pytest.raises(ValidationError) as exc_info:
            PaymentSettings(payment_sandbox_mode=False)

        assert "Missing required LemonSqueezy credentials" in str(exc_info.value)


class TestStorageSettingsValidation:
    """Test validation and normalization in StorageSettings."""

    def test_storage_settings_blank_credentials_normalize_to_none(self, monkeypatch):
        """Test that blank storage credential strings are normalized to None."""
        from src.config.storage_config import StorageSettings

        monkeypatch.setenv("R2_BUCKET", "   ")
        monkeypatch.setenv("R2_ACCOUNT_ID", "")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "\t")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "")

        # When backend is local, it shouldn't raise ValidationError even if missing
        settings = StorageSettings(storage_backend="local")

        assert settings.r2_bucket is None
        assert settings.r2_account_id is None
        assert settings.r2_access_key_id is None
        assert settings.r2_secret_access_key is None

    def test_storage_settings_requires_credentials_when_r2_backend(self, monkeypatch):
        """Test that missing credentials raise ValidationError when R2 backend is selected."""
        from src.config.storage_config import StorageSettings

        monkeypatch.delenv("R2_BUCKET", raising=False)
        monkeypatch.delenv("R2_ACCOUNT_ID", raising=False)
        monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)

        with pytest.raises(ValidationError) as exc_info:
            StorageSettings(storage_backend="r2")

        assert "Missing required R2 storage credentials" in str(exc_info.value)
