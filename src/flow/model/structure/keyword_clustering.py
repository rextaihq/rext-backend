from pydantic import BaseModel, Field
from typing import List, Literal


class ClusterKeywordItem(BaseModel):
    keyword: str = Field(description="A keyword phrase belonging to this cluster")
    relevance_score: float = Field(
        ge=0,
        le=100,
        description="Relevance to the cluster parent (0-100)",
    )


class KeywordClusterGroup(BaseModel):
    cluster_name: str = Field(
        description="Parent/head keyword for the cluster (highest-value representative term)"
    )
    topic_theme: str = Field(
        description="Short label for the topical theme (e.g. 'pricing comparison')"
    )
    intent: Literal[
        "INFORMATIONAL",
        "COMMERCIAL",
        "NAVIGATIONAL",
        "TRANSACTIONAL",
    ] = Field(description="Dominant intent for keywords in this cluster")
    keywords: List[ClusterKeywordItem] = Field(
        min_length=1,
        description="Keywords grouped by shared SERP overlap and topical similarity",
    )
    rationale: str = Field(
        description="Why these keywords belong together (SERP/topic overlap)"
    )


class KeywordClusteringLLMOutput(BaseModel):
    clusters: List[KeywordClusterGroup] = Field(
        min_length=1,
        description="Intent-aligned keyword clusters similar to Semrush/Ahrefs topic groups",
    )
