from typing import List, Optional

from pydantic import Field

from src.flow.model.structure.contents.base import BaseGeneratedContent


class HelpCenterGeneratedContent(BaseGeneratedContent):
    platform_name: Optional[str] = Field(default=None, description="Platform providing help.")
    top_categories: Optional[List[str]] = Field(
        default_factory=list, description="Main support buckets."
    )
    most_popular_articles: Optional[List[str]] = Field(
        default=None, description="Included articles."
    )
    search_bar_prominence: Optional[bool] = Field(default=True)
