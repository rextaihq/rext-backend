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


# Ceiling for the headless-browser fallback. It only runs when the fast scraper
# came back thin, and on a site that blocks or stalls it produces nothing however
# long it is given - so it must never cost more than the fast path it is backing up.
FALLBACK_BUDGET_SECONDS = 25.0

# Ceiling for the whole workspace pipeline. Persona quality is never traded away
# to meet it - the scrape and the three extraction passes run to completion, and
# their own budgets already bound them. What gives way is competitor discovery,
# which is supplementary: a workspace missing competitors is usable, a workspace
# that never finishes is not.
PIPELINE_BUDGET_SECONDS = 110.0

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


# Recency thresholds live with the scraper because that is where publication
# years are read; imported here so the score and the extractor cannot drift
# apart on what counts as current.
from src.utils.fast_scraper import (
    ACTIVE_SINCE_YEAR,
    RECENT_SINCE_YEAR,
    _is_person_name as _fs_is_person_name,
)


def _is_collective(name: str) -> bool:
    """Whether a persona name refers to a group rather than an individual."""
    words = [w for w in re.sub(r"[^\w\s]", " ", (name or "").lower()).split() if w]
    if not words:
        return True
    if words[-1] in _COLLECTIVE_SUFFIXES:
        return True
    return any(w in _COLLECTIVE_WORDS for w in words)


# Confidence is scored as provenance plus completeness, not as a sum over all
# signals. Summing was the first attempt and it misled badly: the strong signals
# are mutually exclusive in practice - a team member has no byline, an author is
# not on the leadership page - so nobody could approach 100, and Gina Gobeyn,
# named on her organisation's own leadership page with a title, a biography and
# a headshot, scored 43. Provenance answers "how do we know this person belongs
# to this brand"; completeness answers "how much do we know about them". They
# are different questions and the first one dominates.
_PROVENANCE = {
    "on_team_page":    60,   # named on the org's own team/leadership page
    "declared_byline": 55,   # credited as author in markup, not inferred
    "author_profile":  50,   # has an author archive page on this site
    # Weaker than the three above - prose is not markup, and a role stated near
    # a name is easier to misread than a byline the site declared - but it is
    # still the brand's own page saying what this person does, which a reviewer
    # or a quoted outsider never gets.
    "stated_role":     40,
}
_PROVENANCE_BONUS = 10       # a second independent provenance signal
_NO_PROVENANCE = 25          # model read them out of prose, nothing corroborates
# Recency. A person who published once in 2005 must not outrank someone
# publishing now, so activity is scored on when it happened rather than only
# that it happened. The bands follow the brief: 2020 is the floor for
# eligibility, 2023 onward is treated as current.
_RECENCY = {
    "active_2023_plus": 20,   # published in the last few years
    "active_2020_plus": 10,   # eligible, but not current
    "prolific": 8,            # several pieces, not a single post
}
_PROLIFIC_ARTICLES = 3
_COMPLETENESS = {
    "job_title": 10, "bio": 8, "social_match": 8, "avatar": 7,
    "published": 4, "multiple_pages": 3,
}


def _confidence(persona: dict, signals: set) -> tuple:
    """Score 0-100 with the signals that produced it.

    The signals are returned alongside the number because a bare score invites
    trust it has not earned. A reader who sees 85 with
    ["on_team_page", "job_title", "bio", "avatar"] can judge it; a reader who
    sees 85 alone cannot.
    """
    provenance = [s for s in signals if s in _PROVENANCE]
    if provenance:
        score = max(_PROVENANCE[s] for s in provenance)
        if len(provenance) > 1:
            score += _PROVENANCE_BONUS
    else:
        score = _NO_PROVENANCE
    score += sum(_COMPLETENESS.get(s, 0) for s in signals)
    score += sum(_RECENCY.get(s, 0) for s in signals)
    # Only old work and nothing since: present on the site, but not someone the
    # brand is currently represented by.
    if "inactive" in signals:
        score = int(score * 0.5)
    return min(100, score), sorted(signals)


