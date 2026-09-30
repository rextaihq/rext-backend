"""Fast, browser-free site scraping shared by workspace brand-voice/persona
extraction and competitor discovery.
"""

import asyncio
import hashlib
import logging
import random
import re
from contextvars import ContextVar
from datetime import datetime
from typing import Dict, Iterable, List, Optional
from urllib.parse import quote, urljoin, urlparse

import httpx
import tldextract
from bs4 import BeautifulSoup

from src.utils.url_validator import SSRFValidationError, validate_url_for_ssrf

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
# Every request (pages, feeds, archives, gravatar) sends the same headers.
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}
CONCURRENCY = 5
REQUEST_TIMEOUT = 25
MAX_FETCH_ATTEMPTS = 3
POST_FETCH_ATTEMPTS = 2
SITEMAP_TIMEOUT = 5
RETRY_BACKOFF_SECONDS = 0.75
_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
# Answers that mean "this client was refused", as opposed to "no such page".
BLOCKED_STATUS = {401, 403, 406, 429, 503}
_CHALLENGE_TITLE_RE = re.compile(
    r"(?i)<title>\s*(?:just a moment|attention required|access denied|checking your browser)"
)
# Collects the refused URLs of the scrape_site() call currently running.
_FETCH_REFUSALS: ContextVar[Optional[Dict[str, object]]] = ContextVar(
    "_FETCH_REFUSALS", default=None
)
REACHABILITY_TIMEOUT = 10
# Only the start of the landing page is read when looking for a parked domain.
PARKED_SNIFF_BYTES = 64 * 1024
# Domain marketplaces a for-sale domain redirects to.
_PARKING_HOSTS = (
    "sedo.com",
    "sedoparking.com",
    "parkingcrew.net",
    "bodis.com",
    "dan.com",
    "afternic.com",
    "hugedomains.com",
    "undeveloped.com",
    "parklogic.com",
    "domainmarket.com",
)
# Scripts that parking landers load, found in the page itself.
_PARKING_SCRIPT_RE = re.compile(
    r"(?:sedoparking\.com|parkingcrew\.net|img1\.wsimg\.com/parking-lander|bodis\.com/)"
)
_PARKED_PHRASE_RE = re.compile(
    r"(?i)(?:this|the)\s+domain(?:\s+name)?(?:\s+[\w.-]+)?\s+(?:is|may\s+be)\s+for\s+sale"
    r"|buy\s+this\s+domain|make\s+an\s+offer\s+on\s+this\s+domain"
    r"|this\s+domain\s+has\s+expired|this\s+domain\s+is\s+parked"
)
_PARKED_MESSAGE = (
    "This website looks parked or for sale, not a live business site. "
    "Please enter your real website URL."
)


class WebsiteUnreachableError(ValueError):
    """Raised when a URL does not point to a live website."""


async def check_website_reachable(url: str) -> None:
    """
    Confirm that `url` belongs to a live website before we build anything on it.

    The domain must resolve to a public IP (same SSRF rules as the scraper) and
    the server must answer an HTTP request. Any HTTP status counts as reachable:
    real sites often refuse bots with 401/403/429, and the scraper already copes
    with those. Only "no such domain", "connection refused", timeouts and
    parked/for-sale landing pages fail.

    Raises:
        WebsiteUnreachableError: with a user-facing message.
    """
    try:
        await asyncio.to_thread(validate_url_for_ssrf, url)
    except SSRFValidationError as exc:
        if str(exc).startswith("Could not resolve hostname"):
            raise WebsiteUnreachableError(
                "This website does not exist. Please check the URL and try again."
            ) from exc
        raise WebsiteUnreachableError("This URL is not allowed.") from exc

    try:
        async with httpx.AsyncClient(
            headers=REQUEST_HEADERS,
            verify=False,
            follow_redirects=True,
            timeout=REACHABILITY_TIMEOUT,
        ) as client:
            # Stream so only the start of the page is read, never the whole body.
            async with client.stream("GET", url) as response:
                final_host = (response.url.host or "").lower()
                head = b""
                async for chunk in response.aiter_bytes():
                    head += chunk
                    if len(head) >= PARKED_SNIFF_BYTES:
                        break
    except httpx.TimeoutException as exc:
        logger.info("Website reachability check timed out for %s", url)
        raise WebsiteUnreachableError(
            "This website is not responding. Please check the URL and try again."
        ) from exc
    except httpx.HTTPError as exc:
        logger.info("Website reachability check failed for %s: %s", url, exc)
        raise WebsiteUnreachableError(
            "We couldn't reach this website. Please check the URL and try again."
        ) from exc

    # A parked or for-sale domain answers HTTP but is not a real business site.
    page = head[:PARKED_SNIFF_BYTES].decode("utf-8", errors="ignore").lower()
    if (
        any(final_host == host or final_host.endswith("." + host) for host in _PARKING_HOSTS)
        or _PARKING_SCRIPT_RE.search(page)
        or _PARKED_PHRASE_RE.search(page)
    ):
        raise WebsiteUnreachableError(_PARKED_MESSAGE)


def _record_refusal(url: str, status: object) -> None:
    refusals = _FETCH_REFUSALS.get()
    if refusals is not None:
        refusals[url] = status


ABOUT_KEYWORDS = ("about", "product", "service", "solution", "pricing", "platform", "feature")
TEAM_KEYWORDS = (
    "team",
    "leadership",
    "staff",
    "people",
    "founder",
    "meet",
    "our-team",
    "who-we-are",
    "story",
    "leadership-team",
    "company",
)
BLOG_KEYWORDS = ("blog", "news", "press", "insights", "articles", "resources")
_PRIORITY_MAX_SEGMENTS = 2

_NON_BRAND_VOICE_MARKERS = (
    "comment-list",
    "comments-area",
    "comment-respond",
    "commentlist",
    "comments-section",
    "comment-form",
    "respond",
    "disqus",
    "livefyre",
    "faq",
    "frequently-asked",
    "question-answer",
    "accordion-faq",
)
_PULL_QUOTE_MIN_BODY = 100
_TESTIMONIAL_MARKERS = (
    "testimonial",
    "wall-of-love",
    "walloflove",
    "customer-story",
    "customer-stories",
    "customer-quote",
    "client-quote",
    "case-study",
    "case-studies",
    "trustpilot",
    "review-card",
    "review-slider",
    "reviews-carousel",
    "review-carousel",
    "quote-card",
    "success-story",
)
_TAXONOMY_SEGMENTS = {
    "page",
    "category",
    "categories",
    "tag",
    "tags",
    "author",
    "authors",
    "topic",
    "topics",
    "label",
    "labels",
    "archive",
    "archives",
    "section",
    "search",
    "feed",
    "rss",
}
_BLOG_INDEX_CANDIDATES = 15

_MAX_SUB_SITEMAPS = 5
_POST_WAVE_SIZE = 4
DEFAULT_BUDGET_SECONDS = 50.0
ENOUGH_AUTHORS = 10
ARCHIVE_GRACE_SECONDS = 10.0
ARCHIVE_RESERVE_SECONDS = 6.0
ARCHIVE_MIN_WINDOW_SECONDS = 10.0
MAX_OVERRUN_SECONDS = 10.0

_EXTERNAL_PERSON_KEYWORDS = (
    "keynote",
    "speaker",
    "guest-post",
    "guest-author",
    "interview-with",
    "podcast",
    "webinar",
    "panelist",
    "ambassador",
    "sponsor",
)
_PERSONA_SIGNAL_KEYWORDS = (
    "meet",
    "welcome",
    "named",
    "president",
    "vice-president",
    "vp-",
    "ceo",
    "cfo",
    "coo",
    "founder",
    "manager",
    "spotlight",
    "profile",
    "employee",
    "team-member",
    "promoted",
    "promotion",
    "joins",
    "appointed",
    "leadership",
    "hire",
    "welcomes",
)

_CO_AUTHOR_SPLIT_RE = re.compile(r"\b(?:and|&|with)\b|,", re.I)


def _tokens(text: str) -> List[str]:
    words = re.split(r"[^a-z0-9]+", text.lower())
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if w]


def _matches_keyword(path: str, keywords: Iterable[str]) -> bool:
    segments = [seg for seg in path.lower().split("/") if seg]
    for keyword in keywords:
        kw = _tokens(keyword)
        if not kw:
            continue
        for seg in segments:
            words = _tokens(seg)
            n = len(kw)
            if any(words[i : i + n] == kw for i in range(len(words) - n + 1)):
                return True
    return False


PAGE_TEAM = "team"
PAGE_ARTICLE = "article"
PAGE_OTHER = "other"

_ARTICLE_PATH_HINTS = (
    "blog",
    "news",
    "article",
    "articles",
    "post",
    "posts",
    "insights",
    "press",
    "stories",
    "story",
    "resources",
    "perspectives",
    "updates",
)
_ARTICLE_HOST_PREFIXES = ("blog.", "news.", "insights.", "stories.", "press.")


def classify_page(url: str, text: str = "") -> str:
    if text.startswith("Article author:") or text.startswith("Author profile:"):
        return PAGE_ARTICLE
    path = urlparse(url).path.lower()
    host = (urlparse(url).netloc or "").lower()
    if _matches_keyword(path, TEAM_KEYWORDS + ("about", "about-us")):
        return PAGE_TEAM
    if _matches_keyword(path, _ARTICLE_PATH_HINTS):
        return PAGE_ARTICLE
    if any(host.startswith(prefix) for prefix in _ARTICLE_HOST_PREFIXES):
        return PAGE_ARTICLE
    return PAGE_OTHER


_SOUP_CACHE: Dict[int, tuple] = {}
_SOUP_CACHE_MAX = 6


def _soup(html: str) -> BeautifulSoup:
    key = id(html)
    hit = _SOUP_CACHE.get(key)
    if hit is not None and hit[0] is html:
        return hit[1]
    tree = BeautifulSoup(html or "", "html.parser")
    if len(_SOUP_CACHE) >= _SOUP_CACHE_MAX:
        _SOUP_CACHE.clear()
    _SOUP_CACHE[key] = (html, tree)
    return tree


