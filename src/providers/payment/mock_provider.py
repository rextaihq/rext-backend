"""
Mock Payment Provider

This provider is used for development and testing. It simulates a payment provider
without actually processing real payments. Useful for:
- Local development
- Testing subscription flows
- CI/CD pipelines
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import uuid
import json

from src.providers.payment.base_provider import (
    PaymentProvider,
    CheckoutSession,
    SubscriptionData,
    CustomerData,
)
from src.utils.logger import logger


class MockPaymentProvider(PaymentProvider):
    """Mock payment provider for testing and development"""

    def __init__(self):
        """Initialize mock provider with in-memory storage"""
        self.customers: Dict[str, Dict[str, Any]] = {}
        self.subscriptions: Dict[str, SubscriptionData] = {}
        self.checkout_sessions: Dict[str, Dict[str, Any]] = {}
        logger.info("MockPaymentProvider initialized")

    async def create_customer(
        self,
        email: str,
        name: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create mock customer"""
        customer_id = f"cus_mock_{uuid.uuid4().hex[:12]}"

        self.customers[customer_id] = {
            "id": customer_id,
            "email": email,
            "name": name,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat()
        }

        logger.info(f"Mock: Created customer {customer_id} for {email}")
        return customer_id

    async def get_customer(
        self,
        customer_id: str
    ) -> CustomerData:
        """Get mock customer details"""
        if customer_id not in self.customers:
            raise ValueError(f"Customer {customer_id} not found")

        customer = self.customers[customer_id]
        return CustomerData(
            customer_id=customer["id"],
            email=customer["email"],
            name=customer["name"],
            metadata=customer.get("metadata", {})
        )

    async def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        discount_code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CheckoutSession:
        """Create mock checkout session"""
        session_id = f"cs_mock_{uuid.uuid4().hex[:12]}"

        session_data = {
            "id": session_id,
            "customer_id": customer_id,
            "price_id": price_id,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "discount_code": discount_code,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat()
        }

        self.checkout_sessions[session_id] = session_data

        # Mock checkout URL - in real provider, this would be provider's hosted checkout
        checkout_url = f"/mock-checkout/{session_id}"

        logger.info(
            f"Mock: Created checkout session {session_id} for customer {customer_id}" +
            (f" with discount code {discount_code}" if discount_code else "")
        )

        return CheckoutSession(
            session_id=session_id,
            checkout_url=checkout_url,
            customer_id=customer_id,
            metadata=metadata or {}
        )

    async def get_subscription(
        self,
        subscription_id: str
    ) -> SubscriptionData:
        """Get mock subscription details"""
        if subscription_id not in self.subscriptions:
            raise ValueError(f"Subscription {subscription_id} not found")

        return self.subscriptions[subscription_id]

    async def cancel_subscription(
        self,
        subscription_id: str,
        at_period_end: bool = True
    ) -> SubscriptionData:
        """Cancel mock subscription"""
        subscription = await self.get_subscription(subscription_id)

        if at_period_end:
            subscription.cancel_at_period_end = True
            subscription.cancelled_at = datetime.utcnow()
            logger.info(f"Mock: Subscription {subscription_id} will cancel at period end")
        else:
            subscription.status = "cancelled"
            subscription.cancel_at_period_end = False
            subscription.cancelled_at = datetime.utcnow()
            logger.info(f"Mock: Subscription {subscription_id} cancelled immediately")

        self.subscriptions[subscription_id] = subscription
        return subscription

    async def update_subscription(
        self,
        subscription_id: str,
        price_id: str
    ) -> SubscriptionData:
        """Update mock subscription to new plan"""
        subscription = await self.get_subscription(subscription_id)
        subscription.plan_id = price_id

        logger.info(f"Mock: Updated subscription {subscription_id} to plan {price_id}")

        self.subscriptions[subscription_id] = subscription
        return subscription

    async def create_portal_session(
        self,
        customer_id: str,
        return_url: str
    ) -> str:
        """Create mock customer portal session"""
        portal_url = f"/mock-portal/{customer_id}?return_url={return_url}"
        logger.info(f"Mock: Created portal session for customer {customer_id}")
        return portal_url

    async def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        secret: Optional[str] = None
    ) -> bool:
        """Mock webhook signature verification - always returns True"""
        logger.info("Mock: Webhook signature verification (always True)")
        return True

    async def parse_webhook_event(
        self,
        payload: bytes
    ) -> Dict[str, Any]:
        """Parse mock webhook event"""
        try:
            event_data = json.loads(payload)
            logger.info(f"Mock: Parsed webhook event type: {event_data.get('event_type', 'unknown')}")
            return event_data
        except json.JSONDecodeError as e:
            logger.error(f"Mock: Failed to parse webhook payload: {e}")
            raise ValueError(f"Invalid webhook payload: {e}")

    # Helper methods for testing
    def simulate_successful_checkout(
        self,
        session_id: str,
        plan_id: str
    ) -> SubscriptionData:
        """
        Simulate successful checkout completion.
        This is used in testing to simulate webhook events.
        """
        if session_id not in self.checkout_sessions:
            raise ValueError(f"Checkout session {session_id} not found")

        session = self.checkout_sessions[session_id]
        subscription_id = f"sub_mock_{uuid.uuid4().hex[:12]}"

        now = datetime.utcnow()
        subscription = SubscriptionData(
            subscription_id=subscription_id,
            status="active",
            customer_id=session["customer_id"],
            plan_id=plan_id,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            cancel_at_period_end=False,
            trial_end=now + timedelta(days=14) if session["metadata"].get("trial_days") else None
        )

        self.subscriptions[subscription_id] = subscription
        logger.info(f"Mock: Simulated successful checkout -> subscription {subscription_id}")

        return subscription

    def simulate_subscription_renewal(
        self,
        subscription_id: str
    ) -> SubscriptionData:
        """Simulate subscription renewal"""
        subscription = self.subscriptions.get(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription {subscription_id} not found")

        # Extend the subscription period
        subscription.current_period_start = subscription.current_period_end
        subscription.current_period_end = subscription.current_period_end + timedelta(days=30)

        logger.info(f"Mock: Simulated renewal for subscription {subscription_id}")

        self.subscriptions[subscription_id] = subscription
        return subscription

    def reset(self):
        """Reset all mock data - useful for testing"""
        self.customers.clear()
        self.subscriptions.clear()
        self.checkout_sessions.clear()
        logger.info("Mock: Reset all data")
