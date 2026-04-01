from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class CheckoutPageGeneratedContent(BaseGeneratedContent):
    store_name: str = Field(description="Store name.")
    trust_signals: List[str] = Field(description="Trust signals used.")
    accepted_payment_methods: List[str] = Field(description="Payment methods accepted.")
    upsell_or_cross_sell: Optional[str] = Field(description="Upsell items.")
