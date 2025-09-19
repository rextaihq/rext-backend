from pydantic import BaseModel, HttpUrl, Field
from typing import Optional

class WorkspaceSchema(BaseModel):
    title: str | None = Field(default=None, description="Optional workspace title")
    description: Optional[str] = Field(..., min_length=3, description="Workspace description")
    url: HttpUrl | None = Field(default=None, description="Optional workspace URL")