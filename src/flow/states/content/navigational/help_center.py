from __future__ import annotations
from typing_extensions import Optional
from src.flow.states.content.base import BaseFinalContent


class HelpCenterContentState(BaseFinalContent, total=False):
    platform_name: str
    top_categories: list[str]
    most_popular_articles: Optional[list[str]]
    search_bar_prominence: bool
