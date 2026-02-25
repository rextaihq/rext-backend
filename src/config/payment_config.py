"""
Payment Provider Configuration

This module handles configuration for the LemonSqueezy payment provider.
"""

from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, model_validator
from dotenv import load_dotenv
import os

load_dotenv()

PaymentProviderType = Literal["lemonsqueezy"]


class PaymentSettings(BaseSettings):
    """Payment provider settings"""

    # Provider selection (only lemonsqueezy supported)
    payment_provider: PaymentProviderType = "lemonsqueezy"

    # Sandbox/test mode toggle
    payment_sandbox_mode: bool = True

    # Generic settings
    payment_currency: str = "USD"
    payment_success_url: str = "http://localhost:3000/checkout/success"
    payment_cancel_url: str = "http://localhost:3000/pricing"

    # LemonSqueezy configuration
    lemonsqueezy_api_key: Optional[str] = None
    lemonsqueezy_store_id: Optional[str] = None
    lemonsqueezy_webhook_secret: Optional[str] = None

    # Webhook Security
    webhook_ip_validation_enabled: bool = True
    lemonsqueezy_webhook_ips: str = "159.223.172.0/24"

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

    @field_validator(
        "lemonsqueezy_api_key",
        "lemonsqueezy_store_id",
        "lemonsqueezy_webhook_secret",
        mode="before"
    )
    @classmethod
    def normalize_blank_credentials(cls, v: Optional[str]) -> Optional[str]:
        """Normalize blank strings to None"""
        if v is None:
            return None
        if isinstance(v, str):
            stripped = v.strip()
            return stripped or None
        return v

    @model_validator(mode="after")
    def validate_required_payment_credentials(self) -> "PaymentSettings":
        """Fail fast if any required LemonSqueezy credential is missing in non-sandbox mode"""
        if self.payment_provider == "lemonsqueezy" and not self.payment_sandbox_mode:
            missing = []
            if not self.lemonsqueezy_api_key:
                missing.append("LEMONSQUEEZY_API_KEY")
            if not self.lemonsqueezy_store_id:
                missing.append("LEMONSQUEEZY_STORE_ID")
            if not self.lemonsqueezy_webhook_secret:
                missing.append("LEMONSQUEEZY_WEBHOOK_SECRET")
            if missing:
                raise ValueError(
                    "Missing required LemonSqueezy credentials for non-sandbox mode: "
                    + ", ".join(missing)
                )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Global settings instance
payment_settings = PaymentSettings()
