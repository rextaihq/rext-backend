"""
Payment Provider Configuration

This module handles configuration for the LemonSqueezy payment provider.
"""

from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from dotenv import load_dotenv
import os

load_dotenv()

PaymentProviderType = Literal["lemonsqueezy"]


class PaymentSettings(BaseSettings):
    """Payment provider settings"""

    # Provider selection (only lemonsqueezy supported)
    payment_provider: PaymentProviderType = "lemonsqueezy"

    # Sandbox/test mode toggle
    payment_sandbox_mode: bool = False

    # Generic settings
    payment_currency: str = os.getenv("PAYMENT_CURRENCY", "USD")
    payment_success_url: str = f"{os.getenv('FRONTEND_URL')}/checkout/success"
    payment_cancel_url: str = f"{os.getenv('FRONTEND_URL')}/pricing"

    # LemonSqueezy configuration
    lemonsqueezy_api_key: str = os.getenv("LEMONSQUEEZY_API_KEY")
    lemonsqueezy_store_id: str = os.getenv("LEMONSQUEEZY_STORE_ID")
    lemonsqueezy_webhook_secret: str = os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET")

    # Webhook Security (Phase 2, Task CRITICAL-4)
    webhook_ip_validation_enabled: bool = os.getenv("WEBHOOK_IP_VALIDATION_ENABLED", True)
    lemonsqueezy_webhook_ips: str = os.getenv("LEMONSQUEEZY_WEBHOOK_IPS", "159.223.172.0/24")  # Comma-separated IPs/CIDR ranges

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# Global settings instance
payment_settings = PaymentSettings()
