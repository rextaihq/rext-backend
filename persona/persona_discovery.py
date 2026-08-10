#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
persona_discovery.py — evidence-based author/team persona discovery.

DESIGN
    Sitemap-first, not blind-crawl. Every URL on the site is enumerated
    cheaply (robots.txt -> sitemap.xml -> RSS -> homepage links), classified,
    date-filtered, and only THEN fetched. Capping therefore removes only
    irrelevant pages: hub pages (about / team / author) are never capped, so
    a page limit can never cost you the team page.

    Nothing is invented. Every field is either extracted from the page or
    left null. The LLM step sees only real article text and is instructed to
    return null rather than guess.

LAYERS
    1. config          PersonaConfig
    2. validation      is_person_name / name keys / identity resolution
    3. classification  classify_url
    4. discovery       discover_urls        (robots, sitemap, rss, homepage)
    5. dates           extract_published_date
    6. extraction      extract_page_signals (jsonld, meta, microformat,
                                             byline, team cards)
    7. aggregation     PersonRegistry
    8. analysis        analyze_writing_style   (LLM, strict no-hallucination)
    9. output          build_result / to_persona_rows

USAGE
    python persona/persona_discovery.py https://example.com/
    python persona/persona_discovery.py https://example.com/ --max-articles 150

IMPORT
    from persona.persona_discovery import discover_personas, PersonaConfig
    result = await discover_personas("https://example.com/")
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup, Comment

logger = logging.getLogger(__name__)



# Optional project LLM. Absent -> style analysis is skipped, never faked.
import sys
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from src.flow.model.llm_manager import load_model
    HAS_LLM = True
except Exception as e:                                    # pragma: no cover
    load_model = None
    HAS_LLM = False





# ============================================================================
# 1. CONFIG
# ============================================================================

@dataclass
class PersonaConfig:
    """
    All tunables in one place. Defaults are derived from measured behaviour:
    median server latency on real targets was 6.0-6.8s, so a 5s timeout would
    fail the majority of requests. 20s with 8-way concurrency is the balance
    between throughput and politeness.
    """
    min_article_year: int = 2023        # R7
    max_articles: int = 200             # cap applies to ARTICLES only
    max_hub_pages: int = 40             # hubs are few; bounded for safety
    max_sitemap_urls: int = 20_000
    concurrency: int = 8
    request_timeout: float = 20.0
    retries: int = 3
    retry_backoff_base: float = 1.5     # 1.5s, 3.0s, 6.0s  (grows, not shrinks)
    samples_per_person: int = 4
    sample_chars: int = 2500
    min_confidence: float = 0.35        # below this a persona is discarded
    verify_tls: bool = True             # never disable in production
    user_agent: str = (
        "Mozilla/5.0 (compatible; RextPersonaBot/1.0; +https://rextai.com/bot)"
    )
    enable_llm: bool = True
    out_dir: Path | None = None

    def headers(self) -> dict:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }


# ============================================================================
# 2. NAME VALIDATION
# ============================================================================

# Particles and initials that legitimately appear inside human names.
_TOK = (r"(?:[A-Z][\w'’\-]{1,19}|[A-Z]\.|van|von|de|del|der|da|di|dos|du"
        r"|la|le|bin|binte|ibn|al|el|Mc|Mac|St\.?)")
RE_NAME_SHAPE = re.compile(rf"^{_TOK}(?:\s+{_TOK}){{1,3}}$", re.UNICODE)

# Ranks and honorifics. Leading ones are stripped; anywhere else means the
# match ran into surrounding prose ("SP Investigation Mr") -> reject.
HONORIFICS = {
    "mr", "mrs", "ms", "miss", "dr", "prof", "professor", "sir", "madam", "mx",
    "sp", "dsp", "sho", "ig", "dig", "asp", "capt", "captain", "col", "colonel",
    "sgt", "sergeant", "lt", "maj", "gen", "hon", "rev", "engr", "adv",
    "ceo", "cto", "coo", "cfo", "md", "phd", "esq", "jr", "sr",
}

# Abstract nouns used as Title Case section headings. Structurally identical
# to a two-word human name ("Client Satisfaction", "Our Vision").
ABSTRACT_HEADINGS = {
    "satisfaction", "quality", "growth", "success", "excellence", "innovation",
    "integrity", "transparency", "commitment", "results", "trust", "passion",
    "teamwork", "vision", "mission", "values", "culture", "impact", "expertise",
    "experience", "dedication", "reliability", "creativity", "strategy",
    "performance", "delivery", "communication", "ownership", "accountability",
    "collaboration", "star", "north", "story", "journey", "promise",
}

# Tokens that never occur inside a human name but are everywhere in Title Case
# headings and article titles. NOTE: "will", "can", "may", "mark", "grant",
# "hope", "rose", "grace" are deliberately ABSENT - they are real given names.
NON_NAME_TOKENS = {
    # interrogatives, determiners, pronouns
    "what", "why", "how", "when", "where", "who", "whom", "whose", "which",
    "this", "that", "these", "those", "you", "your", "yours", "we", "our",
    "ours", "us", "my", "mine", "me", "it", "its", "their", "them", "they",
    # auxiliaries / copulas
    "is", "are", "was", "were", "be", "been", "being", "am", "do", "does",
    "did", "done", "should", "would", "could", "shall", "must", "have", "has",
    # function words
    "the", "and", "but", "for", "with", "from", "into", "onto", "upon",
    "about", "after", "before", "during", "while", "because", "than", "then",
    "else", "also", "too", "very", "just", "only", "not", "never", "always",
    "here", "there", "now", "today", "yet", "still", "each", "every", "both",
    "few", "many", "much", "most", "least", "other", "another", "such",
    "same", "own", "any", "some", "none", "of", "in", "on", "at", "to", "or",
    "as", "if", "so", "up", "out", "off", "over", "under", "vs",
    # listicle / how-to scaffolding
    "step", "steps", "guide", "guides", "tips", "tip", "ways", "way", "post",
    "posts", "reasons", "reason", "things", "list", "top", "best", "new",
    "free", "easy", "quick", "simple", "ultimate", "complete", "final", "full",
    "review", "reviews", "tutorial", "tutorials", "example", "examples",
    # call-to-action verbs
    "hire", "buy", "sell", "order", "join", "meet", "find", "see", "view",
    "read", "click", "share", "download", "subscribe", "discover", "explore",
    "follow", "try", "use", "make", "need", "want", "know", "learn", "start",
    "stop", "fix", "check", "create", "build", "grow", "boost", "increase",
    "improve", "choose", "pick", "compare", "get", "started", "login",
    "signup", "register", "contact", "search", "menu", "home",
    # generic business nouns rendered as Title Case headings
    "marketing", "sales", "seo", "sem", "ppc", "design", "development",
    "engineering", "agency", "virtual", "assistant", "expert", "experts",
    "specialist", "consultant", "manager", "director", "officer", "head",
    "lead", "client", "clients", "customer", "customers", "partner",
    "partners", "work", "works", "portfolio", "testimonial", "testimonials",
    "award", "awards", "winning", "winner", "career", "careers", "agency",
    "agencies", "pricing", "plan", "plans", "package", "case", "study", "studies",
    "affiliate", "affiliates", "member", "members", "sponsor", "sponsors",
    "project", "projects", "process", "approach", "solution", "solutions",
    "service", "services", "product", "products", "company", "team", "staff",
    "blog", "news", "article", "articles", "category", "tag", "archive",
    "privacy", "terms", "policy", "cookie", "copyright", "reserved",
    "newsletter", "editorial", "admin", "administrator", "author", "authors",
    "writer", "writers", "contributor", "editor", "guest", "user", "profile",
    "comment", "comments", "reply", "faq", "help", "support", "demo",
    # months and weekdays leak in from date lines
    "january", "february", "march", "april", "june", "july", "august",
    "september", "october", "november", "december", "monday", "tuesday",
    "wednesday", "thursday", "friday", "saturday", "sunday",
}

