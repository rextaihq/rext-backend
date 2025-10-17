"""Mock payment provider for testing and development."""
from typing import Optional, Dict, Any, List
import uuid
import json
from datetime import datetime, timedelta
from .base_provider import (
    PaymentProvider,
    CheckoutSession,
    SubscriptionData,
    CustomerData,
    PaymentMethodData
)


class MockPaymentProvider(PaymentProvider):
    """
    Mock payment provider for testing/development.

    Simulates payment provider behavior without actual payment processing.
    All data is stored in memory (resets on restart).
    """

    def __init__(self):
        self.customers: Dict[str, CustomerData] = {}
        self.subscriptions: Dict[str, SubscriptionData] = {}
        self.payment_methods: Dict[str, PaymentMethodData] = {}
        self.checkout_sessions: Dict[str, CheckoutSession] = {}

    async def create_customer(
        self,
        email: str,
        name: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create mock customer."""
        customer_id = f"cus_mock_{uuid.uuid4().hex[:12]}"
        customer = CustomerData(
            customer_id=customer_id,
            email=email,
            name=name,
            metadata=metadata or {}
        )
        self.customers[customer_id] = customer
        return customer_id

    async def get_customer(
        self,
        customer_id: str
    ) -> CustomerData:
        """Get mock customer."""
        if customer_id not in self.customers:
            raise ValueError(f"Customer {customer_id} not found")
        return self.customers[customer_id]

    async def update_customer(
        self,
        customer_id: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CustomerData:
        """Update mock customer."""
        customer = await self.get_customer(customer_id)
        if email:
            customer.email = email
        if name:
            customer.name = name
        if metadata:
            customer.metadata.update(metadata)
        return customer

    async def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        metadata: Optional[Dict[str, Any]] = None,
        trial_days: Optional[int] = None
    ) -> CheckoutSession:
        """Create mock checkout session."""
        session_id = f"cs_mock_{uuid.uuid4().hex[:12]}"
        session = CheckoutSession(
            session_id=session_id,
            checkout_url=f"http://localhost:3000/mock-checkout/{session_id}",
            customer_id=customer_id,
            metadata={
                **(metadata or {}),
                "price_id": price_id,
                "success_url": success_url,
                "cancel_url": cancel_url,
                "trial_days": trial_days
            }
        )
        self.checkout_sessions[session_id] = session
        return session

    async def get_subscription(
        self,
        subscription_id: str
    ) -> SubscriptionData:
        """Get mock subscription."""
        if subscription_id not in self.subscriptions:
            raise ValueError(f"Subscription {subscription_id} not found")
        return self.subscriptions[subscription_id]

    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        trial_days: Optional[int] = None
    ) -> SubscriptionData:
        """
        Create mock subscription (helper method for testing).

        Not part of the interface but useful for mock provider.
        """
        subscription_id = f"sub_mock_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        trial_end = now + timedelta(days=trial_days) if trial_days else None
        start = trial_end if trial_end else now
        end = start + timedelta(days=30)  # Mock monthly billing

        subscription = SubscriptionData(
            subscription_id=subscription_id,
            status="trialing" if trial_days else "active",
            customer_id=customer_id,
            plan_id=price_id,
            current_period_start=start,
            current_period_end=end,
            cancel_at_period_end=False,
            trial_end=trial_end
        )
        self.subscriptions[subscription_id] = subscription
        return subscription

    async def cancel_subscription(
        self,
        subscription_id: str,
        at_period_end: bool = True
    ) -> SubscriptionData:
        """Cancel mock subscription."""
        subscription = await self.get_subscription(subscription_id)

        if at_period_end:
            subscription.cancel_at_period_end = True
            subscription.cancelled_at = datetime.utcnow()
        else:
            subscription.status = "cancelled"
            subscription.cancelled_at = datetime.utcnow()
            subscription.current_period_end = datetime.utcnow()

        return subscription

    async def resume_subscription(
        self,
        subscription_id: str
    ) -> SubscriptionData:
        """Resume mock subscription."""
        subscription = await self.get_subscription(subscription_id)
        subscription.cancel_at_period_end = False
        subscription.cancelled_at = None
        subscription.status = "active"
        return subscription

    async def update_subscription(
        self,
        subscription_id: str,
        price_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SubscriptionData:
        """Update mock subscription."""
        subscription = await self.get_subscription(subscription_id)
        if price_id:
            subscription.plan_id = price_id
        return subscription

    async def create_portal_session(
        self,
        customer_id: str,
        return_url: str
    ) -> str:
        """Create mock portal session."""
        return f"http://localhost:3000/mock-portal/{customer_id}?return_url={return_url}"

    async def list_payment_methods(
        self,
        customer_id: str
    ) -> List[PaymentMethodData]:
        """List mock payment methods."""
        return [
            pm for pm in self.payment_methods.values()
            if pm.customer_id == customer_id
        ]

    async def add_payment_method(
        self,
        customer_id: str,
        type: str = "card",
        is_default: bool = True
    ) -> PaymentMethodData:
        """
        Add mock payment method (helper method for testing).

        Not part of the interface but useful for mock provider.
        """
        payment_method_id = f"pm_mock_{uuid.uuid4().hex[:12]}"
        payment_method = PaymentMethodData(
            payment_method_id=payment_method_id,
            customer_id=customer_id,
            type=type,
            is_default=is_default,
            status="active",
            card_brand="visa" if type == "card" else None,
            card_last4="4242" if type == "card" else None,
            card_exp_month=12 if type == "card" else None,
            card_exp_year=2025 if type == "card" else None
        )
        self.payment_methods[payment_method_id] = payment_method
        return payment_method

    async def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """Mock webhook signature verification (always returns True)."""
        # In real implementation, this would verify the signature
        # For mock, we always return True
        return True

    async def parse_webhook_event(
        self,
        payload: bytes
    ) -> Dict[str, Any]:
        """Parse mock webhook event."""
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {}

    async def validate_license_key(
        self,
        license_key: str,
        instance_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Mock license key validation.

        Returns mock validation data for testing.
        """
        # For mock provider, always return valid for testing
        return {
            "valid": True,
            "license_key": license_key,
            "status": "active",
            "activated": True,
            "activation_limit": 5,
            "activation_usage": 1 if instance_id else 0,
            "expires_at": None,  # Lifetime license
            "customer_email": "mock@example.com",
            "customer_name": "Mock Customer",
            "product_name": "Mock Lifetime Plan",
            "variant_name": "Lifetime"
        }

    async def get_invoices(
        self,
        customer_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Mock invoice retrieval.

        Returns mock invoice data for testing.
        """
        from datetime import datetime, timedelta

        # Generate mock invoices
        invoices = []
        for i in range(min(3, limit)):  # Return up to 3 mock invoices
            invoice_date = datetime.utcnow() - timedelta(days=30 * (i + 1))
            invoices.append({
                "invoice_id": f"inv_mock_{uuid.uuid4().hex[:8]}",
                "invoice_number": f"INV-MOCK-{2025 - i:04d}-{i + 1:03d}",
                "status": "paid",
                "amount": 29.99,
                "currency": "USD",
                "tax": 2.60,
                "subtotal": 27.39,
                "invoice_url": f"https://mock-provider.com/invoice/mock_{i}",
                "invoice_date": invoice_date,
                "due_date": invoice_date + timedelta(days=15),
                "paid_at": invoice_date + timedelta(days=2),
                "customer_email": "mock@example.com",
                "customer_name": "Mock Customer",
                "items": [
                    {
                        "description": "Mock Plan - Monthly",
                        "quantity": 1,
                        "unit_price": 29.99,
                        "total": 29.99
                    }
                ]
            })

        return invoices

    def reset(self):
        """Reset all mock data (useful for testing)."""
        self.customers.clear()
        self.subscriptions.clear()
        self.payment_methods.clear()
        self.checkout_sessions.clear()