def _domain(url: str) -> str:
    ext = tldextract.extract(url)
    return ".".join(p for p in [ext.domain, ext.suffix] if p)


def _is_stripped_block(marker: str) -> bool:
    """Whether a class/id string marks a testimonial, comment or FAQ block.

    "respond" is WordPress's comment form; it must not match layout classes such
    as "img-responsive" or "table-responsive", which wrap real content.
    """
    return any(
        (re.search(r"respond(?!ive)", marker) if m == "respond" else m in marker)
        for m in _TESTIMONIAL_MARKERS + _NON_BRAND_VOICE_MARKERS
    )


def visible_html(html: str, *, strip_testimonials: bool = False) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "header", "nav", "footer"]):
        tag.decompose()
    if strip_testimonials:
        for figure in soup.find_all(["figure", "blockquote"]):
            caption = figure.find(["figcaption", "cite"])
            if (
                caption
                and (len(figure.get_text(" ", strip=True)) - len(caption.get_text(" ", strip=True)))
                >= _PULL_QUOTE_MIN_BODY
            ):
                figure.decompose()
        doomed = []
        for tag in soup.find_all(True):
            marker = " ".join(tag.get("class") or [])
            marker = f"{marker} {tag.get('id') or ''}".lower()
            if _is_stripped_block(marker):
                doomed.append(tag)
        for tag in doomed:
            tag.decompose()
    return str(soup)


_TEXT_CACHE: Dict[tuple, tuple] = {}
_TEXT_CACHE_MAX = 12


def visible_text(
    html: str,
    max_chars: Optional[int] = 3000,
    *,
    strip_footer: bool = True,
    strip_testimonials: bool = False,
) -> str:
    key = (id(html), strip_footer, strip_testimonials)
    hit = _TEXT_CACHE.get(key)
    if hit is not None and hit[0] is html:
        return hit[1] if max_chars is None else hit[1][:max_chars]
    full = _visible_text_uncached(
        html, None, strip_footer=strip_footer, strip_testimonials=strip_testimonials
    )
    if len(_TEXT_CACHE) >= _TEXT_CACHE_MAX:
        _TEXT_CACHE.clear()
    _TEXT_CACHE[key] = (html, full)
    return full if max_chars is None else full[:max_chars]


def _visible_text_uncached(
    html: str,
    max_chars: Optional[int] = 3000,
    *,
    strip_footer: bool = True,
    strip_testimonials: bool = False,
) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    strip_tags = ["script", "style", "noscript", "svg", "header", "nav"]
    if strip_footer:
        strip_tags.append("footer")
    for tag in soup(strip_tags):
        tag.decompose()
    if strip_testimonials:
        for figure in soup.find_all(["figure", "blockquote"]):
            caption = figure.find(["figcaption", "cite"])
            if not caption:
                continue
            body = figure.get_text(" ", strip=True)
            attribution = caption.get_text(" ", strip=True)
            if len(body) - len(attribution) >= _PULL_QUOTE_MIN_BODY:
                figure.decompose()

        doomed = []
        for tag in soup.find_all(True):
            marker = " ".join(tag.get("class") or [])
            marker = f"{marker} {tag.get('id') or ''}".lower()
            if _is_stripped_block(marker):
                doomed.append(tag)
        for tag in doomed:
            tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    if max_chars is None:
        return text
    return text[:max_chars]


def _head_tail(text: str, max_chars: int, tail_fraction: float = 0.35) -> str:
    if len(text) <= max_chars:
        return text
    tail_chars = int(max_chars * tail_fraction)
    head_chars = max_chars - tail_chars
    return f"{text[:head_chars]}\n...\n{text[-tail_chars:]}"


def _is_priority_hub(url: str, priority_keywords: Iterable[str]) -> bool:
    path = urlparse(url).path.lower()
    segments = [s for s in path.split("/") if s]
    if len(segments) > _PRIORITY_MAX_SEGMENTS:
        return False
    return _matches_keyword(path, priority_keywords)


def find_internal_links(
    html: str,
    base_url: str,
    keywords: Iterable[str],
    limit: int,
    priority_keywords: Iterable[str] = (),
    exclude_keywords: Iterable[str] = (),
) -> List[str]:
    if limit <= 0 or not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    base_domain = _domain(base_url)
    candidates = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if _domain(href) != base_domain:
            continue
        path = urlparse(href).path.lower()
        if exclude_keywords and any(k in path for k in exclude_keywords):
            continue
        if _matches_keyword(path, keywords):
            candidates.append(href.split("#")[0])
    seen, out = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    if priority_keywords:
        priority = [u for u in out if _is_priority_hub(u, priority_keywords)]
        rest = [u for u in out if u not in set(priority)]
        out = priority + rest
    return out[:limit]


_ASSET_SUFFIXES = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".pdf",
    ".zip",
    ".mp4",
    ".mp3",
    ".css",
    ".js",
    ".xml",
    ".json",
)
_MIN_SLUG_LEN = 12
_MAX_POST_DEPTH = 4


def _looks_like_post(path: str) -> bool:
    segments = [s for s in path.split("/") if s]
    if not segments or len(segments) > _MAX_POST_DEPTH:
        return False
    if any(seg in _TAXONOMY_SEGMENTS for seg in segments):
        return False
    last = segments[-1].lower()
    if last.endswith(_ASSET_SUFFIXES):
        return False
    return "-" in last or len(last) >= _MIN_SLUG_LEN


def _find_post_links(
    index_html: str,
    index_url: str,
    limit: int,
    *,
    allow_outside_index_path: bool = False,
) -> List[str]:
    if limit <= 0 or not index_html:
        return []
    soup = BeautifulSoup(index_html, "html.parser")
    index_domain = _domain(index_url)
    index_host = (urlparse(index_url).netloc or "").lower()
    index_path = urlparse(index_url).path.rstrip("/")
    host_locked = not index_path

    seen, under_index, slug_shaped = set(), [], []
    for a in soup.find_all("a", href=True):
        href = urljoin(index_url, a["href"])
        if _domain(href) != index_domain:
            continue
        if host_locked and (urlparse(href).netloc or "").lower() != index_host:
            continue
        path = urlparse(href).path.rstrip("/")
        if path.startswith(index_path + "/"):
            segments = [s for s in path[len(index_path) + 1 :].split("/") if s]
            if not segments or any(seg in _TAXONOMY_SEGMENTS for seg in segments):
                continue
            bucket = under_index
        elif allow_outside_index_path and _looks_like_post(path):
            bucket = slug_shaped
        else:
            continue
        clean = href.split("#")[0].split("?")[0]
        if clean not in seen:
            seen.add(clean)
            bucket.append(clean)
        if len(under_index) >= limit:
            break
    return (under_index + slug_shaped)[:limit]


def _persona_signal_score(url: str) -> int:
    path = urlparse(url).path.lower()
    if any(kw in path for kw in _EXTERNAL_PERSON_KEYWORDS):
        return -1
    return sum(1 for kw in _PERSONA_SIGNAL_KEYWORDS if kw in path)


async def _fetch_xml(client: httpx.AsyncClient, url: str, sem: asyncio.Semaphore) -> str:
    try:
        async with sem:
            resp = await client.get(url, timeout=SITEMAP_TIMEOUT)
            content_type = resp.headers.get("content-type", "")
            if resp.status_code == 200 and ("xml" in content_type or content_type == ""):
                return resp.text
    except Exception:
        pass
    return ""


def _parse_locs(xml: str) -> List[str]:
    out = []
    for raw in re.findall(r"<loc>\s*(.*?)\s*</loc>", xml, re.DOTALL):
        loc = raw.strip()
        if loc.startswith("<![CDATA[") and loc.endswith("]]>"):
            loc = loc[len("<![CDATA[") : -len("]]>")].strip()
        if loc:
            out.append(loc)
    return out


async def discover_blog_hosts(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    base_url: str,
) -> List[str]:
    registered = _domain(base_url)
    scheme = urlparse(base_url).scheme or "https"
    hosts: Dict[str, None] = {}

    def _consider(candidate: str) -> None:
        host = (urlparse(candidate).netloc or "").lower()
        if not host or _domain(candidate) != registered:
            return
        label = host.split(".")[0]
        if label in ("blog", "news", "insights", "stories", "press", "resources"):
            hosts.setdefault(f"{scheme}://{host}/", None)

    try:
        async with sem:
            resp = await client.get(urljoin(base_url, "/robots.txt"), timeout=SITEMAP_TIMEOUT)
        if resp.status_code == 200:
            for line in resp.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    _consider(line.split(":", 1)[1].strip())
    except Exception:
        pass

    try:
        xml = await _discover_sitemap_xml(client, sem, base_url)
        for loc in _parse_locs(xml)[:400]:
            _consider(loc)
    except Exception:
        pass

    for prefix in ("blog", "news"):
        hosts.setdefault(f"{scheme}://{prefix}.{registered}/", None)
    return list(hosts)


def blog_hosts_from_jsonld(html: str, base_url: str) -> List[str]:
    registered = _domain(base_url)
    scheme = urlparse(base_url).scheme or "https"
    found: Dict[str, None] = {}
    soup = BeautifulSoup(html or "", "html.parser")
    for node in soup.find_all("script", type="application/ld+json"):
        raw = node.string or node.get_text() or ""
        for candidate in re.findall(r'https?://[^"\s\\]+', raw)[:200]:
            host = (urlparse(candidate).netloc or "").lower()
            if not host or _domain(candidate) != registered:
                continue
            if host.split(".")[0] in ("blog", "news", "insights", "press"):
                found.setdefault(f"{scheme}://{host}/", None)
    return list(found)