# An organisational byline is a real published credit but NOT a person.
RE_ORG_BYLINE = re.compile(
    r"^([A-Z][A-Za-z0-9.\-]{1,25}(?:\s+[A-Z][A-Za-z0-9.\-]{1,25}){0,2}\s+"
    r"(?:Team|Staff|Editors|Editorial|Newsroom|Desk|Contributors|Group))$")

RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

SOCIAL_PATTERNS = {
    "linkedin": r"linkedin\.com/(in|pub)/",
    "twitter": r"(?:twitter\.com|x\.com)/(?!share|intent|home|hashtag)",
    "github": r"github\.com/",
    "instagram": r"instagram\.com/",
    "facebook": r"facebook\.com/(?!sharer|share|dialog)",
    "medium": r"medium\.com/@",
    "youtube": r"youtube\.com/(@|c/|channel/|user/)",
    "mastodon": r"(?:mastodon\.|@)[a-z]+\.social/@",
}

RE_ROLE = re.compile(
    r"\b(Co[- ]?Founder|Founder|CEO|CTO|COO|CMO|CFO|CPO"
    r"|Chief\s+[A-Za-z]+\s+Officer|President|Vice\s+President"
    r"|VP\s+[Oo]f\s+[A-Za-z]+|Head\s+[Oo]f\s+[A-Za-z ]{2,25}"
    r"|Editor[- ][Ii]n[- ]Chief|Managing\s+Editor|Senior\s+[A-Za-z]+"
    r"|Lead\s+[A-Za-z]+|Director\s+[Oo]f\s+[A-Za-z ]{2,25}|Director|Manager"
    r"|Engineer|Developer|Designer|Editor|Writer|Journalist|Copywriter"
    r"|Consultant|Analyst|Specialist|Strategist|Architect|Scientist"
    r"|Researcher|Coordinator|Executive|Partner|Owner|Principal"
    r"|(?:Digital\s+|Social\s+Media\s+|Growth\s+|Brand\s+)?Marketing\s+[A-Za-z]+|(?:Digital\s+)?Content\s+[A-Za-z]+)\b")

# Function words only. NOT NON_NAME_TOKENS - that set contains "marketing"
# and "head", which are exactly what job titles are made of.
ROLE_TRAIL_STOP = {
    "for", "of", "and", "the", "a", "an", "to", "in", "on", "at", "with",
    "from", "by", "or", "as", "is", "are", "was", "our", "your", "their",
    "we", "you", "they", "this", "that", "who", "award", "awards", "please",
    "feel", "reach", "contact", "email",
}


def clean_person_name(raw: str | None) -> str | None:
    """
    Normalise a raw string into a display-ready human name, or None.

    Casing is PRESERVED - "McDonald" and "Jean-Luc" must survive intact, so
    no .title() is applied anywhere in this pipeline.
    """
    if not raw or not isinstance(raw, str):
        return None
    s = re.sub(r"\s+", " ", raw).strip(" \t\n\r–—•|,:;-")
    s = re.sub(r"^(?:by|written\s+by|posted\s+by|author)\s*[:\-]?\s*", "", s,
               flags=re.I).strip()
    if not (3 <= len(s) <= 60):
        return None
    if any(ch.isdigit() for ch in s):
        return None
    if re.search(r"[<>{}\[\]\\/@_#=$%^*+;\"]", s):
        return None

    toks = s.split()
    # Leading honorific is stripped ("Dr Ali Raza" -> "Ali Raza"); an
    # honorific anywhere else means we captured surrounding prose.
    while toks and toks[0].strip(".,").lower() in HONORIFICS:
        toks = toks[1:]
    if not (2 <= len(toks) <= 4):
        return None
    if any(t.strip(".,").lower() in HONORIFICS for t in toks):
        return None

    s = " ".join(toks)
    if not RE_NAME_SHAPE.match(s):
        return None

    low = [t.strip(".,").lower() for t in toks]
    if any(t in ABSTRACT_HEADINGS for t in low):
        return None
    for t in low:
        if t in NON_NAME_TOKENS:
            return None
        # hyphen parts too, so "Step-by-Step" is caught like a bare "Step"
        if any(p in NON_NAME_TOKENS for p in t.split("-") if p):
            return None

    # ALL-CAPS short tokens are acronyms or ranks, not given names
    if any(len(t) <= 4 and t.isalpha() and t.isupper() for t in toks):
        return None
    return s


def is_org_byline(name: str) -> bool:
    """
    "Nextly Team" is a real byline but not a person. "Meet The Team" is a
    page heading with the same shape - every word before the suffix must be
    a proper noun for it to count as an organisational credit.
    """
    if not RE_ORG_BYLINE.match(name or ""):
        return False
    toks = name.split()
    return not any(t.strip(".,").lower() in NON_NAME_TOKENS for t in toks[:-1])


