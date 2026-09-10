from typing import Optional

from pydantic import BaseModel

from src.api.schema.preferences_schema import UserPreferencesResponse


class UserPreferencesWrappedResponse(BaseModel):
    """Schema for user preferences response wrapped in a 'preferences' key."""

    preferences: UserPreferencesResponse
    message: Optional[str] = None
