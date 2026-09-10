from pydantic import BaseModel


class APIKeyCheckResponse(BaseModel):
    """Schema for API key authentication check response."""

    status: str
    message: str
    api_key_preview: str
    note: str
