from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from uuid import UUID

import tldextract
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.cache.decorators import invalidate_cache_key
from src.api.models.knowledge_models.knowledge_model import BrandVoice
from src.api.models.knowledge_models.persona_model import Persona
from src.api.schema.brand_voice_schema import BrandSchema
from src.flow.engines.competitors.pipeline import discover_competitors, select_display_competitors
from src.flow.model.llm_manager import load_model
from src.flow.model.runaway import ainvoke_watched
from src.services.sse_service import (
    emit_pipeline_complete,
    emit_step_failure,
    emit_step_start,
    emit_step_success,
)
from src.services.workspace_favicon import delete_favicon, find_favicon, store_favicon
from src.utils.fast_scraper import (
    _GENERIC_BYLINES,
    _ROLE_WORD_RE,
    RECENT_SINCE_YEAR,
    REQUEST_HEADERS,
    extract_founder_credits,
    initials_avatar,
)
from src.utils.fast_scraper import (
    _is_person_name as _fs_is_person_name,
)
from src.utils.fast_scraper import (
    declared_authors as _fs_declared_authors,
)
from src.utils.helper import web_page_scraper
from src.utils.logger import logger
from src.utils.site_compliance import assess_site_compliance
from src.utils.url_validator import public_client

ScrapeCallable = Callable[[str], Awaitable[Tuple[List[Any], List[Any]]]]
BrandVoiceGeneratorCallable = Callable[[str], Awaitable[Optional[BrandSchema]]]


@dataclass
class _ScrapeResult:
    chunks: List[Any]
    content: str
    metadata: Dict[str, Any]


_ARCHETYPE_KEYWORDS = {
    "owner",
    "manager",
    "user",
    "customer",
    "client",
    "buyer",
    "blogger",
    "professional",
    "entrepreneur",
    "startup",
    "business",
    "store",
    "shop",
    "target",
    "audience",
    "segment",
    "persona",
    "marketer",
    "executive",
    "director",
    "officer",
    "employee",
    "worker",
    "freelancer",
    "consultant",
    "john doe",
    "jane doe",
    "placeholder",
    "sample user",
}

FALLBACK_MIN_SECONDS = 15.0
FALLBACK_MAX_SECONDS = 30.0
PERSIST_RESERVE_SECONDS = 5.0
PIPELINE_BUDGET_SECONDS = 90.0
EXTRACTION_BUDGET_SECONDS = 35.0
_ARTICLES_PER_AUTHOR = 2
_FEED_BUDGET_SECONDS = 4.0
_BROWSER_START_DELAY_SECONDS = 4.0
_BROWSER_CANCEL_GRACE_SECONDS = 5.0
_MAX_DERIVED_ARCHIVES = 4
_DERIVED_ARCHIVE_BUDGET = 5.0
_REFUSED_RENDER_MAX_PAGES = 8
# Per-person analysis: a persona still missing fields after the site-wide passes
# is analysed again over only its own pages - profile, articles, team blurb.
_MAX_ANALYSED_PERSONAS = 15
_ANALYSIS_BUDGET_SECONDS = 20.0
_ANALYSIS_FETCH_SECONDS = 6.0
_ANALYSIS_MENTION_PAGES = 4
_ANALYSIS_ARTICLES = 3
_ANALYSIS_ARTICLE_CHARS = 3_000
_ANALYSIS_PROFILE_CHARS = 4_000
_ANALYSIS_WINDOW_BEFORE = 200
_ANALYSIS_WINDOW_AFTER = 1_000
_ANALYSIS_MIN_EVIDENCE_CHARS = 200
_ANALYSED_FIELDS = (
    "professional_title",
    "bio",
    "description",
    "areas_of_expertise",
    "tone_of_voice",
    "demographics",
    "pain_points",
    "goals",
    "behaviors",
)
_GENERIC_TITLES = {"author", "staff", "editorial staff", "contributor", "expert"}
# Descriptions the pipeline writes for a name it found in code, before any
# model has read what the person wrote.
_PLACEHOLDER_DESCRIPTION = re.compile(r"^(Credited as the author of|Publishes under this name on)")
# Persona columns with a length limit; a longer value fails the whole insert.
_BOUNDED_TEXT = {"name": 255, "full_name": 255, "professional_title": 255, "tone_of_voice": 255}
_BOUNDED_URL = {"linkedin_url": 500, "avatar_url": 500, "email": 320}
_REFUSED_RENDER_MIN_SECONDS = 8.0
_REFUSED_RENDER_MAX_SECONDS = 20.0

_NAME_TITLES = {
    "dr",
    "dr.",
    "mr",
    "mr.",
    "ms",
    "ms.",
    "mrs",
    "mrs.",
    "prof",
    "prof.",
    "sir",
    "miss",
    "mx",
    "mx.",
}


def _identity_key(name: str) -> str:
    words = re.sub(r"[^\w\s.]", " ", (name or "").lower()).split()
    words = [w for w in words if w not in _NAME_TITLES]
    return " ".join(words)


def _completeness(persona: dict) -> int:
    return sum(1 for v in persona.values() if v not in (None, "", [], {}))


def _last_name(name: str) -> str:
    """Return the last word of a cleaned name (the surname)."""
    parts = _identity_key(name).split()
    return parts[-1] if parts else ""


def _role_key(persona: dict) -> str:
    """Normalised professional title, used as a secondary collision signal."""
    title = (persona.get("professional_title") or persona.get("description") or "").lower().strip()
    return re.sub(r"[^\w\s]", " ", title).split()[0] if title else ""


def _first_name(name: str) -> str:
    parts = _identity_key(name).split()
    return parts[0] if parts else ""


def _names_likely_same_person(name1: str, name2: str) -> bool:
    last1, last2 = _last_name(name1), _last_name(name2)
    if not last1 or not last2 or last1 != last2:
        return False
    f1, f2 = _first_name(name1), _first_name(name2)
    if not f1 or not f2:
        return False
    if f1 == f2:
        return True
    if (len(f1) >= 3 and f2.startswith(f1)) or (len(f2) >= 3 and f1.startswith(f2)):
        return True
    # Spelling variants (Mobeen / Moobeen) share consonants. Short skeletons
    # collide across different people - Omar and Amir are both "mr", Mona and
    # Mina both "mn" - so require three consonants and the same first letter.
    sk1 = re.sub(r"[aeiouy]+", "", f1)
    sk2 = re.sub(r"[aeiouy]+", "", f2)
    return len(sk1) >= 3 and sk1 == sk2 and f1[0] == f2[0]


def _merge_persona_records(winner: dict, loser: dict) -> dict:
    merged = dict(winner)
    p_title = (merged.get("professional_title") or "").strip()
    s_title = (loser.get("professional_title") or "").strip()
    generic_titles = {"author", "staff", "editorial staff", "contributor", "expert"}
    if (not p_title or p_title.lower() in generic_titles) and (
        s_title and s_title.lower() not in generic_titles
    ):
        merged["professional_title"] = s_title
    for key, val in loser.items():
        if val and not merged.get(key):
            merged[key] = val
        elif (
            key == "areas_of_expertise"
            and isinstance(val, list)
            and isinstance(merged.get(key), list)
        ):
            # A new list: dict() copies shallowly, and appending in place would
            # also change the winner's own record.
            combined = list(merged[key])
            existing = {str(item).lower() for item in combined}
            for item in val:
                if str(item).lower() not in existing:
                    combined.append(item)
                    existing.add(str(item).lower())
            merged[key] = combined
    return merged


def _dedupe_personas(personas: list[dict]) -> list[dict]:
    # Pass 1: exact identity-key match (same name, different capitalisation/titles)
    best: dict[str, dict] = {}
    order: list[str] = []
    for persona in personas:
        key = _identity_key(persona.get("name") or "")
        if not key:
            continue
        if key not in best:
            best[key] = persona
            order.append(key)
        else:
            primary, secondary = (
                (persona, best[key])
                if _completeness(persona) > _completeness(best[key])
                else (best[key], persona)
            )
            best[key] = _merge_persona_records(primary, secondary)

    # Pass 2: nickname / phonetic match (Moobeen vs Mobeen, Ben vs Benjamin)
    i = 0
    while i < len(order):
        key_i = order[i]
        p_i = best[key_i]
        name_i = p_i.get("name") or ""
        j = i + 1
        while j < len(order):
            key_j = order[j]
            p_j = best[key_j]
            name_j = p_j.get("name") or ""
            if _names_likely_same_person(name_i, name_j):
                if _completeness(p_j) > _completeness(p_i) or (
                    len(name_j) > len(name_i) and _completeness(p_j) == _completeness(p_i)
                ):
                    best[key_i] = _merge_persona_records(p_j, p_i)
                else:
                    best[key_i] = _merge_persona_records(p_i, p_j)
                del best[key_j]
                order.pop(j)
            else:
                j += 1
        i += 1

    return [best[k] for k in order]


def _format_persona_for_frontend(p_obj: Persona) -> dict:
    meta = p_obj.custom_metadata or {}
    return {
        "id": str(p_obj.id),
        "name": p_obj.name,
        "full_name": p_obj.full_name or p_obj.name,
        "professional_title": p_obj.professional_title,
        "bio": p_obj.bio,
        "description": p_obj.description,
        "tone_of_voice": p_obj.tone_of_voice,
        "areas_of_expertise": p_obj.areas_of_expertise or [],
        "linkedin_url": p_obj.linkedin_url,
        "avatar_url": p_obj.avatar_url,
        "avatar_source": p_obj.avatar_source,
        "demographics": p_obj.demographics,
        "pain_points": p_obj.pain_points,
        "goals": p_obj.goals,
        "behaviors": p_obj.behaviors,
        "persona_type": meta.get("persona_type") or "author",
        "confidence": meta.get("confidence", 85),
        "confidence_signals": meta.get("confidence_signals") or ["verified_source"],
        "custom_metadata": meta,
    }


_EXTERNAL_ROLE_PHRASES = (
    "keynote speaker",
    "keynote at",
    "guest speaker",
    "speaker at",
    "speaking at",
    "presenter at",
    "panelist",
    "panellist",
    "guest author",
    "guest post",
    "guest contributor",
    "interviewed",
    "featured guest",
    "podcast guest",
    "webinar guest",
    "ambassador",
    "spokesperson for",
)

_COLLECTIVE_SUFFIXES = (
    "team",
    "staff",
    "crew",
    "desk",
    "editors",
    "editorial",
    "group",
    "squad",
    "collective",
    "council",
    "committee",
    "board",
    "department",
    "dept",
    "support",
    "admins",
    "moderators",
    "contributors",
    "authors",
    "writers",
)
_COLLECTIVE_WORDS = {
    "team",
    "staff",
    "editorial",
    "admin",
    "administrator",
    "moderator",
    "support",
    "contributors",
    "authors",
    "writers",
    "everyone",
    "us",
}

_PUBLICATION_WORDS = {
    "perspectives",
    "insights",
    "review",
    "reviews",
    "journal",
    "magazine",
    "digest",
    "report",
    "reports",
    "times",
    "post",
    "posts",
    "news",
    "daily",
    "weekly",
    "monthly",
    "quarterly",
    "blog",
    "press",
    "media",
    "network",
    "today",
    "wire",
    "watch",
    "beat",
    "gazette",
    "chronicle",
    "tribune",
    "bulletin",
    "dispatch",
    "observer",
    "standard",
    "standards",
    "council",
    "institute",
    "foundation",
    "association",
    "society",
    "alliance",
}


def _is_publication_name(name: str, brand: str = "") -> bool:
    words = [w for w in re.sub(r"[^\w\s]", " ", (name or "").lower()).split() if w]
    if not words:
        return False
    if words[-1] in _PUBLICATION_WORDS:
        return True
    collapsed = re.sub(r"[^a-z0-9]", "", brand.lower())
    return bool(
        collapsed and len(words) > 1 and collapsed.startswith(re.sub(r"[^a-z0-9]", "", words[0]))
    )


def _is_heading_not_name(name: str) -> bool:
    words = [w for w in re.sub(r"[^\w\s]", " ", (name or "").lower()).split() if w]
    heading_words = {
        "hear",
        "from",
        "our",
        "with",
        "about",
        "meet",
        "join",
        "see",
        "read",
        "more",
        "why",
        "how",
        "what",
        "the",
        "us",
        "your",
    }
    return any(w in heading_words for w in words)


def _fs_brand(url: str) -> str:
    return re.sub(r"[^a-z0-9]", "", tldextract.extract(url or "").domain.lower())


def _is_collective(name: str) -> bool:
    words = [w for w in re.sub(r"[^\w\s]", " ", (name or "").lower()).split() if w]
    if not words:
        return True
    if words[-1] in _COLLECTIVE_SUFFIXES:
        return True
    return any(w in _COLLECTIVE_WORDS for w in words)


def _calculate_recommendation_rank(p: dict) -> tuple:
    """Rank by what the site shows a person contributed, most first.

    Order: recent articles, articles credited to them, an author archive page,
    then the evidence confidence. A job title earns nothing on its own.
    """
    meta = p.get("custom_metadata") or {}
    evidence = meta.get("evidence") or {}
    signals = set(meta.get("confidence_signals") or [])
    return (
        int(evidence.get("recent_article_count") or 0),
        int(evidence.get("article_count") or 0),
        1 if ("author_profile" in signals or evidence.get("author_profile")) else 0,
        float(meta.get("confidence") or 0.0),
        _completeness(p),
        -len(p.get("name") or ""),
    )


_REVIEW_CONTEXT = re.compile(
    r"(?i)(customer\s+review|verified\s+(?:buyer|purchase|customer)|google\s+review|"
    r"trustpilot|yelp|left\s+a\s+review|wrote\s+a\s+review|rated\s+us|"
    r"\d\s*(?:out\s+of\s*)?5\s*stars?|★|reviewed\s+by|testimonial|"
    r"(?:highly|would)\s+recommend|recommends?\s+(?:us|them|this)|"
    r"happy\s+(?:customer|client)|satisfied\s+(?:customer|client))"
)
_REVIEW_WINDOW = 60
_REVIEW_HEADING = re.compile(
    r"(?i)(customer\s+reviews?|testimonials?|what\s+(?:our\s+)?"
    r"(?:clients?|customers?|people)\s+say|client\s+stories|success\s+stories|"
    r"reviews?\s+from\s+our|hear\s+from\s+our\s+(?:customers?|clients?))"
)
_REVIEW_BLOCK_CHARS = 1500


def _review_regions(text: str) -> list:
    return [(m.start(), m.start() + _REVIEW_BLOCK_CHARS) for m in _REVIEW_HEADING.finditer(text)]


_EVIDENCE_SIGNALS = {
    "declared_byline",
    "author_profile",
    "on_team_page",
    "founder_credit",
    "stated_role",
}

_PERSON_ROLE_WORDS = (
    "founder",
    "co-founder",
    "cofounder",
    "chair",
    "chairman",
    "chairwoman",
    "ceo",
    "cto",
    "coo",
    "cfo",
    "cmo",
    "cio",
    "cso",
    "president",
    "vice president",
    "vp",
    "director",
    "head of",
    "chief",
    "partner",
    "manager",
    "lead",
    "engineer",
    "developer",
    "editor",
    "writer",
    "specialist",
    "architect",
    "consultant",
    "analyst",
    "designer",
    "executive",
    "officer",
    "principal",
)
_PERSON_ROLE_RE = re.compile(
    r"\b(?:"
    + "|".join(re.escape(r) for r in sorted(_PERSON_ROLE_WORDS, key=len, reverse=True))
    + r")\b",
    re.I,
)
_DEPARTMENT_RE = re.compile(
    r"(?i)\b(?:education|engagement|product|technology|marketing|sales|"
    r"operations?|engineering|design|finance|legal|people|hr|security|"
    r"standards|communications?|content|growth|support|strategy|research|"
    r"development|delivery|risk|compliance|quality|data|platform|"
    r"experience|success|partnerships?|community|editorial)\b"
)
_ROLE_WINDOW = 300


def _names_other_employer(role: str, brand: str) -> bool:
    """Whether a role string names an employer other than this brand.

    Handles "COO at KitBash3D" and the bare "COO, KitBash3D + Greyscalegorilla"
    that client testimonials print under the quote.
    """
    if not role:
        return False
    # Split only where an employer follows. "Head of Product" is one job.
    segments = [seg.strip() for seg in re.split(r"[,|·•@]| at | for ", role) if seg.strip()]
    for seg in segments[1:] if len(segments) > 1 else []:
        if _PERSON_ROLE_RE.search(seg.lower()) or _DEPARTMENT_RE.search(seg.lower()):
            continue
        named = re.sub(r"[^a-z0-9]", "", seg.lower())
        if not named or len(named) < 3:
            continue
        if brand and (brand in named or named.startswith(brand)):
            return False
        return True
    return False


def _review_mentions(name: str, pages_text: dict) -> Tuple[int, int]:
    """(mentions of ``name`` inside review/testimonial context, all mentions).

    Byline and author-profile stamp lines count as mentions but never as review
    context, so a post opening with "we highly recommend" cannot turn its own
    author into a testimonial.
    """
    in_review = total = 0
    if not name:
        return 0, 0
    for text in pages_text.values():
        if name not in text:
            continue
        regions = _review_regions(text)
        start = 0
        while True:
            i = text.find(name, start)
            if i < 0:
                break
            start = i + len(name)
            total += 1
            line_start = text.rfind("\n", 0, i) + 1
            if text.startswith(("Article author:", "Author profile:"), line_start):
                continue
            window = text[max(0, i - _REVIEW_WINDOW) : i + len(name) + _REVIEW_WINDOW]
            if _REVIEW_CONTEXT.search(window) or any(a <= i < b for a, b in regions):
                in_review += 1
    return in_review, total


def _role_near_name(name: str, title: str, pages_text: dict) -> bool:
    """Whether the stated title, or a role word from it, is printed within
    ``_ROLE_WINDOW`` characters of the name on a fetched page."""
    wanted = [title.lower()] + [m.group(0).lower() for m in _PERSON_ROLE_RE.finditer(title or "")]
    wanted = [w for w in dict.fromkeys(wanted) if w.strip()]
    if not name or not wanted:
        return False
    pattern = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in wanted) + r")\b")
    lowered_name = name.lower()
    for text in pages_text.values():
        lowered = text.lower()
        start = 0
        while True:
            i = lowered.find(lowered_name, start)
            if i < 0:
                break
            if pattern.search(
                lowered, max(0, i - _ROLE_WINDOW), i + len(lowered_name) + _ROLE_WINDOW
            ):
                return True
            start = i + len(lowered_name)
    return False


def _looks_external(persona: dict) -> bool:
    if (persona.get("source") or "").strip().lower() != "expert":
        return False
    haystack = " ".join(
        str(persona.get(f) or "") for f in ("description", "bio", "professional_title", "behaviors")
    ).lower()
    return any(phrase in haystack for phrase in _EXTERNAL_ROLE_PHRASES)


