from __future__ import annotations
from typing_extensions import Optional
from src.flow.states.outline.base import BaseOutlineState


class BrandPageOutlineState(BaseOutlineState, total=False):
    brand_name: str
    core_values: list[str]
    founding_year: Optional[int]
    key_products_or_services: list[str]
