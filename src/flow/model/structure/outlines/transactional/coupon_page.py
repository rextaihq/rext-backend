from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class CouponPageOutline(BaseOutline):
    """Outline for a discount, promo code, or coupon page."""
    brand_or_product: str = Field(description="The brand offering the discount.")
    offer_details: str = Field(description="What the actual discount is (e.g., '20% Off').")
    expiration_date: Optional[str] = Field(description="When the offer ends.")
    terms_and_conditions: List[str] = Field(description="Restrictions on the coupon.")
