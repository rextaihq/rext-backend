from __future__ import annotations
from typing_extensions import TypedDict, Literal, Optional, Annotated
import operator


class BaseFinalContent(TypedDict):
    title: str
    slug: str
    body_markdown: str
    introduction: str
    
    meta_title: str
    meta_description: str
    tags: list[str]

    primary_keyword: Optional[str]
    secondary_keywords: Optional[list[str]]
    word_count: int
    
    status: Literal["approved", "rejected", "draft", "generated"]
    rejected_reason: Optional[str]

    # WordPress publishing fields
    wordpress_post_id: Optional[int]
    wordpress_link: Optional[str]
    publish_error: Optional[str]
