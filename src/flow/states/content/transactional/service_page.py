from __future__ import annotations
from typing_extensions import Optional
from src.flow.states.content.base import BaseFinalContent


class ServicePageContentState(BaseFinalContent, total=False):
    service_name: str
    service_area: Optional[str]
    the_process: list[str]
    why_choose_us: list[str]
