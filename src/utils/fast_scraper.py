"""Fast, browser-free site scraping shared by workspace brand-voice/persona
extraction and the competitor-discovery pipeline (src/flow/engines/competitors).

Uses httpx + BeautifulSoup instead of a headless browser (crawl4ai / web_page_scraper
in src/utils/helper.py) — no JavaScript execution, but homepage + several subpages
fetch concurrently in low single-digit seconds instead of crawl4ai's 20-60+ seconds.

Tradeoff: content rendered client-side (a pure SPA with no server-side rendering)
won't be visible here. Callers that need robustness against that should fall back to
crawl4ai when this comes back too thin — see `_looks_blocked` in src/utils/helper.py.

Only the top-level, user-supplied `url` is SSRF-validated (matching the precedent set
by web_page_scraper and src/utils/multi_page_scraper.py) — discovered subpage/post
links are constrained to the same domain before being fetched.
"""
import asyncio
import logging
import random
import re
from typing import Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
import tldextract
from bs4 import BeautifulSoup

from src.utils.url_validator import validate_url_for_ssrf

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; RextBot/1.0)"
CONCURRENCY = 10
REQUEST_TIMEOUT = 10
# Transient failures are the dominant source of run-to-run variance: three
# consecutive scrapes of css-tricks.com returned 34, 24 and 0 pages from
# identical code, because fetch() swallowed every error and returned "". A
# dropped page silently removes whatever people it named, so the same site
# yields a different persona list each run - and a dropped *homepage* yields
# none at all. Retrying transient statuses removes most of that variance.
MAX_FETCH_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.75
_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}

ABOUT_KEYWORDS = ("about", "product", "service", "solution", "pricing", "platform", "feature")
# Additive to ABOUT_KEYWORDS for callers that want it (workspace brand-voice/persona
# extraction does; competitor discovery doesn't, to keep its behavior unchanged) —
# team/leadership pages are the highest-density source of *multiple* real personas
# at once (a single team page often lists every founder/leader with name + title).
TEAM_KEYWORDS = (
    "team", "leadership", "staff", "people", "founder", "meet", "our-team",
    "who-we-are", "story", "leadership-team", "company",
)
BLOG_KEYWORDS = ("blog", "news", "press", "insights", "articles", "resources")
# Max path segments a URL may have and still count as a *hub* page for priority
# ranking - see _is_priority_hub().
_PRIORITY_MAX_SEGMENTS = 2
# Containers whose *entire* contents are customer voice, not brand voice. Matched
# against a tag's class/id. Deliberately specific: a bare "review" or "quote"
# would also delete legitimate team content - wpbeginner.com's real staff page is
# literally /meet-our-wpbeginner-review-board/ - so every entry here names a
# testimonial widget, never a generic word.
_TESTIMONIAL_MARKERS = (
    "testimonial", "wall-of-love", "walloflove", "customer-story",
    "customer-stories", "customer-quote", "client-quote", "case-study",
    "case-studies", "trustpilot", "review-card", "review-slider",
    "reviews-carousel", "review-carousel", "quote-card", "success-story",
)
_TAXONOMY_SEGMENTS = {"page", "category", "tag", "author"}
# How many blog/news-keyword-matching links to consider before picking the index —
# see the shortest-path selection in scrape_site() for why more than 1 is needed.
_BLOG_INDEX_CANDIDATES = 5
# Sub-sitemaps followed one level deep from a sitemap index.
_MAX_SUB_SITEMAPS = 5

# A blog's own index page (and the /blog RSS-style listing most sites render) only
# shows recent posts — "meet the team"/leadership-announcement posts are often much
# older and fall off that list entirely, even though they're exactly where real,
# richly-titled personas live. sitemap.xml has no such recency bias, so URLs found
# there get ranked by how much they look like they're *about* a specific person.
_PERSONA_SIGNAL_KEYWORDS = (
    "meet", "welcome", "named", "president", "vice-president", "vp-", "ceo",
    "cfo", "coo", "founder", "manager", "spotlight", "profile", "employee",
    "team-member", "promoted", "promotion", "joins", "appointed", "leadership",
    "hire", "welcomes",
)


def _tokens(text: str) -> List[str]:
    """Lowercased alphanumeric words in a path segment ("wordpress-hosting" ->
    ["wordpress", "hosting"]), singularised so "features" matches "feature"."""
    words = re.split(r"[^a-z0-9]+", text.lower())
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if w]


