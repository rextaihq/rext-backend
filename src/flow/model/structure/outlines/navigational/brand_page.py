from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class BrandPageOutline(BaseOutline):
    """Outline for a brand's central informational page."""
    brand_name: str = Field(description="The name of the brand.")
    core_values: List[str] = Field(description="The core values or mission of the brand.")
    founding_year: Optional[int] = Field(description="Year the brand was founded.")
    key_products_or_services: List[str] = Field(description="Main offerings by this brand.")