def identity_key(name: str) -> str:
    """Canonical key for a person. Casing and punctuation normalised away."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", (name or "").lower())).strip()


def resolve_identity(name: str, known: dict) -> str | None:
    """
    Match a name against already-known people.

    Deliberately CONSERVATIVE. Matching on a single shared token would merge
    "Sarah Lee" into "Sarah Johnson" and silently destroy one person, so only
    two things count as the same human:
      - identical canonical key
      - identical first AND last token (middle names/initials may differ)
    """
    key = identity_key(name)
    if not key:
        return None
    if key in known:
        return key
    parts = key.split()
    if len(parts) < 2:
        return None
    signature = (parts[0], parts[-1])
    for other in known:
        o = other.split()
        if len(o) >= 2 and (o[0], o[-1]) == signature:
            return other
    return None


def _person_type(is_team: bool, is_author: bool) -> str:
    """Machine value: what this person IS on this site."""
    if is_team and is_author:
        return "team_member_and_author"
    if is_team:
        return "team_member"
    if is_author:
        return "author"
    return "unknown"


def _person_type_label(is_team: bool, is_author: bool) -> str:
    """Human-readable form for the UI."""
    return {
        "team_member_and_author": "Team Member & Author",
        "team_member": "Team Member",
        "author": "Author / Writer",
        "unknown": "Unknown",
    }[_person_type(is_team, is_author)]


def tidy_role(raw: str | None) -> str | None:
    """"Head Of Marketing For award nomination" -> "Head Of Marketing"."""
    if not raw:
        return None
    toks = re.sub(r"\s+", " ", raw).strip().split()
    while len(toks) > 1 and toks[-1].strip(".,").lower() in ROLE_TRAIL_STOP:
        toks.pop()
    return " ".join(toks) or None


def classify_socials(urls, site_domain: str) -> dict:
    """Keep only personal profiles; drop share widgets and the brand's own."""
    handle = site_domain.replace("www.", "").split(".")[0].lower()
    found = {}
    for u in urls or []:
        if not u or not isinstance(u, str):
            continue
        low = u.lower()
        if any(x in low for x in ("sharer", "share?", "intent/tweet",
                                  "display=popup", "/share")):
            continue
        for network, pattern in SOCIAL_PATTERNS.items():
            if re.search(pattern, low, re.I):
                # the company's own account, not a person's
                if handle and len(handle) > 2 and f"/{handle}" in low:
                    continue
                found.setdefault(network, u)
    return found


# ============================================================================
# 3. URL CLASSIFICATION
# ============================================================================

HUB_SEGMENTS = {"about", "about-us", "aboutus", "team", "teams", "our-team",
                "the-team", "meet-the-team", "meet-our-team", "our-people",
                "people", "staff", "leadership", "management", "founders",
                "who-we-are", "company", "authors", "contributors", "writers"}

PROFILE_PARENTS = {"author", "authors", "writer", "writers", "contributor",
                   "contributors", "editor", "editors", "profile", "profiles",
                   "member", "members", "people", "team", "staff"}

ARTICLE_SEGMENTS = {"blog", "news", "article", "articles", "post", "posts",
                    "insight", "insights", "resource", "resources", "story",
                    "stories", "press", "update", "updates", "journal",
                    "guide", "guides", "learn", "tutorial", "tutorials",
                    "beginners-guide", "wp-tutorials", "showcase"}

SKIP_SEGMENTS = {"category", "categories", "tag", "tags", "page", "feed",
                 "amp", "wp-json", "wp-content", "wp-admin", "search", "cart",
                 "checkout", "login", "signup", "privacy", "terms", "sitemap",
                 "comment-page-1"}

MEDIA_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf", ".zip",
             ".css", ".js", ".xml", ".mp4", ".mp3", ".ico", ".woff", ".woff2",
             ".avif", ".rss", ".txt"}

RE_URL_DATE = re.compile(r"/(19|20)\d{2}/\d{1,2}(?:/\d{1,2})?/")


def classify_url(url: str) -> str:
    """
    -> 'profile' | 'hub' | 'article' | 'skip'

    Segment-based, never substring. A substring test would classify
    '/blog/about-seo-basics/' as a hub page because it contains '/about',
    which lets hub pages explode into the thousands and blows up the crawl.
    """
    try:
        path = urlparse(url).path.lower()
    except Exception:
        return "skip"

    if any(path.endswith(ext) for ext in MEDIA_EXT):
        return "skip"

    segs = [s for s in path.strip("/").split("/") if s]
    if not segs:
        return "hub"                      # homepage: cheap, may hold bylines
    if any(s in SKIP_SEGMENTS for s in segs):
        return "skip"

    # /author/jane-doe/ , /team/john-smith/
    if len(segs) >= 2 and segs[-2] in PROFILE_PARENTS:
        return "profile"
    if segs[-1] in HUB_SEGMENTS or segs[0] in HUB_SEGMENTS and len(segs) == 1:
        return "hub"
    if RE_URL_DATE.search(path):
        return "article"
    if len(segs) >= 1 and segs[0] == "blog":
        return "article"
    if len(segs) >= 2 and segs[0] in ARTICLE_SEGMENTS:
        return "article"
    if len(segs) >= 2 and any(s in ARTICLE_SEGMENTS for s in segs[:-1]):
        return "article"
    return "skip"


# ============================================================================
# 4. DISCOVERY  (robots -> sitemap -> rss -> homepage)
# ============================================================================

def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


async def _get(client, url, cfg, **kw):
    return await client.get(url, headers=cfg.headers(),
                            timeout=cfg.request_timeout, **kw)


async def _robots_sitemaps(base: str, client, cfg) -> list[str]:
    found = []
    try:
        r = await _get(client, urljoin(base, "/robots.txt"), cfg)
        if r.status_code == 200:
            found = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", r.text)
    except Exception as e:
        logger.debug("robots.txt unreachable: %s", e)
    return found or [urljoin(base, "/sitemap.xml"),
                     urljoin(base, "/sitemap_index.xml")]


async def _parse_sitemap(url, client, cfg, seen=None, depth=0):
    """Recursive sitemap walk. Returns [(loc, lastmod|None), ...]."""
    seen = seen if seen is not None else set()
    if url in seen or depth > 3 or len(seen) > 60:
        return []
    seen.add(url)
    try:
        r = await _get(client, url, cfg)
        if r.status_code != 200:
            return []
        root = ElementTree.fromstring(r.content)
    except Exception as e:
        logger.debug("sitemap %s: %s", url, e)
        return []

    out = []
    if _local(root.tag) == "sitemapindex":
        children = [c.text.strip() for sm in root for c in sm
                    if _local(c.tag) == "loc" and c.text]
        for batch in await asyncio.gather(
                *[_parse_sitemap(c, client, cfg, seen, depth + 1)
                  for c in children], return_exceptions=True):
            if isinstance(batch, list):
                out.extend(batch)
    else:
        for entry in root:
            loc = lastmod = None
            for child in entry:
                t = _local(child.tag)
                if t == "loc" and child.text:
                    loc = child.text.strip()
                elif t == "lastmod" and child.text:
                    lastmod = child.text.strip()
            if loc:
                out.append((loc, lastmod))
    return out[:cfg.max_sitemap_urls]


async def _rss_links(base: str, html: str, client, cfg) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    link = soup.select_one("link[type*='rss'], link[type*='atom']")
    if not link or not link.get("href"):
        return []
    try:
        r = await _get(client, urljoin(base, link["href"]), cfg)
        if r.status_code != 200:
            return []
        xml = ElementTree.fromstring(r.content)
        return [el.text.strip() for el in xml.iter()
                if _local(el.tag) == "link" and el.text]
    except Exception as e:
        logger.debug("rss: %s", e)
        return []