async def _discover_sitemap_xml(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    base_url: str,
) -> str:
    for candidate in ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml"):
        xml = await _fetch_xml(client, urljoin(base_url, candidate), sem)
        if xml:
            return xml
    try:
        async with sem:
            resp = await client.get(urljoin(base_url, "/robots.txt"), timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            for line in resp.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    xml = await _fetch_xml(client, line.split(":", 1)[1].strip(), sem)
                    if xml:
                        return xml
    except Exception:
        pass
    return ""


async def _fetch_sitemap_post_urls(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    base_url: str,
    index_url: str,
) -> List[str]:
    try:
        index_origin = ""
        parsed_index = urlparse(index_url)
        if parsed_index.netloc and parsed_index.netloc != urlparse(base_url).netloc:
            index_origin = f"{parsed_index.scheme}://{parsed_index.netloc}/"
        xml = ""
        if index_origin:
            xml = await _discover_sitemap_xml(client, sem, index_origin)
        if not xml:
            xml = await _discover_sitemap_xml(client, sem, base_url)
        if not xml:
            return []
        locs = _parse_locs(xml)
        xml_locs = [ln for ln in locs if ln.lower().split("?")[0].endswith(".xml")]
        if xml_locs and len(xml_locs) >= len(locs) / 2:
            ranked = sorted(xml_locs, key=lambda ln: 0 if "post" in ln.lower() else 1)
            sub_xmls = await asyncio.gather(
                *[_fetch_xml(client, ln, sem) for ln in ranked[:_MAX_SUB_SITEMAPS]],
                return_exceptions=True,
            )
            locs = [ln for x in sub_xmls if isinstance(x, str) and x for ln in _parse_locs(x)]

        domain = _domain(base_url)
        index_path = urlparse(index_url).path.rstrip("/")
        index_host = parsed_index.netloc.lower()
        host_locked = not index_path
        under_index, slug_shaped, seen = [], [], set()
        for loc in locs:
            if _domain(loc) != domain:
                continue
            if host_locked and (urlparse(loc).netloc or "").lower() != index_host:
                continue
            path = urlparse(loc).path.rstrip("/")
            clean = loc.split("#")[0].split("?")[0]
            if clean in seen:
                continue
            if path.startswith(index_path + "/"):
                segments = [s for s in path[len(index_path) + 1 :].split("/") if s]
                if not segments or any(seg in _TAXONOMY_SEGMENTS for seg in segments):
                    continue
                seen.add(clean)
                under_index.append(clean)
            elif _looks_like_post(path):
                seen.add(clean)
                slug_shaped.append(clean)
        return under_index or slug_shaped
    except Exception:
        return []


_SOCIAL_HOSTS = {
    "linkedin": ("linkedin.com",),
    "twitter": ("twitter.com", "x.com"),
    "github": ("github.com",),
    "instagram": ("instagram.com",),
    "facebook": ("facebook.com",),
    "youtube": ("youtube.com",),
}
_NON_PERSONAL_PATH_PARTS = {
    "company",
    "companies",
    "school",
    "showcase",
    "groups",
    "jobs",
    "pub/dir",
    "share",
    "intent",
    "sharer",
    "home",
    "login",
    "signup",
    "help",
    "about",
    "privacy",
    "terms",
    "hashtag",
    "explore",
    "search",
    "sponsors",
}
_SOCIAL_MAX_LEVELS = 6
_SOCIAL_MAX_CONTAINER_CHARS = 2_500


def _social_network(url: str) -> Optional[str]:
    host = (urlparse(url).netloc or "").lower().lstrip("www.")
    for network, hosts in _SOCIAL_HOSTS.items():
        if any(host == h or host.endswith("." + h) for h in hosts):
            return network
    return None


def _is_personal_profile(url: str, network: str) -> bool:
    segments = [seg for seg in urlparse(url).path.split("/") if seg]
    if not segments:
        return False
    if any(seg.lower() in _NON_PERSONAL_PATH_PARTS for seg in segments):
        return False
    if network == "linkedin":
        return segments[0].lower() == "in" and len(segments) >= 2
    if network == "github":
        return len(segments) == 1
    if network == "youtube":
        return segments[0].lower() in {"c", "@", "user"} or segments[0].startswith("@")
    return len(segments) == 1


def _normalise_name(value: str) -> str:
    return re.sub(r"[^a-z ]+", " ", (value or "").lower())


def _handle_matches_name(url: str, name: str) -> bool:
    segments = [seg for seg in urlparse(url).path.split("/") if seg]
    if not segments:
        return False
    handle = re.sub(r"[^a-z0-9]", "", segments[-1].lower().lstrip("@"))
    if not handle:
        return False
    tokens = [re.sub(r"[^a-z]", "", t) for t in _normalise_name(name).split()]
    tokens = [t for t in tokens if len(t) >= 3]
    if not tokens:
        return False
    if any(t in handle for t in tokens):
        return True
    collapsed = "".join(tokens)
    return handle in collapsed or collapsed.startswith(handle)


def _is_brand_account(url: str, base_url: str) -> bool:
    brand = re.sub(r"[^a-z0-9]", "", tldextract.extract(base_url).domain.lower())
    if not brand:
        return False
    segments = [seg for seg in urlparse(url).path.split("/") if seg]
    if not segments:
        return True
    handle = re.sub(r"[^a-z0-9]", "", segments[-1].lower().lstrip("@"))
    if not handle:
        return False
    return handle.startswith(brand) or brand.startswith(handle)


def extract_person_socials(
    html: str,
    names: Iterable[str],
    base_url: str = "",
) -> Dict[str, Dict[str, str]]:
    wanted = {n: _normalise_name(n) for n in names if n and n.strip()}
    if not wanted or not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "header", "nav", "footer"]):
        tag.decompose()

    found: Dict[str, Dict[str, str]] = {}
    for name, needle in wanted.items():
        others = [v for k, v in wanted.items() if k != name]
        anchors = soup.find_all(string=re.compile(re.escape(name), re.I))
        for anchor in anchors:
            node = anchor.parent
            for _ in range(_SOCIAL_MAX_LEVELS):
                if node is None or node.name in ("body", "html", "[document]"):
                    break
                text = node.get_text(" ", strip=True)
                if len(text) > _SOCIAL_MAX_CONTAINER_CHARS:
                    break
                normalised = _normalise_name(text)
                if any(other and other in normalised for other in others):
                    break
                links: Dict[str, str] = {}
                for a in node.find_all("a", href=True):
                    href = urljoin(base_url, a["href"]).split("#")[0]
                    network = _social_network(href)
                    if (
                        network
                        and network not in links
                        and _is_personal_profile(href, network)
                        and not _is_brand_account(href, base_url or href)
                        and _handle_matches_name(href, name)
                    ):
                        links[network] = href
                if links:
                    found.setdefault(name, {}).update(links)
                    break
                node = node.parent
            if name in found:
                break
    return found


_BYLINE_SELECTORS = (
    ".wp-block-post-author__byline",
    ".wp-block-post-author__name",
    "[rel=author]",
    ".author-name",
    ".post-author__name",
    ".post-author-name",
    ".entry-author-name",
    ".entry-author__name",
    ".byline__author",
    ".author-bio__name",
    "[itemprop=author]",
    ".p-author",
    ".byline",
    ".post-author",
    ".entry-author",
)
_COMMENT_MARKERS = re.compile(
    r"(?i)(^|[^a-z])(comment|respond(?!ive)|reply|discussion|disqus|livefyre)"
)
_GENERIC_BYLINES = {
    "editorial staff",
    "editorial team",
    "editor staff",
    "staff writer",
    "staff writers",
    "guest author",
    "guest writer",
    "guest contributor",
    "guest post",
    "content team",
    "marketing team",
    "the team",
    "our team",
    "admin user",
    "site admin",
    "web team",
    "press office",
    "news desk",
}
_BYLINE_NOISE = re.compile(r"(?i)^(post\s+author|author|by|written\s+by|posted\s+by)\s*[:\-]?\s*")
_LANG_PREFIX = re.compile(r"^/[a-z]{2}(-[a-z]{2})?/")
_ROLE_WORD_RE = re.compile(
    r"(?i)\b(?:founder|co-?founder|chair(?:man|woman)?|ceo|cto|coo|cfo|cmo|cio|cso|"
    r"president|vice\s+president|vp|svp|evp|avp|director|head\s+of|chief|partner|manager|"
    r"lead|engineer|developer|editor|writer|specialist|architect|consultant|"
    r"analyst|designer|executive|officer|principal|advisor|strategist)\b"
)
_AUTHOR_PAGE_HINTS = (
    "/author/",
    "/authors/",
    "/team/",
    "/profile/",
    "/people/",
    "/contributor/",
    "/writer/",
    "/staff/",
    "/about/",
)
_MAX_AUTHOR_PAGES = 20
_AUTHOR_PATH_RE = re.compile(r"/(author|authors|contributor|contributors)/", re.I)

_FOUNDER_CREDIT_RE = re.compile(
    r"\b(?:[Ff]ounded|[Cc]reated|[Ss]tarted|[Bb]uilt|[Ee]stablished|[Ll]aunched"
    r"|[Rr]un|[Oo]wned)\s+(?:and\s+\w+\s+)?by\s+"
    r"([A-Z][a-z.'-]+(?:\s+[A-Z][a-z.'-]+){1,3})"
)


def extract_founder_credits(html: str) -> Dict[str, str]:
    if not html:
        return {}
    text = re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    found: Dict[str, str] = {}
    for match in _FOUNDER_CREDIT_RE.finditer(text):
        name = match.group(1).strip()
        if _is_person_name(name) and not _is_collective_name(name):
            start = max(0, match.start() - 60)
            found.setdefault(name, text[start : match.end() + 60].strip())
    return found