def _matches_keyword(path: str, keywords: Iterable[str]) -> bool:
    """Whether `path` contains any keyword as a whole word, not a substring.

    A raw `keyword in path` test silently matches inside unrelated words, and
    one case poisons this product's core market: "press" is a substring of
    "wordpress", so on any WordPress-adjacent site every `/wordpress-hosting/*`
    URL registers as a blog/news link. On kinsta.com that filled all five blog
    index candidates, `/wordpress-hosting/` won as the "index" (shortest path),
    and the real `/blog/` - the entire byline-bearing archive - was never
    fetched at all. Matching on word boundaries makes "press" match "/press/"
    and "/press-releases/" while rejecting "wordpress".
    """
    segments = [seg for seg in path.lower().split("/") if seg]
    for keyword in keywords:
        kw = _tokens(keyword)
        if not kw:
            continue
        for seg in segments:
            words = _tokens(seg)
            n = len(kw)
            if any(words[i:i + n] == kw for i in range(len(words) - n + 1)):
                return True
    return False


def _domain(url: str) -> str:
    ext = tldextract.extract(url)
    return ".".join(p for p in [ext.domain, ext.suffix] if p)


def visible_text(
    html: str,
    max_chars: Optional[int] = 3000,
    *,
    strip_footer: bool = True,
    strip_testimonials: bool = False,
) -> str:
    """`max_chars=None` returns the full extracted text, untruncated.

    `strip_testimonials` removes customer testimonial/review/case-study widgets
    before text extraction. Persona extraction must return people who speak *for*
    the brand, and a testimonial names someone who speaks *about* it - usually
    with a real name and an impressive title, which is precisely what makes them
    survive every downstream name-shape filter. kinsta.com surfaced Phlearn's CEO
    and Modern Castle's founder as Kinsta "experts" this way. Deleting the block
    is the only defence that does not depend on the model choosing to obey; the
    prompt cannot un-see text it was given.
    """
    soup = BeautifulSoup(html, "html.parser")
    strip_tags = ["script", "style", "noscript", "svg", "header", "nav"]
    if strip_footer:
        strip_tags.append("footer")
    for tag in soup(strip_tags):
        tag.decompose()
    if strip_testimonials:
        doomed = []
        for tag in soup.find_all(True):
            marker = " ".join(tag.get("class") or [])
            marker = f"{marker} {tag.get('id') or ''}".lower()
            if any(m in marker for m in _TESTIMONIAL_MARKERS):
                doomed.append(tag)
        for tag in doomed:
            tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    if max_chars is None:
        return text
    return text[:max_chars]


def _head_tail(text: str, max_chars: int, tail_fraction: float = 0.35) -> str:
    """Keep both ends of `text` within an overall `max_chars` budget.

    A flat head-only slice reliably drops content that sits near the end of a
    page — e.g. a founder "Built by ..." credit in a homepage footer, or a
    trailing byline/bio on a blog post. Confirmed bug case: nextlyhq.com had
    "Built by Mobeen Abdullah at Revnix" at char ~10,800 of a 10,816-char page;
    an 8,000-char head-only cut discarded it entirely.
    """
    if len(text) <= max_chars:
        return text
    tail_chars = int(max_chars * tail_fraction)
    head_chars = max_chars - tail_chars
    return f"{text[:head_chars]}\n...\n{text[-tail_chars:]}"


