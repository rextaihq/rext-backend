"""
User Preferences API endpoints.

This module provides endpoints for managing user-specific preferences.
"""

from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from pydantic import BaseModel, Field
from typing import Optional

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.user_models.user_preferences import UserPreferences
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.utils.logger import logger

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
async def get_user_preferences(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current user's preferences.

    Returns:
    - User preferences or defaults if not set
    """
    try:
        user_id = UUID(current_user.get("identity"))

        # Get or create preferences
        query = select(UserPreferences).where(UserPreferences.user_id == user_id)
        result = await db.execute(query)
        preferences = result.scalar_one_or_none()

        if not preferences:
            # Create default preferences
            preferences = UserPreferences(
                user_id=user_id,
                theme="system",
                date_format="iso",
                time_format="24h",
                items_per_page=25,
                sidebar_collapsed=False
            )
            db.add(preferences)
            await db.commit()
            await db.refresh(preferences)
            logger.info(f"Created default preferences for user {user_id}")

        return success(
            data={"preferences": preferences.to_dict()},
            request=request,
            message="Preferences retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Error fetching preferences: {str(e)}")
        await db.rollback()
        return error(
            message="Failed to fetch preferences",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.patch("/preferences", response_model=dict)
async def update_user_preferences(
    request: Request,
    preferences_data: UpdateUserPreferencesRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update current user's preferences.

    Supports partial updates - only provided fields will be updated.

    Request Body:
    - theme: UI theme (system, light, dark)
    - date_format: Date format (iso, us, eu, relative)
    - time_format: Time format (24h, 12h)
    - items_per_page: Items per page (10-100)
    - sidebar_collapsed: Sidebar state (boolean)

    Returns:
    - Updated preferences
    """
    try:
        user_id = UUID(current_user.get("identity"))

        # Get existing preferences or create new
        query = select(UserPreferences).where(UserPreferences.user_id == user_id)
        result = await db.execute(query)
        preferences = result.scalar_one_or_none()

        if not preferences:
            # Create new preferences
            preferences = UserPreferences(user_id=user_id)
            db.add(preferences)

        # Update only provided fields
        update_data = preferences_data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if value is not None:
                setattr(preferences, field, value)

        await db.commit()
        await db.refresh(preferences)

        logger.info(f"Updated preferences for user {user_id}: {update_data}")

        return success(
            data={"preferences": preferences.to_dict()},
            request=request,
            message="Preferences updated successfully"
        )

    except Exception as e:
        logger.error(f"Error updating preferences: {str(e)}")
        await db.rollback()
        return error(
            message="Failed to update preferences",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )
