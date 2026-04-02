from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class PricingTier(BaseModel):
    tier_name: str = Field(description="Name of the tier.")
    price_point: str = Field(description="Price point details.")
    target_user: str = Field(description="Target audience for the tier.")
    details: str = Field(description="Feature details for this tier.")


class PricingPageGeneratedContent(BaseGeneratedContent):
    product_name: str = Field(description="The product being priced.")
    pricing_model: str = Field(description="Pricing model applied.")
    has_free_tier: bool = Field(default=False)
    pricing_tiers: List[PricingTier] = Field(description="The pricing tiers detailed.")