def _archive_heading(html: str) -> str:
    heading = _soup(html).find("h1")
    if not heading:
        return ""
    text = re.sub(r"\s+", " ", heading.get_text(" ", strip=True)).strip()
    text = re.sub(r"(?i)^(author|articles|posts?)\s+by:?\s*", "", text)
    text = re.sub(r"(?i)^(author|archives?\s+for)\s*[:\-]?\s*", "", text).strip()
    return text if _is_person_name(text) else ""


def extract_archive_latest_year(html: str) -> Optional[int]:
    soup = _soup(html)
    main = soup.find("main") or soup.find(attrs={"id": re.compile("content|main", re.I)}) or soup
    entries = main.find_all("article")
    scope = entries if entries else [main]
    years: List[int] = []
    for entry in scope:
        for tag in entry.find_all("time"):
            stamp = tag.get("datetime") or tag.get_text(" ", strip=True)
            years += [int(y) for y in re.findall(r"\b(20[0-3]\d)\b", stamp or "")]
        if not entry.find_all("time"):
            years += [
                int(y) for y in re.findall(r"\b(20[0-3]\d)\b", entry.get_text(" ", strip=True))
            ]
    plausible = [y for y in years if 2000 <= y <= datetime.now().year]
    return max(plausible) if plausible else None


_YEARS_RE = re.compile(
    r"(?:over|more\s+than|nearly|almost|about|around)?\s*(\d{1,2})\+?\s*years?\s+(?:of\s+)?(?:hands[\s-]?on\s+)?(?:experience|expertise)",
    re.I,
)
_SINCE_RE = re.compile(
    r"\b(?:since|start(?:ed|ing)(?:\s+\w+){0,2}\s+in|beg[ai]n(?:\s+\w+){0,2}\s+in)\s+((?:19|20)\d{2})\b",
    re.I,
)
_JOINED_RE = re.compile(
    r"\bjoined\s+(?:the\s+)?[\w\s.&'-]{0,40}?\b(?:team\s+)?in\s+((?:19|20)\d{2})\b", re.I
)


def extract_author_facts(html: str) -> Dict[str, object]:
    if not html:
        return {}
    main = BeautifulSoup(visible_html(html, strip_testimonials=True), "html.parser")
    text = re.sub(r"\s+", " ", main.get_text(" ", strip=True))[:4000]
    facts: Dict[str, object] = {}

    years = [int(m.group(1)) for m in _YEARS_RE.finditer(text)]
    plausible = [y for y in years if 1 <= y <= 60]
    if plausible:
        facts["years_experience"] = max(plausible)

    joined = _JOINED_RE.search(text)
    if joined:
        facts["joined_year"] = int(joined.group(1))

    since = [int(m.group(1)) for m in _SINCE_RE.finditer(text)]
    valid = [y for y in since if 1950 <= y <= datetime.now().year]
    if valid:
        facts["active_since"] = min(valid)
        facts.setdefault("years_experience", datetime.now().year - min(valid))
    return facts


def extract_author_activity(html: str, url: str) -> Optional[int]:
    if not html:
        return None
    soup = _soup(html)
    main = soup.find("main") or soup.find(attrs={"id": re.compile("content|main", re.I)}) or soup
    entries = main.find_all("article")
    if not entries:
        entries = [h for h in main.find_all(["h2", "h3"]) if h.find("a", href=True)]
    per_page = len(entries)
    if not per_page:
        return None

    path = urlparse(url).path.rstrip("/")
    pages = {int(n) for n in re.findall(re.escape(path) + r"/page/(\d{1,3})", html)}
    last = max(pages) if pages else 1
    return per_page * (last - 1) + 1 if last > 1 else per_page


def extract_author_links(html: str, base_url: str) -> Dict[str, str]:
    if not html:
        return {}
    found: Dict[str, str] = {}
    base_domain = _domain(base_url)
    for anchor in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        href = urljoin(base_url, anchor["href"]).split("#")[0].split("?")[0]
        if _domain(href) != base_domain:
            continue
        segments = [seg for seg in urlparse(href).path.split("/") if seg]
        lower = [seg.lower() for seg in segments]
        if ("author" in lower[:-1] or "authors" in lower[:-1]) and len(segments) <= 3:
            label = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True)).strip()
            if href.rstrip("/") not in found or _is_person_name(label):
                found[href.rstrip("/")] = label
    return found


async def discover_author_pages(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    base_url: str,
    index_url: str,
) -> List[str]:
    try:
        parsed_index = urlparse(index_url)
        origin = (
            f"{parsed_index.scheme}://{parsed_index.netloc}/" if parsed_index.netloc else base_url
        )
        xml = await _discover_sitemap_xml(client, sem, origin) or await _discover_sitemap_xml(
            client, sem, base_url
        )
        if not xml:
            return []
        locs = _parse_locs(xml)
        xml_locs = [ln for ln in locs if ln.lower().split("?")[0].endswith(".xml")]
        if xml_locs and len(xml_locs) >= len(locs) / 2:
            ranked = sorted(xml_locs, key=lambda ln: 0 if "author" in ln.lower() else 1)
            subs = await asyncio.gather(
                *[_fetch_xml(client, ln, sem) for ln in ranked[:2]], return_exceptions=True
            )
            locs = [ln for x in subs if isinstance(x, str) and x for ln in _parse_locs(x)]

        domain = _domain(base_url)
        found: Dict[str, None] = {}
        for loc in locs:
            if _domain(loc) != domain:
                continue
            segments = [s for s in urlparse(loc).path.split("/") if s]
            if len(segments) == 2 and segments[0].lower() in ("author", "authors"):
                found.setdefault(loc.split("#")[0].split("?")[0], None)
        return list(found)
    except Exception:
        return []


def extract_author_link(html: str, name: str, base_url: str = "") -> Optional[str]:
    if not html or not name:
        return None
    soup = BeautifulSoup(html, "html.parser")
    target = _normalise_name(name).strip()
    fallback = None
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, anchor["href"]).split("#")[0]
        if _domain(href) != _domain(base_url or href):
            continue
        if not any(hint in urlparse(href).path.lower() for hint in _AUTHOR_PAGE_HINTS):
            continue
        if _normalise_name(anchor.get_text(" ", strip=True)).strip() == target:
            return href
        if fallback is None and _handle_matches_name(href, name):
            fallback = href
    return fallback


_NON_AVATAR_HINTS = (
    "logo",
    "icon",
    "sprite",
    "banner",
    "placeholder",
    "default-avatar",
    "avatar-default",
    "blank",
    "spacer",
    "pixel",
    "gravatar.com/avatar/00000",
    "favicon",
    "badge",
    "arrow",
    "chevron",
    "flag",
    "cookie",
    "article",
    "hero",
    "featured",
    "cover",
    "thumbnail",
    "screenshot",
    "diagram",
    "chart",
    "infographic",
    "og-image",
    "social-share",
)
_WIDE_IMAGE_RE = re.compile(r"(\d{3,4})[x_-](\d{2,4})")
_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")


def _is_person_image(url: str) -> bool:
    if not url or url.startswith("data:"):
        return False
    lowered = url.lower()
    if any(hint in lowered for hint in _NON_AVATAR_HINTS):
        return False
    path = urlparse(lowered).path
    if "." in path.rsplit("/", 1)[-1] and not path.endswith(_IMAGE_SUFFIXES):
        return False
    match = _WIDE_IMAGE_RE.search(lowered)
    if match:
        width, height = int(match.group(1)), int(match.group(2))
        if height and width / height > 1.6:
            return False
    return True


def _img_src(tag) -> str:
    for attr in ("src", "data-src", "data-lazy-src", "data-original"):
        value = tag.get(attr)
        if value and not value.startswith("data:"):
            return value
    srcset = tag.get("srcset") or tag.get("data-srcset")
    if srcset:
        parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return ""


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_INITIAL_COLOURS = (
    "#4F6BED",
    "#2E7D6B",
    "#B4531F",
    "#7A3E9D",
    "#0F6C9E",
    "#8C2F4A",
    "#3F6212",
    "#5B4636",
)


def gravatar_url(email: str, size: int = 200) -> str:
    address = (email or "").strip().lower()
    if not _EMAIL_RE.fullmatch(address):
        return ""
    digest = hashlib.md5(address.encode("utf-8")).hexdigest()
    return f"https://www.gravatar.com/avatar/{digest}?s={size}&d=404"


def extract_person_email(html: str, name: str) -> str:
    if not html or not name or "@" not in html:
        return ""
    if "mailto:" in html.lower():
        soup = BeautifulSoup(visible_html(html, strip_testimonials=True), "html.parser")
        for anchor in soup.find_all(string=re.compile(re.escape(name), re.I)):
            node = anchor.parent
            for _ in range(_SOCIAL_MAX_LEVELS):
                if node is None or node.name in ("body", "html", "[document]"):
                    break
                if len(node.get_text(" ", strip=True)) > _SOCIAL_MAX_CONTAINER_CHARS:
                    break
                for link in node.find_all("a", href=True):
                    if link["href"].lower().startswith("mailto:"):
                        found = _EMAIL_RE.search(link["href"])
                        if found:
                            return found.group(0)
                node = node.parent

    for candidate in dict.fromkeys(_EMAIL_RE.findall(html)):
        local = candidate.split("@")[0]
        if _handle_matches_name("/" + local, name):
            return candidate
    return ""


def initials_avatar(name: str, size: int = 200) -> str:
    parts = [p for p in re.split(r"[^\w]+", (name or "").strip()) if p]
    if not parts:
        return ""
    letters = (parts[0][:1] + (parts[-1][:1] if len(parts) > 1 else "")).upper()
    colour = _INITIAL_COLOURS[
        int(hashlib.md5(name.lower().encode("utf-8")).hexdigest(), 16) % len(_INITIAL_COLOURS)
    ]
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}"><rect width="{size}" height="{size}" '
        f'rx="{size // 2}" fill="{colour}"/><text x="50%" y="50%" dy="0.35em" '
        f'text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" '
        f'font-size="{int(size * 0.4)}" fill="#ffffff">{letters}</text></svg>'
    )
    return "data:image/svg+xml;utf8," + quote(svg)


