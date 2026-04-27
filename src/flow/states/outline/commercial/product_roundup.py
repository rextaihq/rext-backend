from __future__ import annotations
from typing_extensions import Optional
from src.flow.states.outline.base import BaseOutlineState


class ProductRoundupOutlineState(BaseOutlineState, total=False):
    category_name: str
    total_products: int
    roundup_theme: Optional[str]
    best_value_pick: Optional[str]
    premium_pick: Optional[str]
