from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class ProductRoundupGeneratedContent(BaseGeneratedContent):
    category_name: str = Field(description="The general category for the roundup.")
    total_products: int = Field(description="Number of products included.")
    roundup_theme: Optional[str] = Field(description="Theme of the roundup.")
    best_value_pick: Optional[str] = Field(description="The best value product.")
    premium_pick: Optional[str] = Field(description="The premium option.")
