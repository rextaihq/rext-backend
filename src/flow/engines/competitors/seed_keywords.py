"""Generates SERP-search seed keywords for competitor discovery from scraped site content."""
import logging

from langchain_core.messages import SystemMessage, HumanMessage

from src.flow.model.llm_manager import load_competitor_discovery_model
from src.flow.model.structure.competitor_discovery import SeedKeywordsOutput

logger = logging.getLogger(__name__)

SEED_KEYWORD_SYSTEM_PROMPT = """You are an expert SEO strategist and competitor-research specialist.

You will receive raw content extracted from a company's website. Your goal is to generate
SEED KEYWORDS for SERP-based competitor discovery: each keyword will be searched on Google,
and domains that repeat across results for MULTIPLE keywords will be flagged as competitors.

CRITICAL: Only generate phrases that are REAL, commonly-searched Google queries — the kind
with actual monthly search volume. Do NOT invent novel combinations of service-category
words that sound plausible but nobody actually searches (e.g. "wordpress architecture
engineering", "wordpress security and risk management" are NOT real search terms — a buyer
would search "wordpress security services" or "wordpress developer" instead).

Test each keyword against this question: "Would this phrase show up in Google Keyword
Planner or Ahrefs with non-trivial search volume?" If you're not confident it would, use a
more standard/common phrasing instead, even if it feels less descriptive of the exact niche.

Ignore: headers, footers, navigation, cookie banners, contact info, testimonials (unless
naming a distinct service), blog titles, careers content, and the company's own brand name.

Generate 15 TOTAL keywords (1 primary + 14 secondary). Since only a handful will end up
being real high-volume searches, generate a WIDE spread across phrasing styles so enough
survive a search-volume filter: standard category terms, "[service] agency/company/services",
"hire [role]", "[service] for [audience]", "best [service]", "[service] near me" (only if
the business is local), and close synonyms of the core offering.

Then output:
1. "primary_keyword": the ONE 2-4 word phrase that is the standard, commonly-searched term
   for this business's core category. Not the brand name.
2. "secondary_keywords": exactly 9 other REAL, standard commercial search phrases covering
   the breadth described above. Avoid compound jargon phrases combining two abstract nouns.
   Avoid near-duplicates of each other.
3. "business_summary": one sentence describing what the company sells and to whom.
4. "audience": one short phrase describing the target customer/buyer persona.
"""


async def generate_seed_keywords(content: str) -> SeedKeywordsOutput:
    """Generate seed keywords + business summary/audience from scraped site content."""
    model = load_competitor_discovery_model().with_structured_output(SeedKeywordsOutput)
    messages = [
        SystemMessage(content=SEED_KEYWORD_SYSTEM_PROMPT),
        HumanMessage(content=f"WEBSITE CONTENT:\n---\n{content}\n---"),
    ]
    return await model.ainvoke(messages)
