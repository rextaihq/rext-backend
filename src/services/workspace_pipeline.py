from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select

from src.api.models.knowledge_models.knowledge_model import BrandVoice
from src.api.schema.knowledge_schema import BrandSchema
from src.flow.engines.competitors.pipeline import discover_competitors, select_display_competitors
from src.flow.model.llm_manager import load_model
from src.services.sse_service import (
    emit_pipeline_complete,
    emit_step_failure,
    emit_step_start,
    emit_step_success,
)
from src.api.models.knowledge_models.persona_model import Persona

from src.utils.helper import web_page_scraper
from src.utils.logger import logger
from src.utils.vector_store import add_to_vector_store

#site compliance import
from src.utils.site_compliance import assess_site_compliance

ScrapeCallable = Callable[[str], Awaitable[Tuple[List[Any], List[Any]]]]
VectorUploaderCallable = Callable[[Sequence[Any], str], Awaitable[bool]]
BrandVoiceGeneratorCallable = Callable[[str], Awaitable[Optional[BrandSchema]]]


@dataclass
class _ScrapeResult:
    """Container for scraped data reused across pipeline steps."""

    chunks: List[Any]
    content: str
    metadata: Dict[str, Any]


_ARCHETYPE_KEYWORDS = {
    "owner", "manager", "user", "customer", "client", "buyer", "blogger",
    "professional", "entrepreneur", "startup", "business", "store", "shop",
    "target", "audience", "segment", "persona", "marketer", "executive",
    "director", "officer", "employee", "worker", "freelancer", "consultant",
}


_NAME_TITLES = {"dr", "dr.", "mr", "mr.", "ms", "ms.", "mrs", "mrs.", "prof", "prof.",
                "sir", "miss", "mx", "mx."}


def _identity_key(name: str) -> str:
    """Collapse a name to the identity it refers to.

    The same person is routinely named more than one way on a site - a team page
    saying "Syed Balkhi" and an author box saying "Dr. Syed Balkhi" produced two
    personas for one human. Honorifics and punctuation carry no identity, so
    they are dropped before comparison.
    """
    words = re.sub(r"[^\w\s.]", " ", (name or "").lower()).split()
    words = [w for w in words if w not in _NAME_TITLES]
    return " ".join(words)


def _completeness(persona: dict) -> int:
    """How many fields a persona actually carries - used to pick which of two
    records for the same person to keep."""
    return sum(1 for v in persona.values() if v not in (None, "", [], {}))


def _dedupe_personas(personas: list[dict]) -> list[dict]:
    """One record per human, keeping whichever duplicate carries more detail."""
    best: dict[str, dict] = {}
    order: list[str] = []
    for persona in personas:
        key = _identity_key(persona.get("name") or "")
        if not key:
            continue
        if key not in best:
            best[key] = persona
            order.append(key)
        elif _completeness(persona) > _completeness(best[key]):
            best[key] = persona
    merged = [best[k] for k in order]
    if len(merged) < len(personas):
        logger.info("Merged duplicate personas",
                    extra={"before": len(personas), "after": len(merged)})
    return merged


# Language that marks someone as appearing AT the brand's event or ON its
# channel rather than working for it. pcisecuritystandards.org returned two
# conference keynote speakers as "experts" - Ken Hughes and CJ Meadows, both
# outside consultants booked for a community meeting.
_EXTERNAL_ROLE_PHRASES = (
    "keynote speaker", "keynote at", "guest speaker", "speaker at",
    "speaking at", "presenter at", "panelist", "panellist", "guest author",
    "guest post", "guest contributor", "interviewed", "featured guest",
    "podcast guest", "webinar guest", "ambassador", "spokesperson for",
)


# Collective names that are shaped like a person but are not one. The scraper
# already rejects these as bylines, but a collective can still reach the model
# through page prose - nextlyhq.com produced "Nextly Team" as an author - so the
# same rule has to hold at the filter.
_COLLECTIVE_SUFFIXES = (
    "team", "staff", "crew", "desk", "editors", "editorial", "group", "squad",
    "collective", "council", "committee", "board", "department", "dept",
    "support", "admins", "moderators", "contributors", "authors", "writers",
)
_COLLECTIVE_WORDS = {
    "team", "staff", "editorial", "admin", "administrator", "moderator",
    "support", "contributors", "authors", "writers", "everyone", "us",
}


def _is_collective(name: str) -> bool:
    """Whether a persona name refers to a group rather than an individual."""
    words = [w for w in re.sub(r"[^\w\s]", " ", (name or "").lower()).split() if w]
    if not words:
        return True
    if words[-1] in _COLLECTIVE_SUFFIXES:
        return True
    return any(w in _COLLECTIVE_WORDS for w in words)


def _looks_external(persona: dict) -> bool:
    """Whether the content places this person outside the organisation.

    Only applied to 'expert', which is the loophole: founders, team members and
    authors are asserted affiliations, while 'expert' is the label the model
    reaches for when someone is notable but unplaced. A staff member who also
    speaks at events keeps their team_member/author source and is unaffected.
    """
    if (persona.get("source") or "").strip().lower() != "expert":
        return False
    haystack = " ".join(str(persona.get(f) or "") for f in
                        ("description", "bio", "professional_title", "behaviors")).lower()
    return any(phrase in haystack for phrase in _EXTERNAL_ROLE_PHRASES)


def _filter_valid_personas(personas: list[dict]) -> list[dict]:
    """Return only personas that appear to be real named individuals.

    Rejects entries whose name is a role/archetype (e.g. "Online Store Owner")
    rather than an actual human name (e.g. "John Smith").
    """
    valid = []
    rejected = []
    for p in personas:
        name: str = (p.get("name") or "").strip()
        if not name:
            rejected.append({"name": "(empty)", "reason": "missing name"})
            continue
        source: str = (p.get("source") or "").strip().lower()
        if source == "testimonial":
            rejected.append({"name": name, "reason": "testimonial-only source"})
            continue
        if _looks_external(p):
            rejected.append({"name": name, "reason": "external speaker/guest, not staff"})
            continue
        if _is_collective(name):
            rejected.append({"name": name, "reason": "collective, not an individual"})
            continue
        words = name.lower().split()
        if any(w in _ARCHETYPE_KEYWORDS for w in words):
            rejected.append({"name": name, "reason": "archetype keyword"})
            continue
        title_prefixes = {"dr.", "dr", "mr.", "mr", "ms.", "ms", "mrs.", "prof.", "prof"}
        has_title = words[0] in title_prefixes
        if len(words) < 2 and not has_title:
            rejected.append({"name": name, "reason": "single word / no title"})
            continue
        valid.append(p)

    if rejected:
        logger.info(
            "Filtered out invalid personas",
            extra={"rejected": rejected, "valid_count": len(valid)},
        )
    if not valid:
        logger.info("No valid personas found — no real named individuals identified on site")

    return _dedupe_personas(valid)


