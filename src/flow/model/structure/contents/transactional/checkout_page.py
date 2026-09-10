from typing import List, Optional

from pydantic import Field

from src.flow.model.structure.contents.base import BaseGeneratedContent


class CheckoutPageGeneratedContent(BaseGeneratedContent):
    store_name: Optional[str] = Field(default=None, description="Store name.")
    trust_signals: Optional[List[str]] = Field(
        default_factory=list, description="Trust signals used."
    )
    accepted_payment_methods: Optional[List[str]] = Field(
        default_factory=list, description="Payment methods accepted."
    )
    upsell_or_cross_sell: Optional[str] = Field(default=None, description="Upsell items.")
