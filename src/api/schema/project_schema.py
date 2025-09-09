from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID

class ProjectBase(BaseModel):
    title: str = Field(..., max_length=80, description="Title of the project")
    description: str = Field(..., description="Description of the project")
    instructions: List[str] = Field(..., description="List of instructions for the project")