class WorkspacePipeline:
    """Background pipeline responsible for workspace onboarding tasks."""

    # Head + tail budget for the brand-voice/persona extraction prompt.
    # Landing pages routinely put the founder/team "Built by ..." credit in
    # the footer — the very end of the scraped markdown — while marketing
    # copy (hero, features, testimonials) fills the middle. A flat head-only
    # slice reliably drops that credit on any page longer than the budget.
    # Confirmed on nextlyhq.com: "Built by Mobeen Abdullah at Revnix" sits at
    # char ~10,800 of a 10,816-char page — the old flat 5,000-char head slice
    # discarded it entirely, so the LLM never saw the one real person on the
    # page and correctly (per its own rules) returned an empty persona list.
    # Sampling both ends keeps the prompt bounded while guaranteeing the
    # footer is never lost.
    _HEAD_CHARS = 8_000
    _TAIL_CHARS = 4_000

    def __init__(
        self,
        *,
        db: AsyncSession,
        operation_id: str,
        workspace_id: UUID,
        user_id: UUID,
        url: str,
        scraper: Optional[ScrapeCallable] = None,
        vector_uploader: Optional[VectorUploaderCallable] = None,
        brand_voice_generator: Optional[BrandVoiceGeneratorCallable] = None,
    ) -> None:
        self.db = db
        self.operation_id = operation_id
        self.workspace_id = workspace_id
        self.url = url
        self.user_id = user_id
        self._scraper = scraper or self._default_scraper
        self._vector_uploader = vector_uploader or self._default_vector_uploader
        self._brand_voice_generator = (
            brand_voice_generator or self._default_brand_voice_generator
        )
        self.scope = "workspace"

    async def run(self) -> None:
        """Execute the workspace pipeline and stream progress via SSE."""
        logger.info(
            "Workspace pipeline started",
            extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id},
        )
        brand_voice_schema: Optional[BrandSchema] = None
        discovered_competitors: Optional[List[dict]] = None

        try:
            scrape_result = await self._scrape_website()
            await self._create_vector_embeddings(scrape_result.chunks)
            brand_voice_schema = await self._extract_brand_voice(scrape_result.content)
            await self._persist_brand_voice(brand_voice_schema)
            await self._embed_brand_voice(brand_voice_schema)

            # Runs strictly after the brand-voice flow above completes, as a fully
            # independent step — not concurrent with it — so it can never affect
            # brand-voice extraction's behavior, timing, or SSE step reporting.
            discovered_competitors = await self._discover_competitors()
            if discovered_competitors is not None:
                await self._persist_competitors([c["domain"] for c in discovered_competitors])

            payload: Dict[str, Any] = {"workspace_id": str(self.workspace_id)}
            if brand_voice_schema:
                payload["brand_voice"] = brand_voice_schema.model_dump()
            if discovered_competitors is not None:
                competitor_domains = [c["domain"] for c in discovered_competitors]
                if "brand_voice" in payload:
                    payload["brand_voice"]["competitors"] = competitor_domains
                else:
                    payload["brand_voice"] = {"competitors": competitor_domains}
                # Keep top_competitors for backward compatibility if needed
                payload["top_competitors"] = discovered_competitors

            await emit_pipeline_complete(
                operation_id=self.operation_id,
                scope=self.scope,
                message="Workspace creation pipeline completed successfully",
                payload=payload,
                user_id=self.user_id,
            )
            logger.info(
                "Workspace pipeline completed",
                extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id},
            )

        except Exception as exc:  # noqa: BLE001 - propagate for caller logging
            logger.error(
                "Workspace pipeline failed",
                extra={
                    "workspace_id": str(self.workspace_id),
                    "operation_id": self.operation_id,
                    "error": str(exc),
                },
            )
            await emit_step_failure(
                operation_id=self.operation_id,
                scope=self.scope,
                step="pipeline",
                message="Workspace creation pipeline failed",
                error=str(exc),
                user_id=self.user_id,
            )
            raise

    async def _scrape_website(self) -> _ScrapeResult:
        """Scrape the target URL and emit relevant SSE events.

        Tries the fast, browser-free scraper first (homepage + about/product
        pages + recent blog/news posts — typically 2-5s, no headless browser).
        Falls back to crawl4ai (self._scraper, the original browser-based
        path) only if the fast scrape comes back too thin — e.g. a
        client-rendered SPA with no server-side rendering, where a plain HTTP
        GET sees little or no real content. See _looks_blocked in
        src/utils/helper.py for the thinness heuristic.
        """
        logger.info(
            "Starting to scrape URL",
            extra={
                "workspace_id": str(self.workspace_id),
                "operation_id": self.operation_id,
                "url": self.url,
            },
        )

        await emit_step_start(
            operation_id=self.operation_id,
            scope=self.scope,
            step="scrape",
            message=f"Scraping website: {self.url}",
            progress=10,
            user_id=self.user_id,
        )

        try:
            content, raw_html, used_fallback = await self._fast_or_fallback_scrape()
        except Exception as exc:  # noqa: BLE001 - surface to pipeline
            await emit_step_failure(
                operation_id=self.operation_id,
                scope=self.scope,
                step="scrape",
                message=f"Failed to scrape website: {exc}",
                error=str(exc),
                user_id=self.user_id,
            )
            raise

        title = None
        if raw_html:
            try:
                from bs4 import BeautifulSoup
                title_tag = BeautifulSoup(raw_html, "html.parser").title
                title = title_tag.get_text(strip=True) if title_tag else None
            except Exception:  # noqa: BLE001 - cosmetic metadata only
                title = None

        compliance = await assess_site_compliance(self.url, raw_html)
        self._site_compliance = compliance                   #site compliance
        metadata = {
            "url": self.url,
            "title": title,
            "word_count": len(content.split()),
            "char_count": len(content),
            "compliance": compliance,
            "scrape_method": "crawl4ai_fallback" if used_fallback else "fast",
        }

        await emit_step_success(
            operation_id=self.operation_id,
            scope=self.scope,
            step="scrape",
            message="Website scraped successfully",
            payload=metadata,
            progress=30,
            user_id=self.user_id,
        )

        return _ScrapeResult(
            chunks=[],
            content=content,
            metadata=metadata,
        )

    async def _fast_or_fallback_scrape(self) -> Tuple[str, str, bool]:
        """Returns (content, raw_home_html, used_crawl4ai_fallback)."""
        from src.utils.fast_scraper import (ABOUT_KEYWORDS, DEFAULT_BUDGET_SECONDS,
                                            TEAM_KEYWORDS)
        from src.utils.fast_scraper import scrape_site as fast_scrape_site
        from src.utils.helper import _looks_blocked

        try:
            result = await fast_scrape_site(
                self.url,
                max_about_pages=4,
                about_keywords=ABOUT_KEYWORDS + TEAM_KEYWORDS,
                home_max_chars=6_000,
                about_max_chars=4_000,
                # A leadership page carries the entire executive team in one
                # document; 4k truncates it and loses everyone below the cut.
                team_max_chars=12_000,
                # Trimmed from 30 to pay for the author- and team-profile fetches added
                # alongside it. A profile page yields a full bio, role and
                # expertise for one named person; a post yields only a byline,
                # so the same request budget now returns markedly more detail.
                max_blog_posts=20,
                blog_index_max_chars=1_500,
                blog_post_max_chars=1_500,
                strip_footer=False,
                sample_head_and_tail=True,
                # Team/leadership pages outrank product pages for the limited
                # about-page budget: they are the densest source of real personas,
                # and in DOM order a nav bar of feature links always beats them.
                priority_keywords=TEAM_KEYWORDS,
                # Customer testimonials name real people with real titles, so
                # every name-shape filter downstream passes them. Remove the
                # blocks outright rather than asking the model to ignore them.
                strip_testimonials=True,
                # Hard ceiling so pipeline latency is ours to choose rather than
                # the slowest origin's. Whatever is gathered by then is used.
                budget_seconds=DEFAULT_BUDGET_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 - fall through to crawl4ai below
            logger.warning(
                "Fast scrape raised, falling back to crawl4ai",
                extra={
                    "workspace_id": str(self.workspace_id),
                    "operation_id": self.operation_id,
                    "url": self.url,
                    "error": str(exc),
                },
            )
            result = {"pages": {}, "raw_home_html": ""}

        pages = result.get("pages") or {}
        # visible_text() strips attributes, so social profile URLs only exist in
        # the raw markup. Held for the persona social-link pass further down.
        self._raw_pages = result.get("raw_pages") or {}
        # Split for the two-pass extraction: a leadership page and a dozen blog
        # posts compete inside one prompt, and the leadership page loses -
        # pcisecuritystandards.org returned 11 executives with no posts in the
        # prompt and 6 with twelve. Each pass now sees only its own evidence.
        from src.utils.fast_scraper import (classify_page, PAGE_ARTICLE,
                                             PAGE_TEAM)
        kind = {u: classify_page(u, t) for u, t in pages.items()}
        # Routing is decided here, in code, not left to the prompt: blog, news
        # and article pages are the only source of authors, and team, about and
        # leadership pages the only source of team members. Whatever URL a
        # workspace is created with, each pass sees only evidence of its own
        # kind.
        self._author_text = "\n\n".join(
            f"URL: {u}\n{t}" for u, t in pages.items()
            if kind[u] == PAGE_ARTICLE)
        self._team_text = "\n\n".join(
            f"URL: {u}\n{t}" for u, t in pages.items()
            if kind[u] != PAGE_ARTICLE)
        # A leadership page needs a prompt of its own. Inside the 25k-char team
        # prompt, pcisecuritystandards.org's page listing eleven executives
        # yielded six - and the six returned were the ones repeated on other
        # pages, while the five regional heads, named once each, were dropped.
        # Alone, the page is the only thing to read and nothing outranks it.
        self._leadership_text = "\n\n".join(
            f"URL: {u}\n{t}" for u, t in pages.items() if kind[u] == PAGE_TEAM)
        logger.info("page routing", extra={
            "team_pages": sum(1 for k in kind.values() if k == PAGE_TEAM),
            "article_pages": sum(1 for k in kind.values() if k == PAGE_ARTICLE),
            "other_pages": sum(1 for k in kind.values() if k not in (PAGE_TEAM, PAGE_ARTICLE))})
        combined = "\n\n".join(f"URL: {u}\n{txt}" for u, txt in pages.items())

        if not combined.strip() or _looks_blocked(combined):
            logger.info(
                "Fast scrape too thin, falling back to crawl4ai",
                extra={
                    "workspace_id": str(self.workspace_id),
                    "operation_id": self.operation_id,
                    "url": self.url,
                    "fast_scrape_chars": len(combined),
                },
            )
            chunks, results = await self._scraper(self.url)
            first_success = next(
                (r for r in results or [] if getattr(r, "success", False)), None,
            )
            content = getattr(first_success, "markdown", "") if first_success else ""
            raw_html = getattr(first_success, "html", "") if first_success else ""
            content = self._sample_content_for_extraction(content)
            return content, raw_html, True

        return combined, result.get("raw_home_html") or "", False

    async def _create_vector_embeddings(self, chunks: Sequence[Any]) -> None:
        """Create vector embeddings for scraped chunks."""
        if not chunks:
            logger.info(
                "Skipping vector store insertion - no chunks available",
                extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id},
            )
            return

        # ============================================================================
        # VECTOR STORE DISABLED (COMMENTED OUT)
        # To re-enable: uncomment the code block below
        # ============================================================================
        
        logger.info(
            "Vector store disabled, skipping chunks",
            extra={
                "workspace_id": str(self.workspace_id),
                "operation_id": self.operation_id,
                "chunk_count": len(chunks),
            },
        )
        
        # Original code commented out below:
        # await emit_step_start(
        #     operation_id=self.operation_id,
        #     scope=self.scope,
        #     step="vector_store",
        #     message="Generating vector embeddings",
        #     progress=40,
        # )

        # try:
        #     success = await self._vector_uploader(chunks, str(self.workspace_id))
        # except Exception as exc:  # noqa: BLE001 - propagate
        #     await emit_step_failure(
        #         operation_id=self.operation_id,
        #         scope=self.scope,
        #         step="vector_store",
        #         message=f"Failed to create embeddings: {exc}",
        #         error=str(exc),
        #     )
        #     raise

        # if not success:
        #     error_message = "Vector store reported failure"
        #     await emit_step_failure(
        #         operation_id=self.operation_id,
        #         scope=self.scope,
        #         step="vector_store",
        #         message=error_message,
        #         error=error_message,
        #     )
        #     raise RuntimeError(error_message)

        # payload = {"chunks": len(chunks)}
        # await emit_step_success(
        #     operation_id=self.operation_id,
        #     scope=self.scope,
        #     step="vector_store",
        #     message="Vector embeddings created",
        #     payload=payload,
        #     progress=60,
        # )

    async def _extract_brand_voice(
        self,
        content: str,
    ) -> Optional[BrandSchema]:
        """Generate brand voice insights from scraped content.

        `content` arrives already budgeted by `_scrape_website` — either the
        fast scraper's per-page-capped multi-page combine, or (on the
        crawl4ai fallback path) `_sample_content_for_extraction`'s head+tail
        sample of the single scraped page. No further trimming needed here.
        """
        await emit_step_start(
            operation_id=self.operation_id,
            scope=self.scope,
            step="brand_voice",
            message="Analyzing brand voice",
            progress=70,
            user_id=self.user_id,
        )

        if not content.strip():
            await emit_step_success(
                operation_id=self.operation_id,
                scope=self.scope,
                step="brand_voice",
                message="No content available for brand voice extraction",
                payload=None,
                progress=90,
                user_id=self.user_id,
            )
            return None

        trimmed_content = content

        logger.info(
            "Scraped content prepared for brand voice extraction",
            extra={
                "workspace_id": str(self.workspace_id),
                "operation_id": self.operation_id,
                "original_length": len(content),
                "trimmed_length": len(trimmed_content),
            },
        )
        logger.debug(
            "Scraped content for LLM analysis",
            extra={
                "workspace_id": str(self.workspace_id),
                "operation_id": self.operation_id,
                "content_preview": trimmed_content[:500],
                "content_length": len(trimmed_content),
            },
        )


        try:
            brand_voice_schema = await self._brand_voice_generator(trimmed_content)
        except Exception as exc:  # noqa: BLE001 - surface to pipeline
            await emit_step_failure(
                operation_id=self.operation_id,
                scope=self.scope,
                step="brand_voice",
                message=f"Failed to extract brand voice: {exc}",
                error=str(exc),
                user_id=self.user_id,
            )
            raise

        if brand_voice_schema is None:
            await emit_step_success(
                operation_id=self.operation_id,
                scope=self.scope,
                step="brand_voice",
                message="Brand voice extraction returned no data",
                payload=None,
                progress=90,
                user_id=self.user_id,
            )
            return None

        await emit_step_success(
            operation_id=self.operation_id,
            scope=self.scope,
            step="brand_voice",
            message="Brand voice extracted successfully",
            payload=brand_voice_schema.model_dump(),
            progress=90,
            user_id=self.user_id,
        )
        return brand_voice_schema

    async def _discover_competitors(self) -> Optional[List[dict]]:
        """Run SERP-based competitor discovery, independently of brand-voice extraction.

        Non-fatal: any failure is logged and reported via SSE but does not fail
        the overall workspace pipeline. Returns None (as opposed to an empty
        list) on failure so the caller knows to leave any existing stored
        competitors untouched rather than overwriting them with nothing.

        Returns the raw list of classified-competitor dicts (each with at
        least a "domain" key) — the shape the workspace-create wizard's SSE
        handler already expects under the "top_competitors" payload key
        (rext-admin/components/workspace/workspace-create-wizard.tsx), so no
        frontend change is required.
        """
        await emit_step_start(
            operation_id=self.operation_id,
            scope=self.scope,
            step="competitor_discovery",
            message="Discovering competitors via search data",
            progress=92,
            user_id=self.user_id,
        )

        try:
            analysis = await discover_competitors(site_url=self.url)
        except Exception as exc:  # noqa: BLE001 - non-fatal to the overall pipeline
            logger.error(
                "Competitor discovery failed",
                extra={
                    "workspace_id": str(self.workspace_id),
                    "operation_id": self.operation_id,
                    "error": str(exc),
                },
                exc_info=True,
            )
            await emit_step_failure(
                operation_id=self.operation_id,
                scope=self.scope,
                step="competitor_discovery",
                message=f"Competitor discovery failed: {exc}",
                error=str(exc),
                user_id=self.user_id,
            )
            return None

        competitors = select_display_competitors(analysis.get("competitors", []))

        await emit_step_success(
            operation_id=self.operation_id,
            scope=self.scope,
            step="competitor_discovery",
            message="Competitor discovery completed",
            payload={"competitors": [c["domain"] for c in competitors]},
            progress=98,
            user_id=self.user_id,
        )
        return competitors

    def _sample_content_for_extraction(self, content: str) -> str:
        """Sample the scraped page for the brand-voice/persona extraction prompt.

        Takes the head (hero/intro/features — brand voice signal) AND the
        tail (footer — where founder/"Built by"/author credits usually live)
        instead of a single flat head-slice, so long landing pages don't
        silently drop the one line that names a real person. See
        ``_HEAD_CHARS``/``_TAIL_CHARS`` for why this exists.
        """
        total_budget = self._HEAD_CHARS + self._TAIL_CHARS
        if len(content) <= total_budget:
            return content
        head = content[: self._HEAD_CHARS]
        tail = content[-self._TAIL_CHARS:]
        return f"{head}\n\n...[middle of page omitted]...\n\n{tail}"

    async def _persist_brand_voice(
        self,
        brand_voice_schema: Optional[BrandSchema],
    ) -> Optional[BrandVoice]:
        """Persist brand voice data and extract personas to separate table.

        Does not touch `.competitors` — that field is owned exclusively by
        `_persist_competitors`, run as an independent step (see `run()`).
        """
        if brand_voice_schema is None:
            return None

        data = brand_voice_schema.model_dump()

        # Extract personas before processing brand voice
        raw_personas = data.pop("personas", [])
        raw_personas.extend(getattr(self, "_author_personas", []) or [])
        personas_data = _filter_valid_personas(raw_personas)
        self._attach_social_links(personas_data)

        try:
            result = await self.db.execute(
                select(BrandVoice).where(BrandVoice.workspace_id == self.workspace_id)
            )
            existing = result.scalar_one_or_none() if result else None

            if existing:
                # Preserve a manually-entered brand name if this extraction pass
                # couldn't find one on the site — don't let a refresh null it out.
                existing.brand_name = data.get("brand_name") or existing.brand_name
                existing.about = data.get("about")
                existing.customer_profile = data.get("customer_profile")
                existing.selling_position = data.get("selling_position")
                existing.target_audience = data.get("target_audience") or []
                existing.brand_voice = data.get("brand_voice") or []
                existing.content_pillar = data.get("content_pillar") or []
                brand_voice_record = existing
                brand_voice_record.site_compliance = getattr(self, "_site_compliance", None)   # ← ADD THIS LINE

                print("Saving compliance:", getattr(self, "_site_compliance", None))
            else:
                brand_voice_record = BrandVoice(
                    workspace_id=self.workspace_id,
                    brand_name=data.get("brand_name"),
                    about=data.get("about"),
                    customer_profile=data.get("customer_profile"),
                    selling_position=data.get("selling_position"),
                    target_audience=data.get("target_audience") or [],
                    brand_voice=data.get("brand_voice") or [],
                    content_pillar=data.get("content_pillar") or [],
                )
                brand_voice_record.site_compliance = getattr(self, "_site_compliance", None)   # ← ADD THIS LINE
                self.db.add(brand_voice_record)


            await self.db.flush()
            print("BrandVoice flushed successfully")
            # Persist personas separately
            await self._persist_personas(personas_data)

            await self.db.flush()
            return brand_voice_record

        except Exception as exc:  # noqa: BLE001 - rollback and propagate
            await self.db.rollback()
            logger.error(
                "Failed to persist brand voice and personas",
                extra={
                    "workspace_id": str(self.workspace_id),
                    "operation_id": self.operation_id,
                    "error": str(exc),
                },
            )
            raise

    async def _persist_competitors(self, competitors: List[str]) -> None:
        """Persist discovered competitor domains, independent of brand-voice persistence.

        Best-effort: logs and swallows failures rather than raising, so a
        competitor-persistence problem never fails workspace creation.
        """
        try:
            result = await self.db.execute(
                select(BrandVoice).where(BrandVoice.workspace_id == self.workspace_id)
            )
            existing = result.scalar_one_or_none() if result else None

            if existing:
                existing.competitors = competitors
            else:
                self.db.add(BrandVoice(workspace_id=self.workspace_id, competitors=competitors))

            await self.db.flush()
        except Exception as exc:  # noqa: BLE001 - non-fatal to the overall pipeline
            await self.db.rollback()
            logger.error(
                "Failed to persist discovered competitors",
                extra={
                    "workspace_id": str(self.workspace_id),
                    "operation_id": self.operation_id,
                    "error": str(exc),
                },
                exc_info=True,
            )

    async def _embed_brand_voice(self, brand_voice_schema: Optional[BrandSchema]) -> None:
        """Store brand voice embedding in the vector store (non-fatal)."""
        if not brand_voice_schema:
            return
        try:
            from src.services.brand_voice_embedding_service import BrandVoiceEmbeddingService
            from src.api.models.workspace_models.workspace_model import WorkspaceModel

            result = await self.db.execute(
                select(WorkspaceModel).where(WorkspaceModel.id == self.workspace_id)
            )
            workspace = result.scalar_one_or_none()
            workspace_name = workspace.name if workspace else None

            svc = BrandVoiceEmbeddingService()
            await svc.upsert_brand_voice_embedding(
                workspace_id=self.workspace_id,
                brand_data=brand_voice_schema.model_dump(),
                workspace_name=workspace_name,
            )
        except Exception as exc:
            logger.warning(
                "[BrandVoiceEmbed] Embedding failed (non-fatal)",
                extra={"workspace_id": str(self.workspace_id), "error": str(exc)},
            )

    def _attach_social_links(self, personas_data: list[dict]) -> None:
        """Fill each persona's own social profile URLs from the scraped markup.

        Anchored on the person's name (see extract_person_socials): a persona
        gets a link only when it sits in a container mentioning nobody else, and
        never when the handle matches the site's own brand. Anyone whose links
        cannot be attributed that confidently keeps none - an empty field is
        correct, another person's or the company's profile is not.
        """
        raw_pages = getattr(self, "_raw_pages", None)
        if not raw_pages or not personas_data:
            return
        from src.utils.fast_scraper import extract_person_socials

        names = [p.get("name") for p in personas_data if p.get("name")]
        merged: Dict[str, Dict[str, str]] = {}
        for page_url, html in raw_pages.items():
            try:
                for name, links in extract_person_socials(html, names, page_url).items():
                    merged.setdefault(name, {}).update(links)
            except Exception:  # noqa: BLE001 - enrichment is never worth failing a run
                continue

        for persona in personas_data:
            links = merged.get(persona.get("name") or "")
            if not links:
                continue
            if links.get("linkedin") and not persona.get("linkedin_url"):
                persona["linkedin_url"] = links["linkedin"]
            others = {k: v for k, v in links.items() if k != "linkedin"}
            if others:
                meta = dict(persona.get("custom_metadata") or {})
                meta["social_links"] = {**(meta.get("social_links") or {}), **others}
                persona["custom_metadata"] = meta

        logger.info(
            "Attached persona social links",
            extra={"with_links": sum(1 for p in personas_data
                                     if p.get("linkedin_url") or p.get("custom_metadata")),
                   "total": len(personas_data)},
        )

    async def _persist_personas(self, personas_data: list[dict]) -> None:
        """Save extracted personas to persona table.

        Always clears out personas from the previous workspace URL, even when
        the new extraction found none — otherwise a refresh to a persona-less
        site would leave stale personas from the old site in place.
        """
        if not personas_data:
            logger.info(
                "No personas extracted; clearing existing personas for workspace",
                extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
            )
        else:
            logger.info(
                "Extracted personas ready for persistence",
                extra={
                    "workspace_id": str(self.workspace_id),
                    "operation_id": self.operation_id,
                    "persona_count": len(personas_data),
                    "persona_names": [p.get("name", "Unnamed") for p in personas_data],
                },
            )
            logger.debug(
                "Extracted persona details",
                extra={
                    "workspace_id": str(self.workspace_id),
                    "operation_id": self.operation_id,
                    "personas": [
                        {
                            "name": p.get("name"),
                            "description": p.get("description"),
                            "professional_title": p.get("professional_title"),
                            "has_bio": bool(p.get("bio")),
                            "has_linkedin": bool(p.get("linkedin_url")),
                        }
                        for p in personas_data
                    ],
                },
            )

        # Use a savepoint to make the delete-then-insert atomic.
        # If insertion fails, the savepoint rollback also undoes the deletion,
        # preserving the original personas.
        def _normalize_text(value: Any) -> Optional[str]:
            if value is None:
                return None
            if isinstance(value, (list, tuple, set)):
                return ", ".join(str(item).strip() for item in value if item is not None)
            if isinstance(value, dict):
                return json.dumps(value, ensure_ascii=False)
            return str(value)

        async with self.db.begin_nested():
            # Delete existing personas for this workspace
            await self.db.execute(
                delete(Persona).where(Persona.workspace_id == self.workspace_id)
            )

            # Insert new personas with ALL fields
            for persona_data in personas_data:
                persona = Persona(
                    workspace_id=self.workspace_id,
                    # Basic fields
                    name=_normalize_text(persona_data.get("name")) or "",
                    description=_normalize_text(persona_data.get("description")),
                    # E-E-A-T Professional fields
                    full_name=_normalize_text(persona_data.get("full_name")),
                    professional_title=_normalize_text(persona_data.get("professional_title")),
                    areas_of_expertise=persona_data.get("areas_of_expertise"),
                    tone_of_voice=_normalize_text(persona_data.get("tone_of_voice")),
                    bio=_normalize_text(persona_data.get("bio")),
                    linkedin_url=_normalize_text(persona_data.get("linkedin_url")),
                    # User persona fields
                    demographics=_normalize_text(persona_data.get("demographics")),
                    pain_points=_normalize_text(persona_data.get("pain_points")),
                    goals=_normalize_text(persona_data.get("goals")),
                    behaviors=_normalize_text(persona_data.get("behaviors")),
                    avatar_url=_normalize_text(persona_data.get("avatar_url")),
                    custom_metadata=persona_data.get("custom_metadata"),
                )
                self.db.add(persona)

            # Flush within the savepoint to detect constraint violations
            await self.db.flush()

        logger.info(
            "Persisted personas",
            extra={
                "workspace_id": str(self.workspace_id),
                "operation_id": self.operation_id,
                "persona_count": len(personas_data),
            },
        )

    @staticmethod
    async def _default_scraper(url: str) -> Tuple[List[Any], List[Any]]:
        return await web_page_scraper(urls=[url])

    @staticmethod
    async def _default_vector_uploader(
        chunks: Sequence[Any],
        workspace_id: str,
    ) -> bool:
        return await asyncio.to_thread(
            add_to_vector_store,
            blog_context=list(chunks),
            workspace_id=workspace_id,
        )

    @staticmethod
    async def _default_brand_voice_generator(content: str) -> Optional[BrandSchema]:
        if not content.strip():
            return None

        async def _invoke_model() -> BrandSchema:
            from langchain_core.messages import SystemMessage, HumanMessage
            
            # Extraction, not generation: the same page must yield the same
            # people every time. At OpenAI's default temperature (1.0) three
            # runs over identical css-tricks.com content returned 11, then 5,
            # then 3 personas, which made every before/after comparison
            # unreadable and every bug report unreproducible.
            model = load_model(temperature=0)
            structured = model.with_structured_output(BrandSchema)
            
            system_prompt = """You are an expert at analyzing website content and extracting brand information and real people.

IMPORTANT INSTRUCTIONS FOR BRAND INFORMATION:
- Extract 'brand_name': The actual brand/company/product name as it appears on the site (e.g. in the logo, title tag, "About Us", or copyright line) — NOT a generic description, NOT the URL/domain, and NOT anything you infer from context. If the real brand name genuinely cannot be found in the content, leave this null — never guess or fabricate one.
- Extract 'about': A brief summary of what the brand/business does (1-2 sentences).
- Extract 'customer_profile': Who their ideal customers are and their characteristics.
- Extract 'selling_position': Their unique value proposition (what makes them different).
- Extract 'target_audience': Specific segments or demographics they target.
- Extract 'brand_voice': The characteristics of their communication style (e.g., Authoritative, Friendly, Professional, etc.).
- 'competitors': ALWAYS return an empty list for this field. Competitor discovery is handled by a separate, dedicated SERP-based pipeline elsewhere in the system — do not attempt to name or guess competitors here, even if the content strongly suggests some.
- Extract 'content_pillar': The main themes or categories they create content about.

STRICT RULES FOR PERSONAS — READ CAREFULLY:

RULE 1 — REAL PEOPLE ONLY, AND ONLY IF THEY SPEAK FOR THE BRAND:
The personas list MUST contain ONLY real, named human individuals explicitly mentioned by name on the website who represent or speak ON BEHALF OF the brand/business itself.
Valid sources — these four groups and nothing else: founders/co-founders, authors and blog writers, team members and executives, and named experts employed by or affiliated with the brand.
If a person does not clearly belong to one of those four groups, leave them out. Writing for the brand or working for the brand is the test; merely being named on a page is not.

RULE 2 — NAME REQUIREMENT:
A valid persona MUST have a real human name consisting of at least a first and last name (e.g., "John Smith", "Dr. Sarah Mitchell", "Mobheen Abdullah").
Single words, job titles, roles, or descriptions are NOT valid names.

RULE 3 — STRICTLY FORBIDDEN PERSONAS (these are NEVER valid — DO NOT add them to the personas list at all):
Do NOT create a persona entry for any of the following. Simply OMIT them from the list entirely — they belong conceptually in 'target_audience' or 'customer_profile', NOT personas:
  - Named individuals who ONLY appear as customer testimonial/review/case-study contributors (e.g., a quote attributed to "Jane Doe, Ohio" praising the product). These are customers, not brand representatives. Even though they have a real name, do NOT add them to the personas list under any circumstances. If you do include such a person, you MUST set source='testimonial' so the system can discard them — never relabel them as 'expert' or 'team_member'.
  - A senior-sounding title is NOT evidence of affiliation. A "CEO", "Founder" or "Director" quoted praising this brand almost always leads a DIFFERENT company and is a customer. Treat a person as brand-affiliated only when the content states they work for, founded, or write for THIS brand.
  - EXTERNAL SPEAKERS AND GUESTS: someone who appears only because they spoke at, presented at, or were interviewed for one of the brand's events, podcasts or webinars. A keynote speaker at the company's own conference works for a different organisation. This exclusion applies ONLY to people whose sole connection is that appearance — it never applies to anyone listed on the organisation's own team, leadership or about page.
  - People who only appear in a COMMENT or discussion thread on a post. Commenters are readers of the site, not writers for it, however real their name or detailed their comment.
  - People named only inside an FAQ, Q&A or help section.
  - People named only as a reviewer, rater, or review-board contributor evaluating the brand's products.
  - Customer archetypes (e.g., "Online Store Owner", "Busy Blogger", "Small Business Owner")
  - Target audience segments (e.g., "Marketing Manager", "Entrepreneur", "Startup Founder")
  - Fictional or representative users (e.g., "The Modern Professional", "Tech-Savvy User")
  - Generic roles without a real name attached

RULE 3B — TEAM AND LEADERSHIP PAGES ARE AUTHORITATIVE, LIST EVERY SINGLE PERSON ON THEM:
If the content includes an About, Team, Leadership, Staff, Executive or "Who We Are" page, every named individual listed there with a role at this organisation IS a valid persona.

Work through such a page methodically before you answer:
  1. Read the WHOLE page, top to bottom, including every section below the first one.
  2. Count the people named on it.
  3. Return that many personas from that page. If the page names eleven people, eleven personas come from that page — not six, not "the main ones", not a representative sample.

Returning a subset is the most serious error you can make here. Do NOT summarise, do NOT select the most senior, do NOT stop after the first group.

Specifically included, because these are routinely and wrongly skipped:
  - Regional, country and territory leads (e.g. "Regional Head, Asia-Pacific", "Director, Brazil"). A regional leader employed by the organisation is a team member exactly like a head-office executive.
  - People in a second or third section of the page (e.g. an executive block followed by a regional block, or a "leadership" block followed by "advisors who are staff").
  - People whose entry is only a name and a job title. A biography is NOT required — name plus title on a team page is sufficient evidence.
  - People whose name is non-English or unfamiliar to you.

Give each one source='team_member', or 'founder' where the content says so.

CRITICAL EXCEPTION — BOARD AND COMMITTEE REPRESENTATIVES ARE NOT STAFF:
The same page often carries two different kinds of people, and only the first kind counts:
  (a) EMPLOYEES of this organisation — an Executive Director, a Head of Product, a Regional Director. Their entry gives a job title describing work they do FOR this organisation. INCLUDE these.
  (b) REPRESENTATIVES of other companies who sit on a board, executive committee, or member council. Their entry names their OWN employer instead of a job title here. EXCLUDE these — they work for that other company.

The give-away is a company name where a job title should be. On a payments standards body, "Sophie Rainford — American Express", "Adam Sommer — Mastercard" and "Meng Ren — UnionPay" are Amex, Mastercard and UnionPay employees sitting on a committee; they are NOT staff of the standards body, and returning them is the same error as returning a conference speaker.

Treat these section headings as marking group (b), and exclude everyone under them: "Executive Committee", "Board of Advisors", "Board of Directors", "Founding Members", "Strategic Members", "Affiliate Members", "Participating Organizations", "Steering Committee", "Advisory Board".

If you cannot tell which group someone belongs to, ask: does the content give them a role performing work for THIS organisation, or does it merely name their employer? Only the former is a persona.

RULE 4 — EMPTY LIST WHEN NO REAL PEOPLE FOUND:
If the website content does NOT explicitly mention any real named individuals who are founders, team members, authors, or otherwise represent the brand, you MUST return an EMPTY list: personas = []
Do NOT invent, fabricate, or infer personas. Do NOT use testimonial/review authors as a substitute. Do NOT populate this field with guesses.
Returning an empty list IS the correct answer when no real brand-affiliated people are named on the site — even if named customers/testimonial contributors are present.

For each valid PERSONA extracted, provide:
- name: The person's actual name exactly as it appears on the site (e.g., "Mobheen Abdullah"). It must be ONE human being. A collective byline — "Nextly Team", "Editorial Staff", "The Support Crew", "<Brand> Team" — is not a person and must never be returned, even when it appears in the author position of an article.
- source: One of 'founder', 'team_member', 'author', 'expert', or 'testimonial'. Use 'expert' ONLY for someone the content states is employed by or formally affiliated with this brand — never for a guest, speaker, or interviewee. If your justification for 'expert' would be "they spoke at the company's event" or "they were interviewed on the company's podcast", the correct action is to omit them entirely. Omitting a testimonial-only contributor is still the best outcome, but if you are not fully certain a person is employed by, founded, or writes for THIS brand, you MUST label them 'testimonial' rather than guessing 'expert' or 'team_member'. 'expert' is only for a named expert the content states is affiliated with this brand. When torn between 'expert' and 'testimonial', always choose 'testimonial'.
- full_name: Their complete professional name if available.
- professional_title: Their stated job title (e.g., "Founder & CEO").
- areas_of_expertise: What they specialize in based on their stated role and content.
- tone_of_voice: Their writing or communication style if discernible.
- bio: A brief professional background based ONLY on what the site explicitly states about them. Pages headed "Author profile:" are that person's own bio page — use them as the primary source for this field.
- description: A one-line summary of their role at the brand.
- behaviors: What this person is OBSERVED doing, read off their article list. An "Author profile:" page lists their articles with titles and dates — that IS the evidence. Summarise the topics they cover, the formats they use (tutorials, product news, opinion), and roughly how often they publish. Example, from an author page listing six hosting articles across two months: "Publishes hosting and infrastructure articles on the company blog, roughly monthly, favouring hands-on benchmark and comparison pieces." Do NOT leave this null when an article list is present — the list is the evidence.
- demographics: PROFESSIONAL context, which you can nearly always derive — do not leave this null when you know their title and the brand's industry. Combine: seniority implied by the job title (C-level, VP, head of function, individual contributor), the industry the brand operates in, and any region, tenure or credentials the content states. Example, from "VP, Distinguished Standards Architect" at a payments-security body: "Senior technical leadership, payment security and standards industry." What you must never state is an age, gender, income or personal circumstance — those are not derivable from a job title and must stay out.
- pain_points: The professional problems this person writes about solving, drawn from their article titles and bio. Example: "Site performance under load, email deliverability, recurring revenue for agencies." Null only if you have neither bio nor articles for them.
- goals: What their bio or article focus shows they are working towards in their role. Null if genuinely unstated.
For these four, an article list counts as evidence and should be used. What you must never do is invent a personal detail the content cannot support — an empty field beats a confident fabrication.

FIELD COMPLETENESS: if a piece of content is specifically ABOUT one person — e.g. a
"meet the team" profile, a promotion/leadership-announcement post, or a bio page —
extract EVERY detail that page states for that person (full title, department, years of
experience, background, specialties), not just their name. Don't leave professional_title
or bio empty when the source content plainly states them just because the mention was
brief elsewhere too. Still never infer or guess anything the content doesn't say.
"""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content="Analyze the following website content and extract brand information and any real named individuals:\n\n"
                             + (getattr(self, "_team_text", "") or content))
            ]
            
            return await structured.ainvoke(messages)

        async def _extract_authors() -> list:
            """Second pass over the writing evidence only.

            Run concurrently with the main call, so the wall clock is the slower
            of the two rather than their sum - the scrape dominates either way.
            """
            author_text = getattr(self, "_author_text", "") or ""
            fallback = False
            if not author_text.strip():
                # Nothing classified as editorial, and no byline was declared in
                # markup anywhere. That is not proof the site has no writers -
                # it can equally mean the theme names its author in prose, or
                # publishes on a path no keyword matches. Rather than return no
                # authors on the strength of missing markup, hand the model
                # everything that was scraped and let it read for a byline.
                # Costs one extra call only on sites where the cheap
                # deterministic path already came up empty.
                author_text = getattr(self, "_team_text", "") or content
                fallback = True
                if not author_text.strip():
                    return []
                logger.info("author pass falling back to full content "
                            "(no declared bylines found)")
            from langchain_core.messages import SystemMessage, HumanMessage
            model = load_model(temperature=0).with_structured_output(BrandSchema)
            out = await model.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=(
                    ("Read the following pages from ONE website and identify every "
                     "person who WRITES for this brand - article authors, blog "
                     "writers, contributors. Look for bylines in the prose "
                     "('by <name>', 'written by <name>', a name beside a publish "
                     "date). Return each as a persona with source='author'. If "
                     "nobody is credited as a writer, return an empty list rather "
                     "than guessing. Extract only personas; leave the brand fields "
                     "empty.\n\n"
                     if fallback else
                     "The following pages are article bylines and author profile "
                     "pages from ONE website. Every 'Article author:' and 'Author "
                     "profile:' line names a real writer for this brand - return "
                     "each of them as a persona with source='author'. Extract only "
                     "personas; leave the brand fields empty.\n\n") + author_text)),
            ])
            return [p.model_dump() if hasattr(p, "model_dump") else p
                    for p in (out.personas or [])]

        async def _extract_leadership() -> list:
            """Third pass, over team/leadership pages alone."""
            text = getattr(self, "_leadership_text", "") or ""
            if not text.strip():
                return []
            from langchain_core.messages import SystemMessage, HumanMessage
            model = load_model(temperature=0).with_structured_output(BrandSchema)
            out = await model.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=(
                    "The following pages are the organisation's own team and "
                    "leadership pages. Read each one completely, top to bottom, "
                    "including every section. Count the people named on it and "
                    "return exactly that many personas — every executive, every "
                    "regional or country lead, and everyone whose entry is only a "
                    "name and a job title. Returning a subset is a failure. "
                    "Extract only personas; leave the brand fields empty.\n\n" + text)),
            ])
            return [p.model_dump() if hasattr(p, "model_dump") else p
                    for p in (out.personas or [])]

        # All three passes together: wall clock is the slowest of them, not the
        # sum, and the scrape dominates all three regardless.
        brand, authors, leaders = await asyncio.gather(
            _invoke_model(), _extract_authors(), _extract_leadership())
        self._author_personas = list(authors) + list(leaders)
        logger.info("persona extraction passes complete",
                    extra={"team_pass": len(brand.personas or []),
                           "author_pass": len(authors),
                           "leadership_pass": len(leaders)})
        return brand


async def run_workspace_pipeline(
    *,
    db: AsyncSession,
    operation_id: str,
    workspace_id: UUID,
    user_id: UUID,
    url: str,
    scraper: Optional[ScrapeCallable] = None,
    vector_uploader: Optional[VectorUploaderCallable] = None,
    brand_voice_generator: Optional[BrandVoiceGeneratorCallable] = None,
) -> None:
    """
    Entrypoint for triggering the workspace pipeline, typically from background tasks.

    Args:
        db: Async SQLAlchemy session
        operation_id: Identifier correlating SSE stream subscribers
        workspace_id: Workspace being processed
        url: Primary website URL provided during creation
        scraper: Optional override used for testing
        vector_uploader: Optional override used for testing
        brand_voice_generator: Optional override used for testing
    """
    pipeline = WorkspacePipeline(
        db=db,
        operation_id=operation_id,
        workspace_id=workspace_id,
        user_id=user_id,
        url=url,
        scraper=scraper,
        vector_uploader=vector_uploader,
        brand_voice_generator=brand_voice_generator,
    )
    await pipeline.run()