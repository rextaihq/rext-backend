from __future__ import annotations

from typing_extensions import Optional

from src.flow.states.content.base import BaseFinalContent


class ProductRoundupContentState(BaseFinalContent, total=False):
    category_name: str
    total_products: int
    roundup_theme: Optional[str]
    best_value_pick: Optional[str]
    premium_pick: Optional[str]