_IMG_SRC_RE = re.compile(
    r'<img[^>]+?(?:data-lazy-src|data-src|src)\s*=\s*["\']([^"\']+)["\']', re.I
)


def extract_named_images(
    html: str,
    names: Iterable[str],
    base_url: str = "",
) -> Dict[str, str]:
    if not html:
        return {}
    found: Dict[str, str] = {}
    images = [(urljoin(base_url, m.group(1)).split("#")[0], "") for m in _IMG_SRC_RE.finditer(html)]
    for name in names:
        if not name or not name.strip():
            continue
        tokens = [t for t in re.sub(r"[^a-z ]", " ", name.lower()).split() if len(t) >= 4]
        if len(tokens) < 2:
            continue
        for src, alt in images:
            if not src or not _is_person_image(src):
                continue
            haystack = f"{src.lower()} {alt}"
            if all(t in haystack for t in tokens):
                found[name] = src
                break
    return found


def extract_person_avatars(
    html: str,
    names: Iterable[str],
    base_url: str = "",
) -> Dict[str, str]:
    wanted = {n: _normalise_name(n) for n in names if n and n.strip()}
    if not wanted or not html:
        return {}
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "nav", "footer"]):
        tag.decompose()

    found: Dict[str, str] = {}
    for name, needle in wanted.items():
        others = [v for k, v in wanted.items() if k != name and v]
        for anchor in soup.find_all(string=re.compile(re.escape(name), re.I)):
            node = anchor.parent
            for _ in range(_SOCIAL_MAX_LEVELS):
                if node is None or node.name in ("body", "html", "[document]"):
                    break
                text = node.get_text(" ", strip=True)
                if len(text) > _SOCIAL_MAX_CONTAINER_CHARS:
                    break
                if any(other and other in _normalise_name(text) for other in others):
                    break
                for img in node.find_all("img"):
                    alt = _normalise_name(img.get("alt") or "")
                    if any(other and other in alt for other in others):
                        continue
                    src = urljoin(base_url, _img_src(img)).split("#")[0]
                    if _is_person_image(src):
                        found[name] = src
                        break
                if name in found:
                    break
                node = node.parent
            if name in found:
                break

        if name not in found:
            tokens = [t for t in re.sub(r"[^a-z ]", " ", name.lower()).split() if len(t) >= 4]
            for match in _IMG_SRC_RE.finditer(html):
                src = urljoin(base_url, match.group(1)).split("#")[0]
                if not src or not _is_person_image(src):
                    continue
                if any(t in src.lower() for t in tokens):
                    found[name] = src
                    break
    return found


_CARD_NAME_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6", "strong", "b", "p", "span", "div")
_CARD_MAX_GAP = 3


def extract_team_names(html: str, base_url: str = "") -> Dict[str, str]:
    if not html:
        return {}
    soup = BeautifulSoup(visible_html(html, strip_testimonials=True), "html.parser")
    found: Dict[str, str] = {}
    for node in soup.find_all(_CARD_NAME_TAGS):
        text = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if not _is_person_name(text):
            continue
        siblings = []
        nxt = node
        for _ in range(_CARD_MAX_GAP):
            nxt = nxt.find_next_sibling()
            if nxt is None:
                break
            siblings.append(nxt)
        prev = node.find_previous_sibling()
        if prev is not None:
            siblings.append(prev)
        for sib in siblings:
            role = re.sub(r"\s+", " ", sib.get_text(" ", strip=True)).strip()
            if not role or len(role) > 90 or _is_person_name(role):
                continue
            if _ROLE_WORD_RE.search(role):
                found.setdefault(text, role)
                break
    return found


