"""Payment provider abstraction layer."""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CheckoutSession:
    """Checkout session data returned by payment provider."""
    session_id: str
    checkout_url: str
    customer_id: str
    metadata: Dict[str, Any]


@dataclass
class SubscriptionData:
    """Subscription data from payment provider."""
    subscription_id: str
    status: str  # active, cancelled, expired, trialing, etc.
    customer_id: str
    plan_id: str
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    cancelled_at: Optional[datetime] = None
    trial_end: Optional[datetime] = None


@dataclass
class CustomerData:
    """Customer data from payment provider."""
    customer_id: str
    email: str
    name: str
    metadata: Dict[str, Any]


@dataclass
class PaymentMethodData:
    """Payment method data from payment provider."""
    payment_method_id: str
    customer_id: str
    type: str  # card, bank_account, etc.
    is_default: bool
    status: str
    card_brand: Optional[str] = None
    card_last4: Optional[str] = None
    card_exp_month: Optional[int] = None
    card_exp_year: Optional[int] = None


class PaymentProvider(ABC):
    """
    Abstract payment provider interface.

    Any payment provider (Stripe, LemonSqueezy, Paddle, FastSpring) must implement this interface.
    This allows swapping payment providers without changing business logic.
    """

    @abstractmethod
    async def create_customer(
        self,
        email: str,
        name: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a customer in the payment provider.

        Args:
            email: Customer email
            name: Customer name
            metadata: Optional metadata to attach to customer

        Returns:
            Customer ID from payment provider
        """
        pass

    @abstractmethod
    async def get_customer(
        self,
        customer_id: str
    ) -> CustomerData:
        """
        Get customer details from payment provider.

        Args:
            customer_id: Payment provider customer ID

        Returns:
            CustomerData object
        """
        pass

    @abstractmethod
    async def update_customer(
        self,
        customer_id: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CustomerData:
        """
        Update customer in payment provider.

        Args:
            customer_id: Payment provider customer ID
            email: New email (optional)
            name: New name (optional)
            metadata: New metadata (optional)

        Returns:
            Updated CustomerData
        """
        pass

    @abstractmethod
    async def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        metadata: Optional[Dict[str, Any]] = None,
        trial_days: Optional[int] = None
    ) -> CheckoutSession:
        """
        Create a checkout session for subscription purchase.

        Args:
            customer_id: Payment provider customer ID
            price_id: Payment provider price/plan ID
            success_url: URL to redirect on success
            cancel_url: URL to redirect on cancel
            metadata: Optional metadata
            trial_days: Optional trial period in days

        Returns:
            CheckoutSession with checkout URL
        """
        pass

    @abstractmethod
    async def get_subscription(
        self,
        subscription_id: str
    ) -> SubscriptionData:
        """
        Get subscription details from payment provider.

        Args:
            subscription_id: Payment provider subscription ID

        Returns:
            SubscriptionData object
        """
        pass

    @abstractmethod
    async def cancel_subscription(
        self,
        subscription_id: str,
        at_period_end: bool = True
    ) -> SubscriptionData:
        """
        Cancel a subscription.

        Args:
            subscription_id: Payment provider subscription ID
            at_period_end: If True, cancel at end of billing period. If False, cancel immediately.

        Returns:
            Updated SubscriptionData
        """
        pass

    @abstractmethod
    async def resume_subscription(
        self,
        subscription_id: str
    ) -> SubscriptionData:
        """
        Resume a cancelled subscription (before period end).

        Args:
            subscription_id: Payment provider subscription ID

        Returns:
            Updated SubscriptionData
        """
        pass

    @abstractmethod
    async def update_subscription(
        self,
        subscription_id: str,
        price_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SubscriptionData:
        """
        Update a subscription (e.g., change plan).

        Args:
            subscription_id: Payment provider subscription ID
            price_id: New price/plan ID (optional)
            metadata: New metadata (optional)

        Returns:
            Updated SubscriptionData
        """
        pass

    @abstractmethod
    async def create_portal_session(
        self,
        customer_id: str,
        return_url: str
    ) -> str:
        """
        Create a billing portal session for customer to manage subscription.

        Args:
            customer_id: Payment provider customer ID
            return_url: URL to return to after portal session

        Returns:
            Portal URL
        """
        pass

    @abstractmethod
    async def list_payment_methods(
        self,
        customer_id: str
    ) -> List[PaymentMethodData]:
        """
        List payment methods for a customer.

        Args:
            customer_id: Payment provider customer ID

        Returns:
            List of PaymentMethodData
        """
        pass

    @abstractmethod
    async def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """
        Verify webhook signature from payment provider.

        Args:
            payload: Raw webhook payload
            signature: Signature header from webhook

        Returns:
            True if signature is valid, False otherwise
        """
        pass

    @abstractmethod
    async def parse_webhook_event(
        self,
        payload: bytes
    ) -> Dict[str, Any]:
        """
        Parse webhook event from payment provider.

        Args:
            payload: Raw webhook payload

        Returns:
            Parsed event data as dictionary
        """
        pass
