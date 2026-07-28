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

# Environments that are NOT deployed. Anything else — including a misspelling such
# as "stagging" — is treated as deployed so a typo fails closed rather than
# silently disabling these guards.
_LOCAL_ENVIRONMENTS = frozenset({"development", "dev", "local", "test", "testing"})

# Sender addresses that must never reach real users. onboarding@resend.dev is
# Resend's shared sandbox sender: it only delivers to the Resend account owner and
# rejects every other recipient, so all outbound mail fails one message at a time.
_PLACEHOLDER_SENDERS = frozenset({
    "onboarding@resend.dev",
    "noreply@rext.com",       # EmailConfig's own fallback default
    "noreply@example.com",
})

_env = _os.getenv("ENVIRONMENT", "development").strip().lower()
_is_deployed = _env not in _LOCAL_ENVIRONMENTS

if _is_deployed and not email_config.resend_webhook_secret:
    _startup_logger.critical(
        "RESEND_WEBHOOK_SECRET is not configured! "
        "Webhook signature verification will reject all incoming webhooks in %s. "
        "Set RESEND_WEBHOOK_SECRET in your environment variables.",
        _env
    )


def _validate_sender_config() -> None:
    """
    Fail fast when the outbound sender cannot actually deliver mail.

    A bad RESEND_FROM_EMAIL does not surface until the first send, where it fails
    per-message inside the provider and is easily missed. Deployed environments
    refuse to boot instead; local development only warns.

    Resend-specific: the sender rules only apply when Resend is actually in use.
    The mock and SMTP providers ignore RESEND_FROM_EMAIL, so validating it there
    would block valid configurations (e.g. EMAIL_PROVIDER=mock in tests) over a
    setting that is never read.
    """
    if not email_config.email_enabled:
        return

    active_providers = {email_config.email_provider, email_config.email_fallback_provider}
    if "resend" not in active_providers:
        return

    sender = (email_config.resend_from_email or "").strip().lower()

    problem = None
    if not sender:
        problem = "RESEND_FROM_EMAIL is not set"
    elif "@" not in sender:
        problem = f"RESEND_FROM_EMAIL is not a valid address: {sender!r}"
    elif sender in _PLACEHOLDER_SENDERS:
        problem = (
            f"RESEND_FROM_EMAIL is the placeholder/sandbox address {sender!r}, which "
            "only delivers to the Resend account owner. Verify a domain at "
            "resend.com/domains and set a sender on that domain"
        )

    if not problem:
        return

    if _is_deployed:
        raise RuntimeError(
            f"Invalid email sender configuration in environment {_env!r}: {problem}. "
            "Refusing to start — outbound email would fail silently."
        )

    _startup_logger.warning(
        "Email sender configuration problem (allowed in %s): %s", _env, problem
    )


def _validate_environment_name() -> None:
    """Warn loudly when ENVIRONMENT is not a value the codebase branches on."""
    known = _LOCAL_ENVIRONMENTS | {"staging", "stage", "production", "prod"}
    if _env not in known:
        _startup_logger.critical(
            "ENVIRONMENT=%r is not a recognised value %s. Environment-gated behaviour "
            "(webhook signature enforcement, IP allowlisting, email guards) will not "
            "match the environment you intended.",
            _env,
            sorted(known),
        )


_validate_environment_name()
_validate_sender_config()
