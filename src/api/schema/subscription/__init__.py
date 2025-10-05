"""
Subscription schema package.

This package provides all subscription-related Pydantic schemas organized by functionality.
"""

# Enums
from .enums import (
    SubscriptionStatus,
    BillingPeriod,
)

# Plan schemas
from .plan_schemas import (
    SubscriptionPlanCreate,
    SubscriptionPlanUpdate,
    SubscriptionPlanResponse,
)

# User subscription schemas
from .user_subscription_schemas import (
    SubscriptionCreateRequest,
    SubscriptionUpgradeRequest,
    SubscriptionCancelRequest,
    UserSubscriptionResponse,
)

# Usage and trial schemas
from .usage_schemas import (
    UsageStatsResponse,
    TrialStatusResponse,
)

# Admin management schemas
from .admin_schemas import (
    AdminSubscriptionAssignRequest,
    AdminSubscriptionExtendRequest,
    AdminUsageResetRequest,
)

# Stripe integration schemas
from .stripe_schemas import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
)

# Analytics schemas
from .analytics_schemas import (
    SubscriptionStatsResponse,
    PlanBreakdown,
    RevenueMetricsResponse,
    ChurnAnalysisResponse,
    TrialConversionResponse,
)

__all__ = [
    # Enums (2)
    "SubscriptionStatus",
    "BillingPeriod",

    # Plan schemas (3)
    "SubscriptionPlanCreate",
    "SubscriptionPlanUpdate",
    "SubscriptionPlanResponse",

    # User subscription schemas (4)
    "SubscriptionCreateRequest",
    "SubscriptionUpgradeRequest",
    "SubscriptionCancelRequest",
    "UserSubscriptionResponse",

    # Usage and trial schemas (2)
    "UsageStatsResponse",
    "TrialStatusResponse",

    # Admin management schemas (3)
    "AdminSubscriptionAssignRequest",
    "AdminSubscriptionExtendRequest",
    "AdminUsageResetRequest",

    # Stripe integration schemas (2)
    "CheckoutSessionRequest",
    "CheckoutSessionResponse",

    # Analytics schemas (5)
    "SubscriptionStatsResponse",
    "PlanBreakdown",
    "RevenueMetricsResponse",
    "ChurnAnalysisResponse",
    "TrialConversionResponse",
]
