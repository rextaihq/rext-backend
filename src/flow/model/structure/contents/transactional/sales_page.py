from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class SalesPageGeneratedContent(BaseGeneratedContent):
    product_or_service: Optional[str] = Field(default=None, description="What is being sold.")
    main_pain_point_addressed: Optional[str] = Field(default=None, description="The core problem addressed.")
    urgency_or_scarcity_element: Optional[str] = Field(default=None, description="Urgency element.")
    guarantee_or_risk_reversal: Optional[str] = Field(default=None, description="Guarantee details.")
    primary_cta: Optional[str] = Field(default=None, description="Primary CTA.")
