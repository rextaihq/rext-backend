"""
Permission management API endpoints.

This module provides CRUD operations for permissions with proper authorization.
"""

from fastapi import APIRouter
from .permission_crud import router as crud_router

router = APIRouter(
    prefix="/permissions",
    tags=["permissions"]
)

router.include_router(crud_router)

__all__ = ["router"]