def _filter_valid_personas(personas: list[dict], brand_url: str = "") -> list[dict]:
    _brand_token = tldextract.extract(brand_url).domain if brand_url else ""
    valid = []
    for p in personas:
        name: str = (p.get("name") or "").strip()
        if not name or len(name) < 2:
            continue

        lowered_name = name.lower().strip()
        if lowered_name in {"john doe", "jane doe", "admin", "author", "placeholder"}:
            continue

        source: str = (p.get("source") or "").strip().lower()
        if source == "testimonial":
            continue
        if _looks_external(p):
            continue
        if _is_heading_not_name(name):
            continue
        # Slugs ("mobeen-abdullahs"), labels ("Categories: wordpress") and
        # other strings that are not written like a person's name.
        if not _fs_is_person_name(name):
            continue
        if _is_publication_name(name, _brand_token):
            continue
        if _is_collective(name):
            # A collective byline is useful page metadata, but it is not a
            # real person and must never surface as a persona.
            continue
        words = name.lower().split()
        if any(w in _ARCHETYPE_KEYWORDS for w in words):
            continue

        # Sanitize professional_title: never allow collective mastheads as titles.
        # A title naming an individual role ("Editorial Director", "Team Lead",
        # "Staff Engineer") is the person's real title and stays.
        title = (p.get("professional_title") or "").strip()
        if title:
            t_low = title.lower()
            if not _ROLE_WORD_RE.search(title) and (
                t_low in _GENERIC_BYLINES
                or t_low in _COLLECTIVE_WORDS
                or any(
                    t_low.endswith(s)
                    for s in (" staff", " team", " desk", " editors", " department", " dept")
                )
                or any(t_low.startswith(s) for s in ("editorial ", "staff ", "team "))
            ):
                p["professional_title"] = "Author"
        elif source == "author":
            p["professional_title"] = "Author"

        valid.append(p)

    return _dedupe_personas(valid)


def _profile_name(text: str) -> str:
    """The name on an "Author profile: <name> | posts=N" stamp."""
    return text.split("\n", 1)[0][len("Author profile:") :].split("|")[0].strip()


_PROFILE_PLACEHOLDER = re.compile(r"\n[^\n]* is credited as an author on [^\n]*\.$")


def _profile_rank(text: str) -> tuple:
    """Order profile texts so a fetched page beats the one-line placeholder
    written for it before the fetch, and a longer page beats a shorter one."""
    return (bool(text) and not _PROFILE_PLACEHOLDER.search(text), len(text))


def _is_blank(value: Any) -> bool:
    return value in (None, "", [], {})


def _fields_to_analyse(persona: dict) -> list[str]:
    missing = [f for f in _ANALYSED_FIELDS if _is_blank(persona.get(f))]
    if _PLACEHOLDER_DESCRIPTION.match(persona.get("description") or ""):
        missing.append("description")
    if (persona.get("professional_title") or "").strip().lower() in _GENERIC_TITLES:
        missing.append("professional_title")
    return missing


def _apply_analysis(persona: dict, analysis: dict) -> list[str]:
    """Fill the persona's missing fields from its per-person analysis.

    Never overwrites a value an earlier pass or the site already gave, except a
    placeholder description and a generic "Author" title. Returns the fields
    that were filled.
    """
    filled = []
    for field in _fields_to_analyse(persona):
        value = analysis.get(field)
        if isinstance(value, str):
            value = value.strip()
        if _is_blank(value):
            continue
        if field == "professional_title" and value.lower() in _GENERIC_TITLES:
            if not _is_blank(persona.get(field)):
                continue
        persona[field] = value
        filled.append(field)
    return filled


def _bounded(field: str, value: Optional[str]) -> Optional[str]:
    """Fit a value to its column: text is cut at a word, a URL too long to
    store is dropped rather than cut into a broken link."""
    if value is None:
        return None
    if field in _BOUNDED_URL:
        return value if len(value) <= _BOUNDED_URL[field] else None
    limit = _BOUNDED_TEXT.get(field)
    if limit is None or len(value) <= limit:
        return value
    return value[:limit].rsplit(" ", 1)[0].rstrip(" ,;")


_PERSONA_ANALYSIS_PROMPT = """You are building the author profile of ONE real person from pages on the brand's own website: their profile page, what the site prints around their name, and articles published under their byline.

Analyse the supplied text and fill each field from it:
- professional_title: the role the site gives them (e.g. 'Founder', 'Head of Content'). If they only appear as an article byline, 'Author'.
- bio: 1-2 factual sentences on who they are and what they write about or do, based only on the supplied text.
- description: one short line naming their role and focus.
- areas_of_expertise: 3-6 concrete topics their articles cover or their profile names.
- tone_of_voice: 2-4 comma-separated adjectives for how their articles are written. Only when ARTICLES WRITTEN BY them are supplied.
- demographics: the readers their articles are written for (e.g. 'Beginner WordPress site owners, small-business marketers').
- pain_points: comma-separated reader problems their articles address.
- goals: comma-separated outcomes their articles guide readers toward.
- behaviors: comma-separated working methods their articles demonstrate (e.g. 'step-by-step tutorials, tests changes on a staging site first').

Rules:
- Use only the supplied text. Never fill a gap from general knowledge of the role, industry or brand.
- Ignore text about other people, customer reviews and testimonials.
- Leave a field empty when the supplied text does not support it."""


