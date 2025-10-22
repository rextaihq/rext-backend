"""
Payment Provider Configuration

This module handles configuration for the LemonSqueezy payment provider.
"""

from typing import Literal
from pydantic_settings import BaseSettings
from pydantic import field_validator


PaymentProviderType = Literal["lemonsqueezy"]


class PaymentSettings(BaseSettings):
    """Payment provider settings"""

    # Provider selection (only lemonsqueezy supported)
    payment_provider: PaymentProviderType = "lemonsqueezy"

    # Generic settings
    payment_currency: str = "USD"
    payment_success_url: str = "http://localhost:3000/checkout/success"
    payment_cancel_url: str = "http://localhost:3000/pricing"

    # LemonSqueezy configuration
    lemonsqueezy_api_key: str = ""
    lemonsqueezy_store_id: str = ""
    lemonsqueezy_webhook_secret: str = ""

    @field_validator("payment_provider")
    @classmethod
    def validate_payment_provider(cls, v: str) -> str:
        """Validate that only lemonsqueezy is used as payment provider"""
        if v != "lemonsqueezy":
            raise ValueError(
                f"Invalid payment provider: {v}. Only 'lemonsqueezy' is supported. "
                f"Mock payment provider has been removed."
            )
        return v

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


# Global settings instance
payment_settings = PaymentSettings()
