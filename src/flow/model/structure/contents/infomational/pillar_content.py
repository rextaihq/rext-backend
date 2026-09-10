from typing import List, Optional

from pydantic import BaseModel, Field

from src.flow.model.structure.contents.base import BaseGeneratedContent


class SubtopicCluster(BaseModel):
    topic: str = Field(description="Subtopic.")
    link_suggestion: Optional[str] = Field(
        default=None, description="Suggested internal link context."
    )
    context: str = Field(description="Content summary for this subtopic cluster.")


class PillarContentGeneratedContent(BaseGeneratedContent):
    subtopic_clusters: Optional[List[SubtopicCluster]] = Field(
        default_factory=list, description="Topic cluster mapping within the content."
    )
    table_of_contents: Optional[List[str]] = Field(
        default_factory=list, description="Section headings for TOC."
    )
    comprehensive_checklist_included: Optional[bool] = Field(default=False)