async def discover_urls(base_url: str, client, cfg: PersonaConfig) -> dict:
    """
    Enumerate the site cheaply and bucket every URL by type.

    Returns {"hub": [...], "profile": [...], "article": [(url, lastmod), ...]}
    """
    domain = urlparse(base_url).netloc
    hubs, profiles, articles = {}, {}, {}

    def add(u, lastmod=None):
        if urlparse(u).netloc.replace("www.", "") != domain.replace("www.", ""):
            return
        kind = classify_url(u)
        if kind == "hub":
            hubs[u] = None
        elif kind == "profile":
            profiles[u] = None
        elif kind == "article":
            articles.setdefault(u, lastmod)

    # homepage links + RSS
    try:
        r = await _get(client, base_url, cfg)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                add(urljoin(base_url, a["href"].strip()))
            for u in await _rss_links(base_url, r.text, client, cfg):
                add(u)
    except Exception as e:
        logger.warning("homepage fetch failed for %s: %s", base_url, e)

    # sitemaps
    for sm in await _robots_sitemaps(base_url, client, cfg):
        for loc, lastmod in await _parse_sitemap(sm, client, cfg):
            add(loc, lastmod)

    return {"hub": list(hubs), "profile": list(profiles),
            "article": list(articles.items())}


# ============================================================================
# 5. DATES  (R7 — 2020 onwards)
# ============================================================================

