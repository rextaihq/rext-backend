"""
Role management API endpoints.

This module provides CRUD operations for roles with proper permission checks.
"""

from fastapi import APIRouter

from .role_crud import router as crud_router
from .role_permissions import router as permissions_router

router = APIRouter(prefix="/roles", tags=["roles"])

router.include_router(crud_router)
router.include_router(permissions_router)

__all__ = ["router"]
