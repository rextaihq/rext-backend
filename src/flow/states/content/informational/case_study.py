from __future__ import annotations
from typing_extensions import TypedDict, Optional
from src.flow.states.content.base import BaseFinalContent


class CaseResult(TypedDict):
    name: str
    value: str
    context: Optional[str]


class CaseStudyContent(BaseFinalContent):
    case_results: list[CaseResult]
    client_name: str
    the_challenge: str
    the_solution: str
    implementation_process: list[str]
