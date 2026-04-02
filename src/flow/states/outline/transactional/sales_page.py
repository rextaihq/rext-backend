from __future__ import annotations
from typing_extensions import Optional
from src.flow.states.outline.base import BaseOutlineState


class SalesPageOutlineState(BaseOutlineState, total=False):
    product_or_service: str
    main_pain_point_addressed: str
    urgency_or_scarcity_element: Optional[str]
    guarantee_or_risk_reversal: Optional[str]
    primary_cta: str
