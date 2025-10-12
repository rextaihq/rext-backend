"""
Email Provider Factory

Factory pattern for creating email provider instances based on configuration.
Supports multiple providers with fallback mechanism.
"""
from typing import Optional
from src.providers.email.base import IEmailProvider
from src.providers.email.resend_provider import ResendEmailProvider
from src.providers.email.smtp_provider import SMTPEmailProvider
from src.providers.email.mock_provider import MockEmailProvider
from src.config.email_config import email_config
from src.api.lib.logger import auto_logger

logger = auto_logger()


class EmailProviderFactory:
    """
    Factory for creating email provider instances.

    Uses configuration to determine which provider to instantiate.
    Supports fallback providers if primary provider fails to initialize.
    """

    _instance: Optional[IEmailProvider] = None
    _fallback_instance: Optional[IEmailProvider] = None

    @classmethod
    def get_provider(cls, force_recreate: bool = False) -> IEmailProvider:
        """
        Get email provider instance (singleton pattern).

        Args:
            force_recreate: If True, creates new instance even if one exists

        Returns:
            Configured email provider instance

        Raises:
            ValueError: If no valid provider can be created

        Note:
            Uses singleton pattern to reuse provider instances across the application.
            Provider is determined by EMAIL_PROVIDER environment variable.
        """
        if cls._instance is None or force_recreate:
            cls._instance = cls._create_provider(email_config.email_provider)

        return cls._instance

    @classmethod
    def get_fallback_provider(cls, force_recreate: bool = False) -> Optional[IEmailProvider]:
        """
        Get fallback email provider instance.

        Args:
            force_recreate: If True, creates new instance even if one exists

        Returns:
            Fallback provider instance or None if not configured

        Note:
            Fallback provider is used when primary provider fails.
            Configured via EMAIL_FALLBACK_PROVIDER environment variable.
        """
        if not email_config.email_fallback_provider:
            logger.debug("No fallback provider configured")
            return None

        if cls._fallback_instance is None or force_recreate:
            try:
                cls._fallback_instance = cls._create_provider(
                    email_config.email_fallback_provider
                )
            except Exception as e:
                logger.error(
                    f"Failed to create fallback provider: {str(e)}",
                    extra={
                        "fallback_provider": email_config.email_fallback_provider,
                        "error_type": type(e).__name__
                    }
                )
                return None

        return cls._fallback_instance

    @classmethod
    def _create_provider(cls, provider_name: str) -> IEmailProvider:
        """
        Create email provider instance by name.

        Args:
            provider_name: Provider identifier ('resend', 'smtp', 'mock')

        Returns:
            Email provider instance

        Raises:
            ValueError: If provider_name is invalid or provider creation fails
        """
        provider_name = provider_name.lower().strip()

        logger.info(
            f"Creating email provider",
            extra={"provider": provider_name}
        )

        try:
            if provider_name == "resend":
                return cls._create_resend_provider()
            elif provider_name == "smtp":
                return cls._create_smtp_provider()
            elif provider_name == "mock":
                return cls._create_mock_provider()
            else:
                error_msg = f"Unknown email provider: {provider_name}"
                logger.error(error_msg)
                raise ValueError(error_msg)

        except Exception as e:
            error_msg = f"Failed to create {provider_name} provider: {str(e)}"
            logger.error(
                error_msg,
                extra={
                    "provider": provider_name,
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            raise ValueError(error_msg) from e

    @classmethod
    def _create_resend_provider(cls) -> ResendEmailProvider:
        """
        Create Resend email provider instance.

        Returns:
            ResendEmailProvider instance

        Raises:
            ValueError: If Resend configuration is invalid
        """
        logger.info("Creating Resend email provider")
        return ResendEmailProvider()

    @classmethod
    def _create_smtp_provider(cls) -> SMTPEmailProvider:
        """
        Create SMTP email provider instance.

        Returns:
            SMTPEmailProvider instance

        Raises:
            ValueError: If SMTP configuration is invalid
        """
        logger.info("Creating SMTP email provider")
        return SMTPEmailProvider()

    @classmethod
    def _create_mock_provider(cls) -> MockEmailProvider:
        """
        Create Mock email provider instance.

        Returns:
            MockEmailProvider instance
        """
        logger.info("Creating Mock email provider")
        return MockEmailProvider()

    @classmethod
    def reset(cls) -> None:
        """
        Reset factory singleton instances.

        Useful for testing to force recreation of providers with new configuration.
        """
        logger.info("Resetting email provider factory instances")
        cls._instance = None
        cls._fallback_instance = None

    @classmethod
    def get_available_providers(cls) -> list[str]:
        """
        Get list of available provider names.

        Returns:
            List of provider identifiers
        """
        return ["resend", "smtp", "mock"]

    @classmethod
    def is_provider_available(cls, provider_name: str) -> bool:
        """
        Check if a provider is available and can be created.

        Args:
            provider_name: Provider identifier to check

        Returns:
            True if provider can be created, False otherwise
        """
        try:
            # Try to create provider (don't store it)
            cls._create_provider(provider_name)
            return True
        except Exception as e:
            logger.debug(
                f"Provider {provider_name} not available: {str(e)}",
                extra={"provider": provider_name}
            )
            return False


# Convenience functions for common use cases

def get_email_provider() -> IEmailProvider:
    """
    Get the configured email provider instance.

    This is a convenience function that wraps EmailProviderFactory.get_provider().

    Returns:
        Configured email provider instance

    Raises:
        ValueError: If no valid provider can be created

    Example:
        >>> provider = get_email_provider()
        >>> result = await provider.send_email(message)
    """
    return EmailProviderFactory.get_provider()


def get_fallback_email_provider() -> Optional[IEmailProvider]:
    """
    Get the fallback email provider instance if configured.

    This is a convenience function that wraps EmailProviderFactory.get_fallback_provider().

    Returns:
        Fallback provider instance or None if not configured

    Example:
        >>> fallback = get_fallback_email_provider()
        >>> if fallback:
        >>>     result = await fallback.send_email(message)
    """
    return EmailProviderFactory.get_fallback_provider()
