"""
Payment Provider Factory

This module provides a factory function to get the configured payment provider.
The provider is selected based on the PAYMENT_PROVIDER environment variable.
"""

from src.providers.payment.base_provider import PaymentProvider
from src.config.payment_config import payment_settings
from src.utils.logger import logger


def get_payment_provider() -> PaymentProvider:
    """
    Factory function to get the configured payment provider.

    The provider is determined by the payment_settings.payment_provider value:
    - "lemonsqueezy": LemonSqueezyProvider (production payment processing)

    Returns:
        PaymentProvider: Configured payment provider instance

    Raises:
        ValueError: If unknown payment provider is configured or required config is missing
    """
    provider_name = payment_settings.payment_provider

    logger.info(f"Initializing payment provider: {provider_name}")

    if payment_settings.payment_sandbox_mode:
        logger.warning(
            "Payment provider initialized in SANDBOX MODE. "
            "No real charges will be processed."
        )

    if provider_name == "lemonsqueezy":
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
                sandbox_mode=payment_settings.payment_sandbox_mode
            )
        except ImportError as e:
            logger.error(f"LemonSqueezy provider import failed: {e}")
            raise ValueError(
                "LemonSqueezy provider not available. "
                "Ensure the provider is properly installed."
            )

    else:
        logger.error(f"Unknown payment provider: {provider_name}")
        raise ValueError(
            f"Unknown payment provider: {provider_name}. "
            f"Only 'lemonsqueezy' is supported."
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
