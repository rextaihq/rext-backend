from pydantic import BaseModel, Field,HttpUrl
from typing import List, Optional

class TopicSelectionSchema(BaseModel):
    topic:List[str]


class RSSFeedSchema(BaseModel):
    title: str = Field(default="WP Tavern", description="Title of the RSS feed")
    url: HttpUrl = Field(defaut="https://wptavern.com/feed", description="URL of the RSS feed")

class WorkflowConfigSchema(BaseModel):
    country: str = Field(default="pk", description="Country code for news articles")
    category: str = Field(default="technology", description="Category of news articles")
    language: str = Field(default="en", description="Language code for news articles")
    rss_sources: Optional[List[RSSFeedSchema]] = Field(default=None, description="Custom RSS feed URLs")