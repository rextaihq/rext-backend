from __future__ import annotations
from typing_extensions import Optional
from src.flow.states.outline.base import BaseOutlineState, SectionState


class PricingTierState(SectionState, total=False):
    tier_name: str
    price_point: str
    target_user: str


class PricingPageOutlineState(BaseOutlineState, total=False):
    product_name: str
    pricing_model: str
    has_free_tier: bool
    sections: list[PricingTierState]
