"""
Base Payment Provider Interface

This module defines the abstract interface that all payment providers must implement.
This abstraction allows the application to work with any payment provider
(LemonSqueezy, Paddle, FastSpring, etc.) without changing business logic.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CheckoutSession:
    """Checkout session data returned by payment provider"""
    session_id: str
    checkout_url: str
    customer_id: str
    metadata: Dict[str, Any]


@dataclass
class CustomerData:
    """Customer data returned by payment provider"""
    customer_id: str
    email: str
    name: str
    metadata: Dict[str, Any]


@dataclass
class SubscriptionData:
    """Subscription data returned by payment provider"""
    subscription_id: str
    status: str  # active, cancelled, expired, trialing, past_due
    customer_id: str
    plan_id: str
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    cancelled_at: Optional[datetime] = None
    trial_end: Optional[datetime] = None


class PaymentProvider(ABC):
    """Abstract payment provider interface that all providers must implement"""

    @abstractmethod
    async def create_customer(
        self,
        email: str,
        name: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create customer in payment provider.

        Args:
            email: Customer email
            name: Customer name
            metadata: Additional metadata to store with customer

        Returns:
            str: Customer ID from payment provider
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
            customer_id: Customer ID from payment provider

        Returns:
            CustomerData: Customer information
        """
        pass

    @abstractmethod
    async def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CheckoutSession:
        """
        Create checkout session for subscription.

        Args:
            customer_id: Customer ID from payment provider
            price_id: Price/Plan ID from payment provider
            success_url: URL to redirect on successful payment
            cancel_url: URL to redirect on cancelled payment
            metadata: Additional metadata to store with checkout

        Returns:
            CheckoutSession: Checkout session details including URL
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
            subscription_id: Subscription ID from payment provider

        Returns:
            SubscriptionData: Subscription information
        """
        pass

    @abstractmethod
    async def cancel_subscription(
        self,
        subscription_id: str,
        at_period_end: bool = True
    ) -> SubscriptionData:
        """
        Cancel subscription.

        Args:
            subscription_id: Subscription ID from payment provider
            at_period_end: If True, cancel at end of billing period.
                          If False, cancel immediately.

        Returns:
            SubscriptionData: Updated subscription information
        """
        pass

    @abstractmethod
    async def update_subscription(
        self,
        subscription_id: str,
        price_id: str
    ) -> SubscriptionData:
        """
        Update subscription to new plan/price.

        Args:
            subscription_id: Subscription ID from payment provider
            price_id: New price/plan ID from payment provider

        Returns:
            SubscriptionData: Updated subscription information
        """
        pass

    @abstractmethod
    async def create_portal_session(
        self,
        customer_id: str,
        return_url: str
    ) -> str:
        """
        Create customer portal session for managing subscription.

        Args:
            customer_id: Customer ID from payment provider
            return_url: URL to return to after portal session

        Returns:
            str: Portal URL
        """
        pass

    @abstractmethod
    async def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        secret: Optional[str] = None
    ) -> bool:
        """
        Verify webhook signature from payment provider.

        Args:
            payload: Raw webhook payload
            signature: Signature header from webhook request
            secret: Optional webhook secret (if not using config)

        Returns:
            bool: True if signature is valid
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
            Dict containing:
                - event_type: Type of event (e.g., "subscription.created")
                - data: Event-specific data
                - timestamp: Event timestamp
        """
        pass
