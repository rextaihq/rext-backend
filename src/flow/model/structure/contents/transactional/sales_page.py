from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class SalesPageGeneratedContent(BaseGeneratedContent):
    product_or_service: str = Field(description="What is being sold.")
    main_pain_point_addressed: str = Field(description="The core problem addressed.")
    urgency_or_scarcity_element: Optional[str] = Field(description="Urgency element.")
    guarantee_or_risk_reversal: Optional[str] = Field(description="Guarantee details.")
    primary_cta: str = Field(description="Primary CTA.")
