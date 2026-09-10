from typing import List, Literal

from pydantic import BaseModel, Field


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
    rationale: str = Field(description="Why these keywords belong together (SERP/topic overlap)")
    likely_serp_page_type: str = Field(
        default="",
        description=(
            "Likely SERP page type shared by this cluster, such as blog article, "
            "FAQ page, comparison page, tutorial, glossary, landing page, or "
            "transactional page."
        ),
    )
    natural_heading: str = Field(
        default="",
        description="Natural H2/H3/body-copy heading or label for this cluster.",
    )
    outline_placement: str = Field(
        default="H2",
        description="Recommended outline placement: H2, H3, or body.",
    )
    intent_match_score: float = Field(
        default=0,
        ge=0,
        le=100,
        description="How tightly the cluster matches the primary search intent.",
    )
    serp_overlap_score: float = Field(
        default=0,
        ge=0,
        le=100,
        description="How likely the keywords share overlapping SERP results/page type.",
    )
    content_type_fit_score: float = Field(
        default=0,
        ge=0,
        le=100,
        description="How well the cluster fits the requested content type.",
    )
    cluster_strength_score: float = Field(
        default=0,
        ge=0,
        le=100,
        description="Compactness, topical cohesion, and keyword quality of the cluster.",
    )


class KeywordClusteringLLMOutput(BaseModel):
    clusters: List[KeywordClusterGroup] = Field(
        min_length=1,
        description="Intent-aligned keyword clusters similar to Semrush/Ahrefs topic groups",
    )