def _is_priority_hub(url: str, priority_keywords: Iterable[str]) -> bool:
    """True if `url` looks like a dedicated hub page for one of `priority_keywords`.

    Deliberately stricter than the plain substring match used for ordinary
    candidates: the keyword must appear in a *short* path (a real hub lives at
    `/about`, `/our-team`, `/meet-the-team`, not buried under three segments of
    article taxonomy). Without the depth cap, ordinary content URLs hijack the
    priority tier the same way they hijack the budget - e.g. wpbeginner.com's
    `/showcase/best-email-marketing-services/` matches "service" purely as a
    substring of "services".
    """
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
) -> List[str]:
    """Links on `html` whose path matches one of `keywords`, same-domain only.

    `priority_keywords` (empty by default, so competitor discovery's behaviour is
    unchanged) promotes matching hub pages to the front of the result *before*
    `limit` is applied. Without it the cut is pure DOM order, and a nav bar full
    of product/feature links exhausts the budget before the footer's "About"/
    "Team" link is ever reached - confirmed on nextlyhq.com (four `/features/*`
    pages chosen, `/for-content-teams` dropped) and wpbeginner.com (showcase and
    guide articles chosen, `/meet-our-wpbeginner-review-board/` dropped). Those
    team pages are the single densest source of real personas, so losing them to
    ordering is exactly why persona extraction came back empty.
    """
    if limit <= 0:
        return []
    soup = BeautifulSoup(html, "html.parser")
    base_domain = _domain(base_url)
    candidates = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if _domain(href) != base_domain:
            continue
        path = urlparse(href).path.lower()
        if _matches_keyword(path, keywords):
            candidates.append(href.split("#")[0])
    seen, out = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    if priority_keywords:
        # Stable partition: DOM order is preserved within each tier.
        priority = [u for u in out if _is_priority_hub(u, priority_keywords)]
        rest = [u for u in out if u not in set(priority)]
        out = priority + rest
    return out[:limit]


_ASSET_SUFFIXES = (
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".pdf", ".zip",
    ".mp4", ".mp3", ".css", ".js", ".xml", ".json",
)
# A post slug is the give-away for an article URL: real posts are hyphenated
# prose ("how-to-choose-a-host"), navigation is not ("editor", "pricing").
_MIN_SLUG_LEN = 12
_MAX_POST_DEPTH = 4


def _looks_like_post(path: str) -> bool:
    """Whether a same-domain path looks like an individual article/post."""
    segments = [s for s in path.split("/") if s]
    if not segments or len(segments) > _MAX_POST_DEPTH:
        return False
    if any(seg in _TAXONOMY_SEGMENTS for seg in segments):
        return False
    last = segments[-1].lower()
    if last.endswith(_ASSET_SUFFIXES):
        return False
    # Hyphenated or simply long -> prose slug. Short single words are nav.
    return "-" in last or len(last) >= _MIN_SLUG_LEN


def _find_post_links(
    index_html: str,
    index_url: str,
    limit: int,
    *,
    allow_outside_index_path: bool = False,
) -> List[str]:
    """Individual post links from a blog/news index page.

    Primary heuristic: same-domain links one path segment deeper than the index
    itself (index `/blog` -> post `/blog/<slug>`), excluding pagination/taxonomy
    noise. Takes the first `limit` in page order (blog templates are almost
    always newest-first, but this isn't guaranteed for every site).

    `allow_outside_index_path` relaxes the "under the index path" requirement to
    a slug-shape test (`_looks_like_post`). That requirement is wrong on a large
    share of real sites: wpbeginner.com's index is `/blog/` but every actual post
    lives at `/beginners-guide/<slug>` or `/showcase/<slug>`, so the strict pass
    matched only `/blog/page/2|3|248` - all pagination, all discarded as taxonomy
    - and returned zero posts while a 30-post budget went unspent. Post pages are
    where author bylines live, so zero posts means zero authors.
    """
    if limit <= 0:
        return []
    soup = BeautifulSoup(index_html, "html.parser")
    index_domain = _domain(index_url)
    index_path = urlparse(index_url).path.rstrip("/")
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        href = urljoin(index_url, a["href"])
        if _domain(href) != index_domain:
            continue
        path = urlparse(href).path.rstrip("/")
        if path.startswith(index_path + "/"):
            segments = [s for s in path[len(index_path) + 1:].split("/") if s]
            if not segments or any(seg in _TAXONOMY_SEGMENTS for seg in segments):
                continue
        elif not (allow_outside_index_path and _looks_like_post(path)):
            continue
        clean = href.split("#")[0].split("?")[0]
        if clean not in seen:
            seen.add(clean)
            out.append(clean)
        if len(out) >= limit:
            break
    return out


def _persona_signal_score(url: str) -> int:
    """How much a URL looks like it's *about* a specific named person, by slug."""
    path = urlparse(url).path.lower()
    return sum(1 for kw in _PERSONA_SIGNAL_KEYWORDS if kw in path)


async def _fetch_xml(client: httpx.AsyncClient, url: str, sem: asyncio.Semaphore) -> str:
    """Like fetch(), but for sitemap.xml — served as application/xml or text/xml,
    not text/html, so the shared fetch()'s content-type gate always rejected it."""
    try:
        async with sem:
            resp = await client.get(url, timeout=REQUEST_TIMEOUT)
            content_type = resp.headers.get("content-type", "")
            if resp.status_code == 200 and ("xml" in content_type or content_type == ""):
                return resp.text
    except Exception:
        pass
    return ""


