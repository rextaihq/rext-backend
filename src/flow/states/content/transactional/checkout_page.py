from __future__ import annotations
from typing_extensions import Optional
from src.flow.states.content.base import BaseFinalContent


class CheckoutPageContentState(BaseFinalContent, total=False):
    store_name: str
    trust_signals: list[str]
    accepted_payment_methods: list[str]
    upsell_or_cross_sell: Optional[str]
