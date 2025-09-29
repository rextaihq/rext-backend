from pydantic import BaseModel, HttpUrl, Field
from typing import Optional

class WorkspaceSchema(BaseModel):
    name: str | None = Field(default=None, description="Optional workspace title")
    description: Optional[str] = Field(..., min_length=3, description="Workspace description")
    url: HttpUrl  = Field(description="workspace URL")