def _parse_locs(xml: str) -> List[str]:
    """<loc> values from a sitemap, with any CDATA wrapper removed.

    WordPress/Yoast wraps every entry as `<loc><![CDATA[https://...]]></loc>`.
    A bare `<loc>(.*?)</loc>` capture therefore yields the literal string
    `<![CDATA[https://example.com/post-sitemap.xml]]>`, which breaks *both*
    downstream checks: it does not end in ".xml" (so a sitemap index is never
    recognised and its sub-sitemaps are never followed) and tldextract reads its
    domain as "<![CDATA[https" (so every URL is discarded as off-domain). On
    wpbeginner.com this reduced the sitemap - the only recency-unbiased source of
    post URLs - to zero usable entries.
    """
    out = []
    for raw in re.findall(r"<loc>\s*(.*?)\s*</loc>", xml, re.DOTALL):
        loc = raw.strip()
        if loc.startswith("<![CDATA[") and loc.endswith("]]>"):
            loc = loc[len("<![CDATA["):-len("]]>")].strip()
        if loc:
            out.append(loc)
    return out


async def _discover_sitemap_xml(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, base_url: str,
) -> str:
    """First sitemap that actually responds.

    `/sitemap.xml` alone is not enough: Yoast serves `/sitemap_index.xml` and
    core WordPress 5.5+ serves `/wp-sitemap.xml`, neither of which is guaranteed
    to redirect. robots.txt is the authoritative last resort.
    """
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
    client: httpx.AsyncClient, sem: asyncio.Semaphore, base_url: str, index_url: str,
) -> List[str]:
    """Best-effort: every blog/news post URL the sitemap knows about - not just
    the recent ones a paginated index page shows.

    Handles both a flat sitemap (loc entries are pages) and a sitemap *index*
    (loc entries are other .xml files, common with WordPress/Yoast) by following
    up to `_MAX_SUB_SITEMAPS` sub-sitemaps one level deep, post sitemaps first.
    Returns [] on any failure - this is a supplementary source, never required.

    Post URLs are collected under the blog index path when that works, and by
    slug shape otherwise, for the same reason as `_find_post_links`: on many
    sites the index lives at `/blog` while the posts do not.
    """
    try:
        xml = await _discover_sitemap_xml(client, sem, base_url)
        if not xml:
            return []
        locs = _parse_locs(xml)
        # A sitemap index points at other sitemaps. Treat it as one when the
        # majority of entries are .xml, rather than requiring all of them - real
        # indexes routinely mix in a stray non-.xml entry.
        xml_locs = [l for l in locs if l.lower().split("?")[0].endswith(".xml")]
        if xml_locs and len(xml_locs) >= len(locs) / 2:
            # Post sitemaps first: a budget spent on page-/category- sitemaps
            # finds no bylines.
            ranked = sorted(xml_locs, key=lambda l: 0 if "post" in l.lower() else 1)
            sub_xmls = await asyncio.gather(
                *[_fetch_xml(client, l, sem) for l in ranked[:_MAX_SUB_SITEMAPS]]
            )
            locs = [l for x in sub_xmls if x for l in _parse_locs(x)]

        domain = _domain(base_url)
        index_path = urlparse(index_url).path.rstrip("/")
        under_index, slug_shaped, seen = [], [], set()
        for loc in locs:
            if _domain(loc) != domain:
                continue
            path = urlparse(loc).path.rstrip("/")
            clean = loc.split("#")[0].split("?")[0]
            if clean in seen:
                continue
            if path.startswith(index_path + "/"):
                segments = [s for s in path[len(index_path) + 1:].split("/") if s]
                if not segments or any(seg in _TAXONOMY_SEGMENTS for seg in segments):
                    continue
                seen.add(clean)
                under_index.append(clean)
            elif _looks_like_post(path):
                seen.add(clean)
                slug_shaped.append(clean)
        # Fallback, not supplement: when the blog index path already yields
        # posts, slug-shaped URLs elsewhere are docs/use-case/compare pages that
        # would flood the budget with content carrying no bylines.
        return under_index or slug_shaped
    except Exception:
        return []