def extract_page_title(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return re.sub(r"\s+", " ", og["content"]).strip()[:200]
    h1 = soup.find("h1")
    if h1:
        text = re.sub(r"\s+", " ", h1.get_text(" ", strip=True)).strip()
        if text:
            return text[:200]
    if soup.title and soup.title.string:
        return re.sub(
            r"\s*[|\-–—]\s*[^|\-–—]{1,40}$", "", re.sub(r"\s+", " ", soup.title.string).strip()
        )[:200]
    return ""


def extract_jsonld_authors(html: str, base_url: str = "") -> List[str]:
    if not html:
        return []
    brand = re.sub(r"[^a-z0-9]", "", tldextract.extract(base_url).domain.lower())
    soup = BeautifulSoup(html, "html.parser")
    names: Dict[str, None] = {}
    for node in soup.find_all("script", type="application/ld+json"):
        raw = node.string or node.get_text() or ""
        candidates = re.findall(r'"author"\s*:\s*\{[^{}]*?"name"\s*:\s*"([^"]+)"', raw)
        candidates += re.findall(r'"author"\s*:\s*"([^"]+)"', raw)
        candidates += re.findall(
            r'\{[^{}]*"@type"\s*:\s*"Person"[^{}]*?"name"\s*:\s*"([^"]+)"', raw
        )
        for raw_name in candidates:
            name = re.sub(r"\s+", " ", raw_name).strip()
            if not _is_person_name(name):
                for part in re.split(r"\s+[-\u2013\u2014|,]\s+", name):
                    if _is_person_name(part.strip()):
                        name = part.strip()
                        break
            if len(name.split()) < 2 or len(name) > 60:
                continue
            collapsed = name.lower()
            if collapsed in _GENERIC_BYLINES or collapsed.endswith(
                (" team", " staff", " desk", " editors")
            ):
                continue
            if brand and re.sub(r"[^a-z0-9]", "", collapsed).startswith(brand):
                continue
            names.setdefault(name, None)
    return list(names)


_EMAIL_NAME_PARTS = (
    "gmail",
    "com",
    "net",
    "org",
    "co",
    "io",
    "outlook",
    "hotmail",
    "yahoo",
    "mail",
    "email",
    "admin",
    "info",
    "noreply",
    "no reply",
    "support",
    "dev",
    "test",
)
_UI_LABEL_WORDS = {
    "read",
    "more",
    "view",
    "profile",
    "learn",
    "continue",
    "reading",
    "click",
    "here",
    "see",
    "all",
    "show",
    "load",
    "next",
    "previous",
    "back",
    "home",
    "share",
    "follow",
    "subscribe",
    "comments",
    "reply",
    "posts",
    "articles",
    "details",
    "info",
    "link",
    "page",
    "menu",
    "search",
}
_COLLECTIVE_SUFFIXES = (
    " team",
    " staff",
    " desk",
    " editors",
    " editorial",
    " group",
    " crew",
    " contributors",
    " newsroom",
)


def _is_collective_name(value: str) -> bool:
    text = re.sub(r"\s+", " ", (value or "")).strip().lower()
    return text.startswith("editorial") or text.endswith(_COLLECTIVE_SUFFIXES)


# Topic and taxonomy words. A string containing one is a category or tag label
# ("WordPress Performance", "Filed Under News"), not a person.
_NOT_NAME_WORDS = {
    "categories",
    "category",
    "tags",
    "tag",
    "filed",
    "uncategorized",
    "topics",
    "topic",
    "archive",
    "archives",
    "posted",
    "wordpress",
    "woocommerce",
    "performance",
    "security",
    "hosting",
    "seo",
    "marketing",
    "tutorial",
    "tutorials",
    "guide",
    "guides",
    "tips",
    "news",
    "updates",
    "plugins",
    "plugin",
    "themes",
    "theme",
    "ecommerce",
    "optimization",
    "maintenance",
    "development",
    "technology",
    "business",
    "website",
    "websites",
    "software",
    "services",
    "solutions",
    "agency",
    "strategy",
    "insights",
    "resources",
}


def _is_person_name(value: str) -> bool:
    text = re.sub(r"\s+", " ", (value or "")).strip()
    if not text or len(text) > 60 or "@" in text:
        return False
    # "Categories: wordpress" and "news/updates" are labels, not names.
    if ":" in text or "/" in text:
        return False
    tokens = text.split(" ")
    # A published name has at least two space-separated parts. A single token
    # such as "mobeen-abdullahs" or "jane_doe" is a login slug.
    if len(tokens) < 2 or "_" in text:
        return False
    # First and last parts start with a capital ("Ludwig van Beethoven" still
    # passes); lowercase strings are slugs or labels.
    if not (tokens[0][:1].isupper() and tokens[-1][:1].isupper()):
        return False
    letters = [c for c in text if c.isalpha()]
    if letters and not any(c.islower() for c in letters):
        return False
    words = [w for w in re.sub(r"[^\w\s.]", " ", text.lower()).split() if w]
    if not 2 <= len(words) <= 5:
        return False
    if _ROLE_WORD_RE.search(text):
        return False
    if any(w in _EMAIL_NAME_PARTS for w in words):
        return False
    if all(w in _UI_LABEL_WORDS for w in words):
        return False
    if any(w in _NOT_NAME_WORDS for w in words):
        return False
    # Letters (accented ones included), dots, apostrophes and hyphens only.
    return all(re.match(r"^[^\W\d_](?:[^\W\d_]|[.'\-])*$", w) for w in words)


_DATE_META = (
    "article:published_time",
    "datePublished",
    "publish_date",
    "date",
    "DC.date.issued",
    "article:modified_time",
)
_ISO_DATE = re.compile(r"(19|20)\d{2}-\d{2}-\d{2}")
_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
_PROSE_DATE = re.compile(
    r"(?i)(?:\d{1,2}\s+(?:" + _MONTHS + r")[a-z]*,?\s+(?:19|20)\d{2}"
    r"|(?:" + _MONTHS + r")[a-z]*\s+\d{1,2},?\s+(?:19|20)\d{2})"
)
_DATE_PROSE_WINDOW = 900
_YEAR_ONLY = re.compile(r"\b(19|20)\d{2}\b")
ACTIVE_SINCE_YEAR = 2020
RECENT_SINCE_YEAR = 2023


def extract_publish_year(html: str) -> Optional[int]:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    for node in soup.find_all("script", type="application/ld+json"):
        raw = node.string or node.get_text() or ""
        found = re.search(r'"datePublished"\s*:\s*"([^"]+)"', raw)
        if found:
            year = _ISO_DATE.search(found.group(1)) or _YEAR_ONLY.search(found.group(1))
            if year:
                return int(year.group(0)[:4])

    for key in _DATE_META:
        tag = (
            soup.find("meta", attrs={"property": key})
            or soup.find("meta", attrs={"name": key})
            or soup.find("meta", attrs={"itemprop": key})
        )
        if tag and tag.get("content"):
            year = _ISO_DATE.search(tag["content"]) or _YEAR_ONLY.search(tag["content"])
            if year:
                return int(year.group(0)[:4])

    for tag in soup.find_all("time"):
        value = tag.get("datetime") or tag.get_text(" ", strip=True)
        year = _ISO_DATE.search(value or "") or _YEAR_ONLY.search(value or "")
        if year:
            return int(year.group(0)[:4])

    for node in soup.find_all(attrs={"class": re.compile("(date|published|posted)", re.I)}):
        year = _YEAR_ONLY.search(node.get_text(" ", strip=True))
        if year:
            return int(year.group(0))

    prose = BeautifulSoup(str(soup), "html.parser")
    for tag in prose(["script", "style", "noscript", "svg", "header", "nav", "footer"]):
        tag.decompose()
    head = re.sub(r"\s+", " ", prose.get_text(" ", strip=True))[:_DATE_PROSE_WINDOW]
    written = _PROSE_DATE.search(head)
    if written:
        year = _YEAR_ONLY.search(written.group(0))
        if year:
            return int(year.group(0))
    return None


_BYLINE_NOT_A_NAME = re.compile(
    r"(?i)\b(?:19|20)\d{2}\b"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d"
    r"|[|/\u2022\u00b7]"
)


def extract_bylines(html: str, base_url: str = "") -> List[str]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")

    doomed = []
    for node in soup.find_all(True):
        marker = f"{' '.join(node.get('class') or [])} {node.get('id') or ''}".lower()
        if _COMMENT_MARKERS.search(marker) or any(m in marker for m in _TESTIMONIAL_MARKERS):
            doomed.append(node)
    for node in doomed:
        node.decompose()

    raw_candidates: List[str] = []

    for node in soup.find_all("script", type="application/ld+json"):
        raw = node.string or node.get_text() or ""
        for match in re.finditer(r'"author"\s*:\s*(\[[^\]]+\]|\{[^}]+\}|"[^"]+")', raw, re.S):
            block = match.group(1)
            for name_match in re.finditer(r'"name"\s*:\s*"([^"]+)"', block):
                raw_candidates.append(name_match.group(1))
            if block.startswith('"'):
                raw_candidates.append(block.strip('"'))
        if '"@graph"' in raw or "schema-author" in raw:
            for person in re.finditer(r'\{[^{}]*"@type"\s*:\s*"Person"[^{}]*\}', raw, re.S):
                named = re.search(r'"name"\s*:\s*"([^"]+)"', person.group(0))
                if named:
                    raw_candidates.append(named.group(1))

    for meta in soup.find_all(
        "meta", attrs={"name": re.compile(r"^(?:author|dc\.creator|byl)$", re.I)}
    ):
        if meta.get("content"):
            raw_candidates.append(meta["content"])

    for selector in _BYLINE_SELECTORS:
        for node in soup.select(selector):
            raw_candidates.append(node.get_text(" ", strip=True))

    brand = (
        re.sub(r"[^a-z0-9]", "", tldextract.extract(base_url).domain.lower()) if base_url else ""
    )
    validated_authors: List[str] = []
    seen_keys = set()

    for cand in raw_candidates:
        cand = _BYLINE_NOISE.sub("", cand or "").strip(" :-|")
        if not cand or _BYLINE_NOT_A_NAME.search(cand):
            continue

        sub_names = _CO_AUTHOR_SPLIT_RE.split(cand) if _CO_AUTHOR_SPLIT_RE.search(cand) else [cand]
        for piece in sub_names:
            clean_name = re.sub(r"\s+", " ", piece).strip(" :-|")
            for coll in _GENERIC_BYLINES:
                if clean_name.lower().endswith(f" {coll}"):
                    clean_name = clean_name[: -(len(coll) + 1)].strip(" :-|")
            if not _is_person_name(clean_name) or _is_collective_name(clean_name):
                continue
            if brand and re.sub(r"[^a-z0-9]", "", clean_name.lower()).startswith(brand):
                continue
            key = _normalise_name(clean_name)
            if key not in seen_keys:
                seen_keys.add(key)
                validated_authors.append(clean_name)

    return validated_authors


def extract_byline(html: str, base_url: str = "") -> Optional[str]:
    bylines = extract_bylines(html, base_url)
    return bylines[0] if bylines else None


def declared_authors(text: str) -> list:
    out = []
    for line in (text or "").split("\n"):
        if not line.startswith("Article author:"):
            break
        who = line.replace("Article author:", "").split("|")[0].strip()
        # Stamps also come from feeds and JSON-LD; re-check them so a login
        # slug or a category label never becomes an author.
        if who and (_is_person_name(who) or _is_collective_name(who)):
            out.append(who)
    return out


def extract_collective_byline(html: str, base_url: str = "") -> Optional[str]:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    doomed = []
    for node in soup.find_all(True):
        marker = f"{' '.join(node.get('class') or [])} {node.get('id') or ''}"
        if _COMMENT_MARKERS.search(marker) or any(
            m in marker.lower() for m in _TESTIMONIAL_MARKERS
        ):
            doomed.append(node)
    for node in doomed:
        node.decompose()

    candidates: List[str] = []
    for meta in soup.find_all("meta", attrs={"name": re.compile("^author$", re.I)}):
        if meta.get("content"):
            candidates.append(meta["content"])
    for node in soup.find_all("script", type="application/ld+json"):
        raw = node.string or node.get_text() or ""
        for match in re.finditer(r'"author"\s*:\s*(\{.*?\}|"[^"]+")', raw, re.S):
            found = re.search(r'"name"\s*:\s*"([^"]+)"', match.group(1)) or re.match(
                r'"([^"]+)"', match.group(1)
            )
            if found:
                candidates.append(found.group(1))
    for selector in _BYLINE_SELECTORS:
        for node in soup.select(selector):
            candidates.append(node.get_text(" ", strip=True))

    brand = (
        re.sub(r"[^a-z0-9]", "", tldextract.extract(base_url).domain.lower()) if base_url else ""
    )
    for candidate in candidates:
        name = _BYLINE_NOISE.sub("", (candidate or "").strip())
        name = re.sub(r"\s+", " ", name).strip(" :-|")
        if not name or len(name) > 40 or len(name.split()) > 4:
            continue
        if not _is_collective_name(name):
            continue
        if brand and re.sub(r"[^a-z0-9]", "", name.lower()).startswith(brand):
            continue
        return name
    return None


async def fetch(
    client: httpx.AsyncClient,
    url: str,
    sem: asyncio.Semaphore,
    attempts: int = MAX_FETCH_ATTEMPTS,
    deadline: Optional[float] = None,
    timeout_seconds: Optional[float] = None,
) -> str:
    last_status: Optional[int] = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            timeout = timeout_seconds or REQUEST_TIMEOUT
            if deadline is not None:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    return ""
                timeout = max(1.0, min(timeout, remaining))
            async with sem:
                resp = await client.get(url, timeout=timeout)
            last_status = resp.status_code
            if resp.status_code == 200:
                if "text/html" not in resp.headers.get("content-type", ""):
                    return ""
                if _CHALLENGE_TITLE_RE.search(resp.text[:4000]):
                    _record_refusal(url, "challenge")
                    return ""
                return resp.text
            if resp.status_code not in _RETRYABLE_STATUS:
                break
        except Exception:
            last_status = None

        if attempt >= max(1, attempts):
            break
        await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt * (1 + random.random()))
    if last_status in BLOCKED_STATUS:
        _record_refusal(url, last_status)
    return ""


_PEOPLE_PATHS = (
    "/blog/",
    "/about/",
    "/team/",
    "/authors/",
    "/contributors/",
    "/leadership/",
    "/our-team/",
    "/people/",
    "/news/",
)
_SWEEP_CONCURRENCY = 5
_SPECULATIVE_TIMEOUT = 8.0


def _author_slug_candidates(name: str) -> List[str]:
    parts = [p for p in re.split(r"[^\w]+", (name or "").lower()) if p]
    if len(parts) < 2:
        return []
    first, last = parts[0], parts[-1]
    return [
        f"{first}{last}",
        f"{first}-{last}",
        f"{first}.{last}",
        f"{first[0]}{last}",
        f"{first}{last[0]}",
        last,
        first,
    ]


async def find_author_archive(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    base_url: str,
    name: str,
    deadline: Optional[float] = None,
    limit: int = 7,
) -> Optional[tuple]:
    candidates = [
        urljoin(base_url, f"/author/{slug}/") for slug in _author_slug_candidates(name)[:limit]
    ]
    if not candidates:
        return None
    pages = await asyncio.gather(
        *[fetch(client, u, sem, attempts=1, deadline=deadline) for u in candidates],
        return_exceptions=True,
    )
    target = _normalise_name(name).strip()
    for url, html in zip(candidates, pages):
        if (
            isinstance(html, str)
            and html
            and _normalise_name(_archive_heading(html)).strip() == target
        ):
            return url, html
    return None


_PEOPLE_PATH_RE = re.compile(
    r"/(author|authors|contributor|contributors|team|our-team|people|"
    r"our-people|staff|leadership|crew|writers|editors|experts)/",
    re.I,
)


