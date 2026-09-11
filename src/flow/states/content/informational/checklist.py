from __future__ import annotations

from typing_extensions import Literal, Optional, TypedDict

from src.flow.states.content.base import BaseFinalContent


class CheckItem(TypedDict):
    label: str
    context: Optional[str]
    difficulty: Literal["Easy", "Medium", "Hard"]


class ChecklistContent(BaseFinalContent):
    check_items: list[CheckItem]
    is_printable_ready: bool = True
    total_phases: Optional[int]
    estimated_total_time: Optional[str]
