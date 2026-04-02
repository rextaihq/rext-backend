from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class CouponPageGeneratedContent(BaseGeneratedContent):
    brand_or_product: str = Field(description="Brand offering discount.")
    offer_details: str = Field(description="Discount details.")
    expiration_date: Optional[str] = Field(description="Offer expiration.")
    terms_and_conditions: List[str] = Field(description="Restrictions.")
