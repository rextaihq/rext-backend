from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class CaseResult(BaseModel):
    name: str = Field(description="KPI or metric name.")
    value: str = Field(description="The achievement or measurement.")
    context: Optional[str] = Field(default=None, description="Context for this particular result.")


class CaseStudyGeneratedContent(BaseGeneratedContent):
    case_results: Optional[List[CaseResult]] = Field(default_factory=list, description="Measurable transformations or outcomes.")
    client_name: Optional[str] = Field(default=None, description="Client or product name.")
    the_challenge: Optional[str] = Field(default=None, description="Problem solved.")
    the_solution: Optional[str] = Field(default=None, description="Strategy or tool used.")
    implementation_process: Optional[List[str]] = Field(default_factory=list, description="Phases or steps in the solution.")
