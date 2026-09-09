"""
Audit Log API endpoints.

This module provides read-only access to audit logs for administrators and users.
Audit logs are immutable - they can only be created via the internal audit_helper
and queried via these endpoints.
"""

from fastapi import APIRouter

from .audit_export import router as export_router
from .audit_retrieval import router as retrieval_router
from .audit_user import router as user_router

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])

router.include_router(retrieval_router)
router.include_router(user_router)
router.include_router(export_router)

__all__ = ["router"]