# Review and testimonial attribution written as prose rather than marked up.
# Stripping is class-based, so a site that prints "Cindy Matticks - Customer
# Review (Google)" in plain text keeps its reviewers in the extraction input,
# and a reviewer's name passes every shape rule a staff member's does.
_REVIEW_CONTEXT = re.compile(
    r"(?i)(customer\s+review|verified\s+(?:buyer|purchase|customer)|google\s+review|"
    r"trustpilot|yelp|left\s+a\s+review|wrote\s+a\s+review|rated\s+us|"
    r"\d\s*(?:out\s+of\s*)?5\s*stars?|★|reviewed\s+by)")
_REVIEW_WINDOW = 60


def _in_review_context(name: str, pages_text: dict) -> bool:
    """Whether every mention of `name` sits beside review/rating language.

    Judged on all mentions, not the first: someone who writes for the brand and
    is also quoted in a review is staff, and must not be dropped for the second
    fact. Only a person who appears nowhere except beside review language is a
    reviewer.
    """
    if not name:
        return False
    seen = False
    for text in pages_text.values():
        start = 0
        while True:
            i = text.find(name, start)
            if i < 0:
                break
            seen = True
            window = text[max(0, i - _REVIEW_WINDOW): i + len(name) + _REVIEW_WINDOW]
            if not _REVIEW_CONTEXT.search(window):
                return False          # at least one clean mention - not a reviewer
            start = i + len(name)
    return seen


# Roles that place someone inside an organisation when written beside their
# name. Deliberately senior-or-functional rather than generic: "member" or
# "user" would match anybody.
_ROLE_WORDS = (
    "founder", "co-founder", "cofounder", "chair", "chairman", "chairwoman",
    "ceo", "cto", "coo", "cfo", "cmo", "cio", "cso", "president",
    "vice president", "vp", "director", "head of", "chief", "partner",
    "manager", "lead", "engineer", "developer", "editor", "writer",
    "specialist", "architect", "consultant", "analyst", "designer",
    "executive", "officer", "principal",
)
_ROLE_WINDOW = 70
# Word-boundary matched, never substring: the acronyms are short enough to hide
# inside ordinary words - "tractors" contains "cto", which read "Amy Lee wrote
# this guide about tractors" as a stated role.
_ROLE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(r) for r in sorted(_ROLE_WORDS, key=len, reverse=True))
    + r")\b", re.I)


# Typographic quotation marks around a name mean it is attribution on a pull
# quote, not a roster entry. revnix.com credits "Hannah Ross, VP of Marketing,
# 21st Century Equipment" in a <figcaption> with no testimonial class - class
# stripping misses it, and her title would otherwise earn her provenance under
# _states_role, admitting a client's marketing VP as a Revnix persona. A team
# page writes "Jane Roe, Head of Product" without quotation marks; a testimonial
# almost never omits them.
_PULL_QUOTE = re.compile(r"[\u201c\u201d\u2018\u2019\u00ab\u00bb\u201e]")
# A role followed by another company's name is that company's role, not this
# brand's - the same reasoning that excludes board representatives.
_ROLE_AT_OTHER = re.compile(
    r"(?i)\b(?:at|of|from|with)\s+[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3}")


# Functions inside an organisation. A trailing segment naming one of these is
# the person's department - "SVP, Education & Engagement" - not a second
# employer, and treating it as one dropped real executives.
_DEPARTMENT_RE = re.compile(
    r"(?i)\b(?:education|engagement|product|technology|marketing|sales|"
    r"operations?|engineering|design|finance|legal|people|hr|security|"
    r"standards|communications?|content|growth|support|strategy|research|"
    r"development|delivery|risk|compliance|quality|data|platform|"
    r"experience|success|partnerships?|community|editorial)\b")