def _parse_date(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    v = value.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d %B %Y", "%B %d, %Y"):
        try:
            dt = datetime.strptime(v[:len(v)], fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", v)
    if m:
        return datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=timezone.utc)
    return None


def extract_published_date(soup: BeautifulSoup, url: str,
                           lastmod: str | None = None) -> datetime | None:
    """
    Priority order, measured coverage on real targets:
      1. JSON-LD datePublished   ~96% of pages
      2. meta article:published_time
      3. <time datetime="...">
      4. /YYYY/MM/ in the URL
      5. sitemap <lastmod>       (weakest: modification, not publication)
    Returns None when unknown - never a guessed date.
    """
    for script in soup.find_all("script", type=re.compile(r"ld\+json", re.I)):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except Exception:
            continue

        def walk(node):
            if isinstance(node, dict):
                for key in ("datePublished", "dateCreated", "uploadDate"):
                    if node.get(key):
                        d = _parse_date(node[key])
                        if d:
                            return d
                for v in node.values():
                    d = walk(v)
                    if d:
                        return d
            elif isinstance(node, list):
                for v in node:
                    d = walk(v)
                    if d:
                        return d
            return None

        d = walk(data)
        if d:
            return d

    for sel in ("meta[property='article:published_time']",
                "meta[name='article:published_time']",
                "meta[property='og:article:published_time']",
                "meta[name='date']", "meta[name='dc.date']"):
        el = soup.select_one(sel)
        if el and el.get("content"):
            d = _parse_date(el["content"])
            if d:
                return d

    el = soup.find("time")
    if el and el.get("datetime"):
        d = _parse_date(el["datetime"])
        if d:
            return d

    m = RE_URL_DATE.search(urlparse(url).path)
    if m:
        parts = [p for p in m.group(0).strip("/").split("/") if p]
        try:
            return datetime(int(parts[0]), int(parts[1]),
                            int(parts[2]) if len(parts) > 2 else 1,
                            tzinfo=timezone.utc)
        except (ValueError, IndexError):
            pass

    return _parse_date(lastmod)


def url_year_hint(url: str) -> int | None:
    """Cheap pre-filter before fetching. None = unknown, keep the URL."""
    m = RE_URL_DATE.search(urlparse(url).path)
    return int(m.group(0).strip("/").split("/")[0]) if m else None


# ============================================================================
# 6. PAGE EXTRACTION
# ============================================================================

# Signal strength drives the confidence score and the evidence gate.
SIGNAL_WEIGHT = {
    "team_card": 0.40,
    "jsonld_author": 0.35,
    "jsonld_person": 0.25,
    "meta_author": 0.30,
    "profile_page": 0.35,
    "microformat": 0.20,
    "byline": 0.20,
    "author_anchor": 0.10,
}
STRONG_SIGNALS = {"team_card", "jsonld_author", "meta_author", "profile_page"}

RE_BYLINE_STRICT = re.compile(
    r"\b(?:written\s+by|posted\s+by|published\s+by|reviewed\s+by|words\s+by"
    r"|story\s+by|author)\s*[:\-–]?\s+"
    rf"({_TOK}(?:\s+{_TOK}){{0,3}})", re.I)
# Bare "by" is prose almost everywhere ("used by Google Analytics to collect
# data"). Only trustworthy directly under the title.
RE_BYLINE_LOOSE = re.compile(rf"\bby\s+({_TOK}(?:\s+{_TOK}){{0,3}})")
BYLINE_TOP_WINDOW = 400


def _strip_noise(soup: BeautifulSoup) -> None:
    for node in soup.select(
            "#comments, .comments-area, .comment-list, .comment-respond, "
            "#disqus_thread, .responses, .trackbacks, script, style, noscript"):
        node.decompose()
    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()


def _name_from_byline(captured: str | None) -> str | None:
    """
    "Mobeen Abdullah on January 12" -> "Mobeen Abdullah".
    Longest-first; the strict token rules in clean_person_name reject the
    contaminated variants, so the first accepted trim is the real name.
    """
    if not captured:
        return None
    toks = captured.split()
    for end in range(len(toks), 1, -1):
        n = clean_person_name(" ".join(toks[:end]))
        if n:
            return n
    return None


def _validate_role(raw: str | None, name: str) -> str | None:
    """
    A role scraped from a CSS selector is only a role if it looks like one.

    Class names are unreliable: WordPress/Elementor emit the person's NAME
    inside <h3 class="elementor-heading-title">, so a naive "[class*='title']"
    selector returns the name and calls it a job title. That bogus role then
    satisfies the corroboration check and lets section headings through as
    people. Two guards: it must not restate the name, and it must contain a
    recognised job-title token.
    """
    if not raw:
        return None
    cand = tidy_role(raw)
    if not cand:
        return None
    if identity_key(cand) == identity_key(name):
        return None
    if name.lower() in cand.lower():
        return None
    if not RE_ROLE.search(cand):
        return None
    return cand


def _role_near(text: str, name: str) -> str | None:
    for m in re.finditer(re.escape(name), text):
        r = RE_ROLE.search(text[m.end(): m.end() + 120])
        if r:
            return tidy_role(r.group(0))
    return None


def _emails_in(*chunks) -> list[str]:
    out = set()
    for c in chunks:
        for m in RE_EMAIL.findall(c or ""):
            if not re.search(r"\.(png|jpe?g|gif|webp|svg)$", m, re.I):
                out.add(m.lower())
    return sorted(out)


def extract_jsonld_people(soup, domain) -> list[dict]:
    people = []
    for script in soup.find_all("script", type=re.compile(r"ld\+json", re.I)):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except Exception:
            continue

        def emit(node, signal):
            if not isinstance(node, dict):
                if isinstance(node, str):
                    n = clean_person_name(node)
                    if n:
                        people.append({"name": n, "signal": signal})
                return
            n = clean_person_name(node.get("name"))
            if not n:
                return
            people.append({
                "name": n,
                "signal": signal,
                "role": tidy_role(node.get("jobTitle")),
                "bio": (node.get("description") or None),
                "emails": _emails_in(node.get("email") or ""),
                "socials": classify_socials(
                    node.get("sameAs") if isinstance(node.get("sameAs"), list)
                    else [node.get("sameAs")], domain),
                "profile_url": node.get("url") if isinstance(node.get("url"), str) else None,
            })

        def walk(node):
            if isinstance(node, list):
                for v in node:
                    walk(v)
                return
            if not isinstance(node, dict):
                return
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if "Person" in types:
                emit(node, "jsonld_person")
            author = node.get("author")
            if author is not None:
                for a in (author if isinstance(author, list) else [author]):
                    emit(a, "jsonld_author")
            for key in ("@graph", "mainEntity", "itemListElement", "hasPart"):
                if node.get(key):
                    walk(node[key])

        walk(data)
    return people


def extract_meta_authors(soup, domain) -> list[dict]:
    out = []
    for sel in ("meta[name='author']", "meta[property='article:author']",
                "meta[name='dc.creator']", "meta[name='twitter:creator']"):
        el = soup.select_one(sel)
        if el and el.get("content"):
            n = clean_person_name(el["content"])
            if n:
                out.append({"name": n, "signal": "meta_author"})
    return out


def extract_microformat_authors(soup, domain) -> list[dict]:
    out = []
    nodes = (soup.find_all(attrs={"rel": re.compile(r"\bauthor\b", re.I)})
             + soup.find_all(attrs={"itemprop": "author"}))
    for el in nodes:
        n = clean_person_name(el.get_text(" ", strip=True))
        if n:
            out.append({"name": n, "signal": "microformat"})
    return out


def extract_bylines(soup, domain) -> list[dict]:
    scope = soup.find("article") or soup.find("main") or soup
    text = scope.get_text(" ", strip=True)
    out = []
    zones = ((text[:1500], RE_BYLINE_STRICT),
             (text[-1500:], RE_BYLINE_STRICT),
             (text[:BYLINE_TOP_WINDOW], RE_BYLINE_LOOSE))
    for zone, rx in zones:
        for m in rx.finditer(zone):
            raw = m.group(1).strip() if m.group(1) else None
            if raw and is_org_byline(raw):
                # Keep org bylines as-is, don't filter through clean_person_name
                out.append({"name": raw, "signal": "byline"})
            else:
                n = _name_from_byline(m.group(1))
                if n:
                    out.append({"name": n, "signal": "byline"})
    return out


def extract_author_anchors(soup, domain, page_url) -> list[dict]:
    out = []
    for a in soup.find_all("a", href=True):
        if classify_url(urljoin(page_url, a["href"])) != "profile":
            continue
        n = clean_person_name(a.get_text(" ", strip=True))
        if n:
            out.append({"name": n, "signal": "author_anchor",
                        "profile_url": urljoin(page_url, a["href"])})
    return out


def _socials_for_person(socials: dict, name: str) -> dict:
    """
    Drop a social link whose handle clearly belongs to someone else.

    Team grids interleave cards, so a scope can bleed into the neighbouring
    person's icons and hand Mushad Usama a colleague's LinkedIn. A profile
    slug like /in/tuba-batool-2106a71b4 carries the owner's name, so when the
    slug parses as a human name that shares NO token with this person, the
    link is not theirs. Slugs that are opaque (handles, initials, numbers)
    carry no counter-evidence and are kept.
    """
    if not socials or not name:
        return socials or {}
    person_tokens = {t for t in identity_key(name).split() if len(t) > 2}
    kept = {}
    for network, url in socials.items():
        slug = urlparse(url).path.rstrip("/").split("/")[-1]
        words = [w for w in re.split(r"[-_.]", slug.lower())
                 if w.isalpha() and len(w) > 2]
        # Only treat it as counter-evidence when the slug reads like a name.
        if len(words) >= 2 and person_tokens and not (set(words) & person_tokens):
            logger.debug("dropped %s for %s (slug=%s)", network, name, slug)
            continue
        kept[network] = url
    return kept


def _card_scope(heading):
    """
    The smallest ancestor of `heading` that still contains only THIS person.

    Team grids frequently place every member's <h2> under one shared parent.
    Using heading.parent as the card would then hand every person the same
    block, and the first name would shadow all the others. Walk up only while
    the ancestor holds a single person-heading.
    """
    node = heading
    for _ in range(4):
        parent = node.parent
        if parent is None:
            break
        count = sum(1 for h in parent.find_all(["h2", "h3", "h4", "h5"])
                    if clean_person_name(h.get_text(" ", strip=True)))
        if count > 1:
            break
        node = parent
    return node


def extract_team_cards(soup, domain, page_url) -> list[dict]:
    """
    Team pages render one repeated card per person. Each card is a scope, so
    the role, bio, socials and email inside it belong to THAT person - which
    is how multi-person team pages get per-person contact details instead of
    all-or-nothing.
    """
    out = []
    selectors = (".team-member, .staff-member, .team-card, .member-card, "
                 ".person, .profile-card, [class*='team-member'], "
                 "[class*='staff'], [class*='teamMember'], li.member, "
                 ".our-team .col, .team .col")
    # (card, is_semantic). A semantic class like .team-member is itself proof
    # the block describes a person.
    candidates = [(c, True) for c in soup.select(selectors)]

    # Fallback for hand-rolled markup with no semantic class names. A bare
    # Title Case heading is NOT enough on its own - "Media Library" and
    # "TypeScript Native" are shaped exactly like two-word human names - so
    # these are corroborated below before being accepted.
    candidates = [(c, True, None) for c, _ in candidates]

    heading_tag = {}          # name -> heading level it was found at
    if not candidates:
        for h in soup.find_all(["h2", "h3", "h4", "h5"]):
            n = clean_person_name(h.get_text(" ", strip=True))
            if n:
                candidates.append((_card_scope(h), False, n))
                heading_tag.setdefault(n, h.name)

    img_alts = " . ".join(
        img.get("alt", "") for img in soup.find_all("img") if img.get("alt"))

    seen = set()
    for card, is_semantic, forced_name in candidates[:60]:
        name = forced_name
        if not name:
            for tag in ("h2", "h3", "h4", "h5", ".name", "[class*='name']",
                        "strong", "b"):
                el = (card.find(tag) if tag.startswith("h")
                      else card.select_one(tag))
                if el:
                    name = clean_person_name(el.get_text(" ", strip=True))
                    if name:
                        break
        if not name or name in seen:
            continue

        card_text = card.get_text(" ", strip=True)
        role = None
        for sel in (".role", ".title", ".position", ".designation", ".job-title",
                    "[class*='role']", "[class*='position']", "[class*='designation']",
                    "[class*='title']"):
            el = card.select_one(sel)
            if not el:
                continue
            cand = _validate_role(el.get_text(" ", strip=True), name)
            if cand:
                role = cand
                break
        role = role or _role_near(card_text, name)

        bio = None
        for sel in (".bio", ".description", "[class*='bio']", "p"):
            el = card.select_one(sel)
            if el:
                t = el.get_text(" ", strip=True)
                if t and len(t) > 30 and t != name:
                    bio = t[:600]
                    break

        hrefs = [urljoin(page_url, a["href"]) for a in card.find_all("a", href=True)]
        mailtos = [h[7:] for h in hrefs if h.lower().startswith("mailto:")]
        socials = _socials_for_person(classify_socials(hrefs, domain), name)
        profile = next((h for h in hrefs if classify_url(h) == "profile"), None)

        # Corroboration for non-semantic cards: a real team member has a job
        # title, a profile link, a headshot alt bearing their name, or a
        # personal social account. A feature heading has none of these.
        corroborated = is_semantic or bool(role) or bool(profile) or bool(socials) \
            or bool(re.search(r"\b" + re.escape(name) + r"\b", img_alts))

        seen.add(name)
        out.append({
            "_corroborated": corroborated,
            "_tag": heading_tag.get(name),
            "name": name,
            "signal": "team_card",
            "role": role,
            "bio": bio,
            "socials": socials,
            "emails": _emails_in(" ".join(mailtos), card_text),
            "profile_url": profile,
            "is_team_member": True,
        })

    # SIBLING RULE: a team grid emits every member at the same heading level.
    # Once two names at that level are corroborated, the level IS a person
    # list, so accept the rest. Without this, a member whose job title is
    # misspelt ("Cheif Technology Officer") or simply absent is dropped even
    # though their colleagues in the identical markup were kept.
    strong_tags = {}
    for e in out:
        if e["_corroborated"] and e["_tag"]:
            strong_tags[e["_tag"]] = strong_tags.get(e["_tag"], 0) + 1
    person_tags = {t for t, c in strong_tags.items() if c >= 2}

    accepted = []
    for e in out:
        if e["_corroborated"] or e["_tag"] in person_tags:
            e.pop("_corroborated", None)
            e.pop("_tag", None)
            accepted.append(e)
    return accepted


def extract_profile_page(soup, domain, page_url) -> list[dict]:
    """A dedicated /author/<slug>/ page. The whole page is one person."""
    name = None
    h1 = soup.find("h1")
    if h1:
        name = clean_person_name(h1.get_text(" ", strip=True))
    if not name and soup.title:
        name = clean_person_name(re.split(r"[|–—\-]",
                                          soup.title.get_text())[0])
    if not name:
        slug = urlparse(page_url).path.rstrip("/").split("/")[-1]
        name = clean_person_name(slug.replace("-", " ").replace("_", " ").title())
    if not name:
        return []

    text = soup.get_text(" ", strip=True)
    hrefs = [urljoin(page_url, a["href"]) for a in soup.find_all("a", href=True)]
    role = _role_near(text, name)
    if not role:
        m = RE_ROLE.search(text[:2000])
        role = tidy_role(m.group(0)) if m else None

    bio = None
    for sel in (".author-bio", ".bio", "[class*='bio']", "[class*='description']"):
        el = soup.select_one(sel)
        if el:
            t = el.get_text(" ", strip=True)
            if len(t) > 40:
                bio = t[:800]
                break

    return [{
        "name": name,
        "signal": "profile_page",
        "role": role,
        "bio": bio,
        "socials": classify_socials(hrefs, domain),
        "emails": _emails_in(text[:6000]),
        "profile_url": page_url,
    }]



def extract_page_signals(html: str, url: str, kind: str, domain: str) -> dict:
    """
    Parse one page into person-signals plus metadata.

    Takes RAW HTML. Passing extracted text here silently disables every
    selector-based extractor.
    """
    soup = BeautifulSoup(html, "html.parser")
    _strip_noise(soup)

    people: list[dict] = []
    people += extract_jsonld_people(soup, domain)
    people += extract_meta_authors(soup, domain)

    if kind == "profile":
        people += extract_profile_page(soup, domain, url)
    if kind in ("hub", "profile"):
        people += extract_team_cards(soup, domain, url)
    if kind == "article":
        people += extract_microformat_authors(soup, domain)
        people += extract_bylines(soup, domain)
    people += extract_author_anchors(soup, domain, url)

    # organisational credits are recorded separately, never as humans
    org = None
    for cand in (soup.find("h1"), soup.title):
        if cand:
            t = re.sub(r"\s+", " ", cand.get_text()).strip()
            if is_org_byline(t):
                org = t
                break
    
    # Check extracted bylines for organization names
    if not org:
        for person in people:
            if person.get("signal") == "byline" and is_org_byline(person["name"]):
                org = person["name"]
                people = [p for p in people if p["name"] != org]
                break
    
    # Fallback: search article text for company/team byline patterns like "Nextly Team · 2026"
    if not org and kind == "article":
        scope = soup.find("article") or soup.find("main") or soup
        text = scope.get_text(" ", strip=True)[:1000]
        # Look for pattern: "OrgName · YYYY-MM-DD" or "OrgName · YYYY"
        import re as regex_module
        for m in regex_module.finditer(r"([A-Z][A-Za-z\s]{2,30}Team)\s*[·•\-]\s*(?:20|19)\d{2}", text):
            cand = m.group(1).strip()
            if is_org_byline(cand):
                org = cand
                break

    scope = soup.find("article") or soup.find("main") or soup
    return {
        "url": url,
        "kind": kind,
        "people": people,
        "org_byline": org,
        "title": (soup.title.get_text(strip=True) if soup.title else None),
        "published": None,          # filled by caller (needs lastmod)
        "soup": soup,
        "text": scope.get_text(" ", strip=True),
    }


# ============================================================================
# 7. FETCH
# ============================================================================

async def fetch_page(client, url, kind, cfg, sem, lastmod=None):
    """Fetch one page with bounded concurrency and growing backoff."""
    async with sem:
        for attempt in range(cfg.retries):
            try:
                r = await _get(client, url, cfg, follow_redirects=True)
                if r.status_code == 200:
                    ctype = r.headers.get("content-type", "")
                    if "html" not in ctype.lower():
                        return None
                    sig = extract_page_signals(r.text, url, kind,
                                               urlparse(url).netloc)
                    sig["published"] = extract_published_date(
                        sig.pop("soup"), url, lastmod)
                    return sig
                if r.status_code in (429, 502, 503, 504):
                    await asyncio.sleep(cfg.retry_backoff_base * (2 ** attempt))
                    continue
                return None
            except Exception as e:
                logger.debug("fetch %s attempt %d: %s", url, attempt + 1, e)
                if attempt < cfg.retries - 1:
                    await asyncio.sleep(cfg.retry_backoff_base * (2 ** attempt))
    return None


# ============================================================================
# 8. REGISTRY
# ============================================================================

class PersonRegistry:
    """Accumulates evidence per person. Merging is conservative."""

    def __init__(self):
        self.people: dict[str, dict] = {}

    def add(self, entry: dict, page: dict) -> None:
        name = entry.get("name")
        if not name:
            return
        key = resolve_identity(name, self.people) or identity_key(name)
        p = self.people.setdefault(key, {
            "name": name, "role": None, "bio": None, "profile_url": None,
            "emails": [], "socials": {}, "signals": {}, "is_team_member": False,
            "articles": {},     # url -> published datetime|None
            "evidence": [],
        })
        # keep the longest spelling ("J. Smith" < "Jane Smith")
        if len(name) > len(p["name"]):
            p["name"] = name

        sig = entry.get("signal", "unknown")
        p["signals"][sig] = p["signals"].get(sig, 0) + 1
        p["evidence"].append(f"{sig}:{page['url']}")

        p["role"] = p["role"] or tidy_role(entry.get("role"))
        if not p["bio"] and entry.get("bio"):
            p["bio"] = re.sub(r"\s+", " ", entry["bio"]).strip()[:800]
        p["profile_url"] = p["profile_url"] or entry.get("profile_url")
        p["is_team_member"] = p["is_team_member"] or bool(entry.get("is_team_member"))
        if page["kind"] in ("hub", "profile") and sig in ("team_card", "profile_page"):
            p["is_team_member"] = True

        for k, v in (entry.get("socials") or {}).items():
            p["socials"].setdefault(k, v)
        for e in entry.get("emails") or []:
            if e not in p["emails"]:
                p["emails"].append(e)

        if page["kind"] == "article":
            p["articles"].setdefault(page["url"], page.get("published"))

    def confidence(self, p: dict) -> float:
        score = sum(SIGNAL_WEIGHT.get(s, 0.05) for s in p["signals"])
        score += 0.10 * bool(p["profile_url"])
        score += 0.10 * bool(p["socials"])
        score += 0.10 * bool(p["emails"])
        return round(min(1.0, score), 2)

    def has_sufficient_evidence(self, p: dict) -> bool:
        """One strong signal, or two independent medium ones. Never one weak."""
        signals = set(p["signals"])
        if signals & STRONG_SIGNALS:
            return True
        return len([s for s in signals if s != "author_anchor"]) >= 2


# ============================================================================
# 9. LLM WRITING STYLE  (R5 — strict, never hallucinated)
# ============================================================================

STYLE_PROMPT = """You are analysing one writer's voice from real excerpts of their published work.

Return ONLY a JSON object. No preamble, no markdown fences. Exact keys:
  "tone": array of 3-5 adjectives, or null
  "vocabulary": one of "technical" | "conversational" | "academic" | "mixed", or null
  "sentence_style": 1-2 sentences on sentence length, rhythm and structure, or null
  "point_of_view": "first" | "second" | "third" | "mixed", or null
  "signature_traits": array of 2-4 concrete habits, or null
  "expertise_topics": array of 3-6 subject areas, or null

RULES — these override everything else:
- Base every field ONLY on the excerpts below. Use no outside knowledge.
- If the excerpts are too short, too few, or too generic to judge a field,
  set that field to null. A null is correct; a guess is a failure.
- Never infer demographics, seniority, employer or credentials.

WRITER: {name}
EXCERPT COUNT: {count}
EXCERPTS:
{samples}"""


async def analyze_writing_style(model, name: str, samples: list[dict],
                                cfg: PersonaConfig) -> dict:
    """
    Returns the analysis dict, or {"error": ...} — never partial, never faked.
    One sample minimum, by explicit request — style read from a single
    article is weaker than from several, but is run rather than skipped.
    """
    usable = [s for s in samples if s.get("text")]

    print(f"DEBUG: Samples count: {len(samples)}, Usable text count: {len(usable)}")
    if len(usable) < 1:
        return {"error": f"insufficient_evidence: {len(usable)} sample(s), need 1+"}

    per = max(500, cfg.sample_chars)
    blob = "\n\n---\n\n".join(
        f"[{s.get('title') or s['url']}]\n{s['text'][:per]}" for s in usable
    )
    try:
        prompt = STYLE_PROMPT.format(name=name, count=len(usable), samples=blob)
        if hasattr(model, "ainvoke"):
            resp = await model.ainvoke(prompt)
        else:
            resp = await asyncio.to_thread(model.invoke, prompt)
        raw = getattr(resp, "content", None) or str(resp)
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return {"error": "llm_returned_non_object"}
        parsed["_evidence"] = {
            "sample_count": len(usable),
            "chars_analysed": sum(len(s["text"][:per]) for s in usable),
            "article_urls": [s["url"] for s in usable],
        }
        return parsed
    except Exception as e:
        logger.debug("style analysis failed for %s: %s", name, e)
        return {"error": f"{type(e).__name__}: {e}"}


# ============================================================================
# 10. PIPELINE
# ============================================================================

async def discover_personas(base_url: str,
                            cfg: PersonaConfig | None = None) -> dict:
    cfg = cfg or PersonaConfig()
    if not base_url.startswith(("http://", "https://")):
        base_url = "https://" + base_url
    domain = urlparse(base_url).netloc
    started = datetime.now(timezone.utc)

    limits = httpx.Limits(max_connections=cfg.concurrency * 2,
                          max_keepalive_connections=cfg.concurrency)
    async with httpx.AsyncClient(limits=limits, follow_redirects=True,
                                 verify=cfg.verify_tls) as client:

        # -- phase 1: enumerate ------------------------------------------
        logger.info("[1/4] enumerating %s", base_url)
        buckets = await discover_urls(base_url, client, cfg)
        hubs = buckets["hub"][:cfg.max_hub_pages]
        profiles = buckets["profile"][:cfg.max_hub_pages]
        articles = buckets["article"]

        # cheap pre-filter: drop URLs whose PATH proves they predate the cutoff.
        # Unknown-date URLs are kept and re-checked after fetch (R7 exactly).
        dated_out = [(u, lm) for u, lm in articles
                     if (y := url_year_hint(u)) is not None
                     and y < cfg.min_article_year]
        kept = [(u, lm) for u, lm in articles if (u, lm) not in set(dated_out)]

        # newest-first where lastmod is known, so the cap keeps recent work
        kept.sort(key=lambda t: (t[1] or ""), reverse=True)
        capped = kept[:cfg.max_articles]

        logger.info("      hubs=%d profiles=%d articles=%d "
                    "(pre-filtered %d, capped to %d)",
                    len(hubs), len(profiles), len(articles),
                    len(dated_out), len(capped))

        # -- phase 2: fetch ----------------------------------------------
        sem = asyncio.Semaphore(cfg.concurrency)
        tasks = ([fetch_page(client, u, "hub", cfg, sem) for u in hubs]
                 + [fetch_page(client, u, "profile", cfg, sem) for u in profiles]
                 + [fetch_page(client, u, "article", cfg, sem, lm)
                    for u, lm in capped])
        logger.info("[2/4] fetching %d pages (concurrency=%d)",
                    len(tasks), cfg.concurrency)
        pages = [p for p in await asyncio.gather(*tasks, return_exceptions=True)
                 if isinstance(p, dict)]

        # -- phase 3: aggregate ------------------------------------------
        logger.info("[3/4] extracting people from %d pages", len(pages))
        registry = PersonRegistry()
        org_bylines: dict[str, set] = {}
        cutoff = datetime(cfg.min_article_year, 1, 1, tzinfo=timezone.utc)
        article_text: dict[str, dict] = {}

        for page in pages:
            # authoritative date filter, now that we have the real date (R7)
            if page["kind"] == "article":
                pub = page.get("published")
                if pub is not None and pub < cutoff:
                    continue
                article_text[page["url"]] = {
                    "url": page["url"], "title": page.get("title"),
                    "text": page.get("text", ""), "published": pub,
                }
                # If there is no explicit human author, attribute article to team members
                if not page.get("people"):
                    for key, p in registry.people.items():
                        if p["is_team_member"]:
                            p["articles"].setdefault(page["url"], pub)

            if page.get("org_byline"):
                org_bylines.setdefault(page["org_byline"], set()).add(page["url"])
                # Ensure article text is available for style analysis
                if page["url"] not in article_text and page.get("text"):
                    article_text[page["url"]] = {
                        "url": page["url"], "title": page.get("title"),
                        "text": page.get("text"), "published": page.get("published"),
                    }
                for key, p in registry.people.items():
                    if p["is_team_member"]:
                        p["articles"].setdefault(page["url"], page.get("published"))

            for entry in page["people"]:
                registry.add(entry, page)

        # -- phase 4: score, sample, analyse ------------------------------
        model = None
        if cfg.enable_llm and HAS_LLM:
            try:
                model = load_model()
            except Exception as e:
                logger.warning("LLM unavailable, style analysis skipped: %s", e)

        personas = []
        for key, p in registry.people.items():
            if is_org_byline(p["name"]):
                continue
            if not registry.has_sufficient_evidence(p):
                logger.debug("dropped (weak evidence): %s %s", p["name"], p["signals"])
                continue
            conf = registry.confidence(p)
            if conf < cfg.min_confidence:
                continue

            # newest articles first (R7)
            arts = sorted(p["articles"].items(),
                          key=lambda kv: (kv[1] is not None, kv[1] or cutoff),
                          reverse=True)
            samples = [article_text[u] for u, _ in arts
                       if u in article_text][:cfg.samples_per_person]
            style = {"error": "not_run"}
            if model is not None and len(samples) >= 1:
                style = await analyze_writing_style(model, p["name"], samples, cfg)

           

            dates = [d for _, d in arts if d is not None]
            personas.append({
                "name": p["name"],
                "title_role": p["role"] or _person_type_label(
                    p["is_team_member"], bool(p["articles"])),
                "bio": p["bio"],
                "is_team_member": p["is_team_member"],                 # R9
                "is_author": bool(p["articles"]),
                "person_type": _person_type(p["is_team_member"],
                                            bool(p["articles"])),
                "person_type_label": _person_type_label(
                    p["is_team_member"], bool(p["articles"])),
                "cross_check": ("team_member_and_author"
                                if p["is_team_member"] and p["articles"]
                                else "team_member_only" if p["is_team_member"]
                                else "author_only"),
                "profile_url": p["profile_url"],
                "email": p["emails"][0] if p["emails"] else None,      # R3
                "all_emails": p["emails"],
                "socials": p["socials"],                               # R2
                "article_count": len(p["articles"]),                   # R6
                "article_urls": [u for u, _ in arts],
                "latest_article_date": max(dates).isoformat() if dates else None,
                "earliest_article_date": min(dates).isoformat() if dates else None,
                "sample_articles": [                                   # R7
                    {"url": s["url"], "title": s["title"],
                     "published": s["published"].isoformat() if s["published"] else None}
                    for s in samples
                ],
                "expertise": (style.get("expertise_topics")             # R4
                              if isinstance(style, dict) else None) or [],
                "writing_style": style,                                # R5
                "confidence": conf,
                "signals": sorted(p["signals"]),
                "evidence": p["evidence"][:12],
            })

        personas.sort(key=lambda x: (-x["confidence"], -x["article_count"], x["name"]))

    result = {
        "target": base_url,
        "domain": domain,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(
            (datetime.now(timezone.utc) - started).total_seconds(), 1),
        "config": {"min_article_year": cfg.min_article_year,
                   "max_articles": cfg.max_articles,
                   "concurrency": cfg.concurrency},
        "stats": {
            "urls_found": {k: len(v) for k, v in buckets.items()},
            "pages_fetched": len(pages),
            "people_before_gating": len(registry.people),
            "personas_returned": len(personas),
        },
        "organizational_bylines": [
            {"name": n, "article_count": len(urls)}
            for n, urls in sorted(org_bylines.items())
        ],
        "personas": personas,
    }

    if cfg.out_dir:
        cfg.out_dir.mkdir(parents=True, exist_ok=True)
        out = cfg.out_dir / f"{domain.replace('.', '_')}_personas.json"
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False,
                                  default=str), encoding="utf-8")
        logger.info("saved -> %s", out)
    return result