# ============================================================================
# Personal social links
# ============================================================================

# Networks worth attaching to a person. Order is priority when one container
# holds several links to the same network.
_SOCIAL_HOSTS = {
    "linkedin": ("linkedin.com",),
    "twitter": ("twitter.com", "x.com"),
    "github": ("github.com",),
    "instagram": ("instagram.com",),
    "facebook": ("facebook.com",),
    "youtube": ("youtube.com",),
}
# Paths that are a *company* or a site-wide action, never a personal profile.
# The whole point of this feature is to return the person's own account, so a
# company page or a "share this" intent link is a wrong answer, not a partial one.
_NON_PERSONAL_PATH_PARTS = {
    "company", "companies", "school", "showcase", "groups", "jobs", "pub/dir",
    "share", "intent", "sharer", "home", "login", "signup", "help", "about",
    "privacy", "terms", "hashtag", "explore", "search", "sponsors",
}
# How far up the DOM to look for the card that owns a person's name, and how
# much text that card may hold. A byline sits within a few levels of its links;
# anything larger is a page section or a footer, where the links belong to the
# company rather than to this person.
_SOCIAL_MAX_LEVELS = 6
_SOCIAL_MAX_CONTAINER_CHARS = 2_500


def _social_network(url: str) -> Optional[str]:
    host = (urlparse(url).netloc or "").lower().lstrip("www.")
    for network, hosts in _SOCIAL_HOSTS.items():
        if any(host == h or host.endswith("." + h) for h in hosts):
            return network
    return None


def _is_personal_profile(url: str, network: str) -> bool:
    """Whether the URL points at an individual rather than a brand or an action."""
    segments = [seg for seg in urlparse(url).path.split("/") if seg]
    if not segments:
        return False                      # bare domain - a company link
    if any(seg.lower() in _NON_PERSONAL_PATH_PARTS for seg in segments):
        return False
    if network == "linkedin":
        # linkedin.com/in/<slug> is a person; /company/<slug> is not.
        return segments[0].lower() == "in" and len(segments) >= 2
    if network == "github":
        return len(segments) == 1         # /<user>, not /<user>/<repo>
    if network == "youtube":
        return segments[0].lower() in {"c", "@", "user"} or segments[0].startswith("@")
    return len(segments) == 1             # twitter/instagram/facebook handle


def _normalise_name(value: str) -> str:
    return re.sub(r"[^a-z ]+", " ", (value or "").lower())


def _handle_matches_name(url: str, name: str) -> bool:
    """Whether a profile URL's handle plausibly belongs to `name`.

    The container guard alone rejects only containers naming another *known*
    persona, so an adjacent team card for someone the LLM did not extract still
    leaked through: rankinggrow.com attributed
    linkedin.com/in/tuba-batool-2106a71b4 to Mushad Usama. Requiring a name
    token to appear in the handle closes that, because a stranger's handle
    cannot match. Precision is the priority here - an empty field is a correct
    answer, someone else's profile is not - so a handle bearing no relation to
    the person is dropped even when it sits in their card.
    """
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
    # Handles also appear abbreviated ("jsmith" for John Smith).
    collapsed = "".join(tokens)
    return handle in collapsed or collapsed.startswith(handle)


def _is_brand_account(url: str, base_url: str) -> bool:
    """Whether a handle is the site's *own* account rather than a person's.

    A brand account is shaped exactly like a personal one - `x.com/css`,
    `facebook.com/kinstahosting` - so path structure cannot separate them. The
    handle matching the site's own domain can: css-tricks.com owning `x.com/css`,
    kinsta.com owning `facebook.com/kinstahosting`. Attributing either to a
    person would put the company's account on someone's profile, which is the
    wrong answer this whole feature exists to avoid.
    """
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
    """Map each name in `names` to that person's own social profile URLs.

    Anchored on the name rather than on the links: we locate where the person is
    mentioned, then take only the social links inside the smallest enclosing
    container that mentions nobody else. Scanning for links first and guessing an
    owner afterwards is what produces the failure this guards against - handing
    back the company's LinkedIn, or another author's Twitter, for every person on
    the page.

    Returns {} for anyone whose links cannot be attributed with confidence. An
    empty result is correct; a wrong profile URL is not.
    """
    wanted = {n: _normalise_name(n) for n in names if n and n.strip()}
    if not wanted or not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    # Header/nav/footer hold the brand's own accounts on essentially every site.
    for tag in soup(["script", "style", "noscript", "svg", "header", "nav", "footer"]):
        tag.decompose()

    found: Dict[str, Dict[str, str]] = {}
    for name, needle in wanted.items():
        others = [v for k, v in wanted.items() if k != name]
        anchors = [
            el for el in soup.find_all(string=re.compile(re.escape(name), re.I))
        ]
        for anchor in anchors:
            node = anchor.parent
            for _ in range(_SOCIAL_MAX_LEVELS):
                if node is None or node.name in ("body", "html", "[document]"):
                    break
                text = node.get_text(" ", strip=True)
                if len(text) > _SOCIAL_MAX_CONTAINER_CHARS:
                    break                      # too big to belong to one person
                normalised = _normalise_name(text)
                if any(other and other in normalised for other in others):
                    break                      # shared container - ambiguous owner
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


