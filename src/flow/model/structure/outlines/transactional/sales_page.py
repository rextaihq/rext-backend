from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class SalesPageOutline(BaseOutline):
    """Outline for a long-form or direct sales page."""
    product_or_service: str = Field(description="What is being sold.")
    main_pain_point_addressed: str = Field(description="The core problem the user has that this solves.")
    urgency_or_scarcity_element: Optional[str] = Field(description="Why they should buy right now.")
    guarantee_or_risk_reversal: Optional[str] = Field(description="Money-back guarantee, free trial, etc.")
    primary_cta: str = Field(description="The primary button copy (e.g., 'Buy Now for $99').")
