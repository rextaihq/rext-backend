from __future__ import annotations
from typing_extensions import TypedDict, Literal, Optional
from src.flow.states.content.base import BaseFinalContent


class HowToStep(TypedDict):
    title: str
    description: str
    tools: Optional[list[str]]


class HowToGuideContent(BaseFinalContent):
    steps: list[HowToStep]
    total_time: Optional[str]
    difficulty: Literal["Beginner", "Intermediate", "Advanced"]
    tools_needed: list[str]
