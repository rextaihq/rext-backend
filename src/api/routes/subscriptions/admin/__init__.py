"""
Admin subscription routes aggregation.

This module aggregates all admin subscription routes from the modular components.
"""

from fastapi import APIRouter

from .admin_subscription_analytics import router as analytics_router
from .admin_subscription_retrieval import router as retrieval_router
from .refund_routes import router as refund_router
from .webhook_monitoring_routes import router as webhook_monitoring_router

router = APIRouter(prefix="/admin/subscriptions", tags=["admin-subscriptions"])

router.include_router(analytics_router)
router.include_router(webhook_monitoring_router)
router.include_router(refund_router)
router.include_router(retrieval_router)

__all__ = ["router"]
