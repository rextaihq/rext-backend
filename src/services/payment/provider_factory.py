"""Payment provider factory."""
from typing import Optional
from .base_provider import PaymentProvider
from .mock_provider import MockPaymentProvider
from src.config.payment_config import payment_settings


def get_payment_provider() -> PaymentProvider:
    """
    Factory to get payment provider based on configuration.

    Returns the appropriate payment provider instance based on the
    PAYMENT_PROVIDER environment variable.

    Returns:
        PaymentProvider instance

    Raises:
        ValueError: If provider is not recognized
    """
    provider_name = payment_settings.payment_provider

    if provider_name == "mock":
        return MockPaymentProvider()

    elif provider_name == "lemonsqueezy":
        # Import here to avoid loading SDK if not needed
        from .providers.lemonsqueezy import LemonSqueezyProvider
        return LemonSqueezyProvider()

    elif provider_name == "paddle":
        # Import here to avoid loading SDK if not needed
        from .providers.paddle import PaddleProvider
        return PaddleProvider()

    elif provider_name == "fastspring":
        # Import here to avoid loading SDK if not needed
        from .providers.fastspring import FastSpringProvider
        return FastSpringProvider()

    else:
        raise ValueError(
            f"Unknown payment provider: {provider_name}. "
            f"Supported providers: mock, lemonsqueezy, paddle, fastspring"
        )


# Singleton instance for dependency injection
_payment_provider_instance: Optional[PaymentProvider] = None


def get_payment_provider_singleton() -> PaymentProvider:
    """
    Get or create singleton payment provider instance.

    This ensures we reuse the same provider instance across the application,
    which is important for providers that maintain internal state or connections.

    Returns:
        PaymentProvider instance
    """
    global _payment_provider_instance
    if _payment_provider_instance is None:
        _payment_provider_instance = get_payment_provider()
    return _payment_provider_instance


def reset_payment_provider():
    """
    Reset the payment provider singleton.

    Useful for testing or when changing provider configuration at runtime.
    """
    global _payment_provider_instance
    _payment_provider_instance = None
