"""
Pydantic schemas for user preferences endpoints.

Defines request and response models for the preferences API,
following the project convention of centralized schema definitions.
"""

from typing import Optional
from pydantic import BaseModel, Field


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
