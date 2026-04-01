from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class HelpCenterGeneratedContent(BaseGeneratedContent):
    platform_name: str = Field(description="Platform providing help.")
    top_categories: List[str] = Field(description="Main support buckets.")
    most_popular_articles: Optional[List[str]] = Field(description="Included articles.")
    search_bar_prominence: bool = Field(default=True)