# ============================================================================
# 11. DB MAPPING  (matches src/api/models/knowledge_models/persona_model.py)
# ============================================================================

def to_persona_rows(result: dict, workspace_id) -> list[dict]:
    """Map discovery output onto the Persona table's columns."""
    rows = []
    for p in result["personas"]:
        style = p.get("writing_style") or {}
        tone = style.get("tone") if isinstance(style, dict) else None
        rows.append({
            "workspace_id": workspace_id,
            "name": p["name"],
            "full_name": p["name"],
            "professional_title": p["title_role"],
            "areas_of_expertise": p["expertise"] or None,
            "tone_of_voice": ", ".join(tone) if isinstance(tone, list) else None,
            "bio": p["bio"],
            "linkedin_url": p["socials"].get("linkedin"),
            "description": (
                f"{p['person_type_label']}; {p['article_count']} article(s)"
                + (f"; latest {p['latest_article_date'][:10]}"
                   if p["latest_article_date"] else "")),
            "custom_metadata": {
                "email": p["email"],
                "all_emails": p["all_emails"],
                "socials": p["socials"],
                "profile_url": p["profile_url"],
                "person_type": p["person_type"],
                "person_type_label": p["person_type_label"],
                "is_team_member": p["is_team_member"],
                "is_author": p["is_author"],
                "cross_check": p["cross_check"],
                "article_count": p["article_count"],
                "article_urls": p["article_urls"][:50],
                "latest_article_date": p["latest_article_date"],
                "earliest_article_date": p["earliest_article_date"],
                "sample_articles": p["sample_articles"],
                "writing_style": style,
                "confidence": p["confidence"],
                "signals": p["signals"],
                "evidence": p["evidence"],
                "discovered_at": result["finished_at"],
            },
        })
    return rows