# ============================================================================
# Bylines
# ============================================================================

_BYLINE_SELECTORS = (
    "[rel=author]", ".author-name", ".post-author", ".entry-author",
    ".byline__author", ".byline", "[itemprop=author]", ".p-author",
)
_BYLINE_NOISE = re.compile(
    r"(?i)^(post\s+author|author|by|written\s+by|posted\s+by)\s*[:\-]?\s*")


def extract_byline(html: str, base_url: str = "") -> Optional[str]:
    """The human author declared in a post's markup, or None.

    Bylines live in attributes and small elements that survive neither
    visible_text() nor the per-post character cap - rankinggrow.com declares
    `<span rel="author">Noor Khalid</span>`, which sat outside the 975-char head
    slice, so the LLM never saw the one real author on the page. Reading the
    declaration directly makes an author's presence independent of where it
    happens to fall in the document.

    Returns None for account handles rather than people: most posts on that site
    are authored by "rankinggrow", the site's own username, which is not a
    persona and must never become one.
    """
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    candidates: List[str] = []
    for node in soup.find_all("script", type="application/ld+json"):
        raw = node.string or node.get_text() or ""
        for match in re.finditer(r'"author"\s*:\s*(\{.*?\}|"[^"]+")', raw, re.S):
            found = re.search(r'"name"\s*:\s*"([^"]+)"', match.group(1)) \
                or re.match(r'"([^"]+)"', match.group(1))
            if found:
                candidates.append(found.group(1))
    meta = soup.find("meta", attrs={"name": re.compile("^author$", re.I)})
    if meta and meta.get("content"):
        candidates.append(meta["content"])
    for selector in _BYLINE_SELECTORS:
        for node in soup.select(selector):
            candidates.append(node.get_text(" ", strip=True))

    brand = re.sub(r"[^a-z0-9]", "", tldextract.extract(base_url).domain.lower())
    for candidate in candidates:
        name = _BYLINE_NOISE.sub("", (candidate or "").strip())
        name = re.sub(r"\s+", " ", name).strip(" :-|")
        if not name or len(name) > 60:
            continue
        # A person has at least two name parts; "rankinggrow" and "admin" do not.
        if len(name.split()) < 2:
            continue
        if brand and re.sub(r"[^a-z0-9]", "", name.lower()).startswith(brand):
            continue
        return name
    return None


async def fetch(client: httpx.AsyncClient, url: str, sem: asyncio.Semaphore) -> str:
    """Fetch one HTML page, retrying transient failures.

    Returns "" only after every attempt failed, and logs why. The previous
    silent `except Exception: pass` made rate limiting indistinguishable from a
    genuine 404, so a throttled run just quietly produced fewer personas with
    no signal that anything had gone wrong.
    """
    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        try:
            async with sem:
                resp = await client.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                if "text/html" in resp.headers.get("content-type", ""):
                    return resp.text
                return ""  # non-HTML is a permanent answer, not a transient one
            if resp.status_code not in _RETRYABLE_STATUS:
                logger.debug("fetch %s -> HTTP %s, not retrying", url, resp.status_code)
                return ""
            reason = f"HTTP {resp.status_code}"
        except Exception as exc:  # noqa: BLE001 - timeouts, resets, DNS
            reason = f"{type(exc).__name__}: {exc}"

        if attempt == MAX_FETCH_ATTEMPTS:
            logger.warning("fetch %s failed after %d attempts (%s)",
                           url, MAX_FETCH_ATTEMPTS, reason)
            return ""
        # Jittered backoff: a whole gather() batch hitting a rate limit would
        # otherwise retry in lockstep and be throttled again together.
        await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt * (1 + random.random()))
    return ""


