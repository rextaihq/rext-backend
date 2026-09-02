"""
LemonSqueezy Webhook Utilities

Provides utilities for handling LemonSqueezy webhook events including
signature verification, payload parsing, and security validations.

Security: Uses HMAC SHA-256 with timing-safe comparison to prevent timing attacks.

Documentation: https://docs.lemonsqueezy.com/guides/developer-guide/webhooks
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.utils.logger import logger


class WebhookVerificationError(Exception):
    """Raised when webhook signature verification fails"""

    pass


class WebhookParsingError(Exception):
    """Raised when webhook payload cannot be parsed"""

    pass


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify webhook signature from LemonSqueezy using HMAC SHA-256.

    This function uses timing-safe comparison to prevent timing attacks.
    LemonSqueezy sends the signature in the X-Signature header.

    Args:
        payload: Raw webhook payload bytes (must be raw, not parsed)
        signature: Signature from X-Signature header
        secret: Webhook signing secret from LemonSqueezy settings

    Returns:
        bool: True if signature is valid, False otherwise

    Example:
        >>> raw_body = request.body  # FastAPI: await request.body()
        >>> signature = request.headers.get("X-Signature")
        >>> secret = settings.LEMONSQUEEZY_WEBHOOK_SECRET
        >>> is_valid = verify_webhook_signature(raw_body, signature, secret)
        >>> if not is_valid:
        >>>     raise HTTPException(401, "Invalid signature")

    Security Notes:
        - Always use raw request body (bytes), never parsed JSON
        - Use timing-safe comparison (hmac.compare_digest)
        - Log verification failures for security monitoring
        - Return 401 immediately if signature is invalid

    Reference:
        https://docs.lemonsqueezy.com/guides/developer-guide/webhooks#signing-requests
    """
    if not secret:
        logger.error("LemonSqueezy webhook secret is not configured")
        return False

    if not signature:
        logger.warning("LemonSqueezy webhook signature header is missing")
        return False

    try:
        # Compute HMAC SHA-256 signature
        expected_signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

        # Timing-safe comparison to prevent timing attacks
        is_valid = hmac.compare_digest(expected_signature, signature)

        if not is_valid:
            logger.warning(
                "SECURITY: LemonSqueezy webhook signature verification FAILED",
                extra={
                    "event": "webhook_verification_failed",
                    "severity": "SECURITY",
                    "expected_prefix": expected_signature[:8],
                    "received_prefix": signature[:8] if len(signature) >= 8 else signature,
                    "signature_length": len(signature),
                    "payload_size": len(payload),
                },
            )
        else:
            logger.debug(
                "LemonSqueezy webhook signature verified successfully",
                extra={"event": "webhook_verified", "signature_prefix": expected_signature[:8]},
            )

        return is_valid

    except Exception as e:
        logger.error(f"Error verifying webhook signature: {str(e)}")
        return False


