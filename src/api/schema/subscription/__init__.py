"""
Subscription schema package.

This package provides all subscription-related Pydantic schemas organized by functionality.
"""

# Enums
# Admin management schemas
from .admin_schemas import (
    AdminSubscriptionAssignRequest,
    AdminSubscriptionExtendRequest,
    AdminUsageResetRequest,
)

# Analytics schemas
from .analytics_schemas import (
    ChurnAnalysisResponse,
    PlanBreakdown,
    RevenueMetricsResponse,
    SubscriptionStatsResponse,
    TrialConversionResponse,
)

# Payment checkout schemas
from .checkout_schemas import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
)
from .enums import (
    BillingPeriod,
    SubscriptionStatus,
)

# Invoice schemas
from .invoice_schemas import (
    Invoice,
    InvoiceItem,
    InvoiceListResponse,
)

# Plan schemas
from .plan_schemas import (
    SubscriptionPlanCreate,
    SubscriptionPlanResponse,
    SubscriptionPlanUpdate,
)

# Usage and trial schemas
from .usage_schemas import (
    TrialStatusResponse,
    UsageStatsResponse,
)

# User subscription schemas
from .user_subscription_schemas import (
    SubscriptionCancelRequest,
    SubscriptionCreateRequest,
    SubscriptionUpgradeRequest,
    UserSubscriptionResponse,
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
    # Payment checkout schemas (2)
    "CheckoutSessionRequest",
    "CheckoutSessionResponse",
    # Invoice schemas (3)
    "Invoice",
    "InvoiceItem",
    "InvoiceListResponse",
    # Analytics schemas (5)
    "SubscriptionStatsResponse",
    "PlanBreakdown",
    "RevenueMetricsResponse",
    "ChurnAnalysisResponse",
    "TrialConversionResponse",
]