async def discover_people_from_sitemap(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    base_url: str,
) -> List[str]:
    try:
        xml = await _discover_sitemap_xml(client, sem, base_url)
        if not xml:
            return []
        locs = _parse_locs(xml)
        sub = [ln for ln in locs if ln.lower().split("?")[0].endswith(".xml")]
        if sub and len(sub) >= len(locs) / 2:
            ranked = sorted(sub, key=lambda ln: 0 if _PEOPLE_PATH_RE.search(ln) else 1)
            parts = await asyncio.gather(
                *[_fetch_xml(client, ln, sem) for ln in ranked[:2]], return_exceptions=True
            )
            locs = [ln for x in parts if isinstance(x, str) and x for ln in _parse_locs(x)]
        domain = _domain(base_url)
        found: Dict[str, None] = {}
        for loc in locs:
            if _domain(loc) != domain or not _PEOPLE_PATH_RE.search(loc):
                continue
            if _LANG_PREFIX.match(urlparse(loc).path):
                continue
            segments = [x for x in urlparse(loc).path.split("/") if x]
            if 1 <= len(segments) <= 3:
                found.setdefault(loc.split("#")[0].split("?")[0], None)
        return list(found)
    except Exception:
        return []


async def gravatar_if_exists(
    client: httpx.AsyncClient,
    email: str,
    size: int = 200,
) -> str:
    url = gravatar_url(email, size)
    if not url:
        return ""
    try:
        resp = await client.head(url, timeout=_SPECULATIVE_TIMEOUT, follow_redirects=True)
        return url if resp.status_code == 200 else ""
    except Exception:
        return ""


_FEED_PATHS = (
    "/feed",
    "/feed/",
    "/rss",
    "/rss.xml",
    "/feed.xml",
    "/atom.xml",
    "/index.xml",
    "/blog/feed",
    "/blog/rss",
)
_FEED_AUTHOR_RE = re.compile(
    r"<(?:dc:creator|author|itunes:author)[^>]*>\s*(?:<!\[CDATA\[)?\s*"
    r"(.*?)\s*(?:\]\]>)?\s*</(?:dc:creator|author|itunes:author)>",
    re.I | re.S,
)
_FEED_EMAIL_NAME = re.compile(r"^[^\s@]+@[^\s@]+\s*\((.+)\)$")
_FEED_NESTED_NAME = re.compile(r"<name[^>]*>\s*(.*?)\s*</name>", re.I | re.S)
_FEED_ITEM_RE = re.compile(r"<(?:item|entry)\b.*?</(?:item|entry)>", re.I | re.S)
_FEED_LINK_RE = re.compile(
    r"<link[^>]*?(?:href=[\"\']([^\"\']+)[\"\']|>\s*([^<]+?)\s*</link>)", re.I
)
_MAX_FEED_ITEMS = 40


def _feed_author_name(raw: str) -> str:
    text = (raw or "").strip()
    nested = _FEED_NESTED_NAME.search(text)
    if nested:
        text = nested.group(1).strip()
    addressed = _FEED_EMAIL_NAME.match(text)
    if addressed:
        text = addressed.group(1).strip()
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def parse_feed_authors(xml: str, base_url: str = "") -> Dict[str, List[str]]:
    if not xml or "<" not in xml:
        return {}
    out: Dict[str, List[str]] = {}
    for block in _FEED_ITEM_RE.findall(xml)[:_MAX_FEED_ITEMS]:
        found = _FEED_AUTHOR_RE.search(block)
        if not found:
            continue
        name = _feed_author_name(found.group(1))
        if not name or len(name) > 60:
            continue
        if not (_is_person_name(name) or _is_collective_name(name)):
            continue
        link = ""
        for match in _FEED_LINK_RE.finditer(block):
            candidate = (match.group(1) or match.group(2) or "").strip()
            if candidate.startswith("http"):
                link = candidate
                break
        out.setdefault(name, [])
        if link and link not in out[name]:
            out[name].append(link)
    return out


async def discover_feed_authors(
    client: "httpx.AsyncClient",
    base_url: str,
    home_html: str = "",
    budget_seconds: float = 4.0,
) -> Dict[str, List[str]]:
    candidates: List[str] = []
    if home_html:
        for match in re.finditer(
            r"<link[^>]+type=[\"\']application/(?:rss|atom)\+xml[\"\'][^>]*>", home_html, re.I
        ):
            href = re.search(r"href=[\"\']([^\"\']+)[\"\']", match.group(0), re.I)
            if href:
                candidates.append(urljoin(base_url, href.group(1)))
    candidates += [urljoin(base_url, path) for path in _FEED_PATHS]
    seen, ordered = set(), []
    for url in candidates:
        key = url.rstrip("/")
        if key not in seen:
            seen.add(key)
            ordered.append(url)

    async def _one(url: str) -> Dict[str, List[str]]:
        try:
            resp = await client.get(url, timeout=SITEMAP_TIMEOUT, follow_redirects=True)
            if resp.status_code != 200:
                return {}
            return parse_feed_authors(resp.text, base_url)
        except Exception:
            return {}

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*[_one(u) for u in ordered[:6]], return_exceptions=True),
            timeout=budget_seconds,
        )
    except Exception:
        return {}
    merged: Dict[str, List[str]] = {}
    for found in results:
        if not isinstance(found, dict):
            continue
        for name, links in found.items():
            merged.setdefault(name, [])
            for link in links:
                if link not in merged[name]:
                    merged[name].append(link)
    return merged


async def discover_people_pages(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    base_url: str,
    deadline: Optional[float] = None,
) -> Dict[str, str]:
    targets = [urljoin(base_url, path) for path in _PEOPLE_PATHS]
    lane = asyncio.Semaphore(_SWEEP_CONCURRENCY)
    pages = await asyncio.gather(
        *[
            fetch(
                client, u, lane, attempts=1, deadline=deadline, timeout_seconds=_SPECULATIVE_TIMEOUT
            )
            for u in targets
        ],
        return_exceptions=True,
    )
    found: Dict[str, str] = {}
    for page_url, html in zip(targets, pages):
        if not isinstance(html, str) or not html:
            continue
        for archive_url, label in extract_author_links(html, page_url).items():
            if _is_person_name(label):
                found.setdefault(archive_url, label)
    return found


async def _no_list() -> List[str]:
    return []


async def _no_pages() -> Dict[str, str]:
    return {}


async def scrape_site(*args, **kwargs) -> Dict[str, object]:
    """Run the scrape and report the URLs the site refused.

    The result gains ``refused``: every URL answered with 401/403/406/429/503
    or a bot-challenge page, mapped to that status, so the caller can render
    those pages in a real browser instead of silently losing them.
    """
    refusals: Dict[str, object] = {}
    token = _FETCH_REFUSALS.set(refusals)
    try:
        result = await _scrape_site(*args, **kwargs)
    finally:
        _FETCH_REFUSALS.reset(token)
    result = dict(result or {})
    result["refused"] = dict(refusals)
    return result


