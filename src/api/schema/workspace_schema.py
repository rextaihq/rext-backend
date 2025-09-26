from pydantic import BaseModel, HttpUrl, Field
from typing import Optional

class WorkspaceSchema(BaseModel):
    user_id: str = Field(..., description="ID of the user creating the workspace")
    name: str | None = Field(default=None, description="Optional workspace title")
    description: Optional[str] = Field(..., min_length=3, description="Workspace description")
    url: HttpUrl | None = Field(default=None, description="Optional workspace URL")