class WorkspacePipeline:
    """Background pipeline responsible for workspace onboarding tasks."""

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
        brand_voice_generator: Optional[BrandVoiceGeneratorCallable] = None,
    ) -> None:
        self.db = db
        self.operation_id = operation_id
        self.workspace_id = workspace_id
        self.url = url
        self.user_id = user_id
        self._scraper = scraper or self._default_scraper
        self._brand_voice_generator = brand_voice_generator or self._default_brand_voice_generator
        # The per-person analysis calls the same model, so it runs only with
        # the default extraction, never under an injected generator.
        self._use_default_llm = brand_voice_generator is None
        self.scope = "workspace"

    async def run(self) -> None:
        """Execute the workspace pipeline and stream progress via SSE."""
        logger.info(
            "Workspace pipeline started",
            extra={"workspace_id": str(self.workspace_id), "url": self.url},
        )
        brand_voice_schema: Optional[BrandSchema] = None
        discovered_competitors: Optional[List[dict]] = None

        try:
            started = asyncio.get_event_loop().time()
            self._started = started
            scrape_result = await self._scrape_website()
            brand_voice_schema = await self._extract_brand_voice(scrape_result.content)
            await self._persist_brand_voice(brand_voice_schema)
            await self._embed_brand_voice(brand_voice_schema)

            # Runs strictly after the brand-voice flow above completes, as a fully
            # independent step — not concurrent with it — so it can never affect
            # brand-voice extraction's behavior, timing, or SSE step reporting.
            discovered_competitors = await self._discover_competitors()
            if discovered_competitors is not None:
                await self._persist_competitors([c["domain"] for c in discovered_competitors])

            # The site's favicon for the workspace switcher: best-effort and
            # independent, like the competitor step; it never fails the pipeline.
            replaced_favicon = await self._store_favicon()

            payload: Dict[str, Any] = {"workspace_id": str(self.workspace_id)}
            if brand_voice_schema:
                bv_dict = brand_voice_schema.model_dump()
                bv_dict["personas"] = []
                payload["brand_voice"] = bv_dict

            payload["personas"] = getattr(self, "_extracted_personas", []) or []

            if discovered_competitors is not None:
                competitor_domains = [c["domain"] for c in discovered_competitors]
                if "brand_voice" in payload:
                    payload["brand_voice"]["competitors"] = competitor_domains
                else:
                    payload["brand_voice"] = {"competitors": competitor_domains}
                payload["top_competitors"] = discovered_competitors

            await self.db.commit()
            if replaced_favicon:
                # The row now names the new file, so the old one belongs to nobody.
                await delete_favicon(replaced_favicon)

            # The workspace detail API serves brand_voice from a 10-minute
            # Redis cache (workspace:brand_voice:{id}). Without this
            # invalidation a refresh keeps serving the OLD brand voice until
            # the cache expires — the UI then looks "not fully updated".
            try:
                await invalidate_cache_key(f"workspace:brand_voice:{self.workspace_id}")
            except Exception as exc:  # noqa: BLE001 - cache invalidation is best-effort
                logger.warning(
                    "Failed to invalidate brand voice cache after refresh: %r",
                    exc,
                )

            await emit_pipeline_complete(
                operation_id=self.operation_id,
                scope=self.scope,
                message="Workspace creation pipeline completed successfully",
                payload=payload,
                user_id=self.user_id,
            )
            logger.info(
                "Workspace pipeline completed", extra={"workspace_id": str(self.workspace_id)}
            )

        except Exception as exc:  # noqa: BLE001 - propagate for caller logging
            await self.db.rollback()
            logger.error(
                "Workspace pipeline failed",
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
                step="pipeline",
                message="Workspace creation pipeline encountered an error.",
                error=None,
                user_id=self.user_id,
            )
            raise

    async def _store_favicon(self) -> Optional[str]:
        """Fetch the site's favicon once and keep it with the workspace.

        Returns the previous favicon's object name when a refresh replaced it, so
        the caller removes that file once the new name is committed. Never raises.
        """
        try:
            found = await find_favicon(getattr(self, "_homepage_html", None), self.url)
            if not found:
                logger.info(
                    "No usable favicon on the site", extra={"workspace_id": str(self.workspace_id)}
                )
                return None
            object_name = await store_favicon(str(self.workspace_id), found["data"], found["mime"])
            if not object_name:
                return None
            from src.api.models.workspace_models.workspace_model import WorkspaceModel

            workspace = await self.db.get(WorkspaceModel, self.workspace_id)
            if workspace is None:
                return None
            previous, workspace.favicon_url = workspace.favicon_url, object_name
            await self.db.flush()
            return previous if previous and previous != object_name else None
        except Exception as exc:  # noqa: BLE001 - a favicon is a nicety, never a failure
            logger.warning(
                "Favicon step failed: %r", exc, extra={"workspace_id": str(self.workspace_id)}
            )
            return None

    async def _scrape_website(self) -> _ScrapeResult:
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
            self._homepage_html = raw_html
            await self._merge_feed_authors()
            self._seed_authors_from_stamps()
        except Exception:
            await self._cancel_browser("scrape failed")
            feed_task = getattr(self, "_feed_task", None)
            if feed_task is not None and not feed_task.done():
                feed_task.cancel()
            logger.error("Scrape failed", exc_info=True)
            await emit_step_failure(
                operation_id=self.operation_id,
                scope=self.scope,
                step="scrape",
                message="We couldn't retrieve the website content. Please verify the URL and try again.",
                error=None,
                user_id=self.user_id,
            )
            raise

        title = None
        if raw_html:
            try:
                from bs4 import BeautifulSoup

                title_tag = BeautifulSoup(raw_html, "html.parser").title
                title = title_tag.get_text(strip=True) if title_tag else None
            except Exception:
                pass

        compliance = await assess_site_compliance(self.url, raw_html)
        self._site_compliance = compliance
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

        return _ScrapeResult(chunks=[], content=content, metadata=metadata)

    async def _browser_attempt(self) -> list:
        await asyncio.sleep(_BROWSER_START_DELAY_SECONDS)
        for window in (FALLBACK_MAX_SECONDS, FALLBACK_MIN_SECONDS):
            try:
                _, attempt = await asyncio.wait_for(self._scraper(self.url), timeout=window)
                good = [
                    r
                    for r in attempt or []
                    if getattr(r, "success", False) and getattr(r, "markdown", "")
                ]
                if good:
                    return good
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                continue
        return []

    async def _feed_attempt(self) -> dict:

        from src.utils.fast_scraper import SITEMAP_TIMEOUT, discover_feed_authors

        try:
            # The site's own address: public_client connects only to the address it checked.
            async with public_client(headers=REQUEST_HEADERS, follow_redirects=True) as client:
                home_html = ""
                try:
                    resp = await client.get(self.url, timeout=SITEMAP_TIMEOUT)
                    if resp.status_code == 200:
                        home_html = resp.text
                except Exception:
                    pass
                return await discover_feed_authors(
                    client, self.url, home_html, budget_seconds=_FEED_BUDGET_SECONDS
                )
        except Exception:
            return {}

    def _seed_authors_from_stamps(self) -> None:
        from src.utils.fast_scraper import _is_collective_name

        pages = getattr(self, "_page_text_by_url", None) or {}
        seeded = getattr(self, "_fallback_authors", None) or []
        known = {(p.get("name") or "").lower() for p in seeded}
        for text in pages.values():
            for who in _fs_declared_authors(text):
                if who.lower() not in known:
                    known.add(who.lower())
                    seeded.append(
                        {
                            "name": who,
                            "description": f"Credited as the author of pages on {_fs_brand(self.url) or 'this site'}",
                            "source": "author",
                            "is_collective": _is_collective_name(who),
                        }
                    )
        self._fallback_authors = seeded

    async def _merge_feed_authors(self) -> None:
        from src.utils.fast_scraper import _is_collective_name

        task = getattr(self, "_feed_task", None)
        if task is None:
            return
        try:
            found = await task
        except Exception:
            return
        if not found:
            return
        pages = getattr(self, "_page_text_by_url", None) or {}
        seeded = getattr(self, "_fallback_authors", None) or []
        known = {(p.get("name") or "").lower() for p in seeded}
        for name, links in found.items():
            key = f"{self.url.rstrip('/')}/feed#author={name}"
            if key not in pages:
                pages[key] = f"Article author: {name}\n" + "\n".join(links[:_ARTICLES_PER_AUTHOR])
            if name.lower() not in known:
                known.add(name.lower())
                seeded.append(
                    {
                        "name": name,
                        "description": f"Credited as the author of posts in {_fs_brand(self.url) or 'this site'}'s feed",
                        "source": "author",
                        "is_collective": _is_collective_name(name),
                    }
                )
        self._page_text_by_url = pages
        self._fallback_authors = seeded

    async def _fast_or_fallback_scrape(self) -> Tuple[str, str, bool]:
        from src.utils.fast_scraper import ABOUT_KEYWORDS, DEFAULT_BUDGET_SECONDS, TEAM_KEYWORDS
        from src.utils.fast_scraper import scrape_site as fast_scrape_site
        from src.utils.helper import _looks_blocked

        self._feed_task = asyncio.create_task(self._feed_attempt())

        try:
            result = await fast_scrape_site(
                self.url,
                max_about_pages=2,
                about_keywords=ABOUT_KEYWORDS + TEAM_KEYWORDS,
                home_max_chars=6_000,
                about_max_chars=4_000,
                team_max_chars=12_000,
                max_blog_posts=25,
                blog_index_max_chars=1_500,
                blog_post_max_chars=1_500,
                strip_footer=False,
                sample_head_and_tail=True,
                priority_keywords=TEAM_KEYWORDS,
                strip_testimonials=True,
                budget_seconds=DEFAULT_BUDGET_SECONDS,
            )
        except Exception as exc:
            logger.warning("Fast scrape raised, proceeding to browser fallback: %s", exc)
            result = {"pages": {}, "raw_home_html": "", "raw_pages": {}}

        pages = result.get("pages") or {}
        self._raw_pages = result.get("raw_pages") or {}

        # Posts, author archives and team pages the site refused to plain HTTP
        # (403, bot challenge) are rendered in a real browser, so a partly
        # blocked blog still yields its bylines.
        refused = self._refused_pages_worth_rendering(
            result.get("refused") or {}, pages, result.get("raw_home_html") or ""
        )
        if refused:
            await self._render_refused_pages(refused, pages, self._raw_pages)
        self._index_pages(pages)

        combined = "\n\n".join(f"URL: {u}\n{txt}" for u, txt in pages.items() if txt.strip())
        if not combined.strip() or len(combined) < 300 or _looks_blocked(combined):
            logger.info("Fast scrape was thin; attempting one standard browser render.")
            self._browser_task = asyncio.create_task(self._browser_attempt())
            try:
                results = await asyncio.wait_for(
                    asyncio.shield(self._browser_task), timeout=FALLBACK_MAX_SECONDS
                )
            except Exception:
                results = []

            if not results:
                return combined, result.get("raw_home_html") or "", False

            successes = [r for r in results or [] if getattr(r, "success", False)]
            by_url, html_by_url = {}, {}
            for r in successes:
                p_url = str(getattr(r, "url", "") or self.url)
                md = str(getattr(r, "markdown", "") or "")
                if md.strip():
                    by_url[p_url] = md
                    html_by_url[p_url] = str(getattr(r, "html", "") or "")

            raw_html = getattr(successes[0], "html", "") if successes else ""
            content = self._sample_content_for_extraction(
                "\n\n".join(f"URL: {u}\n{t}" for u, t in by_url.items())
            )

            from src.utils.fast_scraper import _is_collective_name as _fs_is_collective_name
            from src.utils.fast_scraper import (
                extract_byline,
                extract_collective_byline,
                extract_publish_year,
            )

            seeded_authors: dict = {}
            for p_url, markdown in list(by_url.items()):
                p_html = html_by_url.get(p_url) or ""
                if not p_html:
                    continue
                person = extract_byline(p_html, p_url)
                masthead = extract_collective_byline(p_html, p_url)
                authors = [person] if person else ([masthead] if masthead else [])
                if authors:
                    year = extract_publish_year(p_html)
                    stamp = "".join(
                        f"Article author: {a}{f' | {year}' if year else ''}\n" for a in authors
                    )
                    by_url[p_url] = f"{stamp}{markdown}"
                    for who in authors:
                        seeded_authors.setdefault(
                            who.lower(),
                            {
                                "name": who,
                                "description": f"Publishes under this name on {_fs_brand(self.url) or 'this site'}",
                                "source": "author",
                                "is_collective": _fs_is_collective_name(who),
                            },
                        )

            if seeded_authors:
                self._fallback_authors = list(seeded_authors.values())
            if by_url:
                if raw_html:
                    # The homepage only loaded in a browser, so its posts and
                    # team pages will refuse plain HTTP too; render them as well.
                    await self._render_refused_pages(
                        self._links_worth_rendering_from_home(raw_html), by_url, html_by_url
                    )
                self._index_pages(by_url)
                self._raw_pages = dict(html_by_url)
                content = self._sample_content_for_extraction(
                    "\n\n".join(f"URL: {u}\n{t}" for u, t in by_url.items())
                )

            self._fallback_text = content
            return content, raw_html, True

        await self._cancel_browser("fast scrape succeeded")
        return combined, result.get("raw_home_html") or "", False

    def _index_pages(self, pages: Dict[str, str]) -> None:
        """Split scraped pages into the texts each extraction pass reads."""
        from src.utils.fast_scraper import PAGE_ARTICLE, PAGE_TEAM, classify_page

        kind = {u: classify_page(u, t) for u, t in pages.items()}
        self._page_text_by_url = dict(pages)

        by_author: Dict[str, List[str]] = {}
        profiles: Dict[str, str] = {}
        loose: List[str] = []
        for page_url, text in pages.items():
            if kind.get(page_url) != PAGE_ARTICLE:
                continue
            authors_on_page = _fs_declared_authors(text)
            if authors_on_page:
                for who in authors_on_page:
                    by_author.setdefault(who, []).append(f"URL: {page_url}\n{text}")
            elif text.startswith("Author profile:"):
                # The person's own profile page carries their bio; it belongs
                # beside their articles, not after everyone else's. The same
                # profile can be keyed with and without a trailing slash, and
                # the one-line placeholder must never win over the fetched page.
                who = _profile_name(text)
                block = f"URL: {page_url}\n{text}"
                key = _identity_key(who)
                if not key:
                    loose.append(block)
                elif _profile_rank(block) > _profile_rank(profiles.get(key, "")):
                    profiles[key] = block
            else:
                loose.append(f"URL: {page_url}\n{text}")

        # Most prolific writers first, so their writing survives any truncation.
        ranked = sorted(by_author.items(), key=lambda item: len(item[1]), reverse=True)
        blocks = []
        for who, written in ranked:
            profile = profiles.pop(_identity_key(who), "")
            blocks.append(
                f"===== WRITING BY {who} ({len(written)} piece(s) found) =====\n"
                + "\n\n".join(([profile] if profile else []) + written[:_ARTICLES_PER_AUTHOR])
            )
        blocks += [f"===== AUTHOR PROFILE =====\n{profile}" for profile in profiles.values()]
        self._author_text = "\n\n".join(blocks + loose)
        self._team_text = "\n\n".join(
            f"URL: {u}\n{t}" for u, t in pages.items() if kind.get(u) != PAGE_TEAM
        )
        self._leadership_text = "\n\n".join(
            f"URL: {u}\n{t}" for u, t in pages.items() if kind.get(u) == PAGE_TEAM
        )

    def _refused_pages_worth_rendering(
        self, refused: Dict[str, object], pages: Dict[str, str], home_html: str
    ) -> List[str]:
        """Refused URLs that can hold author evidence: posts first, then author
        archives and team pages the homepage links to. Feeds and guessed,
        unlinked paths are skipped."""
        from urllib.parse import urlparse

        from src.utils.fast_scraper import (
            _AUTHOR_PATH_RE,
            PAGE_ARTICLE,
            TEAM_KEYWORDS,
            _looks_like_post,
            _matches_keyword,
            classify_page,
        )

        home = self.url.rstrip("/")
        posts: List[str] = []
        slugs: List[str] = []
        people: List[str] = []
        for page_url in refused:
            if page_url in pages or page_url.rstrip("/") == home:
                continue
            path = urlparse(page_url).path.lower()
            segments = [s for s in path.split("/") if s]
            if path.endswith((".xml", ".rss", ".atom", ".json")) or (
                segments and segments[-1] in {"feed", "rss", "atom"}
            ):
                continue
            if _AUTHOR_PATH_RE.search(path) and len(segments) >= 2:
                people.append(page_url)
            elif _matches_keyword(path, TEAM_KEYWORDS + ("about",)):
                if segments and "/" + "/".join(segments) in home_html:
                    people.append(page_url)
            elif classify_page(page_url) == PAGE_ARTICLE:
                posts.append(page_url)
            elif _looks_like_post(path):
                slugs.append(page_url)
        # Blog-path URLs first, then bare slugs (for sites that publish at the root).
        posts += slugs
        return (posts[: _REFUSED_RENDER_MAX_PAGES - 2] + people)[:_REFUSED_RENDER_MAX_PAGES]

    def _links_worth_rendering_from_home(self, home_html: str) -> List[str]:
        from src.utils.fast_scraper import (
            BLOG_KEYWORDS,
            TEAM_KEYWORDS,
            _find_post_links,
            find_internal_links,
        )

        try:
            links = (
                find_internal_links(home_html, self.url, BLOG_KEYWORDS, 2)
                + _find_post_links(home_html, self.url, 6, allow_outside_index_path=True)
                + find_internal_links(home_html, self.url, TEAM_KEYWORDS, 2)
            )
        except Exception:
            return []
        return list(dict.fromkeys(links))

    async def _render_refused_pages(
        self, urls: List[str], pages: Dict[str, str], raw_pages: Dict[str, str]
    ) -> None:
        """Render refused pages in a browser and add them to ``pages`` and
        ``raw_pages``, stamped exactly the way the HTTP scrape stamps pages."""
        from urllib.parse import urlparse

        from src.utils.fast_scraper import (
            _AUTHOR_PATH_RE,
            BLOG_KEYWORDS,
            _archive_heading,
            _find_post_links,
            _is_person_name,
            _matches_keyword,
            extract_author_activity,
            extract_bylines,
            extract_publish_year,
            visible_text,
        )
        from src.utils.helper import render_pages

        urls = [u for u in dict.fromkeys(urls) if u not in pages][:_REFUSED_RENDER_MAX_PAGES]
        if not urls:
            return
        loop = asyncio.get_event_loop()
        elapsed = loop.time() - getattr(self, "_started", loop.time())
        left = (
            PIPELINE_BUDGET_SECONDS - elapsed - EXTRACTION_BUDGET_SECONDS - PERSIST_RESERVE_SECONDS
        )
        budget = max(_REFUSED_RENDER_MIN_SECONDS, min(_REFUSED_RENDER_MAX_SECONDS, left))

        def _expand(page_url: str, html: str) -> List[str]:
            parsed = urlparse(page_url)
            segments = [s for s in parsed.path.split("/") if s]
            is_index = len(segments) <= 1 and (
                _matches_keyword(parsed.path.lower(), BLOG_KEYWORDS)
                or parsed.netloc.lower().startswith(("blog.", "news."))
            )
            if not is_index:
                return []
            links = _find_post_links(html, page_url, 6) or _find_post_links(
                html, page_url, 6, allow_outside_index_path=True
            )
            return [link for link in links if link not in pages]

        logger.info("Rendering %d refused page(s) in a browser (budget %.0fs)", len(urls), budget)
        try:
            rendered = await asyncio.wait_for(
                render_pages(
                    urls, budget_seconds=budget, expand=_expand, max_pages=_REFUSED_RENDER_MAX_PAGES
                ),
                timeout=budget + _BROWSER_CANCEL_GRACE_SECONDS,
            )
        except Exception as exc:
            logger.warning("Browser render of refused pages failed: %r", exc)
            return

        for page_url, html in rendered.items():
            raw_pages[page_url] = html
            text = visible_text(html, 1_500, strip_footer=False, strip_testimonials=True)
            if _AUTHOR_PATH_RE.search(urlparse(page_url).path):
                who = _archive_heading(html) or ""
                counted = extract_author_activity(html, page_url)
                pages[page_url] = (
                    "Author profile:"
                    + (f" {who}" if _is_person_name(who) else "")
                    + (f" | posts={counted}" if counted else "")
                    + "\n"
                    + text
                )
                continue
            bylines = extract_bylines(html, page_url)
            if bylines:
                year = extract_publish_year(html)
                stamp = f" | {year}" if year else ""
                text = "".join(f"Article author: {b}{stamp}\n" for b in bylines) + text
            pages[page_url] = text
        logger.info(
            "Browser rendered %d refused page(s): %s", len(rendered), ", ".join(rendered) or "none"
        )

    async def _cancel_browser(self, why: str) -> None:
        task = getattr(self, "_browser_task", None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await asyncio.wait([task], timeout=_BROWSER_CANCEL_GRACE_SECONDS)
            except Exception:
                pass

    async def _extract_brand_voice(self, content: str) -> Optional[BrandSchema]:
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

        try:
            brand_voice_schema = await self._brand_voice_generator(content)
        except Exception:
            logger.error("Brand voice extraction failed", exc_info=True)
            await emit_step_failure(
                operation_id=self.operation_id,
                scope=self.scope,
                step="brand_voice",
                message="We couldn't analyze the brand voice right now. Please try again.",
                error=None,
                user_id=self.user_id,
            )
            raise

        await emit_step_success(
            operation_id=self.operation_id,
            scope=self.scope,
            step="brand_voice",
            message="Brand voice extracted successfully",
            payload={**brand_voice_schema.model_dump(), "personas": []}
            if brand_voice_schema
            else None,
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
                message="Competitor discovery could not be completed. You can add competitors manually.",
                error=None,
                user_id=self.user_id,
            )
            return None

        competitors = select_display_competitors(analysis.get("competitors", []), self_url=self.url)

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
        total_budget = self._HEAD_CHARS + self._TAIL_CHARS
        if len(content) <= total_budget:
            return content
        return f"{content[: self._HEAD_CHARS]}\n\n...[middle omitted]...\n\n{content[-self._TAIL_CHARS :]}"

    async def _persist_brand_voice(
        self, brand_voice_schema: Optional[BrandSchema]
    ) -> Optional[BrandVoice]:
        if brand_voice_schema is None:
            return None

        data = brand_voice_schema.model_dump()

        raw_personas = data.pop("personas", []) or []
        raw_personas.extend(getattr(self, "_author_personas", []) or [])
        raw_personas.extend(getattr(self, "_fallback_authors", []) or [])

        raw_home_html = (getattr(self, "_raw_pages", {}) or {}).get(self.url, "")
        if raw_home_html:
            for f_name, f_credit in extract_founder_credits(raw_home_html).items():
                raw_personas.append(
                    {
                        "name": f_name,
                        "professional_title": "Founder",
                        "description": f_credit,
                        "source": "founder",
                    }
                )

        personas_data = _filter_valid_personas(raw_personas, self.url)
        await self._fetch_missing_author_archives(personas_data)
        gravatars = await self._resolve_gravatars(personas_data)
        await self._render_missing_persona_avatars(personas_data)
        self._attach_social_links(personas_data, gravatars)
        if self._use_default_llm:
            try:
                await self._analyse_incomplete_personas(personas_data)
            except Exception as exc:  # noqa: BLE001 - personas still save as found
                logger.warning("Per-persona analysis failed: %r", exc)

        try:
            result = await self.db.execute(
                select(BrandVoice).where(BrandVoice.workspace_id == self.workspace_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                # The freshly scraped name replaces the stored one; keep the old
                # name only when extraction found none.
                existing.brand_name = data.get("brand_name") or existing.brand_name
                existing.about = data.get("about") or existing.about
                existing.customer_profile = (
                    data.get("customer_profile") or existing.customer_profile
                )
                existing.selling_position = (
                    data.get("selling_position") or existing.selling_position
                )
                existing.target_audience = (
                    data.get("target_audience") or existing.target_audience or []
                )
                existing.brand_voice = data.get("brand_voice") or existing.brand_voice or []
                existing.content_pillar = (
                    data.get("content_pillar") or existing.content_pillar or []
                )
                brand_voice_record = existing
                brand_voice_record.site_compliance = getattr(self, "_site_compliance", None)
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
                brand_voice_record.site_compliance = getattr(self, "_site_compliance", None)
                self.db.add(brand_voice_record)

            await self.db.flush()

            await self._persist_personas(personas_data)
            await self.db.flush()
            return brand_voice_record

        except Exception as exc:
            await self.db.rollback()
            logger.error("Failed to persist brand voice and personas: %s", exc)
            raise

    async def _persist_competitors(self, competitors: List[str]) -> None:
        try:
            result = await self.db.execute(
                select(BrandVoice).where(BrandVoice.workspace_id == self.workspace_id)
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.competitors = competitors
            else:
                self.db.add(BrandVoice(workspace_id=self.workspace_id, competitors=competitors))
            await self.db.flush()
        except Exception:
            await self.db.rollback()

    async def _embed_brand_voice(self, brand_voice_schema: Optional[BrandSchema]) -> None:
        if not brand_voice_schema:
            return
        try:
            from src.api.models.workspace_models.workspace_model import WorkspaceModel
            from src.services.brand_voice_embedding_service import BrandVoiceEmbeddingService

            result = await self.db.execute(
                select(WorkspaceModel).where(WorkspaceModel.id == self.workspace_id)
            )
            workspace = result.scalar_one_or_none()
            svc = BrandVoiceEmbeddingService()
            await svc.upsert_brand_voice_embedding(
                workspace_id=self.workspace_id,
                brand_data=brand_voice_schema.model_dump(),
                workspace_name=workspace.name if workspace else None,
            )
        except Exception:
            pass

    async def _render_missing_persona_avatars(self, personas_data: list) -> None:
        """Render only relevant pages when server HTML has no usable profile image."""
        from src.utils.fast_scraper import extract_person_avatars
        from src.utils.helper import render_pages

        raw_pages = getattr(self, "_raw_pages", {}) or {}
        missing = []
        for persona in personas_data:
            name = (persona.get("name") or "").strip()
            if not name or persona.get("avatar_url"):
                continue
            present = any(
                extract_person_avatars(html, [name], base_url=self.url).get(name)
                for html in raw_pages.values()
            )
            if not present:
                missing.append(name)
        if not missing:
            return

        urls = [
            url
            for url, html in raw_pages.items()
            if any(name.casefold() in html.casefold() for name in missing)
        ]
        if not urls:
            return
        loop = asyncio.get_event_loop()
        left = (
            PIPELINE_BUDGET_SECONDS
            - (loop.time() - self._started)
            - EXTRACTION_BUDGET_SECONDS
            - PERSIST_RESERVE_SECONDS
        )
        budget = min(8.0, left)
        if budget < 3.0:
            return
        try:
            rendered = await asyncio.wait_for(
                render_pages(urls[:3], budget_seconds=budget, max_pages=3), timeout=budget + 2
            )
        except Exception as exc:
            logger.info("Persona avatar browser fallback failed: %r", exc)
            return

        raw_pages.update(rendered)
        self._raw_pages = raw_pages

    async def _resolve_gravatars(self, personas_data: list) -> dict:
        import httpx

        from src.utils.fast_scraper import gravatar_if_exists

        needing = [
            (p.get("name"), (p.get("email") or "").strip().lower())
            for p in personas_data
            if not (p.get("avatar_url") or "").strip() and (p.get("email") or "").strip()
        ]
        if not needing:
            return {}
        unique_emails = list({email for _, email in needing})
        try:
            async with httpx.AsyncClient(headers=REQUEST_HEADERS, follow_redirects=True) as client:
                answers = await asyncio.gather(
                    *[gravatar_if_exists(client, email) for email in unique_emails],
                    return_exceptions=True,
                )
            by_email = {
                email: url
                for email, url in zip(unique_emails, answers)
                if isinstance(url, str) and url
            }
            return {name: by_email[email] for name, email in needing if email in by_email}
        except Exception:
            return {}

    async def _fetch_missing_author_archives(self, personas_data: list) -> None:

        from src.utils.fast_scraper import (
            CONCURRENCY,
            extract_archive_latest_year,
            extract_author_activity,
            find_author_archive,
            visible_text,
        )

        pages_text = getattr(self, "_page_text_by_url", {}) or {}
        raw_pages = getattr(self, "_raw_pages", {}) or {}
        have = " ".join(
            t.split("\n", 1)[0] for t in pages_text.values() if t.startswith("Author profile:")
        )
        missing = [
            p.get("name") for p in personas_data if p.get("name") and p.get("name") not in have
        ]
        if not missing:
            return

        sem = asyncio.Semaphore(CONCURRENCY)
        deadline = asyncio.get_event_loop().time() + _DERIVED_ARCHIVE_BUDGET
        try:
            # Author pages on the site, through the public client as every fetch of it is.
            async with public_client(headers=REQUEST_HEADERS, follow_redirects=True) as client:
                results = await asyncio.gather(
                    *[
                        find_author_archive(client, sem, self.url, name, deadline)
                        for name in missing[:_MAX_DERIVED_ARCHIVES]
                    ],
                    return_exceptions=True,
                )
                found = [(n, r) for n, r in zip(missing, results) if isinstance(r, tuple)]
                for (name, url), html in zip(
                    [(n, u) for n, (u, _) in found], [h for _, (_, h) in found]
                ):
                    if isinstance(html, str) and html:
                        counted = extract_author_activity(html, url)
                        year = extract_archive_latest_year(html)
                        raw_pages[url] = html
                        pages_text[url] = (
                            f"Author profile: {name}"
                            + (f" | posts={counted}" if counted else "")
                            + (f" | latest={year}" if year else "")
                            + "\n"
                            + visible_text(html, 4000)
                        )
            self._raw_pages, self._page_text_by_url = raw_pages, pages_text
        except Exception:
            pass

    def _attach_social_links(
        self, personas_data: list[dict], gravatar_lookup: Optional[dict] = None
    ) -> None:
        """Keep only candidates the fetched site proves are real, score them on
        that evidence, and rank top contributors first.

        A candidate survives only when its name is printed on a fetched page and
        it has provenance: an article byline, an author archive, a team/about
        page listing, a homepage founder credit, or its stated role printed next
        to its name. Scores come from that evidence alone; nothing the language
        model wrote about the person raises them.
        """
        if not personas_data:
            return

        from src.utils.fast_scraper import PAGE_TEAM, classify_page

        pages_text = getattr(self, "_page_text_by_url", {}) or {}
        raw_pages = getattr(self, "_raw_pages", {}) or {}
        gravatar_lookup = gravatar_lookup or {}
        brand = _fs_brand(self.url)

        lowered_pages = {u: t.lower() for u, t in pages_text.items()}
        lowered_html = [h.lower() for h in raw_pages.values() if isinstance(h, str) and h]
        team_pages = [
            lowered_pages[u] for u, t in pages_text.items() if classify_page(u, t) == PAGE_TEAM
        ]
        home_html = raw_pages.get(self.url) or ""
        founder_keys = (
            {_identity_key(n) for n in extract_founder_credits(home_html)} if home_html else set()
        )

        stamped: Dict[str, set] = {}
        recent: Dict[str, int] = {}
        profiles: Dict[str, int] = {}
        for page_url, text in pages_text.items():
            if text.startswith("Author profile:"):
                parts = [
                    s.strip() for s in text.split("\n", 1)[0][len("Author profile:") :].split("|")
                ]
                who = _identity_key(parts[0]) if parts and parts[0] else ""
                if who:
                    posts = next(
                        (
                            int(p[len("posts=") :])
                            for p in parts[1:]
                            if p.startswith("posts=") and p[len("posts=") :].isdigit()
                        ),
                        0,
                    )
                    profiles[who] = max(profiles.get(who, 0), posts)
                continue
            for line in text.split("\n"):
                if not line.startswith("Article author:"):
                    break
                parts = [s.strip() for s in line[len("Article author:") :].split("|")]
                if not parts[0] or not (_fs_is_person_name(parts[0]) or _is_collective(parts[0])):
                    continue
                who = _identity_key(parts[0])
                if "#author=" in page_url:
                    # Feed entry: the lines after the stamp are that author's post links.
                    links = {
                        ln.strip().rstrip("/")
                        for ln in text.split("\n")[1:]
                        if ln.strip().startswith("http")
                    }
                    stamped.setdefault(who, set()).update(links)
                    continue
                stamped.setdefault(who, set()).add(page_url.rstrip("/"))
                year = parts[1] if len(parts) > 1 else ""
                if year.isdigit() and int(year) >= RECENT_SINCE_YEAR:
                    recent[who] = recent.get(who, 0) + 1

        kept: list[dict] = []
        dropped: list[str] = []
        for persona in personas_data:
            name = (persona.get("name") or "").strip()
            if not name:
                continue
            key = _identity_key(name)
            lowered = name.lower()

            article_urls = stamped.get(key, set())
            byline_articles = len(article_urls)
            has_author_profile = key in profiles
            profile_posts = profiles.get(key, 0)
            on_team_page = any(lowered in t or key in t for t in team_pages)
            founder_credit = key in founder_keys
            found_on_site = bool(
                byline_articles
                or has_author_profile
                or any(lowered in t or key in t for t in lowered_pages.values())
                or any(lowered in h or key in h for h in lowered_html)
            )
            if not found_on_site:
                dropped.append(f"{name} (name not printed on any fetched page)")
                continue

            title = (persona.get("professional_title") or "").strip()
            role_evidenced = bool(title) and _role_near_name(name, title, pages_text)
            hard_evidence = bool(
                byline_articles or has_author_profile or on_team_page or founder_credit
            )
            # "Jane Roe, CEO" under a quote is a printed role too, so a role alone
            # is not proof; only a byline, author page, team page or founder credit is.
            if not hard_evidence:
                dropped.append(f"{name} (no byline, author page, team page or founder credit)")
                continue
            if _names_other_employer(title, brand) and not (byline_articles or has_author_profile):
                dropped.append(f"{name} (title names another company: {title})")
                continue
            review_hits, mentions = _review_mentions(name, pages_text)
            if review_hits and (review_hits >= mentions or not hard_evidence):
                dropped.append(f"{name} (mentioned in a review/testimonial)")
                continue

            meta = dict(persona.get("custom_metadata") or {})
            source = (persona.get("source") or "author").strip().lower()
            meta["source"] = source
            meta["persona_type"] = persona.get("persona_type") or source

            identity = 0.30
            reasons = ["name printed on the site"]
            if byline_articles:
                # More credited articles, more certainty: 1 -> +0.25, 2 -> +0.35,
                # 3-4 -> +0.45, 5 or more -> +0.55.
                identity += (
                    0.55
                    if byline_articles >= 5
                    else 0.45
                    if byline_articles >= 3
                    else 0.35
                    if byline_articles == 2
                    else 0.25
                )
                reasons.append(f"author byline on {byline_articles} article(s)")
            if has_author_profile:
                identity += 0.20
                reasons.append(
                    "author archive page"
                    + (f" listing {profile_posts} post(s)" if profile_posts else "")
                )
            if on_team_page:
                identity += 0.20
                reasons.append("listed on a team/about page")
            if founder_credit:
                identity += 0.15
                reasons.append("credited as founder on the homepage")
            if role_evidenced:
                identity += 0.10
                reasons.append(f"role '{title}' printed next to the name")
            identity = round(min(identity, 0.99), 2)

            signals = set(meta.get("confidence_signals") or []) - _EVIDENCE_SIGNALS
            for present, signal in (
                (byline_articles, "declared_byline"),
                (has_author_profile, "author_profile"),
                (on_team_page, "on_team_page"),
                (founder_credit, "founder_credit"),
                (role_evidenced, "stated_role"),
            ):
                if present:
                    signals.add(signal)

            if not persona.get("avatar_url"):
                from src.utils.fast_scraper import extract_person_avatars

                for _page_html in raw_pages.values():
                    if not isinstance(_page_html, str) or not _page_html:
                        continue
                    _found = extract_person_avatars(_page_html, [name], base_url=self.url)
                    if _found.get(name):
                        persona["avatar_url"] = _found[name]
                        persona["avatar_source"] = "page"
                        meta["avatar_source"] = "page"
                        break
            if not persona.get("avatar_url") and gravatar_lookup.get(name):
                persona["avatar_url"] = gravatar_lookup[name]
                persona["avatar_source"] = "gravatar"
                meta["avatar_source"] = "gravatar"
            if not persona.get("avatar_url"):
                persona["avatar_url"] = initials_avatar(name)
                persona["avatar_source"] = "generated"
                meta["avatar_source"] = "generated"

            meta["confidence"] = int(round(identity * 100))
            meta["confidence_signals"] = sorted(signals)
            meta["identity_confidence"] = identity
            meta["identity_reasons"] = reasons
            meta["evidence_urls"] = (
                sorted(article_urls)[:8]
                or [u for u, t in lowered_pages.items() if lowered in t or key in t][:8]
            )
            meta["evidence"] = {
                "team_member": on_team_page,
                "author": bool(byline_articles),
                "author_profile": has_author_profile,
                "founder_credit": founder_credit,
                "stated_role": role_evidenced,
                "article_count": max(byline_articles, profile_posts),
                "recent_article_count": recent.get(key, 0),
            }
            persona["custom_metadata"] = meta
            persona["persona_type"] = meta["persona_type"]
            kept.append(persona)

        if dropped:
            logger.info("Dropped %d persona candidate(s): %s", len(dropped), "; ".join(dropped))

        # Ordered by what the site shows each person contributed. Deliberately NOT
        # a recommendation: which persona to write as depends on the article's
        # topic, title, search intent and content type, none of which exist yet
        # here. That choice is made in the content outline step
        # (flow/engines/content/generation/persona_relevance.py).
        kept.sort(key=_calculate_recommendation_rank, reverse=True)
        personas_data[:] = kept

        for position, p in enumerate(personas_data, start=1):
            p.setdefault("custom_metadata", {})["contributor_rank"] = position
        logger.info("Attached links and validated personas: %d kept", len(personas_data))

    def _persona_evidence(
        self, persona: dict, fetched: Optional[Dict[str, str]] = None
    ) -> Tuple[str, List[str], List[str]]:
        """What the site holds by or about one person, as labelled sections.

        Only text tied to this person counts: their profile page, articles
        under their byline, and the text around their name elsewhere on the
        site outside review/testimonial blocks. ``fetched`` holds article pages
        fetched for this analysis. Returns the text, the URLs it came from, and
        the URLs of articles credited to them that were never fetched.
        """
        from src.utils.fast_scraper import visible_text

        name = (persona.get("name") or "").strip()
        key = _identity_key(name)
        lowered_name = name.lower()
        pages_text = getattr(self, "_page_text_by_url", {}) or {}
        raw_pages = getattr(self, "_raw_pages", {}) or {}
        fetched = fetched or {}

        profile, articles, mentions, urls = "", [], [], []
        credited_links: List[str] = []
        for page_url, text in pages_text.items():
            if text.startswith("Author profile:"):
                if _identity_key(_profile_name(text)) == key and _profile_rank(
                    text
                ) > _profile_rank(profile):
                    profile = text[:_ANALYSIS_PROFILE_CHARS]
                    urls.append(page_url)
                continue
            if "#author=" in page_url:
                # Feed stub: the lines after the stamp are this author's posts.
                if any(_identity_key(w) == key for w in _fs_declared_authors(text)):
                    credited_links += [
                        ln.strip() for ln in text.split("\n")[1:] if ln.strip().startswith("http")
                    ]
                continue
            if any(_identity_key(w) == key for w in _fs_declared_authors(text)):
                if len(articles) < _ANALYSIS_ARTICLES:
                    # The scrape kept a short sample of each post; the fetched
                    # page holds the full article.
                    html = raw_pages.get(page_url)
                    body = (
                        visible_text(html, _ANALYSIS_ARTICLE_CHARS, strip_testimonials=True)
                        if isinstance(html, str) and html
                        else ""
                    )
                    articles.append(f"URL: {page_url}\n{body or text[:_ANALYSIS_ARTICLE_CHARS]}")
                    urls.append(page_url)
                continue
            if len(mentions) >= _ANALYSIS_MENTION_PAGES:
                continue
            i = text.lower().find(lowered_name)
            reviews = _review_regions(text)
            while i >= 0 and any(start <= i < end for start, end in reviews):
                i = text.lower().find(lowered_name, i + len(lowered_name))
            if i >= 0:
                start = max(0, i - _ANALYSIS_WINDOW_BEFORE)
                end = i + len(name) + _ANALYSIS_WINDOW_AFTER
                mentions.append(f"URL: {page_url}\n{text[start:end]}")
                urls.append(page_url)

        for page_url, html in fetched.items():
            if len(articles) >= _ANALYSIS_ARTICLES:
                break
            body = visible_text(html, _ANALYSIS_ARTICLE_CHARS, strip_testimonials=True)
            if body:
                articles.append(f"URL: {page_url}\n{body}")
                urls.append(page_url)

        known = {u.rstrip("/") for u in pages_text}
        unfetched = [
            u
            for u in dict.fromkeys(credited_links)
            if u.rstrip("/") not in known and u not in fetched
        ]

        sections = []
        if profile:
            sections.append(f"=== PROFILE PAGE OF {name} ===\n{profile}")
        if mentions:
            sections.append(f"=== WHAT THE SITE SAYS ABOUT {name} ===\n" + "\n\n".join(mentions))
        if articles:
            sections.append(f"=== ARTICLES WRITTEN BY {name} ===\n" + "\n\n".join(articles))
        return "\n\n".join(sections), urls, unfetched

    async def _fetch_credited_articles(self, links: List[str]) -> Dict[str, str]:
        """Fetch articles a person is credited with that the scrape never read -
        a feed lists them, but the crawl stopped before reaching them."""

        if not links:
            return {}
        try:
            # Links the site's own pages give: through the public client, as every fetch of it is.
            async with public_client(
                headers=REQUEST_HEADERS, follow_redirects=True, timeout=_ANALYSIS_FETCH_SECONDS
            ) as client:
                responses = await asyncio.gather(
                    *[client.get(u) for u in links[:_ANALYSIS_ARTICLES]], return_exceptions=True
                )
        except Exception:  # noqa: BLE001 - analysis goes ahead on what the site gave
            return {}
        return {
            u: r.text
            for u, r in zip(links, responses)
            if not isinstance(r, BaseException) and r.status_code == 200 and r.text
        }

    async def _analyse_incomplete_personas(self, personas_data: list[dict]) -> None:
        """Analyse each persona still missing fields over only its own pages.

        The site-wide passes read every author at once and can leave a person
        with a bare name - a byline found in code that no model described, or
        one of many authors in a long prompt. This pass reads one person's own
        pages at a time and fills only what is still empty. A persona with no
        pages of its own is left as it is: with nothing to analyse, anything
        written would be a guess.
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        from src.api.schema.persona_schema import PersonaAnalysis

        candidates = [p for p in personas_data[:_MAX_ANALYSED_PERSONAS] if _fields_to_analyse(p)]
        if not candidates:
            return

        model = load_model(temperature=0).with_structured_output(PersonaAnalysis)

        async def _analyse(persona: dict) -> Tuple[str, List[str], Optional[dict]]:
            evidence, urls, unfetched = self._persona_evidence(persona)
            if "=== ARTICLES WRITTEN BY" not in evidence and unfetched:
                fetched = await self._fetch_credited_articles(unfetched)
                if fetched:
                    evidence, urls, _ = self._persona_evidence(persona, fetched)
            if len(evidence) < _ANALYSIS_MIN_EVIDENCE_CHARS:
                return evidence, urls, None
            out = await ainvoke_watched(
                model,
                [
                    SystemMessage(content=_PERSONA_ANALYSIS_PROMPT),
                    HumanMessage(content=f"Person: {persona.get('name')}\n\n{evidence}"),
                ],
                stage="workspace_personas",
            )
            result = out.model_dump() if hasattr(out, "model_dump") else dict(out or {})
            return evidence, urls, result

        tasks = [asyncio.ensure_future(_analyse(p)) for p in candidates]
        done, pending = await asyncio.wait(tasks, timeout=_ANALYSIS_BUDGET_SECONDS)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.wait(pending, timeout=1.0)

        for persona, task in zip(candidates, tasks):
            if task not in done or task.cancelled() or task.exception() is not None:
                logger.warning(
                    "Persona analysis for %s did not complete: %r",
                    persona.get("name"),
                    None if task not in done or task.cancelled() else task.exception(),
                )
                continue
            evidence, urls, analysis = task.result()
            if analysis is None:
                # Nothing on the site by or about this person to analyse;
                # writing their fields anyway would be a guess.
                logger.info("No pages to analyse for persona %s", persona.get("name"))
                continue
            if "=== ARTICLES WRITTEN BY" not in evidence:
                # Tone is read from how someone writes; a profile blurb is not that.
                analysis["tone_of_voice"] = None
            filled = _apply_analysis(persona, analysis)
            if filled:
                meta = persona.setdefault("custom_metadata", {})
                meta["analysed_fields"] = filled
                meta["analysed_from"] = list(dict.fromkeys(urls))[:8]
                logger.info("Analysed persona %s: filled %s", persona.get("name"), filled)

    async def _persist_personas(self, personas_data: list[dict]) -> None:
        """Save extracted personas to persona table.

        Always clears out extracted personas from the previous workspace URL,
        even when the new extraction found none — otherwise a refresh to a
        persona-less site would leave stale personas from the old site in
        place. Manually created personas are left untouched.
        """
        if not personas_data:
            logger.info("No personas extracted; clearing existing personas for workspace")

        def _normalize_text(value: Any) -> Optional[str]:
            if value is None:
                return None
            if isinstance(value, (list, tuple, set)):
                return ", ".join(str(item).strip() for item in value if item is not None)
            if isinstance(value, dict):
                return json.dumps(value, ensure_ascii=False)
            return str(value)

        def _column(p_data: dict, field: str) -> Optional[str]:
            return _bounded(field, _normalize_text(p_data.get(field)))

        async with self.db.begin_nested():
            # Replace only previously extracted personas. Extraction always
            # writes custom_metadata; manually created personas never have it,
            # so they survive a refresh.
            await self.db.execute(
                delete(Persona).where(
                    Persona.workspace_id == self.workspace_id,
                    Persona.custom_metadata.isnot(None),
                )
            )

            # Insert new personas with ALL fields
            for p_data in personas_data:
                persona = Persona(
                    workspace_id=self.workspace_id,
                    name=_column(p_data, "name") or "",
                    description=_column(p_data, "description"),
                    full_name=_column(p_data, "full_name"),
                    professional_title=_column(p_data, "professional_title"),
                    areas_of_expertise=p_data.get("areas_of_expertise") or [],
                    tone_of_voice=_column(p_data, "tone_of_voice"),
                    bio=_column(p_data, "bio"),
                    linkedin_url=_column(p_data, "linkedin_url"),
                    demographics=_column(p_data, "demographics"),
                    pain_points=_column(p_data, "pain_points"),
                    goals=_column(p_data, "goals"),
                    behaviors=_column(p_data, "behaviors"),
                    avatar_url=_column(p_data, "avatar_url"),
                    avatar_source=_column(p_data, "avatar_source"),
                    email=_column(p_data, "email"),
                    custom_metadata=p_data.get("custom_metadata") or {},
                )
                self.db.add(persona)
            await self.db.flush()

        await self.db.commit()

        result = await self.db.execute(
            select(Persona).where(Persona.workspace_id == self.workspace_id)
        )
        saved_personas = list(result.scalars().all())
        # Keep the contributor ranking; the database does not keep insert order.
        position = {(p.get("name") or ""): i for i, p in enumerate(personas_data)}
        saved_personas.sort(key=lambda p: position.get(p.name or "", len(position)))
        self._extracted_personas = [_format_persona_for_frontend(p) for p in saved_personas]

        logger.info(
            "Persisted and formatted personas for frontend",
            extra={
                "workspace_id": str(self.workspace_id),
                "persona_count": len(self._extracted_personas),
            },
        )

    @staticmethod
    async def _default_scraper(url: str) -> Tuple[List[Any], List[Any]]:
        return await web_page_scraper(urls=[url])

    async def _default_brand_voice_generator(self, content: str) -> Optional[BrandSchema]:
        if not content.strip():
            return None

        system_prompt = """You are an expert at analyzing website content and extracting brand information and real people.

Extract brand information: brand_name, about, customer_profile, selling_position, target_audience, brand_voice, content_pillar.
Always leave competitors as an empty list.

STRICT RULES FOR PERSONAS:
1. Extract ONLY real human beings mentioned on the site who represent the brand (founders, team members, blog authors, executives).
2. Customer reviews, client testimonials, and case-study contributors MUST NOT be added as personas. If you include someone from a review, set source='testimonial' so they are discarded.
3. Every persona attribute must be grounded in the author's actual article(s) or page content (even if only 1 article is available):
   - professional_title: The person's role from the website as identified during scraping (e.g. 'Author', 'Founder', 'Co-Founder', 'CEO', 'Head of Content'). If an article writer has no specific executive title on the site, use 'Author'. NEVER use collective masthead labels like 'Editorial Staff', 'Staff', or 'Editorial Team'.
   - areas_of_expertise: Concrete subjects, technologies, and topics the author writes about in their article(s), even if only 1 article is available.
   - tone_of_voice: The writing style and tone demonstrated in the author's published article(s) (e.g., 'Instructional, practical, technical', 'Authoritative, analytical'). Even with only 1 article, extract the tone from that article.
   - bio / description: Factual 1-2 sentence professional bio summarizing what this author writes about on this site based on their published content.
   - pain_points: Technical challenges, problems, or reader pain points addressed or resolved in the author's writing (e.g., migration downtime, performance issues, database errors).
   - goals: Professional objectives and solutions the author achieves or guides readers toward in their articles (e.g., seamless zero-downtime migrations, optimized site performance).
   - behaviors: Professional methodology, best practices, and writing approach demonstrated in their articles (e.g., step-by-step guides, staging backups, performance testing).
   - demographics: The readers the person's articles are written for (e.g., 'Beginner WordPress site owners, small-business marketers').
4. Analyse, never guess: derive each field only from text by or about that person in the supplied content. When nothing supplied supports a field, leave it empty rather than filling it from general knowledge of the role, industry, or brand.
5. For each real persona, extract: name, source ('founder'|'team_member'|'author'|'expert'), full_name, professional_title, areas_of_expertise, tone_of_voice, bio, description, demographics, pain_points, goals, behaviors.
6. Return an empty list if no real people represent the brand.
"""

        async def _invoke_model() -> BrandSchema:
            from langchain_core.messages import HumanMessage, SystemMessage

            model = load_model(temperature=0)
            structured = model.with_structured_output(BrandSchema)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(
                    content="Analyze the website content and extract brand info and real people:\n\n"
                    + (content or getattr(self, "_team_text", ""))
                ),
            ]
            return await ainvoke_watched(structured, messages, stage="workspace_brand")

        async def _extract_authors() -> list:
            author_text = (
                getattr(self, "_author_text", "") or getattr(self, "_team_text", "") or content
            )
            if not author_text.strip():
                return []
            from langchain_core.messages import HumanMessage, SystemMessage

            model = load_model(temperature=0).with_structured_output(BrandSchema)
            out = await ainvoke_watched(
                model,
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(
                        content="Analyze the articles and writing provided for each author below. For every real author (even with only 1 article), extract their persona attributes: name, professional_title ('Author' or stated site role), areas_of_expertise from their article topics, tone_of_voice from their writing style, bio/description grounded in what they write, demographics (who their articles are written for), pain_points addressed in their writing, goals, and behaviors. An author's profile page, when present, is at the top of their block:\n\n"
                        + author_text
                    ),
                ],
                stage="workspace_brand",
            )
            return [p.model_dump() if hasattr(p, "model_dump") else p for p in (out.personas or [])]

        async def _extract_leadership() -> list:
            text = getattr(self, "_leadership_text", "") or ""
            if not text.strip():
                return []
            from langchain_core.messages import HumanMessage, SystemMessage

            model = load_model(temperature=0).with_structured_output(BrandSchema)
            out = await ainvoke_watched(
                model,
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(
                        content="Read the leadership pages and extract every founder and team member with source='team_member':\n\n"
                        + text
                    ),
                ],
                stage="workspace_brand",
            )
            return [p.model_dump() if hasattr(p, "model_dump") else p for p in (out.personas or [])]

        passes = {
            "brand": asyncio.ensure_future(_invoke_model()),
            "authors": asyncio.ensure_future(_extract_authors()),
            "leadership": asyncio.ensure_future(_extract_leadership()),
        }
        done, pending = await asyncio.wait(passes.values(), timeout=EXTRACTION_BUDGET_SECONDS)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.wait(pending, timeout=1.0)

        # Keep every pass that finished: one slow or failing pass must not
        # throw away the authors and leaders the other passes already found.
        outcomes: Dict[str, Any] = {}
        failures: List[BaseException] = []
        for label, task in passes.items():
            if task not in done or task.cancelled():
                logger.warning(
                    "Extraction pass '%s' did not finish within %.0fs; keeping the passes that did",
                    label,
                    EXTRACTION_BUDGET_SECONDS,
                )
            elif task.exception() is not None:
                failures.append(task.exception())
                logger.warning("Extraction pass '%s' failed: %r", label, task.exception())
            else:
                outcomes[label] = task.result()
        if not outcomes and failures:
            raise failures[0]

        brand = outcomes.get("brand") or BrandSchema()
        authors = outcomes.get("authors") or []
        leaders = outcomes.get("leadership") or []

        brand_personas = [
            p.model_dump() if hasattr(p, "model_dump") else p for p in (brand.personas or [])
        ]

        # Never invent a representative or founder when the source has no
        # attributable person. An empty persona result is more accurate.
        self._author_personas = list(authors) + list(leaders) + list(brand_personas)
        return brand


async def run_workspace_pipeline(
    *,
    db: AsyncSession,
    operation_id: str,
    workspace_id: UUID,
    user_id: UUID,
    url: str,
    scraper: Optional[ScrapeCallable] = None,
    brand_voice_generator: Optional[BrandVoiceGeneratorCallable] = None,
) -> None:
    pipeline = WorkspacePipeline(
        db=db,
        operation_id=operation_id,
        workspace_id=workspace_id,
        user_id=user_id,
        url=url,
        scraper=scraper,
        brand_voice_generator=brand_voice_generator,
    )
    await pipeline.run()
