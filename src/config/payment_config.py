"""
Payment Provider Configuration

This module handles configuration for the LemonSqueezy payment provider.
"""

import os
from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.config.hidden_secrets import HidesSecrets

load_dotenv()

PaymentProviderType = Literal["lemonsqueezy"]


class PaymentSettings(HidesSecrets, BaseSettings):
    """Payment provider settings"""

    # Provider selection (only lemonsqueezy supported)
    payment_provider: PaymentProviderType = "lemonsqueezy"

    # Sandbox/test mode toggle
    payment_sandbox_mode: bool = os.getenv("LEMONSQUEEZY_SANDBOX_MODE", "true").lower() == "true"

    # Generic settings
    payment_currency: str = os.getenv("PAYMENT_CURRENCY", "USD")
    payment_success_url: str = os.getenv(
        "PAYMENT_SUCCESS_URL", "http://localhost:3000/checkout/success"
    )
    payment_cancel_url: str = os.getenv(
        "PAYMENT_CANCEL_URL", "http://localhost:3000/checkout/cancel"
    )

    # LemonSqueezy configuration
    lemonsqueezy_api_key: Optional[str] = os.getenv("LEMONSQUEEZY_API_KEY")
    lemonsqueezy_store_id: Optional[str] = os.getenv("LEMONSQUEEZY_STORE_ID")
    lemonsqueezy_webhook_secret: Optional[str] = os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET")

    # Webhook Security
    # Disabled by default: LemonSqueezy does not publish an official webhook
    # source IP range, so this list cannot be kept reliably accurate and has
    # caused legitimate webhooks (403 "Webhook source IP not authorized") to
    # be dropped in production. HMAC signature verification (verify_webhook_signature)
    # is the real authentication layer for this endpoint. Only enable this if
    # LemonSqueezy support provides a confirmed, stable IP range.
    webhook_ip_validation_enabled: bool = (
        os.getenv("WEBHOOK_IP_VALIDATION_ENABLED", "false").lower() == "true"
    )
    lemonsqueezy_webhook_ips: str = os.getenv("LEMONSQUEEZY_WEBHOOK_IPS", "159.223.172.0/24")

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
        mode="before",
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
