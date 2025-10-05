"""
Subscription enums for status and billing period.

This module defines enumerations used across subscription schemas.
"""

from enum import Enum


class SubscriptionStatus(str, Enum):
    """Subscription status enum."""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"
    SUSPENDED = "suspended"


class BillingPeriod(str, Enum):
    """Billing period enum."""
    MONTHLY = "monthly"
    YEARLY = "yearly"
    LIFETIME = "lifetime"
