from typing import List, Optional

from pydantic import Field

from src.flow.model.structure.contents.base import BaseGeneratedContent


class BrandPageGeneratedContent(BaseGeneratedContent):
    brand_name: Optional[str] = Field(default=None, description="The name of the brand.")
    core_values: Optional[List[str]] = Field(
        default_factory=list, description="The core values or mission."
    )
    founding_year: Optional[int] = Field(default=None, description="Year founded.")
    key_products_or_services: Optional[List[str]] = Field(
        default_factory=list, description="Main offerings."
    )
