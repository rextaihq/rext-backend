# =========================
# Imports
# =========================
from typing import List, Dict, Any, Optional
from typing_extensions import TypedDict, Annotated
from langchain_core.documents import Document
from src.flow.states.countries import SUPPORTED_COUNTRIES
from src.flow.states.seo_state import SEORESULT
from src.flow.states.content import CONTENT
from src.flow.states.reducers.custom_reducer import merge_dicts, deep_merge_dicts
from src.flow.states.reducers.custom_reducer import override
from langchain_core.messages import BaseMessage
import operator
import uuid

# =========================
# SERP ENGINE STATE
# =========================
class SERPEngineState(TypedDict, total=False):
    # Input
    search_params: dict

    # Extracted SERP components
    organic_results: List[Dict[str, Any]]
    related_searches: List[str]
    people_ask: List[Dict[str, Any]]

    # SERP metadata
    # search_information: Dict[str, Any]

    # SERP analysis
    total_results: int

class SERPBacklinks(TypedDict):
    keyword: str
    search_volume: int
    keyword_difficulty: int
    backlinks: int
    referring_domains: int
    dofollow_links: int
    images: bool
    videos: bool
    main_intent: str
    foreign_intent: str


# =========================
# NORMALIZED SERP STATE
# =========================
class NormalizedOrganicResult(TypedDict):
    position: int
    title: str
    url: str
    snippet: str
    domain: str
    date: Optional[str]
    has_sitelinks: bool


class SERPNORMALIZED(TypedDict):
    # Core context
    query: str
    engine: str

    # Cleaned organic results
    normalize_results: List[NormalizedOrganicResult]

    related_topics: List[str]
    questions: List[str]

    # SERP statistics
    stats: Dict[str, int]

    # Competition & authority signals
    domains: List[str]
    domain_stats: Dict[str, Any]

    # Freshness / recency signals
    freshness: Dict[str, Any]

    # SERP feature flags
    features: Dict[str, bool]


# =========================
# COMPETITOR STATE
# =========================
class Competitor(TypedDict):
    domain: str
    top_positions: List[int]
    total_occurrences: int
    has_sitelinks: bool
    intent_distribution: Dict[str, int]
    freshness: Dict[str, int]
    avg_snippet_length: float
    featured_snippet: bool
    is_brand: bool



# =========================
# SERP PAYLOAD
# =========================
class SERPPAYLOAD(TypedDict, total=False):
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    query: str
    country: SUPPORTED_COUNTRIES


# =========================
# SCRAPING STATE
# =========================
class DocumentScrapeData(TypedDict):
    document: Document
    content_length: int
    keywords: List[str]
    headings: List[str]

class ScrapeContext(TypedDict, total=False):
    documents: List[DocumentScrapeData]
    total_documents: int


from langgraph.graph.message import add_messages

# =========================
# ROOT WORKFLOW STATE
# =========================
class REXT(TypedDict, total=False):
    # SERP
    serp_payload: Annotated[SERPPAYLOAD, merge_dicts]
    serp_result: Annotated[SERPEngineState, merge_dicts]
    serp_normalized: Annotated[SERPNORMALIZED, merge_dicts]
    serp_backlinks: Annotated[SERPBacklinks, merge_dicts]

    # Competition
    competitors: List[Competitor]

    # Content & Scraping
    scrape_context: Annotated[ScrapeContext, merge_dicts]
    relevant_context: List[Document]

    # SEO Output
    seo_result: Annotated[SEORESULT, merge_dicts]

    # Content Output
    content: Annotated[CONTENT, deep_merge_dicts]