def _names_other_employer(role: str, brand: str) -> bool:
    """Whether a role string names an employer other than this brand.

    Handles both forms a card uses: "COO at KitBash3D" and the bare
    comma-separated "COO, KitBash3D + Greyscalegorilla". The second is what
    revnix.com writes under its client testimonials, and matching only the
    first let a client's COO through as a team member.
    """
    if not role:
        return False
    # Split only where an employer actually follows. " of " and " from " belong
    # inside roles - "Head of Product & Technology" is one job, not a job at a
    # company called Product & Technology.
    segments = [seg.strip() for seg in re.split(r"[,|·•@]| at | for ", role) if seg.strip()]
    for seg in segments[1:] if len(segments) > 1 else []:
        # A trailing segment that is not itself a role reads as an organisation.
        if _ROLE_RE.search(seg.lower()) or _DEPARTMENT_RE.search(seg.lower()):
            continue
        named = re.sub(r"[^a-z0-9]", "", seg.lower())
        if not named or len(named) < 3:
            continue
        if brand and (brand in named or named.startswith(brand)):
            return False
        return True
    return False


def _states_role(name: str, text: str, brand: str = "") -> bool:
    """Whether the page states a role beside this person's name.

    A role only counts when it reads as this organisation's own description of
    someone. Quoted attribution and roles naming another employer are excluded,
    because both describe a person who does not work here.
    """
    if not name or not text:
        return False
    start = 0
    while True:
        i = text.find(name, start)
        if i < 0:
            return False
        raw = text[max(0, i - _ROLE_WINDOW): i + len(name) + _ROLE_WINDOW]
        if _ROLE_RE.search(raw.lower()) and not _PULL_QUOTE.search(raw):
            after = text[i + len(name): i + len(name) + _ROLE_WINDOW]
            # "VP of Marketing, 21st Century Equipment" - a role held elsewhere.
            role_end = _ROLE_RE.search(after.lower())
            other = _ROLE_AT_OTHER.search(after[role_end.end():]) if role_end else None
            if other:
                # "at WPMU DEV" on wpmudev.com is this brand; "21st Century
                # Equipment" on revnix.com is a client. Compare with the domain
                # rather than assuming any capitalised name is a third party.
                named = re.sub(r"[^a-z0-9]", "", other.group(0).lower())
                if brand and (brand in named or named.endswith(brand)):
                    return True
                if "," in after[:role_end.end() + 40]:
                    return False
            return True
        start = i + len(name)


