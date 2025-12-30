from typing import List, Dict, Any, Optional
from typing_extensions import TypedDict
from langchain_core.documents import Document
from src.flow.states.countries import SUPPORTED_COUNTRIES
from src.flow.states.seo_state import SEORESULT

class SERPEngineState(TypedDict, total=False):
    # Input
    search_params: dict

    # Extracted SERP components
    organic_results: List[Dict[str, Any]]
    related_searches: List[str]
    people_ask: List[Dict[str, Any]]

    # SERP metadata
    search_information: Dict[str, Any]

    # SERP analysis
    total_results: int



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

    # Intent & semantic expansion
    intent: Optional[Dict[str, Any]]
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


class Competitor(TypedDict):
    domain: str
    top_positions: List[int]
    total_occurrences: int
    has_sitelinks: bool
    intent_distribution: Dict[str, int]
    freshness: Dict[str, int]
    avg_snippet_length: float
    featured_snippet: bool

class SERPPAYLOAD(TypedDict, total=False):
    query: str
    country: SUPPORTED_COUNTRIES

class WREXT(TypedDict, total=False):
  serp_payload: SERPPAYLOAD
  serp_result: SERPEngineState

  # Normalized output (used by SEO + AI agents)
  serp_normalized: SERPNORMALIZED

  competitors: List[Competitor]

  scrape_context: List[Document]
  relevant_context: List[Document]

  seo_result: SEORESULT