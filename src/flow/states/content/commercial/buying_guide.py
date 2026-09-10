from __future__ import annotations

from typing_extensions import Optional

from src.flow.states.content.base import BaseFinalContent


class BuyingGuideContentState(BaseFinalContent, total=False):
    product_category: str
    key_features_to_consider: list[str]
    budget_tiers: Optional[list[str]]
    common_mistakes_to_avoid: Optional[list[str]]
