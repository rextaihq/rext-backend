"""
LemonSqueezy Payment Provider

This provider integrates with LemonSqueezy for real payment processing.
Implements the PaymentProvider interface for subscription management, checkouts,
and webhook handling.

Documentation: https://docs.lemonsqueezy.com/api
"""

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.api.lib.logging_config import (
    generate_payment_correlation_id,
    log_payment_timing,
)
from src.api.lib.sentry_config import (
    add_payment_breadcrumb,
    alert_api_error,
    capture_payment_exception,
)
from src.providers.payment.base_provider import (
    CheckoutSession,
    CustomerData,
    PaymentProvider,
    SubscriptionData,
)
from src.utils.logger import logger


class LemonSqueezyError(Exception):
    """Base exception for LemonSqueezy API errors"""

    pass


class LemonSqueezyAPIError(LemonSqueezyError):
    """API request failed"""

    def __init__(self, status_code: int, message: str, details: Optional[Dict] = None):
        self.status_code = status_code
        self.message = message
        self.details = details or {}
        super().__init__(f"LemonSqueezy API Error ({status_code}): {message}")


class LemonSqueezyTransientError(LemonSqueezyError):
    """Transient error that should be retried (5xx, timeout, network)."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.status_code = status_code
        super().__init__(message)


class LemonSqueezyProvider(PaymentProvider):
    """LemonSqueezy payment provider implementation"""

    BASE_URL = "https://api.lemonsqueezy.com/v1"

    def __init__(
        self,
        api_key: str,
        store_id: str,
        webhook_secret: Optional[str] = None,
        sandbox_mode: bool = False,
    ):
        """
        Initialize LemonSqueezy provider.

        Args:
            api_key: LemonSqueezy API key
            store_id: LemonSqueezy store ID
            webhook_secret: Optional webhook signing secret
            sandbox_mode: If True, use test mode
        """
        self.api_key = api_key
        self.store_id = store_id
        self.webhook_secret = webhook_secret
        self.sandbox_mode = sandbox_mode

        # Initialize HTTP client
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/vnd.api+json",
                "Content-Type": "application/vnd.api+json",
            },
            timeout=30.0,
        )

        logger.info(
            f"LemonSqueezyProvider initialized (store_id={store_id}, sandbox_mode={sandbox_mode})"
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(LemonSqueezyTransientError),
        before_sleep=before_sleep_log(logger, 20),  # INFO level
        reraise=True,
    )
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make HTTP request to LemonSqueezy API with automatic retry on transient errors.

        Retries up to 3 times with exponential backoff (1s, 2s, 4s) for:
        - Network errors (timeout, connection reset, DNS failure)
        - Server errors (500, 502, 503, 504)
        - Rate limit errors (429) with Retry-After header awareness

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint (e.g., "/customers")
            data: Request body data
            params: Query parameters

        Returns:
            Dict containing response data

        Raises:
            LemonSqueezyAPIError: If request fails with a non-retryable error (4xx)
            LemonSqueezyTransientError: If all retries are exhausted for transient errors
        """
        # Add breadcrumb for API request (Phase 4, Task 4.2.1)
        add_payment_breadcrumb(
            f"LemonSqueezy API: {method} {endpoint}",
            operation="api_request",
            data={
                "method": method,
                "endpoint": endpoint,
                "has_data": data is not None,
                "has_params": params is not None,
            },
        )

        # Log API request with timing (Phase 4, Task 4.2.2)
        with log_payment_timing(
            logger,
            operation="api_request",
            message=f"LemonSqueezy API: {method} {endpoint}",
            method=method,
            endpoint=endpoint,
            provider="lemonsqueezy",
        ) as ctx:
            try:
                response = await self.client.request(
                    method=method, url=endpoint, json=data, params=params
                )

                ctx["status_code"] = response.status_code

                # Log response status
                if response.status_code < 400:
                    logger.debug(
                        f"LemonSqueezy API response: {response.status_code}",
                        method=method,
                        endpoint=endpoint,
                        status_code=response.status_code,
                    )
                    return response.json()

                # Parse error details
                try:
                    error_data = response.json()
                    # Log full error response for debugging
                    logger.error(
                        f"🔍 LemonSqueezy full error response: {error_data}",
                        method=method,
                        endpoint=endpoint,
                    )
                    error_message = error_data.get("errors", [{}])[0].get("detail", "Unknown error")
                except Exception:
                    error_message = response.text or "Unknown error"

                logger.error(
                    f"LemonSqueezy API error: {response.status_code}",
                    method=method,
                    endpoint=endpoint,
                    status_code=response.status_code,
                    error_message=error_message,
                )

                # Handle rate limiting (429) — raise transient for retry
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "5")
                    logger.warning(
                        f"LemonSqueezy rate limited. Retry-After: {retry_after}s",
                        method=method,
                        endpoint=endpoint,
                    )
                    alert_api_error(
                        method=method,
                        endpoint=endpoint,
                        status_code=429,
                        error_message="Rate limit exceeded",
                        operation="api_request",
                    )
                    raise LemonSqueezyTransientError(
                        f"Rate limited: {error_message}", status_code=429
                    )

                # Handle server errors (5xx) — raise transient for retry
                if response.status_code >= 500:
                    alert_api_error(
                        method=method,
                        endpoint=endpoint,
                        status_code=response.status_code,
                        error_message=error_message,
                        operation="api_request",
                    )
                    raise LemonSqueezyTransientError(
                        f"Server error ({response.status_code}): {error_message}",
                        status_code=response.status_code,
                    )

                # Client errors (4xx except 429) are NOT retryable
                api_error = LemonSqueezyAPIError(
                    status_code=response.status_code,
                    message=error_message,
                    details={"endpoint": endpoint, "method": method},
                )

                # Capture to Sentry (Phase 4, Task 4.2.1)
                capture_payment_exception(
                    api_error,
                    operation="api_request",
                    context={
                        "method": method,
                        "endpoint": endpoint,
                        "status_code": response.status_code,
                        "error_message": error_message,
                    },
                )

                raise api_error

            except httpx.TimeoutException as e:
                logger.error(
                    f"LemonSqueezy timeout: {str(e)}",
                    method=method,
                    endpoint=endpoint,
                )
                capture_payment_exception(
                    e,
                    operation="api_request",
                    context={"method": method, "endpoint": endpoint, "error_type": "timeout"},
                )
                raise LemonSqueezyTransientError(f"Request timeout: {str(e)}") from e

            except httpx.NetworkError as e:
                logger.error(
                    f"LemonSqueezy network error: {str(e)}",
                    method=method,
                    endpoint=endpoint,
                )
                capture_payment_exception(
                    e,
                    operation="api_request",
                    context={"method": method, "endpoint": endpoint, "error_type": "network"},
                )
                raise LemonSqueezyTransientError(f"Network error: {str(e)}") from e

            except httpx.HTTPError as e:
                logger.error(
                    f"LemonSqueezy HTTP error: {str(e)}",
                    method=method,
                    endpoint=endpoint,
                    error_type=type(e).__name__,
                )
                capture_payment_exception(
                    e,
                    operation="api_request",
                    context={"method": method, "endpoint": endpoint, "error_type": "http_error"},
                )
                raise LemonSqueezyError(f"HTTP request failed: {str(e)}") from e

    def _parse_jsonapi_data(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse JSON:API formatted response.

        Args:
            response: JSON:API response

        Returns:
            Dict with flattened data
        """
        if "data" not in response:
            return {}

        data = response["data"]

        # Handle single resource
        if isinstance(data, dict):
            result = {
                "id": data.get("id"),
                "type": data.get("type"),
                **(data.get("attributes", {})),
            }
            return result

        # Handle collection
        if isinstance(data, list):
            return [
                {"id": item.get("id"), "type": item.get("type"), **(item.get("attributes", {}))}
                for item in data
            ]

        return {}

    async def create_customer(
        self, email: str, name: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create customer in LemonSqueezy.

        Args:
            email: Customer email
            name: Customer name
            metadata: Additional metadata

        Returns:
            str: Customer ID from LemonSqueezy
        """
        # LemonSqueezy creates customers automatically during checkout
        # We'll store a reference ID for now and create on first checkout
        # For now, return a temporary ID that will be replaced during checkout
        temp_id = f"temp_{email}"

        logger.info(f"LemonSqueezy: Prepared customer reference for {email}")
        logger.warning(
            "LemonSqueezy creates customers during checkout. "
            "Returning temporary ID until first purchase."
        )

        return temp_id

    async def get_customer(self, customer_id: str) -> CustomerData:
        """
        Get customer details from LemonSqueezy.

        Args:
            customer_id: Customer ID from LemonSqueezy

        Returns:
            CustomerData: Customer information
        """
        response = await self._make_request(method="GET", endpoint=f"/customers/{customer_id}")

        customer = self._parse_jsonapi_data(response)

        return CustomerData(
            customer_id=customer["id"],
            email=customer.get("email", ""),
            name=customer.get("name", ""),
            metadata={},
        )

    async def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,  # In LemonSqueezy, this is variant_id
        success_url: str,
        cancel_url: str,
        discount_code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        customer_email: Optional[str] = None,
        customer_name: Optional[str] = None,
    ) -> CheckoutSession:
        """
        Create checkout session in LemonSqueezy.

        Args:
            customer_id: Customer ID (can be temp ID from create_customer)
            price_id: LemonSqueezy variant ID
            success_url: Success redirect URL
            cancel_url: Cancel redirect URL
            discount_code: Optional discount/promo code to pre-fill
            metadata: Custom data to attach
            customer_email: Pre-fills the checkout email field
            customer_name: Pre-fills the checkout name field

        Returns:
            CheckoutSession: Checkout session details
        """
        # Generate correlation ID for tracking (Phase 4, Task 4.2.2)
        correlation_id = generate_payment_correlation_id()

        logger.info(
            "Creating checkout session",
            operation="checkout",
            customer_id=customer_id,
            variant_id=price_id,
            has_discount=discount_code is not None,
            correlation_id=correlation_id,
        )

        # Add breadcrumb for checkout (Phase 4, Task 4.2.1)
        add_payment_breadcrumb(
            "Creating checkout session",
            operation="checkout",
            data={
                "customer_id": customer_id,
                "variant_id": price_id,
                "has_discount": discount_code is not None,
                "correlation_id": correlation_id,
            },
        )

        # Build checkout attributes
        # Ensure variant ID is an integer (LemonSqueezy requires integer IDs)
        price_id_str = str(price_id)
        if price_id_str.startswith("variant_"):
            variant_id_int = int(price_id_str[8:])
        else:
            variant_id_int = int(price_id_str)

        # Clean metadata - remove None values
        clean_metadata = {k: v for k, v in (metadata or {}).items() if v is not None}

        checkout_attributes = {
            "store_id": int(self.store_id),
            "variant_id": variant_id_int,
            "custom_price": None,
            "product_options": {
                "enabled_variants": [variant_id_int],
                "redirect_url": success_url,
                "receipt_button_text": "Go to Dashboard",
                "receipt_thank_you_note": "Thank you for your purchase!",
                "media": [],  # Required array field
            },
            "checkout_options": {
                # True makes LemonSqueezy return a frameable checkout URL so it
                # can render in the on-site overlay instead of a full redirect.
                "embed": True,
                # The overlay is a single fixed-width column we cannot restyle
                # (it is a cross-origin iframe), so the only lever on its height
                # is how much LemonSqueezy renders inside it. The product media
                # and description are the tallest blocks and are already shown
                # on our own pricing page, so they are redundant here.
                "media": False,
                "desc": False,
                "logo": True,
                "discount": True,
                # Kept: this is the price/renewal summary, which the buyer
                # should see before paying.
                "subscription_preview": True,
            },
            "checkout_data": {
                "custom": clean_metadata,
                "variant_quantities": [],  # Required array field
                # The buyer is already signed in, so there is no reason to make
                # them retype what we know. LemonSqueezy pre-fills these fields;
                # it does not hide them (their form layout is not ours to set).
                **({"email": customer_email} if customer_email else {}),
                **({"name": customer_name} if customer_name else {}),
            },
            "preview": False,  # Always false - test mode is controlled by test products/API keys
        }

        # Add discount code if provided (must be inside checkout_data, not top-level)
        if discount_code:
            checkout_attributes["checkout_data"]["discount_code"] = discount_code
            logger.debug(
                "Adding discount code to checkout",
                discount_code=discount_code,
                correlation_id=correlation_id,
            )

        # LemonSqueezy requires BOTH attributes AND relationships
        checkout_data = {
            "data": {
                "type": "checkouts",
                "attributes": checkout_attributes,
                "relationships": {
                    "store": {"data": {"type": "stores", "id": str(self.store_id)}},
                    "variant": {"data": {"type": "variants", "id": str(variant_id_int)}},
                },
            }
        }

        # Debug: Log the exact payload being sent
        import json

        logger.debug(f"🔍 LemonSqueezy checkout payload: {json.dumps(checkout_data, indent=2)}")

        with log_payment_timing(
            logger,
            operation="checkout",
            message="Creating LemonSqueezy checkout",
            variant_id=price_id,
            correlation_id=correlation_id,
        ) as ctx:
            response = await self._make_request(
                method="POST", endpoint="/checkouts", data=checkout_data
            )

            checkout = self._parse_jsonapi_data(response)
            ctx["session_id"] = checkout["id"]
            ctx["checkout_url"] = checkout["url"]

        logger.info(
            "Checkout session created successfully",
            operation="checkout",
            session_id=checkout["id"],
            variant_id=price_id,
            correlation_id=correlation_id,
            checkout_url=checkout["url"],
        )

        return CheckoutSession(
            session_id=checkout["id"],
            checkout_url=checkout["url"],
            customer_id=customer_id,  # Will be updated after purchase
            metadata=metadata or {},
        )

    async def get_subscription(self, subscription_id: str) -> SubscriptionData:
        """
        Get subscription details from LemonSqueezy.

        Args:
            subscription_id: Subscription ID from LemonSqueezy

        Returns:
            SubscriptionData: Subscription information
        """
        logger.debug(
            "Retrieving subscription details",
            operation="get_subscription",
            subscription_id=subscription_id,
        )

        response = await self._make_request(
            method="GET", endpoint=f"/subscriptions/{subscription_id}"
        )

        subscription = self._parse_jsonapi_data(response)

        # Map LemonSqueezy status to internal status
        status_map = {
            "on_trial": "trialing",
            "active": "active",
            "paused": "paused",
            "past_due": "past_due",
            "unpaid": "past_due",
            "cancelled": "cancelled",
            "expired": "expired",
        }

        internal_status = status_map.get(subscription.get("status", "").lower(), "active")

        logger.info(
            "Retrieved subscription details",
            operation="get_subscription",
            subscription_id=subscription_id,
            status=internal_status,
            customer_id=subscription.get("customer_id"),
            variant_id=subscription.get("variant_id"),
        )

        return SubscriptionData(
            subscription_id=subscription["id"],
            status=internal_status,
            customer_id=subscription.get("customer_id", ""),
            plan_id=subscription.get("variant_id", ""),
            current_period_start=datetime.fromisoformat(
                subscription.get("renews_at") or datetime.now(timezone.utc).isoformat()
            ),
            current_period_end=datetime.fromisoformat(
                subscription.get("ends_at") or datetime.now(timezone.utc).isoformat()
            ),
            cancel_at_period_end=subscription.get("cancelled", False),
            cancelled_at=(
                datetime.fromisoformat(subscription["cancelled_at"])
                if subscription.get("cancelled_at")
                else None
            ),
            trial_end=(
                datetime.fromisoformat(subscription["trial_ends_at"])
                if subscription.get("trial_ends_at")
                else None
            ),
        )

    async def cancel_subscription(
        self, subscription_id: str, at_period_end: bool = True
    ) -> SubscriptionData:
        """
        Cancel subscription in LemonSqueezy.

        Args:
            subscription_id: Subscription ID from LemonSqueezy
            at_period_end: If True, cancel at period end; if False, cancel immediately

        Returns:
            SubscriptionData: Updated subscription information
        """
        logger.info(
            "Cancelling subscription",
            operation="cancel_subscription",
            subscription_id=subscription_id,
            at_period_end=at_period_end,
        )

        # Add breadcrumb for cancellation (Phase 4, Task 4.2.1)
        add_payment_breadcrumb(
            "Cancelling subscription",
            operation="cancel_subscription",
            data={
                "subscription_id": subscription_id,
                "at_period_end": at_period_end,
            },
        )

        # LemonSqueezy DELETE cancels at period end by default
        # For immediate cancellation, we'd need to update first then delete
        with log_payment_timing(
            logger,
            operation="cancel_subscription",
            message="Cancelling subscription in LemonSqueezy",
            subscription_id=subscription_id,
            at_period_end=at_period_end,
        ) as ctx:
            response = await self._make_request(
                method="DELETE", endpoint=f"/subscriptions/{subscription_id}"
            )

            _subscription = self._parse_jsonapi_data(response)
            ctx["cancelled"] = True

        logger.info(
            "Subscription cancelled successfully",
            operation="cancel_subscription",
            subscription_id=subscription_id,
            at_period_end=at_period_end,
        )

        # Return updated subscription data
        return await self.get_subscription(subscription_id)

    async def update_subscription(
        self,
        subscription_id: str,
        price_id: str,  # variant_id in LemonSqueezy
    ) -> SubscriptionData:
        """
        Update subscription to new plan in LemonSqueezy.

        Args:
            subscription_id: Subscription ID from LemonSqueezy
            price_id: New variant ID

        Returns:
            SubscriptionData: Updated subscription information
        """
        logger.info(
            "Updating subscription plan",
            operation="update_subscription",
            subscription_id=subscription_id,
            new_variant_id=price_id,
        )

        # Add breadcrumb for subscription update (Phase 4, Task 4.2.1)
        add_payment_breadcrumb(
            "Updating subscription plan",
            operation="update_subscription",
            data={
                "subscription_id": subscription_id,
                "new_variant_id": price_id,
            },
        )

        update_data = {
            "data": {
                "type": "subscriptions",
                "id": subscription_id,
                "attributes": {"variant_id": price_id, "invoice_immediately": True},
            }
        }

        with log_payment_timing(
            logger,
            operation="update_subscription",
            message="Updating subscription in LemonSqueezy",
            subscription_id=subscription_id,
            new_variant_id=price_id,
        ) as ctx:
            await self._make_request(
                method="PATCH", endpoint=f"/subscriptions/{subscription_id}", data=update_data
            )
            ctx["updated"] = True

        logger.info(
            "Subscription plan updated successfully",
            operation="update_subscription",
            subscription_id=subscription_id,
            new_variant_id=price_id,
        )

        return await self.get_subscription(subscription_id)

    async def get_subscription_urls(self, subscription_id: str) -> Dict[str, str]:
        """
        Get LemonSqueezy's signed URLs for a subscription.

        LemonSqueezy returns short-lived signed links on the subscription
        object. `update_payment_method` is frameable, so it can be shown in the
        on-site overlay; `customer_portal` is a full portal page that refuses
        framing and can only be opened in a new tab.

        Args:
            subscription_id: Subscription ID from LemonSqueezy

        Returns:
            Dict of URL name -> URL. Keys typically include
            "update_payment_method" and "customer_portal".
        """
        response = await self._make_request(
            method="GET", endpoint=f"/subscriptions/{subscription_id}"
        )

        subscription = self._parse_jsonapi_data(response)
        urls = subscription.get("urls") or {}

        logger.info(
            "Retrieved subscription URLs",
            operation="get_subscription_urls",
            subscription_id=subscription_id,
            available=sorted(urls.keys()),
        )

        return {k: v for k, v in urls.items() if v}

    async def pause_subscription(
        self, subscription_id: str, mode: str = "void"
    ) -> SubscriptionData:
        """
        Pause a subscription in LemonSqueezy.

        Args:
            subscription_id: Subscription ID from LemonSqueezy
            mode: "void" (no access, no charge) or "free" (access, no charge)

        Returns:
            SubscriptionData: Updated subscription information
        """
        logger.info(
            "Pausing subscription",
            operation="pause_subscription",
            subscription_id=subscription_id,
            mode=mode,
        )

        await self._make_request(
            method="PATCH",
            endpoint=f"/subscriptions/{subscription_id}",
            data={
                "data": {
                    "type": "subscriptions",
                    "id": subscription_id,
                    "attributes": {"pause": {"mode": mode}},
                }
            },
        )

        return await self.get_subscription(subscription_id)

    async def resume_subscription(self, subscription_id: str) -> SubscriptionData:
        """
        Resume a paused subscription in LemonSqueezy.

        Clearing `pause` is how LemonSqueezy un-pauses; there is no separate
        resume endpoint.

        Args:
            subscription_id: Subscription ID from LemonSqueezy

        Returns:
            SubscriptionData: Updated subscription information
        """
        logger.info(
            "Resuming subscription",
            operation="resume_subscription",
            subscription_id=subscription_id,
        )

        await self._make_request(
            method="PATCH",
            endpoint=f"/subscriptions/{subscription_id}",
            data={
                "data": {
                    "type": "subscriptions",
                    "id": subscription_id,
                    "attributes": {"pause": None},
                }
            },
        )

        return await self.get_subscription(subscription_id)

    async def create_portal_session(self, customer_id: str, return_url: str) -> str:
        """
        Create customer portal URL for LemonSqueezy.

        Note: LemonSqueezy provides customer portal URLs directly in subscription objects.
        This method constructs the portal URL based on customer context.

        Args:
            customer_id: Customer ID from LemonSqueezy
            return_url: URL to return after portal session

        Returns:
            str: Portal URL
        """
        # LemonSqueezy customer portal is accessed via subscription
        # For now, construct the portal URL pattern
        portal_url = f"https://app.lemonsqueezy.com/my-orders?return_url={return_url}"

        logger.info(f"LemonSqueezy: Generated portal URL for customer {customer_id}")

        return portal_url

    async def verify_webhook_signature(
        self, payload: bytes, signature: str, secret: Optional[str] = None
    ) -> bool:
        """
        Verify webhook signature from LemonSqueezy.

        Args:
            payload: Raw webhook payload
            signature: Signature from X-Signature header
            secret: Webhook secret (uses self.webhook_secret if not provided)

        Returns:
            bool: True if signature is valid
        """
        logger.debug(
            "Verifying webhook signature",
            operation="webhook_verification",
            payload_length=len(payload),
            has_signature=bool(signature),
        )

        webhook_secret = secret or self.webhook_secret

        if not webhook_secret:
            logger.error("No webhook secret configured", operation="webhook_verification")
            return False

        # LemonSqueezy uses HMAC SHA-256
        expected_signature = hmac.new(
            webhook_secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()

        # Timing-safe comparison
        is_valid = hmac.compare_digest(expected_signature, signature)

        if is_valid:
            logger.info("Webhook signature verified successfully", operation="webhook_verification")
        else:
            logger.warning(
                "Invalid webhook signature",
                operation="webhook_verification",
                payload_length=len(payload),
            )

        return is_valid

    async def parse_webhook_event(self, payload: bytes) -> Dict[str, Any]:
        """
        Parse webhook event from LemonSqueezy.

        Args:
            payload: Raw webhook payload

        Returns:
            Dict containing event data
        """
        import json

        event_data = json.loads(payload)

        # LemonSqueezy webhook format
        meta = event_data.get("meta", {})
        data = event_data.get("data", {})

        return {
            "event_type": meta.get("event_name", "unknown"),
            "event_id": meta.get("webhook_id", ""),
            "data": data,
            "timestamp": datetime.fromisoformat(
                meta.get("created_at", datetime.now(timezone.utc).isoformat())
            ),
        }

    async def validate_license_key(
        self, license_key: str, instance_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate a license key via LemonSqueezy License API.

        Args:
            license_key: License key to validate
            instance_id: Optional instance identifier to check activation

        Returns:
            Dict containing validation result with:
                - valid: bool - Whether license is valid
                - license_key: Dict - License key details
                - instance: Dict - Instance details if instance_id provided
                - meta: Dict - Additional metadata

        Raises:
            LemonSqueezyAPIError: If validation fails
        """
        validate_data = {"license_key": license_key}

        if instance_id:
            validate_data["instance_id"] = instance_id

        response = await self._make_request(
            method="POST", endpoint="/licenses/validate", data=validate_data
        )

        logger.info(
            f"LemonSqueezy: Validated license key {license_key[:8]}... "
            f"(valid={response.get('valid', False)})"
        )

        return response

    async def activate_license(self, license_key: str, instance_name: str) -> Dict[str, Any]:
        """
        Activate a license on a specific instance.

        Args:
            license_key: License key to activate
            instance_name: Name/identifier for the instance

        Returns:
            Dict containing activation result with:
                - activated: bool - Whether activation succeeded
                - license_key: Dict - License key details
                - instance: Dict - Instance details including instance_id
                - meta: Dict - Additional metadata

        Raises:
            LemonSqueezyAPIError: If activation fails (e.g., limit reached)
        """
        activate_data = {"license_key": license_key, "instance_name": instance_name}

        response = await self._make_request(
            method="POST", endpoint="/licenses/activate", data=activate_data
        )

        instance_id = response.get("instance", {}).get("id", "")

        logger.info(
            f"LemonSqueezy: Activated license {license_key[:8]}... "
            f"on instance '{instance_name}' (id={instance_id})"
        )

        return response

    async def deactivate_license(self, license_key: str, instance_id: str) -> Dict[str, Any]:
        """
        Deactivate a license from a specific instance.

        Args:
            license_key: License key to deactivate
            instance_id: Instance ID to deactivate (from activate_license response)

        Returns:
            Dict containing deactivation result with:
                - deactivated: bool - Whether deactivation succeeded
                - license_key: Dict - License key details
                - meta: Dict - Additional metadata

        Raises:
            LemonSqueezyAPIError: If deactivation fails
        """
        deactivate_data = {"license_key": license_key, "instance_id": instance_id}

        response = await self._make_request(
            method="POST", endpoint="/licenses/deactivate", data=deactivate_data
        )

        logger.info(
            f"LemonSqueezy: Deactivated license {license_key[:8]}... from instance {instance_id}"
        )

        return response

    async def get_license(self, license_id: str) -> Dict[str, Any]:
        """
        Get license details by license ID.

        Args:
            license_id: License ID from LemonSqueezy

        Returns:
            Dict containing license details including:
                - id: License ID
                - status: License status
                - key: License key
                - activation_limit: Max activations allowed
                - activation_usage: Current activations
                - expires_at: Expiration date (if applicable)
                - And other license metadata

        Raises:
            LemonSqueezyAPIError: If license not found
        """
        response = await self._make_request(method="GET", endpoint=f"/license-keys/{license_id}")

        license_data = self._parse_jsonapi_data(response)

        logger.info(
            f"LemonSqueezy: Retrieved license {license_id} "
            f"(status={license_data.get('status', 'unknown')})"
        )

        return license_data

    async def create_refund(
        self, order_id: str, amount: Optional[int] = None, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a refund for an order via LemonSqueezy API.

        LemonSqueezy refunds orders via POST /v1/orders/{order_id}/refund.

        Args:
            order_id: LemonSqueezy order ID
            amount: Refund amount in cents (optional, defaults to full refund)
            reason: Refund reason (optional)

        Returns:
            Dict containing order data returned by LemonSqueezy

        Raises:
            LemonSqueezyAPIError: If API request fails
        """
        logger.info(
            f"LemonSqueezy: Creating refund for order {order_id} "
            f"(amount={amount if amount else 'full'}, reason={reason})"
        )

        attributes = {}
        if amount is not None and amount > 0:
            attributes["amount"] = amount

        refund_data = {"data": {"type": "orders", "id": str(order_id), "attributes": attributes}}

        try:
            response = await self._make_request(
                "POST", f"/orders/{order_id}/refund", data=refund_data
            )

            order_info = response.get("data", {})
            logger.info(f"LemonSqueezy: Refund created successfully for order {order_id}")

            return order_info

        except LemonSqueezyAPIError as e:
            logger.error(
                f"LemonSqueezy: Failed to create refund for order {order_id}: {e.message}",
                extra={"status_code": e.status_code, "details": e.details},
            )
            raise

    async def get_refund(self, refund_id: str) -> Dict[str, Any]:
        """
        Get order details for a refund.

        Args:
            refund_id: LemonSqueezy order ID

        Returns:
            Dict containing order data

        Raises:
            LemonSqueezyAPIError: If API request fails
        """
        logger.info(f"LemonSqueezy: Retrieving order {refund_id}")

        try:
            response = await self._make_request("GET", f"/orders/{refund_id}")

            order_data = response.get("data", {})

            logger.info(
                f"LemonSqueezy: Retrieved order {refund_id} "
                f"(status={order_data.get('attributes', {}).get('status', 'unknown')})"
            )

            return order_data

        except LemonSqueezyAPIError as e:
            logger.error(
                f"LemonSqueezy: Failed to retrieve order {refund_id}: {e.message}",
                extra={"status_code": e.status_code},
            )
            raise

    @staticmethod
    def _parse_ls_datetime(value: Optional[str]) -> Optional[datetime]:
        """Parse a LemonSqueezy ISO-8601 timestamp (e.g. '2026-09-01T13:32:14.000000Z')."""
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    async def _paginate(self, endpoint: str, params: Dict[str, Any], limit: int) -> list:
        """
        Fetch a JSON:API collection following ``meta.page.lastPage`` until ``limit``
        records have been collected (or the pages are exhausted).

        Returns a flat list of parsed resource dicts (id/type/**attributes).
        """
        page_size = max(1, min(limit, 100))  # LemonSqueezy caps page[size] at 100
        collected: list = []
        page = 1
        while len(collected) < limit:
            page_params = {**params, "page[size]": page_size, "page[number]": page}
            response = await self._make_request(
                method="GET",
                endpoint=endpoint,
                params=page_params,
            )
            items = self._parse_jsonapi_data(response)
            if not isinstance(items, list) or not items:
                break
            collected.extend(items)

            last_page = response.get("meta", {}).get("page", {}).get("lastPage")
            if not last_page or page >= last_page:
                break
            page += 1

        return collected[:limit]

    def _order_to_invoice(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Map a LemonSqueezy ``order`` resource to the internal invoice dict."""
        urls = item.get("urls") or {}
        status = item.get("status", "unknown")
        return {
            "invoice_id": str(item.get("id", "")),
            "invoice_number": str(item.get("order_number") or item.get("id") or ""),
            "status": "refunded" if item.get("refunded") else status,
            "amount": (item.get("total") or 0) / 100.0,
            "subtotal": (item.get("subtotal") or 0) / 100.0,
            "tax": (item.get("tax") or 0) / 100.0,
            "currency": item.get("currency", "USD"),
            "invoice_url": urls.get("receipt") or urls.get("invoice_url"),
            "invoice_date": self._parse_ls_datetime(item.get("created_at")),
            "due_date": None,
            "paid_at": self._parse_ls_datetime(item.get("updated_at"))
            if status == "paid"
            else None,
            "customer_email": item.get("user_email"),
            "customer_name": item.get("user_name"),
            "billing_reason": "purchase",
            "source": "order",
            "items": [],
        }

    def _subscription_invoice_to_invoice(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Map a LemonSqueezy ``subscription-invoice`` resource to the internal invoice dict."""
        urls = item.get("urls") or {}
        status = item.get("status", "unknown")
        return {
            "invoice_id": f"si_{item.get('id', '')}",
            "invoice_number": str(item.get("id") or ""),
            "status": "refunded" if item.get("refunded") else status,
            "amount": (item.get("total") or 0) / 100.0,
            "subtotal": (item.get("subtotal") or 0) / 100.0,
            "tax": (item.get("tax") or 0) / 100.0,
            "currency": item.get("currency", "USD"),
            "invoice_url": urls.get("invoice_url") or urls.get("receipt"),
            "invoice_date": self._parse_ls_datetime(item.get("created_at")),
            "due_date": None,
            "paid_at": self._parse_ls_datetime(item.get("updated_at"))
            if status == "paid"
            else None,
            "customer_email": item.get("user_email"),
            "customer_name": item.get("user_name"),
            "billing_reason": item.get("billing_reason"),
            "card_brand": item.get("card_brand"),
            "card_last_four": item.get("card_last_four"),
            "source": "subscription_invoice",
            "items": [],
        }

    async def get_invoices(
        self, user_email: str, limit: int = 10, subscription_ids: Optional[list] = None
    ) -> list:
        """
        Get the full billing/invoice history for a user from LemonSqueezy.

        LemonSqueezy splits billing history across two resources:

        - ``/orders``               -> the initial purchase of each subscription
                                       plus any one-time / lifetime purchases,
                                       filterable by ``user_email``.
        - ``/subscription-invoices`` -> every recurring charge (renewals),
                                       plan changes and refunds, filterable only
                                       by ``subscription_id``.

        ``filter[customer_id]`` is NOT a valid filter on any of these endpoints,
        so subscription invoices must be fetched per subscription id.

        Args:
            user_email: Customer email address (used for the /orders lookup).
            limit: Maximum number of invoices to return.
            subscription_ids: LemonSqueezy subscription ids belonging to the user,
                used to fetch recurring subscription invoices.

        Returns:
            List of invoice dicts, newest first, capped at ``limit``.
        """
        invoices: list = []

        # 1. Orders (initial purchases + one-time / lifetime purchases)
        if user_email:
            try:
                orders = await self._paginate(
                    "/orders",
                    {"filter[user_email]": user_email},
                    limit,
                )
                invoices.extend(self._order_to_invoice(o) for o in orders)
            except LemonSqueezyError as e:
                logger.warning(f"LemonSqueezy: failed to fetch orders for invoice history: {e}")

        # 2. Subscription invoices (renewals, plan changes, refunds) per subscription
        for sub_id in dict.fromkeys(subscription_ids or []):
            if not sub_id:
                continue
            try:
                sub_invoices = await self._paginate(
                    "/subscription-invoices",
                    {"filter[subscription_id]": str(sub_id)},
                    limit,
                )
                invoices.extend(self._subscription_invoice_to_invoice(si) for si in sub_invoices)
            except LemonSqueezyError as e:
                logger.warning(
                    f"LemonSqueezy: failed to fetch subscription invoices for {sub_id}: {e}"
                )

        invoices = self._dedupe_invoices(invoices)

        # Sort newest first; entries without a date sink to the bottom.
        invoices.sort(
            key=lambda inv: inv.get("invoice_date") or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        return invoices[:limit]

    @staticmethod
    def _dedupe_invoices(invoices: list) -> list:
        """
        A subscription's first payment appears twice: once as an ``order`` and
        once as a ``subscription-invoice`` with ``billing_reason == "initial"``
        (same amount, seconds apart). Keep the subscription-invoice (richer
        metadata) and drop the matching order so the user is not shown what
        looks like a double charge.
        """
        initial_keys = {
            (inv["amount"], inv["invoice_date"].date())
            for inv in invoices
            if inv.get("source") == "subscription_invoice"
            and inv.get("billing_reason") == "initial"
            and inv.get("invoice_date")
        }
        if not initial_keys:
            return invoices
        return [
            inv
            for inv in invoices
            if not (
                inv.get("source") == "order"
                and inv.get("invoice_date")
                and (inv["amount"], inv["invoice_date"].date()) in initial_keys
            )
        ]

    async def close(self):
        """Close the HTTP client connection"""
        await self.client.aclose()
        logger.info("LemonSqueezyProvider closed")
