from __future__ import annotations

from typing_extensions import TypedDict

from src.flow.states.content.base import BaseFinalContent


class PricingTierState(TypedDict, total=False):
    tier_name: str
    price_point: str
    target_user: str
    details: str


class PricingPageContentState(BaseFinalContent, total=False):
    product_name: str
    pricing_model: str
    has_free_tier: bool
    pricing_tiers: list[PricingTierState]