def _priority(score: int) -> str:
    """Bucket a score for the UI. Ranking is by score; this labels the bands."""
    if score >= 80:
        return "high"
    if score >= 60:
        return "medium"
    return "low"


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
    rather than an actual human name.
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
        # Second line of defence against names built from an email address or an
        # account handle. The scraper no longer derives names from author slugs,
        # but such a name can also reach the model through page text, and
        # "Devrevnix Com" passes every name-shape rule a real person passes.
        if not _fs_is_person_name(name):
            rejected.append({"name": name, "reason": "address or handle, not a person's name"})
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
            started = asyncio.get_event_loop().time()

            # Competitor discovery does its own scraping and reads nothing from
            # brand voice or personas - its own docstring says it runs
            # "independently of brand-voice extraction". It was sequential by
            # choice rather than dependency, which cost the wall clock of both
            # stages end to end: on wpbeginner.com, ~90s of SERP and fetch waits
            # added to a ~140s brand-voice flow that was already finished. Two
            # independent stages should overlap, so it starts here and is
            # collected at the end.
            competitors_task = asyncio.create_task(self._discover_competitors())

            scrape_result = await self._scrape_website()
            await self._create_vector_embeddings(scrape_result.chunks)
            brand_voice_schema = await self._extract_brand_voice(scrape_result.content)
            await self._persist_brand_voice(brand_voice_schema)
            await self._embed_brand_voice(brand_voice_schema)

            # Whatever is left of the pipeline's budget. Competitor discovery is
            # supplementary - a workspace without it is usable, a workspace that
            # never finishes is not - so it is the stage that gives way when the
            # ceiling is reached.
            remaining = PIPELINE_BUDGET_SECONDS - (
                asyncio.get_event_loop().time() - started)
            try:
                discovered_competitors = await asyncio.wait_for(
                    competitors_task, timeout=max(1.0, remaining))
            except asyncio.TimeoutError:
                competitors_task.cancel()
                discovered_competitors = None
                logger.warning(
                    "Competitor discovery exceeded the pipeline budget, "
                    "completing without it",
                    extra={
                        "workspace_id": str(self.workspace_id),
                        "operation_id": self.operation_id,
                        "budget_seconds": PIPELINE_BUDGET_SECONDS,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - never fail the run for it
                discovered_competitors = None
                logger.warning(
                    "Competitor discovery failed, completing without it",
                    extra={"workspace_id": str(self.workspace_id),
                           "error": str(exc)},
                )
            logger.info(
                "Workspace pipeline timing",
                extra={"total_seconds": round(
                    asyncio.get_event_loop().time() - started, 1)},
            )
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
                max_blog_posts=10,
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
        self._page_text_by_url = dict(pages)
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
            # The fast scraper honours a wall-clock budget; this fallback did
            # not, so a site it could NOT reach cost far more than one it could.
            # mobeenabdullah.com spent 30s on a navigation timeout, then another
            # 45s on the stealth retry, and returned zero chunks - 75s of a
            # 2.5-minute run producing nothing. A browser that cannot load a page
            # in FALLBACK_BUDGET_SECONDS will not load it in three times that.
            try:
                chunks, results = await asyncio.wait_for(
                    self._scraper(self.url), timeout=FALLBACK_BUDGET_SECONDS)
            except asyncio.TimeoutError:
                logger.warning(
                    "crawl4ai fallback exceeded its budget, using the fast scrape",
                    extra={
                        "workspace_id": str(self.workspace_id),
                        "operation_id": self.operation_id,
                        "url": self.url,
                        "budget_seconds": FALLBACK_BUDGET_SECONDS,
                        "fast_scrape_chars": len(combined),
                    },
                )
                return combined, result.get("raw_home_html") or "", False
            first_success = next(
                (r for r in results or [] if getattr(r, "success", False)), None,
            )
            content = getattr(first_success, "markdown", "") if first_success else ""
            raw_html = getattr(first_success, "html", "") if first_success else ""
            content = self._sample_content_for_extraction(content)
            # Kept for the scoring pass: without page boundaries it is still the
            # only text that can confirm a persona's name came off this site.
            self._fallback_text = content
            # An empty fallback is worse than a thin fast scrape - keep whichever
            # actually has content.
            if not content.strip() and combined.strip():
                return combined, result.get("raw_home_html") or "", False
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
        if not personas_data:
            return
        # raw_pages is empty whenever the fast scraper came back thin and the
        # browser fallback supplied the content instead, because that path
        # returns rendered markdown rather than per-page HTML. Returning here
        # skipped confidence, provenance and every rejection rule with it - a
        # site the fast scraper could not read got its personas through
        # unscored and ungated, which is the opposite of what should happen
        # when the evidence is weakest. Enrichment degrades; the gate does not.
        raw_pages = getattr(self, "_raw_pages", None) or {}
        if not getattr(self, "_page_text_by_url", None):
            # Fallback content is one blob with no page boundaries. Treated as a
            # single page so the text-based checks still run.
            self._page_text_by_url = {self.url: getattr(self, "_fallback_text", "")}
        from src.utils.fast_scraper import (classify_page, extract_page_title,
                                             PAGE_TEAM)
        pages_text = getattr(self, "_page_text_by_url", {}) or {}
        kinds = {u: classify_page(u, pages_text.get(u, "")) for u in raw_pages}

        # What each writer actually published, taken from the byline already
        # extracted for that page. Deterministic - the article belongs to
        # whoever the page declared, with no inference involved.
        articles_by_author: Dict[str, list] = {}
        article_years: Dict[str, list] = {}
        from src.utils.fast_scraper import PAGE_ARTICLE as _PA
        for page_url, text in pages_text.items():
            # A byline is prepended on any page that declares one, including
            # about and marketing pages. Only editorial pages are articles -
            # otherwise "Membership Plans & Pricing" is listed as something the
            # writer wrote.
            if not text.startswith("Article author:") or kinds.get(page_url) != _PA:
                continue
            header = text.split("\n", 1)[0].replace("Article author: ", "").strip()
            # The scraper stamps "Article author: <name> | <year>" where a
            # publication date was declared. Splitting here keeps date parsing
            # in one place - the scraper - rather than duplicating it.
            who, _, stamped = header.partition(" | ")
            who = who.strip()
            if stamped.strip().isdigit():
                article_years.setdefault(who, []).append(int(stamped.strip()))
            if not who:
                continue
            title = extract_page_title(raw_pages.get(page_url, "")) or page_url
            entry = {"title": title, "url": page_url}
            bucket = articles_by_author.setdefault(who, [])
            if entry not in bucket:
                bucket.append(entry)

        # Author archive pages ("Author profile: <name>") list that writer's
        # whole output; counting the post links on one gives a real total
        # rather than a sample size.
        from src.utils.fast_scraper import _find_post_links
        archive_counts: Dict[str, int] = {}
        for page_url, text in pages_text.items():
            if not text.startswith("Author profile:"):
                continue
            who = text.split("\n", 1)[0].replace("Author profile: ", "").strip()
            try:
                links = _find_post_links(raw_pages.get(page_url, ""), page_url, 500,
                                         allow_outside_index_path=True)
            except Exception:  # noqa: BLE001
                links = []
            if who and links:
                archive_counts[who] = max(archive_counts.get(who, 0), len(links))
        from src.utils.fast_scraper import (extract_person_avatars,
                                             extract_person_socials)

        names = [p.get("name") for p in personas_data if p.get("name")]
        merged: Dict[str, Dict[str, str]] = {}
        avatars: Dict[str, str] = {}
        for page_url, html in raw_pages.items():
            try:
                for name, links in extract_person_socials(html, names, page_url).items():
                    merged.setdefault(name, {}).update(links)
                # Only people-pages. A portrait lives on a team page or an
                # author profile; on an article page the image beside a byline
                # is the piece's hero artwork, not the writer's face. The first
                # people-page to yield one wins.
                if kinds.get(page_url) == PAGE_TEAM or \
                        (pages_text.get(page_url, "").startswith("Author profile:")):
                    for name, src in extract_person_avatars(html, names, page_url).items():
                        avatars.setdefault(name, src)
            except Exception:  # noqa: BLE001 - enrichment is never worth failing a run
                continue

        # A persona whose name appears nowhere in the scraped text was not
        # extracted, it was invented. thebackyard.com returned "Jane Smith" and
        # "John Doe" - the model echoing this prompt's own example names back
        # when the page gave it nothing to work with. Name-shape checks cannot
        # catch that, because a fabricated name is shaped exactly like a real
        # one; only checking it against the source can. This is the guarantee
        # that every persona came off the site rather than out of the model.
        unverified = [
            p for p in personas_data
            if not any((p.get("name") or "") and (p.get("name") or "") in t
                       for t in pages_text.values())
        ]
        if unverified:
            logger.warning(
                "Dropped personas absent from the scraped content",
                extra={"names": [p.get("name") for p in unverified],
                       "kept": len(personas_data) - len(unverified)},
            )
            personas_data[:] = [p for p in personas_data if p not in unverified]

        import tldextract as _tld
        brand_token = re.sub(r"[^a-z0-9]", "", _tld.extract(self.url).domain.lower())
        # Recall backstop. The model silently omits people - the leadership pass
        # returned 6 of 11 executives before it got a prompt of its own, and
        # nothing downstream could tell that five were missing. Team-card markup
        # states name and role together, so reading it directly turns "did the
        # model notice this person" into a question the code answers.
        from src.utils.fast_scraper import extract_team_names
        declared: Dict[str, str] = {}
        for page_url, html in raw_pages.items():
            if kinds.get(page_url) != PAGE_TEAM:
                continue
            try:
                declared.update(extract_team_names(html, page_url))
            except Exception:  # noqa: BLE001 - a backstop must never fail a run
                continue
        have = {_identity_key(p.get("name") or "") for p in personas_data}
        recovered = []
        for n, r in declared.items():
            if _identity_key(n) in have:
                continue
            # A role naming another employer belongs to that employer. Revnix's
            # about page credits "Noah Proser, COO, KitBash3D + Greyscalegorilla"
            # - a client's COO, whose card is shaped exactly like a team card.
            # Same test the prose-role check uses, for the same reason.
            if _names_other_employer(r, brand_token):
                continue
            recovered.append(
                {"name": n, "source": "team_member", "professional_title": r})
        if recovered:
            logger.info(
                "Recovered team members the model omitted",
                extra={"names": [p["name"] for p in recovered],
                       "already_had": len(personas_data)},
            )
            personas_data.extend(recovered)

        unprovenanced: list = []
        for persona in personas_data:
            name = persona.get("name") or ""
            meta = dict(persona.get("custom_metadata") or {})

            # 'source' decides whether someone is a writer or a team member. It
            # was computed, used for filtering, then discarded - the Persona
            # model has no such column - so the UI could not tell an author from
            # an executive. custom_metadata is JSONB and needs no migration.
            source = (persona.get("source") or "").strip().lower()
            if source:
                meta["source"] = source

            avatar = avatars.get(name)
            if avatar and not persona.get("avatar_url"):
                persona["avatar_url"] = avatar

            # How much this person has published here. The author archive page
            # is authoritative where one was fetched, since it lists their whole
            # output rather than the handful the crawl sampled. Titles are not
            # stored: the count is what marks a prolific writer, and a partial
            # list of titles reads as complete when it is not.
            count = archive_counts.get(name) or len(articles_by_author.get(name) or [])
            years = sorted(y for y in article_years.get(name, []) if y)
            latest = years[-1] if years else None
            recent_count = sum(1 for y in years if y >= RECENT_SINCE_YEAR)
            if count:
                meta["article_count"] = count

            links = merged.get(name)
            if links:
                if links.get("linkedin") and not persona.get("linkedin_url"):
                    persona["linkedin_url"] = links["linkedin"]
                others = {k: v for k, v in links.items() if k != "linkedin"}
                if others:
                    meta["social_links"] = {**(meta.get("social_links") or {}), **others}

            # Confidence rests on evidence observed during the crawl, never on
            # the model's own assurance about its output.
            mentions = [u for u, t in pages_text.items() if name and name in t]
            signals = set()
            if any(kinds.get(u) == PAGE_TEAM for u in mentions):
                signals.add("on_team_page")
            if any(pages_text.get(u, "").startswith("Article author: " + name)
                   for u in mentions):
                signals.add("declared_byline")
            if any(pages_text.get(u, "").startswith("Author profile: " + name)
                   for u in mentions):
                signals.add("author_profile")
            # A role stated next to the name on the site's own pages. wpmudev.com
            # names James Farmer as "Founder & Chair" in its forum, and PCI names
            # regional heads in prose - people with no team page and no byline,
            # who were therefore unprovenanced and are now dropped by the gate
            # above. A stated role on the brand's own domain is evidence of
            # affiliation, and it costs no extra crawling: the pages are already
            # fetched.
            if any(_states_role(name, pages_text[u], brand_token) for u in mentions):
                signals.add("stated_role")
            if persona.get("professional_title"):
                signals.add("job_title")
            if persona.get("bio"):
                signals.add("bio")
            if persona.get("avatar_url"):
                signals.add("avatar")
            if links:
                signals.add("social_match")
            if len(mentions) > 1:
                signals.add("multiple_pages")
            if count:
                signals.add("published")
            if count >= _PROLIFIC_ARTICLES:
                signals.add("prolific")
            # Recency decides whether someone is currently one of this brand's
            # voices or merely appeared on it once, years ago.
            if latest and latest >= RECENT_SINCE_YEAR:
                signals.add("active_2023_plus")
            elif latest and latest >= ACTIVE_SINCE_YEAR:
                signals.add("active_2020_plus")
            elif latest:
                signals.add("inactive")
            # Whether the job title is quoted from the page or inferred by the
            # model. Confidence measures affiliation, not title accuracy, and
            # the two were indistinguishable downstream: wpmudev.com returned
            # "WordPress Advocate" and "WordPress Expert" at the same confidence
            # as a title printed on a leadership page. A reader deciding whether
            # to publish under someone's name needs to know which they have.
            title = (persona.get("professional_title") or "").strip()
            if title:
                meta["title_verified"] = any(
                    title.lower() in t.lower() for t in pages_text.values())

            score, reasons = _confidence(persona, signals)
            meta["confidence"] = score
            meta["confidence_signals"] = reasons
            meta["priority"] = _priority(score)
            meta["persona_type"] = source or "team_member"
            # Enough to reconstruct the score without re-running the crawl. A
            # number alone cannot be argued with; the evidence behind it can.
            meta["evidence"] = {
                "team_member": "on_team_page" in signals,
                "author": "declared_byline" in signals,
                "author_profile": "author_profile" in signals,
                "stated_role": "stated_role" in signals,
                "contributor": count >= _PROLIFIC_ARTICLES,
                "recent_content": "active_2023_plus" in signals,
                "article_count": count,
                "recent_article_count": recent_count,
                "latest_article_year": latest,
            }
            if _in_review_context(name, pages_text):
                unprovenanced.append(persona)
                continue
            if not signals & set(_PROVENANCE):
                # Nothing places this person inside the organisation: not on a
                # team page, no byline declared in markup, no author profile.
                # That is what a quoted expert, a case-study subject, a client
                # and a plain-text review author all look like, and each is a
                # real person with a real name that every shape rule passes.
                # Enumerating what a non-person looks like never ends;
                # requiring evidence of what a real one looks like does.
                unprovenanced.append(persona)

            persona["custom_metadata"] = meta

        if unprovenanced:
            for p in unprovenanced:
                logger.info(
                    "Persona REJECT",
                    extra={"name": p.get("name"),
                           "reason": "no provenance - name present but nothing "
                                     "places this person inside the organisation"},
                )
            personas_data[:] = [p for p in personas_data if p not in unprovenanced]

        # Strongest first. Scraping order and alphabetical order both bury the
        # most important person behind whoever the crawler happened to reach
        # first, and the frontend shows the top of the list.
        # Breadth of evidence breaks ties. The score caps at 100, so two people
        # can reach it while one is corroborated from four independent sources
        # and the other from two - and the frontend shows whoever is first.
        personas_data.sort(
            key=lambda p: (
                (p.get("custom_metadata") or {}).get("confidence", 0),
                len((p.get("custom_metadata") or {}).get("confidence_signals") or []),
                ((p.get("custom_metadata") or {}).get("evidence") or {})
                .get("recent_article_count") or 0,
            ),
            reverse=True)

        for p in personas_data:
            m = p.get("custom_metadata") or {}
            logger.info(
                "Persona ACCEPT",
                extra={"name": p.get("name"), "type": m.get("persona_type"),
                       "confidence": m.get("confidence"), "priority": m.get("priority"),
                       "evidence": m.get("confidence_signals"),
                       "latest_year": (m.get("evidence") or {}).get("latest_article_year")},
            )

        scored = [p for p in personas_data if (p.get("custom_metadata") or {}).get("confidence")]
        logger.info(
            "Persona extraction summary",
            extra={
                "personas": len(personas_data),
                "authors": sum(1 for p in personas_data
                               if (p.get("source") or "") == "author"),
                "team_members": sum(1 for p in personas_data
                                    if (p.get("source") or "") in ("team_member", "founder")),
                "avg_confidence": round(sum((p["custom_metadata"]["confidence"])
                                            for p in scored) / len(scored)) if scored else 0,
                "high_confidence": sum(1 for p in scored
                                       if p["custom_metadata"]["confidence"] >= 70),
                "pages_scraped": len(pages_text),
                "team_pages": sum(1 for k in kinds.values() if k == PAGE_TEAM),
            },
        )
        logger.info(
            "Attached persona social links and avatars",
            extra={"with_links": sum(1 for p in personas_data
                                     if p.get("linkedin_url") or p.get("custom_metadata")),
                   "with_avatar": sum(1 for p in personas_data if p.get("avatar_url")),
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

    # Not a staticmethod: the three extraction passes read the page-type split
    # (_team_text, _author_text, _leadership_text) that _fast_or_fallback_scrape
    # stores on the instance.
    async def _default_brand_voice_generator(self, content: str) -> Optional[BrandSchema]:
        if not content.strip():
            return None

        # Defined at method level, not inside _invoke_model: all three
        # extraction passes share it, and they are siblings rather than
        # nested, so a prompt scoped to one of them is invisible to the
        # other two.
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
A valid persona MUST have a real human name consisting of at least a first and last name, copied exactly as the page writes it. Never supply a placeholder or specimen name: if you find yourself about to write a stock name, the correct output is an empty list instead.
Single words, job titles, roles, or descriptions are NOT valid names.

RULE 3 — STRICTLY FORBIDDEN PERSONAS (these are NEVER valid — DO NOT add them to the personas list at all):
Do NOT create a persona entry for any of the following. Simply OMIT them from the list entirely — they belong conceptually in 'target_audience' or 'customer_profile', NOT personas:
  - Named individuals who ONLY appear as customer testimonial/review/case-study contributors (a quote attributed to someone with a city or company after their name, praising the product). These are customers, not brand representatives. Even though they have a real name, do NOT add them to the personas list under any circumstances. If you do include such a person, you MUST set source='testimonial' so the system can discard them — never relabel them as 'expert' or 'team_member'.
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
- tone_of_voice: How this person writes, in two parts. First the style itself (e.g. "Conversational and instructional"). Then, for anyone who actually writes - source 'author', or a team member with articles in the content - add the SIGNATURE VOCABULARY they reach for: the specific words and phrases that recur across their pieces, quoted from the content, not invented. Example: "Conversational and instructional; favours 'step-by-step', 'beginner-friendly', 'let us dive in', 'pro tip'". If you cannot see enough of their writing to identify recurring vocabulary, give the style alone rather than guessing phrases.
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

        async def _invoke_model() -> BrandSchema:
            from langchain_core.messages import SystemMessage, HumanMessage
            
            # Extraction, not generation: the same page must yield the same
            # people every time. At OpenAI's default temperature (1.0) three
            # runs over identical css-tricks.com content returned 11, then 5,
            # then 3 personas, which made every before/after comparison
            # unreadable and every bug report unreproducible.
            model = load_model(temperature=0)
            structured = model.with_structured_output(BrandSchema)
            


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
                     "each of them as a persona with source='author'. Leave the "
                     "BRAND fields empty, but fill every PERSONA field you can from "
                     "their writing: professional_title, areas_of_expertise, bio, "
                     "demographics, pain_points, goals, behaviors and tone_of_voice. "
                     "tone_of_voice is REQUIRED and must give both the style and "
                     "their SIGNATURE VOCABULARY - the recurring words and phrases "
                     "quoted from their articles, e.g. \"Conversational and "
                     "instructional; favours 'step-by-step', 'beginner-friendly', "
                     "'pro tip'\". Quote only phrases that actually appear.\n\n")
                    + author_text)),
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