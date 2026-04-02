from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class ServicePageGeneratedContent(BaseGeneratedContent):
    service_name: str = Field(description="The service being provided.")
    service_area: Optional[str] = Field(description="Locations covered.")
    the_process: List[str] = Field(description="Process steps.")
    why_choose_us: List[str] = Field(description="Differentiators.")
