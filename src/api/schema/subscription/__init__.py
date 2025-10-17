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

# Payment checkout schemas
from .checkout_schemas import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
)

# License validation schemas
from .license_schemas import (
    LicenseValidateRequest,
    LicenseValidateResponse,
)

# Invoice schemas
from .invoice_schemas import (
    Invoice,
    InvoiceItem,
    InvoiceListResponse,
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

    # Payment checkout schemas (2)
    "CheckoutSessionRequest",
    "CheckoutSessionResponse",

    # License validation schemas (2)
    "LicenseValidateRequest",
    "LicenseValidateResponse",

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
