"""Scores and tiers candidate competitor domains from aggregated SERP data."""
import logging

from langchain_core.messages import SystemMessage, HumanMessage

from src.flow.model.llm_manager import load_competitor_discovery_model
from src.flow.model.structure.competitor_discovery import CompetitorClassification
from src.utils.helper import web_page_scraper

logger = logging.getLogger(__name__)

KNOWN_AGGREGATORS = {
    "g2.com", "capterra.com", "trustpilot.com", "clutch.co", "getapp.com",
    "softwareadvice.com", "producthunt.com", "reddit.com", "quora.com",
    "wikipedia.org", "youtube.com", "linkedin.com", "medium.com",
    "forbes.com", "techcrunch.com", "businessinsider.com", "gartner.com",
}

CLASSIFY_SYSTEM_PROMPT = """You are comparing two businesses to score how similar they are as competitors.

First check: is the candidate a manufacturer, brand, or supplier whose products the customer
business resells/distributes (rather than a rival seller)? If the customer's own site content
mentions the candidate's brand name as a product line they carry, this is very likely a
supplier relationship, not competition — even if the topic overlap looks high.

Score the candidate against the customer business on these dimensions, each 0-100:
- topic_overlap: how much their subject matter / content focus overlaps
- audience_overlap: how much their target customer/buyer persona overlaps
- product_similarity: how similar their actual product/service offering is
- type: one of:
  - "business_competitor" (sells a similar product/service to the same end customers)
  - "content_competitor" (ranks for the same searches but is a publication, blog,
    directory, review site, marketplace, or aggregator)
  - "supplier_or_manufacturer" (makes/owns the brand of products the customer resells —
    not a rival seller, even if topic/product overlap is high)
"""


async def classify_domain(
    domain: str,
    snippet: str,
    business_summary: str,
    audience: str,
) -> CompetitorClassification:
    """Best-effort LLM classification; defaults to content_competitor/zero-overlap on failure."""
    default = CompetitorClassification(
        topic_overlap=0, audience_overlap=0, product_similarity=0, type="content_competitor"
    )
    if not snippet:
        return default

    try:
        model = load_competitor_discovery_model().with_structured_output(CompetitorClassification)
        human_content = (
            f"CUSTOMER BUSINESS:\nSummary: {business_summary}\nAudience: {audience}\n\n"
            f"CANDIDATE DOMAIN: {domain}\nHomepage/snippet content:\n---\n{snippet}\n---"
        )
        return await model.ainvoke([
            SystemMessage(content=CLASSIFY_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ])
    except Exception as exc:
        logger.warning("Competitor classification failed for %s: %s", domain, exc)
        return default


async def fetch_domain_snippet(domain: str, char_limit: int = 2500) -> str:
    """Best-effort homepage snippet for a candidate competitor domain."""
    for scheme in ("https", "http"):
        try:
            _, results = await web_page_scraper(urls=[f"{scheme}://{domain}"])
            first_success = next((r for r in results or [] if getattr(r, "success", False)), None)
            if first_success:
                return (getattr(first_success, "markdown", "") or "")[:char_limit]
        except Exception as exc:
            logger.warning("Snippet crawl failed for %s (%s): %s", domain, scheme, exc)
    return ""


def _tier_for_score(score: float) -> str:
    if score >= 65:
        return "Direct competitor"
    if score >= 50:
        return "Strong competitor"
    if score >= 35:
        return "Indirect competitor"
    return "Related website"


async def score_domain(
    domain: str,
    entry: dict,
    snippet: str,
    business_summary: str,
    audience: str,
    max_serp_appearances: int,
) -> dict:
    keyword_overlap = entry["keyword_overlap_pct"]
    serp_overlap = round(100 * entry["serp_appearances"] / max_serp_appearances, 1) if max_serp_appearances else 0

    classification = await classify_domain(domain, snippet, business_summary, audience)
    topic_overlap = classification.topic_overlap
    audience_overlap = classification.audience_overlap
    product_similarity = classification.product_similarity
    comp_type = classification.type

    if domain in KNOWN_AGGREGATORS:
        comp_type = "content_competitor"

    competitor_score = round(
        keyword_overlap * 0.25
        + serp_overlap * 0.15
        + topic_overlap * 0.30
        + audience_overlap * 0.20
        + product_similarity * 0.10,
        1,
    )

    return {
        "domain": domain,
        "competitor_score": competitor_score,
        "tier": _tier_for_score(competitor_score),
        "competitor_type": comp_type,
        "signals": {
            "keyword_overlap_pct": keyword_overlap,
            "serp_overlap_pct": serp_overlap,
            "topic_overlap": topic_overlap,
            "audience_overlap": audience_overlap,
            "product_similarity": product_similarity,
        },
        "serp_appearances": entry["serp_appearances"],
        "keywords_matched": entry["keywords_matched"],
        "sample_urls": entry["sample_urls"],
    }
