"""Current, official facts about the products an article names — every content type.

Why this exists
---------------
Product facts reached articles from three unreliable places: the outline (written
with no search tool, so from training data), the writer's open web searches
(whatever ranked — review sites and price trackers that keep old plan tables), and
the brand's onboarding About text (a one-off summary that never records things like
a release status). Nothing looked at the products' own websites, and nothing looked
up the promoted brand at all — which is how an article shipped an outdated
competitor price list and presented an alpha product as a finished one.

What it does
------------
Before the writer runs, the promoted brand and every product the approved outline
names are looked up on their OWN domains: the approved brand URL and the
workspace's stored competitor domains. A product without a known official domain is
not researched — nothing unofficial is passed off as official.

Budget
------
Research spends Tavily calls from the SAME per-article search budget as the
writer's `search_tool` (SEARCH_HARD_CAP, enforced by ToolCapMiddleware on the
shared counter): one call per product, restricted to that product's domain, the
brand first. A single call across several domains lets one vendor's pages crowd
out the others, so products are not batched. Research never takes the calls the
writer needs for its required queries (WRITER_RESERVED_CALLS); products past the
research budget are left to the writer's own product query.

Each result keeps Tavily's query-relevant passage for that page (a plan table, a
release note) at the same per-result context size `search_tool` uses. The records
go to the writer as a dated block and into `generation_meta.searched_results`, the
ground truth citation checks, claim checks and repair already read.

Every step soft-fails: a research failure leaves generation exactly as it was.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from langchain_tavily import TavilySearch

from src.flow.engines.agent.tools.tools import SEARCH_HARD_CAP
from src.flow.engines.content.generation.claim_integrity import outline_entity_names

logger = logging.getLogger(__name__)

# The writer's system prompt requires three searches of its own (queries A-C).
WRITER_RESERVED_CALLS = 3
RESULTS_PER_PRODUCT = 3
# Same per-result context the writer's search_tool passes.
EVIDENCE_TEXT_MAX_CHARS = 2000
RESEARCH_TIMEOUT_SECONDS = 45

# What goes stale about a product.
FACT_QUERY = "current pricing plans, release status and key features"

# Subdomains that host user posts rather than the vendor's own statements.
_COMMUNITY_SUBDOMAINS = ("forum.", "forums.", "community.", "discuss.", "discourse.")


@dataclass(frozen=True)
class ResearchTarget:
    name: str
    domain: str
    is_brand: bool = False


# ── targets ─────────────────────────────────────────────────────────────────


def host_of(url_or_domain: str) -> str:
    """'https://www.builder.io/pricing' -> 'builder.io'."""
    host = re.sub(r"^[a-z]+://", "", (url_or_domain or "").strip().lower())
    host = host.split("/", 1)[0].split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host


def domain_matches(domain: str, name: str) -> bool:
    """True when `domain` is plausibly `name`'s own site (builder.io for Builder.io,
    payloadcms.com for Payload CMS, webflow.com for Webflow CMS)."""
    compact_host = re.sub(r"[^a-z0-9]", "", host_of(domain))
    words = re.findall(r"[a-z0-9]+", (name or "").lower())
    if not compact_host or not words:
        return False
    return "".join(words) in compact_host or (len(words[0]) >= 4 and words[0] in compact_host)


def resolve_targets(
    outline: Optional[dict],
    brand_context: Optional[dict],
    competitor_domains: Iterable[str] = (),
) -> list[ResearchTarget]:
    """The brand first, then every named product whose official domain is known.

    Uses the same entity list claim validation grades against, so what is
    researched and what is checked cannot diverge.
    """
    brand = brand_context or {}
    brand_name = (brand.get("brand_name") or "").strip()
    known_domains = [host_of(d) for d in competitor_domains if isinstance(d, str) and d.strip()]

    targets: list[ResearchTarget] = []
    brand_domain = host_of(brand.get("brand_url") or "")
    if brand_name and brand_domain:
        targets.append(ResearchTarget(brand_name, brand_domain, True))
    for name in outline_entity_names(outline, brand_name):
        domain = next((d for d in known_domains if domain_matches(d, name)), "")
        if domain:
            targets.append(ResearchTarget(name, domain))
    return targets


def _target_for(url: str, targets: list[ResearchTarget]) -> Optional[ResearchTarget]:
    """The product whose official, vendor-published page `url` is."""
    host = host_of(url)
    if host.startswith(_COMMUNITY_SUBDOMAINS):
        return None
    return next(
        (t for t in targets if host == t.domain or host.endswith(f".{t.domain}")),
        None,
    )


# ── research ────────────────────────────────────────────────────────────────


def _evidence_record(result: dict, target: ResearchTarget, retrieved: str) -> Optional[dict]:
    snippet = (result.get("content") or "").strip()[:EVIDENCE_TEXT_MAX_CHARS]
    if not snippet:
        return None
    record = {
        "url": result["url"],
        "title": result.get("title") or "",
        "snippet": snippet,
        "retrieved_at": retrieved,
        "entity": target.name,
        "official_domain": target.domain,
        "is_brand": target.is_brand,
    }
    if result.get("published_date"):
        record["published_date"] = str(result["published_date"])
    return record


async def _search_official(target: ResearchTarget) -> list[dict]:
    search = TavilySearch(
        max_results=RESULTS_PER_PRODUCT,
        search_depth="advanced",
        include_domains=[target.domain],
    )
    response = await search.ainvoke(f"{target.name} {FACT_QUERY}")
    results = response.get("results", []) if isinstance(response, dict) else []
    return [r for r in results if isinstance(r, dict) and r.get("url")]


async def research_official_facts(
    outline: Optional[dict],
    brand_context: Optional[dict],
    competitor_domains: Iterable[str],
    search_count: list[int],
) -> list[dict]:
    """Official-source evidence records for every product the article is about.

    `search_count` is the writer's shared search counter; every call made here is
    added to it before it runs, and no call is made past SEARCH_HARD_CAP. Never
    raises: any failure returns what was gathered, possibly nothing.
    """
    budget = SEARCH_HARD_CAP - WRITER_RESERVED_CALLS - search_count[0]
    targets = resolve_targets(outline, brand_context, competitor_domains)[: max(0, budget)]
    if not targets:
        return []
    search_count[0] += len(targets)

    try:
        batches = await asyncio.wait_for(
            asyncio.gather(*(_search_official(t) for t in targets), return_exceptions=True),
            timeout=RESEARCH_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.warning("[EntityResearch] research timed out; continuing without it.")
        return []

    retrieved = datetime.now(timezone.utc).date().isoformat()
    records: dict[str, dict] = {}
    for target, batch in zip(targets, batches):
        if isinstance(batch, BaseException):
            logger.warning("[EntityResearch] %r failed (non-fatal): %s", target.name, batch)
            continue
        for result in batch:
            if _target_for(result["url"], [target]):
                record = _evidence_record(result, target, retrieved)
                if record:
                    records.setdefault(record["url"], record)

    logger.info(
        "[EntityResearch] %d official record(s) for %s using %d search call(s)",
        len(records),
        [t.name for t in targets],
        len(targets),
    )
    return list(records.values())


def format_official_facts_for_prompt(records: list[dict]) -> str:
    """The writer-facing block. How to use it is stated once, in
    FACTUAL_INTEGRITY_RULES; this only labels the evidence and its provenance."""
    if not records:
        return ""
    lines = [
        "========================",
        "VERIFIED CURRENT PRODUCT FACTS — OFFICIAL SOURCES "
        f"(retrieved {records[0]['retrieved_at']})",
        "========================",
        "Passages retrieved just now from each product's own website. For the products below "
        "they are the authority on pricing, plans, billing terms, features, integrations, "
        "requirements and release status — see FACTUAL INTEGRITY. Cite these URLs when you use "
        "a fact from them.",
        "",
    ]
    number = 1
    for entity in dict.fromkeys(r["entity"] for r in records):
        entity_records = [r for r in records if r["entity"] == entity]
        first = entity_records[0]
        role = " — the brand being promoted" if first["is_brand"] else ""
        lines.append(f"## {entity} (official site: {first['official_domain']}){role}")
        for record in entity_records:
            lines.append(f"[{number}] URL: {record['url']}")
            if record.get("published_date"):
                lines.append(f"    PUBLISHED: {record['published_date']}")
            lines.append(f"    TITLE: {record['title']}")
            lines.append(f"    CONTENT:\n{record['snippet']}")
            lines.append("")
            number += 1
    return "\n".join(lines) + "\n"