async def scrape_site(
    url: str,
    *,
    max_about_pages: int = 2,
    about_keywords: Iterable[str] = ABOUT_KEYWORDS,
    home_max_chars: int = 3000,
    about_max_chars: int = 3000,
    max_blog_posts: int = 0,
    blog_index_max_chars: int = 1500,
    blog_post_max_chars: int = 1200,
    strip_footer: bool = True,
    sample_head_and_tail: bool = False,
    priority_keywords: Iterable[str] = (),
    strip_testimonials: bool = False,
) -> Dict[str, object]:
    """Homepage + about/product/etc. subpages, optionally + recent blog/news posts.

    `max_blog_posts=0` (the default) skips the blog/news crawl entirely — this is
    what src/flow/engines/competitors/scraping.py uses, to keep competitor discovery's
    scrape behavior exactly as before. Workspace brand-voice/persona extraction passes
    a positive `max_blog_posts` to also pull in recent post pages, where real author
    bylines usually live.

    `about_keywords` defaults to ABOUT_KEYWORDS (competitor discovery's exact original
    set); workspace brand-voice/persona extraction passes ABOUT_KEYWORDS + TEAM_KEYWORDS
    to also catch team/leadership pages, another common source of real persona bios.

    `sample_head_and_tail=False` (the default, and what competitor discovery uses)
    keeps the original flat head-only truncation for every page. Set it `True` (as
    workspace brand-voice/persona extraction does) to apply `_head_tail()` sampling
    to the homepage and any blog posts specifically — the two page types most likely
    to bury a founder credit or post byline near the end, past a flat char cap. About/
    product subpages and the blog index stay flat-truncated either way (lower risk,
    keeps this simple) — this flag never changes competitor discovery's behavior since
    it isn't set there.

    Returns {"pages": {url: text}, "raw_home_html": str}. `raw_home_html` is the
    unmodified homepage HTML (e.g. for cookie-consent/compliance checks) — empty
    string if the homepage fetch failed.
    """
    validate_url_for_ssrf(url)
    sem = asyncio.Semaphore(CONCURRENCY)
    headers = {"User-Agent": USER_AGENT}

    # Filled by the crawlers below so scrape_site can return raw HTML per page.
    about_html_by_url: Dict[str, str] = {}
    blog_html_by_url: Dict[str, str] = {}

    def _page_text(html: str, max_chars: int) -> str:
        if sample_head_and_tail:
            return _head_tail(
                visible_text(html, None, strip_footer=strip_footer,
                             strip_testimonials=strip_testimonials),
                max_chars,
            )
        return visible_text(html, max_chars, strip_footer=strip_footer,
                            strip_testimonials=strip_testimonials)

    async def _crawl_about(client: httpx.AsyncClient) -> Dict[str, str]:
        links = find_internal_links(
            home_html, url, about_keywords, max_about_pages,
            priority_keywords=priority_keywords,
        )
        html_list = await asyncio.gather(*[fetch(client, link, sem) for link in links])
        about_html_by_url.update({l: h for l, h in zip(links, html_list) if h})
        return {
            link: visible_text(html, about_max_chars, strip_footer=strip_footer,
                               strip_testimonials=strip_testimonials)
            for link, html in zip(links, html_list) if html
        }

    async def _crawl_blog(client: httpx.AsyncClient) -> Dict[str, str]:
        if max_blog_posts <= 0:
            return {}
        # Multiple blog-keyword matches can include both the real index (e.g.
        # /blog) and individual posts the homepage links to directly (e.g.
        # /blog/some-post) — take the shortest path as the index, since an
        # index page is reliably shorter than any specific post under it.
        # (Picking just the first DOM match instead mistook a homepage-linked
        # post for the index on at least one real site, finding zero posts.)
        candidates = find_internal_links(home_html, url, BLOG_KEYWORDS, _BLOG_INDEX_CANDIDATES)
        if not candidates:
            return {}
        # Prefer a candidate whose path is *itself* a blog hub ("/blog", "/news")
        # over one that merely contains the keyword deeper in a marketing path;
        # break ties on shortest path, as an index is always shorter than the
        # posts beneath it.
        index_url = min(
            candidates,
            key=lambda u: (
                0 if len([s for s in urlparse(u).path.split("/") if s]) <= 1
                and _matches_keyword(urlparse(u).path, BLOG_KEYWORDS) else 1,
                len(urlparse(u).path),
            ),
        )

        index_html = await fetch(client, index_url, sem)
        if not index_html:
            return {}
        blog_pages = {index_url: visible_text(
            index_html, blog_index_max_chars, strip_footer=strip_footer,
            strip_testimonials=strip_testimonials)}

        # Two sources, merged: (1) most-recent posts from the index page itself
        # (general freshness/content signal), and (2) every post the sitemap
        # knows about — ranked by how much its URL looks like a "meet the team"/
        # leadership-announcement post — since those are usually old enough to
        # have fallen off the index page's recent-posts list, but are exactly
        # where real, richly-titled personas live. A third of the budget goes
        # to (1), the rest to (2); (2) is best-effort and simply contributes
        # nothing if the site has no sitemap.
        recent_quota = max(3, max_blog_posts // 3)
        recent_links = _find_post_links(index_html, index_url, recent_quota)
        if not recent_links:
            # The index links to posts that don't sit under its own path.
            recent_links = _find_post_links(
                index_html, index_url, recent_quota, allow_outside_index_path=True,
            )
        if not recent_links:
            # Index is client-rendered and ships no post links in static HTML
            # (nextlyhq.com's Next.js /blog). The homepage usually still links
            # a few posts directly, and we already have its HTML.
            recent_links = _find_post_links(
                home_html, index_url, recent_quota, allow_outside_index_path=True,
            )

        sitemap_urls = await _fetch_sitemap_post_urls(client, sem, url, index_url)
        # Rank by persona signal, but never *gate* on it. The old code kept only
        # URLs scoring > 0, so a site whose posts have ordinary slugs contributed
        # zero posts no matter how large the budget - nextlyhq.com's five posts
        # all score 0 and were all dropped, leaving the blog index page as the
        # only blog content the LLM ever saw. Ranking still puts "meet-the-team"
        # and leadership-announcement posts first; the rest just fill the budget.
        signal_ranked = sorted(
            (u for u in sitemap_urls if u not in recent_links),
            key=_persona_signal_score, reverse=True,
        )
        signal_links = signal_ranked[: max(0, max_blog_posts - len(recent_links))]

        post_links = list(dict.fromkeys(recent_links + signal_links))[:max_blog_posts]
        if not post_links:
            return blog_pages
        post_html_list = await asyncio.gather(*[fetch(client, link, sem) for link in post_links])
        blog_html_by_url[index_url] = index_html
        for post_url, post_html in zip(post_links, post_html_list):
            if post_html:
                blog_html_by_url[post_url] = post_html
                text = _page_text(post_html, blog_post_max_chars)
                # Prepended, not appended: the byline is the single most useful
                # line on a post for persona extraction, and prepending puts it
                # inside the head slice no matter where it sat in the document.
                byline = extract_byline(post_html, post_url)
                if byline:
                    text = f"Article author: {byline}\n{text}"
                blog_pages[post_url] = text
        return blog_pages

    async with httpx.AsyncClient(headers=headers, verify=False, follow_redirects=True) as client:
        home_html = await fetch(client, url, sem)
        if not home_html:
            # Everything downstream keys off the homepage, so this is the one
            # failure that costs the entire run. Say so rather than returning
            # an empty result that looks like "this site has no content".
            logger.warning("homepage fetch failed for %s - scrape returned nothing", url)
            return {"pages": {}, "raw_home_html": ""}

        # About/product/team pages and the blog/news crawl are independent —
        # run them concurrently rather than staged one after the other.
        about_pages, blog_pages = await asyncio.gather(_crawl_about(client), _crawl_blog(client))

    pages: Dict[str, str] = {url: _page_text(home_html, home_max_chars)}
    pages.update(about_pages)
    pages.update(blog_pages)

    # Per-page HTML is kept alongside the text because social profile links live
    # in <a href> attributes, which visible_text() necessarily discards.
    raw_pages: Dict[str, str] = {url: home_html}
    raw_pages.update(about_html_by_url)
    raw_pages.update(blog_html_by_url)

    return {"pages": pages, "raw_home_html": home_html, "raw_pages": raw_pages}
