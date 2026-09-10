from typing import List, Optional

from pydantic import Field

from src.flow.model.structure.contents.base import BaseGeneratedContent


class ServicePageGeneratedContent(BaseGeneratedContent):
    service_name: Optional[str] = Field(default=None, description="The service being provided.")
    service_area: Optional[str] = Field(default=None, description="Locations covered.")
    the_process: Optional[List[str]] = Field(default_factory=list, description="Process steps.")
    why_choose_us: Optional[List[str]] = Field(default_factory=list, description="Differentiators.")
