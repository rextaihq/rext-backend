from pydantic import BaseModel, Field
from typing import List

class ProjectBase(BaseModel):
    title: str = Field(..., max_length=80, description="Title of the project")
    memory_mode:bool = Field(False, description="Enable or disable memory mode")
    project_instructions: List[str] = Field(..., description="List of instructions for the project")