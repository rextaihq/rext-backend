from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional

class WorkflowSchema(BaseModel):
    name: str = Field(..., description="Name of the workflow")
    is_active: bool = Field(default=True, description="Indicates if the workflow is active")
    description: Optional[str] = Field(None, description="Description of the workflow")
    status: str = Field(default="pending", description="Current status of the workflow")
