from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class PricingTier(BaseModel):
    tier_name: str = Field(description="Name of the tier.")
    price_point: str = Field(description="Price point details.")
    target_user: Optional[str] = Field(default=None, description="Target audience for the tier.")
    details: str = Field(description="Feature details for this tier.")


class PricingPageGeneratedContent(BaseGeneratedContent):
    product_name: Optional[str] = Field(default=None, description="The product being priced.")
    pricing_model: Optional[str] = Field(default=None, description="Pricing model applied.")
    has_free_tier: Optional[bool] = Field(default=False)
    pricing_tiers: Optional[List[PricingTier]] = Field(default_factory=list, description="The pricing tiers detailed.")
