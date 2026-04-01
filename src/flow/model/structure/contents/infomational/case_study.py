from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class CaseResult(BaseModel):
    name: str = Field(description="KPI or metric name.")
    value: str = Field(description="The achievement or measurement.")
    context: Optional[str] = Field(description="Context for this particular result.")


class CaseStudyGeneratedContent(BaseGeneratedContent):
    case_results: List[CaseResult] = Field(description="Measurable transformations or outcomes.")
    client_name: str = Field(description="Client or product name.")
    the_challenge: str = Field(description="Problem solved.")
    the_solution: str = Field(description="Strategy or tool used.")
    implementation_process: List[str] = Field(description="Phases or steps in the solution.")
