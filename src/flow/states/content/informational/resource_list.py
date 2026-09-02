from __future__ import annotations

from typing_extensions import Optional, TypedDict

from src.flow.states.content.base import BaseFinalContent


class ResourceLink(TypedDict):
    title: str
    url: str
    description: str
    category: Optional[str]


class ResourceListContent(BaseFinalContent):
    resource_links: list[ResourceLink]
    selection_process: Optional[str]
    best_for_context: Optional[str]
