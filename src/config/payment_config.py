"""
Payment Provider Configuration

This module handles configuration for payment providers, supporting multiple
providers through environment variables.
"""

from typing import Literal
from pydantic_settings import BaseSettings


PaymentProviderType = Literal["mock", "lemonsqueezy", "paddle", "fastspring"]


class PaymentSettings(BaseSettings):
    """Payment provider settings"""

    # Provider selection (mock, lemonsqueezy, paddle, fastspring)
    payment_provider: PaymentProviderType = "mock"

    # Generic settings (provider-agnostic)
    payment_currency: str = "USD"
    payment_success_url: str = "http://localhost:3000/subscription/success"
    payment_cancel_url: str = "http://localhost:3000/subscription/cancel"

    # LemonSqueezy configuration
    lemonsqueezy_api_key: str = ""
    lemonsqueezy_store_id: str = ""
    lemonsqueezy_webhook_secret: str = ""

    # Paddle configuration
    paddle_vendor_id: str = ""
    paddle_api_key: str = ""
    paddle_webhook_secret: str = ""

    # FastSpring configuration
    fastspring_username: str = ""
    fastspring_password: str = ""
    fastspring_webhook_secret: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


# Global settings instance
payment_settings = PaymentSettings()
