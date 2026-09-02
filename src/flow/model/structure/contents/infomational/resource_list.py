from typing import List, Optional

from pydantic import BaseModel, Field

from src.flow.model.structure.contents.base import BaseGeneratedContent


class ResourceLink(BaseModel):
    title: str = Field(description="Name or title.")
    url: str = Field(description="The source URL.")
    description: str = Field(description="Summary of the resource.")
    category: Optional[str] = Field(default=None, description="Sub-category within this list.")


class ResourceListGeneratedContent(BaseGeneratedContent):
    resource_links: Optional[List[ResourceLink]] = Field(
        default_factory=list, description="Curated links or tools described."
    )
    selection_process: Optional[str] = Field(
        default=None, description="How the resources were selected."
    )
    best_for_context: Optional[str] = Field(
        default=None, description="Who this list is best for (e.g., 'Small Business Owners')."
    )
