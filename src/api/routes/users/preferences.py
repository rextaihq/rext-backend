"""
User Preferences API endpoints.

This module provides endpoints for managing user-specific preferences.
"""

from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from pydantic import BaseModel, Field
from typing import Optional

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import require_permissions, db_transaction_handler
from src.utils.logger import logger
from src.services.user_preferences_service import UserPreferencesService

router = APIRouter()


class UserPreferencesResponse(BaseModel):
    """User preferences response schema"""
    id: str
    user_id: str
    theme: Optional[str] = "system"
    date_format: Optional[str] = "iso"
    time_format: Optional[str] = "24h"
    items_per_page: Optional[int] = 25
    sidebar_collapsed: Optional[bool] = False
    created_at: str
    updated_at: str


class UpdateUserPreferencesRequest(BaseModel):
    """Update user preferences request schema"""
    theme: Optional[str] = Field(None, pattern="^(system|light|dark)$")
    date_format: Optional[str] = Field(None, pattern="^(iso|us|eu|relative)$")
    time_format: Optional[str] = Field(None, pattern="^(24h|12h)$")
    items_per_page: Optional[int] = Field(None, ge=10, le=100)
    sidebar_collapsed: Optional[bool] = None


@router.get("/preferences", response_model=dict)
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("get user preferences", auto_commit=False)
async def get_user_preferences(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current user's preferences.
    """
    user_id = UUID(current_user.get("identity"))
    service = UserPreferencesService(db)

    # Get or create preferences via service
    preferences = await service.get_or_create_preferences(user_id)

    return {"preferences": preferences.to_dict()}


@router.patch("/preferences", response_model=dict)
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("update user preferences", auto_commit=True)
async def update_user_preferences(
    request: Request,
    preferences_data: UpdateUserPreferencesRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update current user's preferences.
    """
    user_id = UUID(current_user.get("identity"))
    service = UserPreferencesService(db)

    # Update preferences via service
    update_data = preferences_data.model_dump(exclude_unset=True)
    preferences = await service.update_preferences(
        user_id=user_id,
        theme=update_data.get("theme"),
        date_format=update_data.get("date_format"),
        time_format=update_data.get("time_format"),
        items_per_page=update_data.get("items_per_page"),
        sidebar_collapsed=update_data.get("sidebar_collapsed")
    )

    return {"preferences": preferences.to_dict()}
