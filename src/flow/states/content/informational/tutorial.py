from __future__ import annotations

from typing_extensions import Literal, Optional, TypedDict

from src.flow.states.content.base import BaseFinalContent


class CodeBlock(TypedDict):
    language: str
    code: str
    explanation: str


class TutorialStep(TypedDict):
    heading: str
    description: str
    code_blocks: Optional[list[CodeBlock]]


class TutorialContent(BaseFinalContent):
    tutorial_steps: list[TutorialStep]
    prerequisites: Optional[list[str]]
    tutorial_difficulty: Literal["Beginner", "Intermediate", "Advanced"]
    environment_needed: Optional[str]
