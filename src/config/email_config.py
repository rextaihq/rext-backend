"""Email Configuration using Pydantic Settings"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Optional


class EmailConfig(BaseSettings):
    """
    Email configuration from environment variables.
    
    Supports multiple providers with fallback mechanism:
    - resend: Primary production provider
    - smtp: Fallback provider
    - mock: Testing provider
    """
    
    # Provider selection
    email_provider: Literal["resend", "smtp", "mock"] = "resend"
    email_fallback_provider: Optional[Literal["resend", "smtp", "mock"]] = None  # No fallback by default
    
    # Resend configuration
    resend_api_key: Optional[str] = None
    resend_from_email: str = "noreply@rext.com"
    resend_from_name: str = "REXT"
    resend_webhook_secret: Optional[str] = None  # For webhook signature verification
    
    # SMTP configuration (fallback)
    smtp_server: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: bool = True
    
    # Email retry features — consumed by EmailService._send_with_provider()
    email_retry_enabled: bool = True  # When False, send attempts once with no retry or fallback
    email_retry_max_attempts: int = 3  # Max attempts per provider (tenacity stop_after_attempt)
    email_retry_delay_seconds: int = 5  # Min wait between retries in seconds (tenacity wait_exponential min)

    
    # Environment-specific settings
    email_enabled: bool = True  # Master switch to disable all email sending
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"  # Ignore extra fields from .env
    )


# Global configuration instance
email_config = EmailConfig()

import os as _os
import logging as _logging

_startup_logger = _logging.getLogger("email_config")

_env = _os.getenv("ENVIRONMENT", "development").lower()
if _env in ("production", "staging", "prod") and not email_config.resend_webhook_secret:
    _startup_logger.critical(
        "RESEND_WEBHOOK_SECRET is not configured! "
        "Webhook signature verification will reject all incoming webhooks in %s. "
        "Set RESEND_WEBHOOK_SECRET in your environment variables.",
        _env
    )