async def _scrape_site(
    url: str,
    *,
    max_about_pages: int = 1,
    about_keywords: Iterable[str] = ABOUT_KEYWORDS,
    home_max_chars: int = 3000,
    about_max_chars: int = 3000,
    team_max_chars: Optional[int] = None,
    max_blog_posts: int = 0,
    blog_index_max_chars: int = 1500,
    blog_post_max_chars: int = 1200,
    strip_footer: bool = True,
    sample_head_and_tail: bool = False,
    priority_keywords: Iterable[str] = (),
    strip_testimonials: bool = False,
    budget_seconds: Optional[float] = None,
) -> Dict[str, object]:
    validate_url_for_ssrf(url)
    started = asyncio.get_event_loop().time()
    deadline = started + budget_seconds if budget_seconds else None

    def _archive_window() -> Optional[float]:
        return asyncio.get_event_loop().time() + ARCHIVE_MIN_WINDOW_SECONDS

    def _out_of_time(stage: str, grace: float = 0.0) -> bool:
        if deadline is None or asyncio.get_event_loop().time() < deadline + grace:
            return False
        return True

    sem = asyncio.Semaphore(CONCURRENCY)
    headers = dict(REQUEST_HEADERS)
    about_html_by_url: Dict[str, str] = {}
    blog_html_by_url: Dict[str, str] = {}
    team_profile_links: Dict[str, None] = {}
    named_author_links: set = set()
    author_link_labels: Dict[str, str] = {}

    def _with_byline(page_url: str, html: str, text: str) -> str:
        bylines = extract_bylines(html, page_url)
        if not bylines:
            return text
        year = extract_publish_year(html)
        stamp = f" | {year}" if year else ""
        return "".join(f"Article author: {b}{stamp}\n" for b in bylines) + text

    def _page_text(html: str, max_chars: int) -> str:
        if sample_head_and_tail:
            return _head_tail(
                visible_text(
                    html, None, strip_footer=strip_footer, strip_testimonials=strip_testimonials
                ),
                max_chars,
            )
        return visible_text(
            html, max_chars, strip_footer=strip_footer, strip_testimonials=strip_testimonials
        )

    async def _crawl_about(client: httpx.AsyncClient, home_html: str) -> Dict[str, str]:
        links = find_internal_links(
            home_html,
            url,
            about_keywords,
            max_about_pages,
            priority_keywords=priority_keywords,
            exclude_keywords=_EXTERNAL_PERSON_KEYWORDS if priority_keywords else (),
        )
        html_list = await asyncio.gather(
            *[fetch(client, link, sem, deadline=deadline) for link in links], return_exceptions=True
        )
        clean_html = [h if isinstance(h, str) else "" for h in html_list]
        about_html_by_url.update({ln: h for ln, h in zip(links, clean_html) if h})
        team_cap = team_max_chars or about_max_chars

        for link, html in zip(links, clean_html):
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            for anchor in soup.find_all("a", href=True):
                href = urljoin(link, anchor["href"]).split("#")[0]
                if _domain(href) != _domain(url):
                    continue
                path = urlparse(href).path.lower()
                if _LANG_PREFIX.match(path):
                    continue
                if any(h in path for h in _AUTHOR_PAGE_HINTS) and path.count("/") >= 2:
                    team_profile_links.setdefault(href, None)
        return {
            link: _with_byline(
                link,
                html,
                visible_text(
                    html,
                    team_cap
                    if _matches_keyword(urlparse(link).path, TEAM_KEYWORDS)
                    else about_max_chars,
                    strip_footer=strip_footer,
                    strip_testimonials=strip_testimonials,
                ),
            )
            for link, html in zip(links, clean_html)
            if html
        }

    async def _crawl_blog(client: httpx.AsyncClient, home_html: str) -> Dict[str, str]:
        if max_blog_posts <= 0:
            return {}
        candidates = find_internal_links(home_html, url, BLOG_KEYWORDS, _BLOG_INDEX_CANDIDATES)
        candidates_from_links = list(candidates)
        soup = BeautifulSoup(home_html, "html.parser")
        base_domain = _domain(url)
        for anchor in soup.find_all("a", href=True):
            href = urljoin(url, anchor["href"]).split("#")[0]
            host = (urlparse(href).netloc or "").lower()
            if _domain(href) == base_domain and (
                host.startswith("blog.") or host.startswith("news.")
            ):
                root = f"{urlparse(href).scheme}://{host}/"
                if root not in candidates:
                    candidates.append(root)

        for host_root in blog_hosts_from_jsonld(home_html, url):
            if host_root not in candidates:
                candidates.append(host_root)
        for host_root in await discover_blog_hosts(client, sem, url):
            if host_root not in candidates:
                candidates.append(host_root)
        if not candidates:
            return {}

        def _index_rank(candidate: str) -> tuple:
            host = (urlparse(candidate).netloc or "").lower()
            path = urlparse(candidate).path
            segments = [seg for seg in path.split("/") if seg]
            return (
                0 if host.startswith("blog.") or host.startswith("news.") else 1,
                0 if len(segments) <= 1 and _matches_keyword(path, BLOG_KEYWORDS) else 1,
                len(path),
            )

        ranked = sorted(candidates, key=_index_rank)[:4]
        index_url, index_html, recent_seed = "", "", []
        for candidate in ranked:
            speculative = urlparse(candidate).netloc.lower() not in {
                urlparse(c).netloc.lower() for c in candidates_from_links
            }
            html = await fetch(
                client,
                candidate,
                sem,
                attempts=1 if speculative else MAX_FETCH_ATTEMPTS,
                timeout_seconds=(_SPECULATIVE_TIMEOUT if speculative else None),
                deadline=deadline,
            )
            if not html:
                continue
            found = _find_post_links(html, candidate, max_blog_posts) or _find_post_links(
                html, candidate, max_blog_posts, allow_outside_index_path=True
            )
            if found:
                index_url, index_html, recent_seed = candidate, html, found
                break
            if not index_html:
                index_url, index_html = candidate, html

        if not index_html:
            return {}

        index_text = visible_text(
            index_html,
            blog_index_max_chars,
            strip_footer=strip_footer,
            strip_testimonials=strip_testimonials,
        )
        listing_authors = extract_jsonld_authors(index_html, index_url)
        if listing_authors:
            index_text = "Article authors: " + ", ".join(listing_authors) + "\n" + index_text
        blog_pages = {index_url: index_text}

        recent_quota = max(3, max_blog_posts // 3)
        recent_links = recent_seed[:recent_quota] or _find_post_links(
            index_html, index_url, recent_quota
        )
        if not recent_links:
            recent_links = _find_post_links(
                index_html, index_url, recent_quota, allow_outside_index_path=True
            )
        if not recent_links:
            recent_links = _find_post_links(
                home_html, index_url, recent_quota, allow_outside_index_path=True
            )

        sitemap_urls = await _fetch_sitemap_post_urls(client, sem, url, index_url)
        signal_ranked = sorted(
            (u for u in sitemap_urls if u not in recent_links),
            key=_persona_signal_score,
            reverse=True,
        )

        budget_left = max(0, max_blog_posts - len(recent_links))
        signal_links = signal_ranked[:budget_left]
        post_links = list(dict.fromkeys(recent_links + signal_links))[:max_blog_posts]
        if not post_links:
            return blog_pages
        blog_html_by_url[index_url] = index_html

        linked_authors: Dict[str, str] = dict(extract_author_links(index_html, index_url))
        author_pages: Dict[str, str] = {}
        authors_seen: set = set()

        # Synchronously await waves while client is reliably open
        for start in range(0, len(post_links), _POST_WAVE_SIZE):
            if _out_of_time("blog posts"):
                break
            wave = post_links[start : start + _POST_WAVE_SIZE]
            wave_html = await asyncio.gather(
                *[
                    fetch(client, link, sem, attempts=POST_FETCH_ATTEMPTS, deadline=deadline)
                    for link in wave
                ],
                return_exceptions=True,
            )
            for post_url, post_html in zip(wave, wave_html):
                if not isinstance(post_html, str) or not post_html:
                    continue
                blog_html_by_url[post_url] = post_html
                text = _page_text(post_html, blog_post_max_chars)
                bylines = extract_bylines(post_html, post_url)
                if bylines:
                    year = extract_publish_year(post_html)
                    stamp = f" | {year}" if year else ""
                    stamps = "".join(f"Article author: {b}{stamp}\n" for b in bylines)
                    text = f"{stamps}{text}"
                    for b in bylines:
                        authors_seen.add(b)
                blog_pages[post_url] = text

                found = extract_author_links(post_html, post_url)
                linked_authors.update(found)
                for who in bylines:
                    link = extract_author_link(post_html, who, post_url)
                    if link:
                        author_pages.setdefault(who, link)

            if len(authors_seen) >= ENOUGH_AUTHORS:
                break

        for profile_url, label in linked_authors.items():
            if not _is_person_name(label):
                continue
            author_pages.setdefault(label, profile_url)
            team_profile_links.setdefault(profile_url, None)
            named_author_links.add(profile_url)
            author_link_labels.setdefault(profile_url.rstrip("/"), label)
            blog_pages.setdefault(
                profile_url,
                f"Author profile: {label}\n{label} is credited as an author on {_domain(url)}.",
            )

        return blog_pages

    # SINGLE HTTP CLIENT CONTEXT: Kept strictly open for the entire multi-stage scrape
    async with httpx.AsyncClient(
        headers=headers, verify=False, follow_redirects=True, timeout=REQUEST_TIMEOUT
    ) as client:
        home_html = await fetch(client, url, sem)
        if not home_html:
            logger.warning(
                "homepage fetch failed for %s - attempting headless browser fallback", url
            )
            return {"pages": {}, "raw_home_html": "", "raw_pages": {}}

        sweep = (
            discover_people_pages(client, sem, url, deadline) if max_blog_posts > 0 else _no_pages()
        )
        sitemap_people = (
            discover_people_from_sitemap(client, sem, url) if max_blog_posts > 0 else _no_list()
        )

        about_pages, blog_pages, swept, listed = await asyncio.gather(
            _crawl_about(client, home_html),
            _crawl_blog(client, home_html),
            sweep,
            sitemap_people,
            return_exceptions=True,
        )

        about_pages = about_pages if isinstance(about_pages, dict) else {}
        blog_pages = blog_pages if isinstance(blog_pages, dict) else {}
        swept = swept if isinstance(swept, dict) else {}
        listed = listed if isinstance(listed, list) else []

        for people_url in listed:
            if people_url not in blog_pages and people_url not in about_pages:
                team_profile_links.setdefault(people_url, None)
        for archive_url, label in swept.items():
            if archive_url in blog_pages or archive_url in about_pages:
                continue
            team_profile_links.setdefault(archive_url, None)
            named_author_links.add(archive_url)
            author_link_labels.setdefault(archive_url.rstrip("/"), label)

        if team_profile_links:
            deduped: Dict[str, None] = {}
            for candidate in team_profile_links:
                deduped.setdefault(candidate.rstrip("/"), None)
            wanted = sorted(
                (u for u in deduped if u not in about_pages),
                key=lambda u: (
                    0 if u in named_author_links else 1,
                    0 if _AUTHOR_PATH_RE.search(u) else 1,
                    u,
                ),
            )[:_MAX_AUTHOR_PAGES]
            grace_deadline = _archive_window()
            profile_html = await asyncio.gather(
                *[
                    fetch(client, u, sem, attempts=POST_FETCH_ATTEMPTS, deadline=grace_deadline)
                    for u in wanted
                ],
                return_exceptions=True,
            )
            for profile_url, html in zip(wanted, profile_html):
                if not isinstance(html, str) or not html:
                    continue
                blog_html_by_url[profile_url] = html
                who = (
                    _archive_heading(html)
                    or extract_byline(html, profile_url)
                    or author_link_labels.get(profile_url.rstrip("/"), "")
                )
                counted = extract_author_activity(html, profile_url)
                about_pages[profile_url] = (
                    "Author profile:"
                    + (f" {who}" if _is_person_name(who) else "")
                    + (f" | posts={counted}" if counted else "")
                    + "\n"
                    + visible_text(
                        html,
                        about_max_chars,
                        strip_footer=strip_footer,
                        strip_testimonials=strip_testimonials,
                    )
                )

    pages: Dict[str, str] = {url: _page_text(home_html, home_max_chars)}
    pages.update(about_pages)
    for page_url, text in blog_pages.items():
        existing = pages.get(page_url, "")
        # A fetched author page carries the person's bio; the one-line placeholder
        # written before it was fetched must never replace it.
        if existing.startswith("Author profile:") and text.startswith("Author profile:"):
            continue
        pages[page_url] = text

    raw_pages: Dict[str, str] = {url: home_html}
    raw_pages.update(about_html_by_url)
    raw_pages.update(blog_html_by_url)

    return {"pages": pages, "raw_home_html": home_html, "raw_pages": raw_pages}
