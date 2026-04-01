from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class PricingTier(Section):
    """A section describing a specific pricing tier."""
    tier_name: str = Field(description="E.g., 'Basic', 'Pro', 'Enterprise'.")
    price_point: str = Field(description="E.g., '$29/mo' or 'Custom'.")
    target_user: str = Field(description="Who this tier is best for.")


class PricingPageOutline(BaseOutline):
    """Outline for a pricing comparison page."""
    product_name: str = Field(description="The product being priced.")
    pricing_model: str = Field(description="E.g., 'Subscription', 'One-time', 'Usage-based'.")
    has_free_tier: bool = Field(default=False)
    sections: List[PricingTier] = Field(description="The pricing tiers detailed.")
