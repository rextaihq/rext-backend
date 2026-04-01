from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class CheckoutPageOutline(BaseOutline):
    """Outline for an e-commerce checkout flow page."""
    store_name: str = Field(description="The generic or specific store name.")
    trust_signals: List[str] = Field(description="E.g., 'Norton Secured', 'Money-back Guarantee'.")
    accepted_payment_methods: List[str] = Field(description="E.g., 'Visa', 'PayPal', 'Crypto'.")
    upsell_or_cross_sell: Optional[str] = Field(description="Any 'Frequently bought together' item.")
