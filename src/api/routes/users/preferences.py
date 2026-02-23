"""
User Preferences API endpoints.

This module provides endpoints for managing user-specific preferences.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import require_permissions, db_transaction_handler
from src.api.schema.preferences_schema import UserPreferencesResponse, UpdateUserPreferencesRequest
from src.utils.logger import logger
from src.services.user_preferences_service import UserPreferencesService

router = APIRouter()


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