def parse_webhook_payload(payload: bytes) -> Dict[str, Any]:
    """
    Parse LemonSqueezy webhook payload into structured data.

    LemonSqueezy webhook format:
    {
        "meta": {
            "event_name": "subscription_created",
            "webhook_id": "...",
            "custom_data": {...}
        },
        "data": {
            "type": "subscriptions",
            "id": "123",
            "attributes": {...}
        }
    }

    Args:
        payload: Raw webhook payload bytes

    Returns:
        Dict containing parsed webhook data with:
            - event_type: Event name (subscription_created, order_created, etc.)
            - event_id: Unique webhook event ID for idempotency
            - data: Event data (subscription, order, license, etc.)
            - custom_data: Custom metadata passed during checkout
            - timestamp: Event timestamp

    Raises:
        WebhookParsingError: If payload cannot be parsed

    Example:
        >>> webhook_data = parse_webhook_payload(raw_body)
        >>> if webhook_data["event_type"] == "subscription_created":
        >>>     handle_subscription_created(webhook_data)
    """
    try:
        event_data = json.loads(payload)

        meta = event_data.get("meta", {})
        data = event_data.get("data", {})

        return {
            "event_type": meta.get("event_name", "unknown"),
            "event_id": meta.get("webhook_id", ""),
            "custom_data": meta.get("custom_data", {}),
            "data": data,
            "timestamp": datetime.fromisoformat(
                meta.get("created_at", datetime.now(timezone.utc).isoformat())
            ),
            "test_mode": meta.get("test_mode", False),
            "raw_meta": meta,
            "raw_payload": event_data,
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse webhook JSON: {str(e)}")
        raise WebhookParsingError(f"Invalid JSON payload: {str(e)}") from e
    except Exception as e:
        logger.error(f"Error parsing webhook payload: {str(e)}")
        raise WebhookParsingError(f"Failed to parse payload: {str(e)}") from e


def extract_subscription_data(webhook_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract subscription-specific data from webhook payload.

    Args:
        webhook_data: Parsed webhook data from parse_webhook_payload()

    Returns:
        Dict containing subscription fields:
            - subscription_id: LemonSqueezy subscription ID
            - customer_id: LemonSqueezy customer ID
            - variant_id: Product variant ID
            - status: Subscription status
            - renews_at: Next renewal date
            - ends_at: Subscription end date
            - trial_ends_at: Trial end date (if applicable)
            - cancelled: Whether subscription is cancelled

    Raises:
        WebhookParsingError: If data structure is invalid
    """
    try:
        data = webhook_data.get("data", {})
        attributes = data.get("attributes", {})

        return {
            "subscription_id": data.get("id"),
            "customer_id": str(attributes.get("customer_id", "")),
            "variant_id": str(attributes.get("variant_id", "")),
            "product_id": str(attributes.get("product_id", "")),
            "status": attributes.get("status", ""),
            "renews_at": attributes.get("renews_at"),
            "ends_at": attributes.get("ends_at"),
            "trial_ends_at": attributes.get("trial_ends_at"),
            "cancelled": attributes.get("cancelled", False),
            "user_email": attributes.get("user_email", ""),
            "user_name": attributes.get("user_name", ""),
        }

    except Exception as e:
        logger.error(f"Error extracting subscription data: {str(e)}")
        raise WebhookParsingError(f"Invalid subscription data: {str(e)}") from e


def extract_order_data(webhook_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract order-specific data from webhook payload (for one-time purchases/LTDs).

    Args:
        webhook_data: Parsed webhook data from parse_webhook_payload()

    Returns:
        Dict containing order fields:
            - order_id: LemonSqueezy order ID
            - customer_id: LemonSqueezy customer ID
            - variant_id: Product variant ID
            - product_name: Product name
            - status: Order status
            - total: Total amount
            - user_email: Customer email
            - user_name: Customer name

    Raises:
        WebhookParsingError: If data structure is invalid
    """
    try:
        data = webhook_data.get("data", {})
        attributes = data.get("attributes", {})

        return {
            "order_id": data.get("id"),
            "customer_id": str(attributes.get("customer_id", "")),
            "variant_id": str(attributes.get("first_order_item", {}).get("variant_id", "")),
            "product_id": str(attributes.get("first_order_item", {}).get("product_id", "")),
            "product_name": attributes.get("first_order_item", {}).get("product_name", ""),
            "status": attributes.get("status", ""),
            "total": attributes.get("total", 0),
            "subtotal": attributes.get("subtotal", 0),
            "tax": attributes.get("tax", 0),
            "user_email": attributes.get("user_email", ""),
            "user_name": attributes.get("user_name", ""),
            "refunded": attributes.get("refunded", False),
            "refunded_at": attributes.get("refunded_at"),
        }

    except Exception as e:
        logger.error(f"Error extracting order data: {str(e)}")
        raise WebhookParsingError(f"Invalid order data: {str(e)}") from e


def extract_license_key_data(webhook_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract license key data from webhook payload (for LTDs).

    Args:
        webhook_data: Parsed webhook data from parse_webhook_payload()

    Returns:
        Dict containing license fields:
            - license_id: LemonSqueezy license key ID
            - license_key: The actual license key string
            - order_id: Associated order ID
            - product_id: Product ID
            - status: License status
            - activation_limit: Max activations allowed
            - activation_usage: Current activation count
            - expires_at: Expiration date (null for lifetime)

    Raises:
        WebhookParsingError: If data structure is invalid
    """
    try:
        data = webhook_data.get("data", {})
        attributes = data.get("attributes", {})

        return {
            "license_id": data.get("id"),
            "license_key": attributes.get("key", ""),
            "order_id": str(attributes.get("order_id", "")),
            "product_id": str(attributes.get("product_id", "")),
            "status": attributes.get("status", ""),
            "activation_limit": attributes.get("activation_limit", -1),
            "activation_usage": attributes.get("activation_usage", 0),
            "expires_at": attributes.get("expires_at"),
            "disabled": attributes.get("disabled", False),
        }

    except Exception as e:
        logger.error(f"Error extracting license key data: {str(e)}")
        raise WebhookParsingError(f"Invalid license key data: {str(e)}") from e


def get_user_identifier(webhook_data: Dict[str, Any]) -> Optional[str]:
    """
    Extract user identifier from webhook custom_data or email.

    Tries to find user_id from custom_data first (passed during checkout),
    then falls back to email address for user lookup.

    Args:
        webhook_data: Parsed webhook data

    Returns:
        User identifier (user_id or email) or None if not found
    """
    # Try custom_data.user_id first (most reliable)
    custom_data = webhook_data.get("custom_data", {})
    user_id = custom_data.get("user_id")
    if user_id:
        return str(user_id)

    # Fall back to email from data attributes
    data = webhook_data.get("data", {})
    attributes = data.get("attributes", {})
    email = attributes.get("user_email") or attributes.get("customer_email")

    return email if email else None


# Event type constants for easy reference
class WebhookEventTypes:
    """LemonSqueezy webhook event type constants"""

    # Subscription events
    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_UPDATED = "subscription_updated"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    SUBSCRIPTION_RESUMED = "subscription_resumed"
    SUBSCRIPTION_EXPIRED = "subscription_expired"
    SUBSCRIPTION_PAUSED = "subscription_paused"
    SUBSCRIPTION_UNPAUSED = "subscription_unpaused"

    # Payment events
    SUBSCRIPTION_PAYMENT_SUCCESS = "subscription_payment_success"
    SUBSCRIPTION_PAYMENT_FAILED = "subscription_payment_failed"
    SUBSCRIPTION_PAYMENT_RECOVERED = "subscription_payment_recovered"
    SUBSCRIPTION_PAYMENT_REFUNDED = "subscription_payment_refunded"

    # Order events (one-time purchases/LTDs)
    ORDER_CREATED = "order_created"
    ORDER_REFUNDED = "order_refunded"

    # License events (for LTDs)
    LICENSE_KEY_CREATED = "license_key_created"
    LICENSE_KEY_UPDATED = "license_key_updated"
