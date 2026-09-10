"""Email provider abstractions"""

from src.providers.email.base import EmailMessage, EmailRecipient, EmailResult, IEmailProvider
from src.providers.email.factory import (
    EmailProviderFactory,
    get_email_provider,
    get_fallback_email_provider,
)
from src.providers.email.mock_provider import MockEmailProvider
from src.providers.email.resend_provider import ResendEmailProvider
from src.providers.email.smtp_provider import SMTPEmailProvider

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
