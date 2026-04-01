from __future__ import annotations
from typing_extensions import Optional
from src.flow.states.outline.base import BaseOutlineState


class ServicePageOutlineState(BaseOutlineState, total=False):
    service_name: str
    service_area: Optional[str]
    the_process: list[str]
    why_choose_us: list[str]
