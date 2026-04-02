from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class BrandPageGeneratedContent(BaseGeneratedContent):
    brand_name: str = Field(description="The name of the brand.")
    core_values: List[str] = Field(description="The core values or mission.")
    founding_year: Optional[int] = Field(description="Year founded.")
    key_products_or_services: List[str] = Field(description="Main offerings.")
