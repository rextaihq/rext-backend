"""
Admin subscription routes aggregation.

This module aggregates all admin subscription routes from the modular components.
"""

from fastapi import APIRouter
from .admin_subscription_management import router as management_router
from .admin_subscription_retrieval import router as retrieval_router
from .admin_subscription_analytics import router as analytics_router

router = APIRouter(prefix="/admin/subscriptions", tags=["admin-subscriptions"])

router.include_router(management_router)
router.include_router(retrieval_router)
router.include_router(analytics_router)

__all__ = ["router"]
