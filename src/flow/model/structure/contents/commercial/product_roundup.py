from typing import Optional

from pydantic import Field

from src.flow.model.structure.contents.base import BaseGeneratedContent


class ProductRoundupGeneratedContent(BaseGeneratedContent):
    category_name: Optional[str] = Field(
        default=None, description="The general category for the roundup."
    )
    total_products: Optional[int] = Field(default=None, description="Number of products included.")
    roundup_theme: Optional[str] = Field(default=None, description="Theme of the roundup.")
    best_value_pick: Optional[str] = Field(default=None, description="The best value product.")
    premium_pick: Optional[str] = Field(default=None, description="The premium option.")
