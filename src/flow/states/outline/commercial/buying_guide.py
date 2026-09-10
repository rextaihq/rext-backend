from __future__ import annotations

from typing_extensions import Optional

from src.flow.states.outline.base import BaseOutlineState


class BuyingGuideOutlineState(BaseOutlineState, total=False):
    product_category: str
    key_features_to_consider: list[str]
    budget_tiers: Optional[list[str]]
    common_mistakes_to_avoid: Optional[list[str]]
