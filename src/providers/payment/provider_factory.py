"""
Payment Provider Factory

This module provides a factory function to get the configured payment provider.
The provider is selected based on the PAYMENT_PROVIDER environment variable.
"""

from src.providers.payment.base_provider import PaymentProvider
from src.providers.payment.mock_provider import MockPaymentProvider
from src.config.payment_config import payment_settings
from src.utils.logger import logger


def get_payment_provider() -> PaymentProvider:
    """
    Factory function to get the configured payment provider.

    The provider is determined by the payment_settings.payment_provider value:
    - "mock": MockPaymentProvider (for development/testing)
    - "lemonsqueezy": LemonSqueezyProvider (requires Plan 01B implementation)
    - "paddle": PaddleProvider (requires Plan 01B implementation)
    - "fastspring": FastSpringProvider (requires Plan 01B implementation)

    Returns:
        PaymentProvider: Configured payment provider instance

    Raises:
        ValueError: If unknown payment provider is configured
    """
    provider_name = payment_settings.payment_provider

    logger.info(f"Initializing payment provider: {provider_name}")

    if provider_name == "mock":
        return MockPaymentProvider()

    elif provider_name == "lemonsqueezy":
        try:
            from src.providers.payment.providers.lemonsqueezy import LemonSqueezyProvider
            return LemonSqueezyProvider()
        except ImportError:
            logger.error(
                "LemonSqueezy provider not implemented yet. "
                "Please complete Plan 01B first or use mock provider."
            )
            raise ValueError(
                "LemonSqueezy provider not implemented. "
                "Set PAYMENT_PROVIDER=mock in .env to use mock provider."
            )

    elif provider_name == "paddle":
        try:
            from src.providers.payment.providers.paddle import PaddleProvider
            return PaddleProvider()
        except ImportError:
            logger.error(
                "Paddle provider not implemented yet. "
                "Please complete Plan 01B first or use mock provider."
            )
            raise ValueError(
                "Paddle provider not implemented. "
                "Set PAYMENT_PROVIDER=mock in .env to use mock provider."
            )

    elif provider_name == "fastspring":
        try:
            from src.providers.payment.providers.fastspring import FastSpringProvider
            return FastSpringProvider()
        except ImportError:
            logger.error(
                "FastSpring provider not implemented yet. "
                "Please complete Plan 01B first or use mock provider."
            )
            raise ValueError(
                "FastSpring provider not implemented. "
                "Set PAYMENT_PROVIDER=mock in .env to use mock provider."
            )

    else:
        logger.error(f"Unknown payment provider: {provider_name}")
        raise ValueError(
            f"Unknown payment provider: {provider_name}. "
            f"Supported providers: mock, lemonsqueezy, paddle, fastspring"
        )


# Singleton instance for reuse
_provider_instance: PaymentProvider = None


def get_payment_provider_singleton() -> PaymentProvider:
    """
    Get singleton instance of payment provider.

    This ensures the same provider instance is reused across requests,
    which is useful for providers that maintain connection pools or cache data.

    Returns:
        PaymentProvider: Singleton payment provider instance
    """
    global _provider_instance

    if _provider_instance is None:
        _provider_instance = get_payment_provider()

    return _provider_instance
