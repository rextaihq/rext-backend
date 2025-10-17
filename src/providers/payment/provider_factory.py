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
    - "lemonsqueezy": LemonSqueezyProvider (production payment processing)

    Returns:
        PaymentProvider: Configured payment provider instance

    Raises:
        ValueError: If unknown payment provider is configured or required config is missing
    """
    provider_name = payment_settings.payment_provider

    logger.info(f"Initializing payment provider: {provider_name}")

    if provider_name == "mock":
        return MockPaymentProvider()

    elif provider_name == "lemonsqueezy":
        try:
            from src.providers.payment.providers.lemonsqueezy import LemonSqueezyProvider

            # Validate required configuration
            if not payment_settings.lemonsqueezy_api_key:
                raise ValueError("LEMONSQUEEZY_API_KEY is required in .env")
            if not payment_settings.lemonsqueezy_store_id:
                raise ValueError("LEMONSQUEEZY_STORE_ID is required in .env")

            # Initialize with configuration from settings
            return LemonSqueezyProvider(
                api_key=payment_settings.lemonsqueezy_api_key,
                store_id=payment_settings.lemonsqueezy_store_id,
                webhook_secret=payment_settings.lemonsqueezy_webhook_secret,
                sandbox_mode=(payment_settings.payment_provider == "lemonsqueezy_sandbox")
            )
        except ImportError as e:
            logger.error(f"LemonSqueezy provider import failed: {e}")
            raise ValueError(
                "LemonSqueezy provider not available. "
                "Set PAYMENT_PROVIDER=mock in .env to use mock provider."
            )

    else:
        logger.error(f"Unknown payment provider: {provider_name}")
        raise ValueError(
            f"Unknown payment provider: {provider_name}. "
            f"Supported providers: mock, lemonsqueezy"
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
