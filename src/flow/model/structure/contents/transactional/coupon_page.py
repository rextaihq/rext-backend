from typing import List, Optional

from pydantic import Field

from src.flow.model.structure.contents.base import BaseGeneratedContent


class CouponPageGeneratedContent(BaseGeneratedContent):
    brand_or_product: Optional[str] = Field(default=None, description="Brand offering discount.")
    offer_details: Optional[str] = Field(default=None, description="Discount details.")
    expiration_date: Optional[str] = Field(default=None, description="Offer expiration.")
    terms_and_conditions: Optional[List[str]] = Field(
        default_factory=list, description="Restrictions."
    )
