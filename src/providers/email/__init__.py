"""Email provider abstractions"""
from src.providers.email.base import (
    IEmailProvider,
    EmailMessage,
    EmailRecipient,
    EmailResult
)
from src.providers.email.resend_provider import ResendEmailProvider
from src.providers.email.smtp_provider import SMTPEmailProvider
from src.providers.email.mock_provider import MockEmailProvider
from src.providers.email.factory import (
    EmailProviderFactory,
    get_email_provider,
    get_fallback_email_provider
)

__all__ = [
    # Base interfaces
    "IEmailProvider",
    "EmailMessage",
    "EmailRecipient",
    "EmailResult",
    # Providers
    "ResendEmailProvider",
    "SMTPEmailProvider",
    "MockEmailProvider",
    # Factory
    "EmailProviderFactory",
    "get_email_provider",
    "get_fallback_email_provider",
]
