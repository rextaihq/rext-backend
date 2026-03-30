
from __future__ import annotations

import operator
import uuid
from typing_extensions import Annotated, Any, Optional, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from src.flow.states.countries import SUPPORTED_COUNTRIES
from src.flow.states.seo_state import SEORESULT
from src.flow.states.content import CONTENT
from src.flow.states.reducers.custom_reducer import merge_dicts, deep_merge_dicts
from src.flow.states.reducers.custom_reducer import override



class SERPEngineState(TypedDict, total=False):
    # Input
    search_params: dict

    # Extracted SERP components
    organic_results: list[dict[str, Any]]
    related_searches: list[str]
    people_ask: list[dict[str, Any]]

    # SERP metadata
    search_information: dict[str, Any]

    # SERP analysis
    total_results: int

class NormalizedOrganicResult(TypedDict):
    position: int
    title: str
    url: str
    snippet: str
    domain: str
    date: Optional[str]
    # has_sitelinks: bool


class SERPNORMALIZED(TypedDict):
    # Core context
    query: str
    engine: str

    # Cleaned organic results
    normalize_results: list[NormalizedOrganicResult]
    related_topics: list[str]
    questions: list[str]

    # SERP statistics
    stats: dict[str, int]

    # Competition & authority signals
    domains: list[str]
    domain_stats: dict[str, Any]

    # Freshness / recency signals
    freshness: dict[str, Any]

    # SERP feature flags
    features: dict[str, bool]



class Competitor(TypedDict):
    domain: str
    top_positions: list[int]
    total_occurrences: int
    has_sitelinks: bool
    intent_distribution: dict[str, int]
    freshness: dict[str, int]
    avg_snippet_length: float
    featured_snippet: bool
    is_brand: bool



class SERPPAYLOAD(TypedDict, total=False):
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    query: str
    country: SUPPORTED_COUNTRIES
    is_library:bool=False



class DocumentScrapeData(TypedDict):
    document: Document
    content_length: int
    headings: list[str]


class ScrapeContext(TypedDict, total=False):
    documents: list[DocumentScrapeData]
    total_documents: int



class REXT(TypedDict, total=False):
    # Agent Messages
    messages: Annotated[list[BaseMessage], add_messages]

    # SERP
    serp_payload: Annotated[SERPPAYLOAD, merge_dicts]
    serp_result: Annotated[SERPEngineState, merge_dicts]
    serp_normalized: Annotated[SERPNORMALIZED, merge_dicts]

    # Competition
    competitors: list[Competitor]

    # Content & Scraping
    scrape_context: Annotated[ScrapeContext, merge_dicts]
    relevant_context: list[Document]

    # SEO Output
    seo_result: Annotated[SEORESULT, merge_dicts]

    # Content Output
    content: Annotated[CONTENT, deep_merge_dicts]
