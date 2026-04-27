from __future__ import annotations
from typing_extensions import Optional
from src.flow.states.outline.base import BaseOutlineState


class FeatureOverviewOutlineState(BaseOutlineState, total=False):
    product_name: str
    number_of_features_highlighted: int
    target_user_role: Optional[str]
    integration_mentions: Optional[list[str]]
