from __future__ import annotations
from typing_extensions import Optional
from src.flow.states.content.base import BaseFinalContent


class CouponPageContentState(BaseFinalContent, total=False):
    brand_or_product: str
    offer_details: str
    expiration_date: Optional[str]
    terms_and_conditions: list[str]
