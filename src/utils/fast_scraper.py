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
from datetime import datetime
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
# Blog posts are optional breadth, not load-bearing: the homepage, about and
# team pages decide whether a run finds anyone at all, while any single post is
# one byline among thirty. Retrying a post therefore buys very little and costs
# a great deal - one slow wpbeginner.com post spent 22s on a timeout plus retry
# and stalled its whole wave, since a wave completes only when its slowest
# member does. Posts get one attempt; the pages that matter keep all three.
POST_FETCH_ATTEMPTS = 2
# Sitemaps are a supplementary source that contributes nothing when absent, so
# they must fail fast. wpbeginner.com advertises three sub-sitemaps that never
# respond, burning the full timeout each.
SITEMAP_TIMEOUT = 5
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
# Comment threads and FAQ blocks join testimonials as page regions that name
# people who do not speak for the brand. Commenters are readers; FAQ blocks
# quote nobody but often carry names in questions. On wpbeginner.com the
# commenter names happen to sit inside <header>, which visible_text() already
# drops - but that is incidental to one theme, not a guarantee, so the regions
# are removed explicitly.
_NON_BRAND_VOICE_MARKERS = (
    "comment-list", "comments-area", "comment-respond", "commentlist",
    "comments-section", "comment-form", "respond", "disqus", "livefyre",
    "faq", "frequently-asked", "question-answer", "accordion-faq",
)
# Characters of quoted text, excluding the attribution, that make a captioned
# figure a pull quote rather than an image caption.
_PULL_QUOTE_MIN_BODY = 100
_TESTIMONIAL_MARKERS = (
    "testimonial", "wall-of-love", "walloflove", "customer-story",
    "customer-stories", "customer-quote", "client-quote", "case-study",
    "case-studies", "trustpilot", "review-card", "review-slider",
    "reviews-carousel", "review-carousel", "quote-card", "success-story",
)
# Listing pages, not articles. "topic" was missing, so
# blog.pcisecuritystandards.org/topic/events and its siblings were fetched as if
# they were posts - they spent the post budget and every byline came from
# whichever article happened to head the listing, making one author look like
# the site's only writer.
_TAXONOMY_SEGMENTS = {
    "page", "category", "categories", "tag", "tags", "author", "authors",
    "topic", "topics", "label", "labels", "archive", "archives", "section",
    "search", "feed", "rss",
}
# How many blog/news-keyword-matching links to consider before picking the index —
# see the shortest-path selection in scrape_site() for why more than 1 is needed.
# Raised so a blog on its own subdomain is not cut from the candidate list by a
# handful of same-host pages that merely mention "resources" or "press".
_BLOG_INDEX_CANDIDATES = 12
# Sub-sitemaps followed one level deep from a sitemap index.
_MAX_SUB_SITEMAPS = 5
# Posts are fetched in waves and the crawl stops as soon as a wave introduces no
# author the previous waves had not already produced. Blog archives repeat the
# same handful of writers - wpbeginner.com yields 28 bylines from only a few
# distinct people - so fetching the full post budget spends most of its time
# re-confirming authors already known. The wave size keeps enough breadth that a
# single repeat post cannot end the crawl prematurely.
_POST_WAVE_SIZE = 4
# Hard ceiling on a whole scrape. Without one, total time is decided by the
# slowest origin rather than by us: identical settings took 20s on one site and
# over 110s on another, which makes pipeline latency unpredictable. Waves and
# profile fetches check the deadline and stop, keeping whatever they already
# have rather than abandoning the run.
# 60s of scraping plus a ~25s extraction keeps the whole persona step inside
# 90s even on the slowest origins tested. 85 left no room for the LLM.
DEFAULT_BUDGET_SECONDS = 32.0
# Confidence-driven stop. A fixed page budget is blind in both directions: it
# keeps fetching on a site where every persona is already provenance-backed, and
# cuts off on one where nothing is. Provenance - a name on the team page, a
# byline declared in markup, an author profile - is what confidence is built
# from and is exactly what more fetching goes looking for, so once enough of it
# exists another request cannot raise the score and the crawl should stop.
#
# Distinct declared bylines that make further post-fetching pointless. Reaching
# this many means the site's writers are established; posts beyond it repeat
# names already held.
ENOUGH_AUTHORS = 3
# Author archives are exempt from the ordinary budget check for a short,
# bounded grace period. They are the highest-value fetch in the crawl - one
# states a writer's whole output, identity and recency, where a post states a
# single byline - yet they run last and were being cut on every slow site:
# wpbeginner.com spent its entire budget on the homepage, four about pages and
# the sitemap, so a contributor with eighty articles was counted as having one.
ARCHIVE_GRACE_SECONDS = 10.0
# Budget held back from the post waves so the author archives can always run.
# Grace alone was not enough: the waves spent the whole budget before the
# archive stage was reached, so the extra window opened on a clock that was
# already past. Reserving up front means the archives are paid for first.
ARCHIVE_RESERVE_SECONDS = 8.0

# A blog's own index page (and the /blog RSS-style listing most sites render) only
# shows recent posts — "meet the team"/leadership-announcement posts are often much
# older and fall off that list entirely, even though they're exactly where real,
# richly-titled personas live. sitemap.xml has no such recency bias, so URLs found
# there get ranked by how much they look like they're *about* a specific person.
# Slugs that look like persona content but describe someone from OUTSIDE the
# organisation. "meet" in _PERSONA_SIGNAL_KEYWORDS was promoting posts titled
# "meet-this-years-community-meeting-keynote-speaker-<name>" to the top of the
# crawl, so the ranking meant to surface team members was importing conference
# speakers instead.
_EXTERNAL_PERSON_KEYWORDS = (
    "keynote", "speaker", "guest-post", "guest-author", "interview-with",
    "podcast", "webinar", "panelist", "ambassador", "sponsor",
)
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


# ============================================================================
# Page classification
# ============================================================================
# Which kind of persona a page can produce. Deciding this in code rather than
# leaving it to the prompt is what makes the routing hold for any URL: team
# pages are the only valid source of team members, article pages the only valid
# source of authors, and a page that is neither must not manufacture either.
PAGE_TEAM = "team"
PAGE_ARTICLE = "article"
PAGE_OTHER = "other"

# Path segments that mark editorial content wherever they appear.
_ARTICLE_PATH_HINTS = (
    "blog", "news", "article", "articles", "post", "posts", "insights",
    "press", "stories", "story", "resources", "perspectives", "updates",
)
# Hosts that are editorial by definition.
_ARTICLE_HOST_PREFIXES = ("blog.", "news.", "insights.", "stories.", "press.")


def classify_page(url: str, text: str = "") -> str:
    """Whether a page can yield team members, authors, or neither.

    Order matters. A declared byline or author-profile marker is decisive: it is
    direct evidence of a writer, and outranks the URL, because plenty of sites
    publish articles on paths that look like nothing in particular. Team
    keywords are checked next, then editorial paths and hosts.

    An "about" page on a blog host classifies as team, not article - the host
    describes where it is published, the path describes what it is.
    """
    if text.startswith("Article author:") or text.startswith("Author profile:"):
        return PAGE_ARTICLE
    path = urlparse(url).path.lower()
    host = (urlparse(url).netloc or "").lower()
    # "about" is an ABOUT keyword rather than a TEAM one, but an about page is
    # a people page for this purpose - and it must win over the host, so that
    # blog.example.com/about-us/ is read as team rather than as an article.
    if _matches_keyword(path, TEAM_KEYWORDS + ("about", "about-us")):
        return PAGE_TEAM
    if _matches_keyword(path, _ARTICLE_PATH_HINTS):
        return PAGE_ARTICLE
    if any(host.startswith(prefix) for prefix in _ARTICLE_HOST_PREFIXES):
        return PAGE_ARTICLE
    return PAGE_OTHER


def _domain(url: str) -> str:
    ext = tldextract.extract(url)
    return ".".join(p for p in [ext.domain, ext.suffix] if p)


def visible_html(html: str, *, strip_testimonials: bool = False) -> str:
    """The document with the regions visible_text() drops already removed.

    Exists so that markup-reading passes and the text pass cannot disagree about
    what is on a page - any exclusion added for one applies to both.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "header", "nav", "footer"]):
        tag.decompose()
    if strip_testimonials:
        for figure in soup.find_all(["figure", "blockquote"]):
            caption = figure.find(["figcaption", "cite"])
            if caption and (len(figure.get_text(" ", strip=True))
                            - len(caption.get_text(" ", strip=True))) >= _PULL_QUOTE_MIN_BODY:
                figure.decompose()
        doomed = []
        for tag in soup.find_all(True):
            marker = " ".join(tag.get("class") or [])
            marker = f"{marker} {tag.get('id') or ''}".lower()
            if any(m in marker for m in _TESTIMONIAL_MARKERS + _NON_BRAND_VOICE_MARKERS):
                doomed.append(tag)
        for tag in doomed:
            tag.decompose()
    return str(soup)


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
        # Pull quotes identified by STRUCTURE, not class name. revnix.com marks
        # a client testimonial as <figure> holding the quote with a
        # <figcaption> naming "Hannah Ross, VP of Marketing, 21st Century
        # Equipment" - no testimonial class anywhere, so marker matching cannot
        # see it. A figure whose caption sits under a substantial body of text
        # is a quotation; a team card is a short caption under an image, which
        # is why the body length decides rather than the tag alone.
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
            if any(m in marker for m in _TESTIMONIAL_MARKERS + _NON_BRAND_VOICE_MARKERS):
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
    exclude_keywords: Iterable[str] = (),
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
        if exclude_keywords and any(k in path for k in exclude_keywords):
            # "meet" is a team keyword, so "meet-this-years-keynote-speaker-x"
            # registered as a team page and spent slots from the small
            # about-page budget that real leadership pages needed.
            continue
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
    index_host = (urlparse(index_url).netloc or "").lower()
    index_path = urlparse(index_url).path.rstrip("/")
    # A blog on its own subdomain has an empty index path, so "under the index
    # path" degenerates to "anywhere on the site" and _domain() treats
    # www.example.com and blog.example.com as one domain. That combination
    # returned /contact_us/ and /faqs from the main site as blog posts.
    # Posts live on the same host as the index that lists them.
    host_locked = not index_path
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        href = urljoin(index_url, a["href"])
        if _domain(href) != index_domain:
            continue
        if host_locked and (urlparse(href).netloc or "").lower() != index_host:
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
    """How much a URL looks like it's about a specific named person on the team.

    Negative for pages about people from outside the organisation, so a keynote
    or guest-post announcement sinks below ordinary posts rather than being
    promoted ahead of them.
    """
    path = urlparse(url).path.lower()
    if any(kw in path for kw in _EXTERNAL_PERSON_KEYWORDS):
        return -1
    return sum(1 for kw in _PERSONA_SIGNAL_KEYWORDS if kw in path)


async def _fetch_xml(client: httpx.AsyncClient, url: str, sem: asyncio.Semaphore) -> str:
    """Like fetch(), but for sitemap.xml — served as application/xml or text/xml,
    not text/html, so the shared fetch()'s content-type gate always rejected it."""
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


async def discover_blog_hosts(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, base_url: str,
) -> List[str]:
    """Hosts under the same registered domain that look like a blog or newsroom.

    A site's blog often lives on a subdomain that the homepage never links -
    pcisecuritystandards.org links training.<domain> in its nav while publishing
    at blog.<domain> - so relying on internal links alone misses every author on
    such a site. Four independent sources are combined, cheapest first, because
    any one of them can be absent:

      robots.txt   Sitemap: lines routinely point at the blog's own sitemap
      sitemap.xml  <loc> hosts, including sub-sitemaps of other subdomains
      JSON-LD      url/sameAs/@id fields on the homepage
      convention   blog./news./insights. as a last-resort probe

    DNS is deliberately not used: enumerating subdomains needs zone transfer or
    a bruteforce wordlist, neither of which is appropriate here.
    """
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
            resp = await client.get(urljoin(base_url, "/robots.txt"),
                                    timeout=SITEMAP_TIMEOUT)
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

    # Conventional prefixes are a guess, so they are appended last and marked.
    # Most sites do not have them, and a guess that does not resolve must cost
    # a single fast DNS failure rather than retries with backoff -
    # blog.wpbeginner.com and news.wpbeginner.com do not exist, and probing them
    # with the normal retry policy burned ten seconds of the scrape budget.
    for prefix in ("blog", "news"):
        hosts.setdefault(f"{scheme}://{prefix}.{registered}/", None)
    return list(hosts)


def blog_hosts_from_jsonld(html: str, base_url: str) -> List[str]:
    """Blog subdomains declared in the homepage's JSON-LD (url/sameAs/@id)."""
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
        # Look for the sitemap on the INDEX's own host first. When the blog
        # lives on a subdomain, the main site's sitemap lists the marketing
        # pages and knows nothing about the posts - blog.pcisecuritystandards.org
        # has 692 of them in its own sitemap, none of which appear in
        # www.pcisecuritystandards.org/sitemap.xml. Reading the wrong host left
        # the crawl with only the newest posts from the index page, all by one
        # writer, on a blog with nine.
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
# Multi-word bylines that are still not a person. The two-word rule alone lets
# these through - wpmudev.com publishes under "Editorial Staff" - and a
# collective byline must no more become a persona than a bare username.
# Comment threads are the other place a page attaches names to an "author"
# class. WordPress marks every commenter `comment-author`, so scanning for
# author-ish classes without excluding these turns readers into personas:
# wpbeginner.com produced Jiri Vanek, Dennis Muthomi and Rob Phillips-Legge,
# none of whom write for the site - they left comments on it.
_COMMENT_MARKERS = re.compile(
    r"(?i)(^|[^a-z])(comment|respond|reply|discussion|disqus|livefyre)")
_GENERIC_BYLINES = {
    "editorial staff", "editorial team", "editor staff", "staff writer",
    "staff writers", "guest author", "guest writer", "guest contributor",
    "guest post", "content team", "marketing team", "the team", "our team",
    "admin user", "site admin", "web team", "press office", "news desk",
}
_BYLINE_NOISE = re.compile(
    r"(?i)^(post\s+author|author|by|written\s+by|posted\s+by)\s*[:\-]?\s*")


# Two-letter path prefixes are language variants of a page already fetched.
# pcisecuritystandards.org offers its leadership page in five translations, and
# harvesting them spent the entire profile budget re-reading one page.
_LANG_PREFIX = re.compile(r"^/[a-z]{2}(-[a-z]{2})?/")
# Shared with the pipeline's prose-role check; kept here so the scraper can read
# a role without importing from the service layer.
_ROLE_WORD_RE = re.compile(
    r"(?i)\b(?:founder|co-?founder|chair(?:man|woman)?|ceo|cto|coo|cfo|cmo|cio|cso|"
    r"president|vice\s+president|vp|svp|evp|avp|director|head\s+of|chief|partner|manager|"
    r"lead|engineer|developer|editor|writer|specialist|architect|consultant|"
    r"analyst|designer|executive|officer|principal|advisor|strategist)\b")
_AUTHOR_PAGE_HINTS = ("/author/", "/authors/", "/team/", "/profile/", "/people/",
                      "/contributor/", "/writer/", "/staff/", "/about/")
# Author pages are the densest persona source per request: one fetch yields a
# full bio, role and social links for a named person, where a blog post yields a
# byline. Capped because a large archive can list dozens.
# Ten, not six. The fetches run concurrently against a semaphore of ten, so
# the extra four cost almost nothing in wall clock, while six left a site with
# a larger roster reporting arts=0 for everyone past the cut - indistinguishable
# from someone who writes nothing.
_MAX_AUTHOR_PAGES = 10
# An author archive URL, whatever the site calls the segment.
_AUTHOR_PATH_RE = re.compile(r"/(author|authors|contributor|contributors)/", re.I)


# How a site credits whoever started it, when there is no team page at all.
# Small sites and agencies routinely have neither /team nor /about and say it
# once in a footer line instead.
# Case-sensitive on the name deliberately. Under re.I the capitalised classes
# match lowercase too, so "founded by Syed Balkhi in 2009" captured "Syed
# Balkhi in" - the trailing preposition became part of the name.
_FOUNDER_CREDIT_RE = re.compile(
    r"\b(?:[Ff]ounded|[Cc]reated|[Ss]tarted|[Bb]uilt|[Ee]stablished|[Ll]aunched"
    r"|[Rr]un|[Oo]wned)\s+(?:and\s+\w+\s+)?by\s+"
    r"([A-Z][a-z.'-]+(?:\s+[A-Z][a-z.'-]+){1,3})")


def extract_founder_credits(html: str) -> Dict[str, str]:
    """Name -> the sentence crediting them with founding the site.

    A last resort for sites that publish no roster. The credit line is the only
    place such a site names the person behind it, and it is a direct statement
    of belonging - the same claim a team page makes, written as prose.
    """
    if not html:
        return {}
    text = re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    found: Dict[str, str] = {}
    for match in _FOUNDER_CREDIT_RE.finditer(text):
        name = match.group(1).strip()
        if _is_person_name(name) and not _is_collective_name(name):
            start = max(0, match.start() - 60)
            found.setdefault(name, text[start:match.end() + 60].strip())
    return found


def _archive_heading(html: str) -> str:
    """The person's name as an author archive page headlines it.

    Kept separate from extract_byline because the two read different things:
    a byline states who wrote a post and may carry their title and employer,
    while an archive heading names the person the page belongs to.
    """
    heading = BeautifulSoup(html, "html.parser").find("h1")
    if not heading:
        return ""
    text = re.sub(r"\s+", " ", heading.get_text(" ", strip=True)).strip()
    text = re.sub(r"(?i)^(author|articles|posts?)\s+by:?\s*", "", text)
    text = re.sub(r"(?i)^(author|archives?\s+for)\s*[:\-]?\s*", "", text).strip()
    return text if _is_person_name(text) else ""


def extract_archive_latest_year(html: str) -> Optional[int]:
    """The most recent year an author archive shows a post for.

    An archive states how much someone has written but the scoring also needs
    to know when. Without it a writer with eighty-one posts carried no recency
    signal at all - worth twenty points - and scored below the ceiling for
    medium priority while an inactive founder kept his team-page provenance.
    Read from the listing itself so it costs no extra request.
    """
    soup = BeautifulSoup(html, "html.parser")
    # Only the person's own entries. A sidebar of the site's latest posts sits
    # on every archive, so scanning the whole page dated an author by other
    # people's work: Syed Balkhi last published in 2017 and read as active in
    # 2026, which promoted an inactive founder to the top of the ranking.
    main = (soup.find("main")
            or soup.find(attrs={"id": re.compile("content|main", re.I)})
            or soup)
    entries = main.find_all("article")
    scope = entries if entries else [main]
    years: List[int] = []
    for entry in scope:
        for tag in entry.find_all("time"):
            stamp = tag.get("datetime") or tag.get_text(" ", strip=True)
            years += [int(y) for y in re.findall(r"\b(20[0-3]\d)\b", stamp or "")]
        if not entry.find_all("time"):
            years += [int(y) for y in
                      re.findall(r"\b(20[0-3]\d)\b", entry.get_text(" ", strip=True))]
    # Ceiling read from the clock, not written into the source. A literal year
    # here stops recognising dates the moment it goes out of date: 2026 would
    # have silently dropped every 2027 article next January, quietly demoting
    # active writers as their newest work became invisible.
    plausible = [y for y in years if 2000 <= y <= datetime.now().year]
    return max(plausible) if plausible else None


def extract_author_activity(html: str, url: str) -> Optional[int]:
    """How many pieces an author archive says this person has written.

    Counted from the archive's own listing rather than from the posts the crawl
    happened to sample, which is a measure of our crawl and not of them:
    wpbeginner.com credits Nouman Yaqoob with one article by that reckoning and
    roughly ninety by his archive's. Articles per page multiplied by the highest
    page the pagination offers gives a lower bound - the final page is usually
    partial - which is enough to separate a top contributor from a one-off.

    Counts listing entries, not every link on the page: a mega-menu puts a
    hundred links on the same document and none of them are this person's work.
    """
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    main = (soup.find("main")
            or soup.find(attrs={"id": re.compile("content|main", re.I)})
            or soup)
    entries = main.find_all("article")
    if not entries:
        entries = [h for h in main.find_all(["h2", "h3"]) if h.find("a", href=True)]
    per_page = len(entries)
    if not per_page:
        return None

    path = urlparse(url).path.rstrip("/")
    pages = {int(n) for n in re.findall(
        re.escape(path) + r"/page/(\d{1,3})", html)}
    last = max(pages) if pages else 1
    # Lower bound: every page before the last is full, the last holds at least one.
    return per_page * (last - 1) + 1 if last > 1 else per_page


def extract_author_links(html: str, base_url: str) -> Dict[str, str]:
    """Author profile URLs linked from a page, mapped to their link text.

    A blog index lists every writer it shows, each linked to their profile and
    labelled with their name - wpbeginner.com's index alone names nine, Nouman
    Yaqoob among them. Sampling posts to infer the roster misses anyone whose
    posts fall outside the sample, and that site's ten-post sample is entirely
    Syed Balkhi. The links cost nothing: the page is already fetched, and the
    anchor text is the display name, so no profile fetch is needed to learn it.
    """
    if not html:
        return {}
    found: Dict[str, str] = {}
    base_domain = _domain(base_url)
    for anchor in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        href = urljoin(base_url, anchor["href"]).split("#")[0].split("?")[0]
        if _domain(href) != base_domain:
            continue
        segments = [seg for seg in urlparse(href).path.split("/") if seg]
        if len(segments) == 2 and segments[0].lower() in ("author", "authors"):
            label = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True)).strip()
            # Keep the best label seen: the same profile is often linked twice,
            # once from a photo with no text and once from the name.
            if href.rstrip("/") not in found or _is_person_name(label):
                found[href.rstrip("/")] = label
    return found


async def discover_author_pages(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, base_url: str, index_url: str,
) -> List[str]:
    """Every author profile URL the site publishes, from its sitemap.

    Sampling posts to infer who writes is statistics; a site's own list of
    authors is the answer. blog.pcisecuritystandards.org carries nine writers
    across 692 posts, five of whom published once - a ten-post sample can never
    reliably reach them, while one sitemap read names them all.

    Costs a single request against a sitemap already fetched for post URLs, and
    contributes nothing when the site publishes no author pages, so it is never
    worth skipping.
    """
    try:
        parsed_index = urlparse(index_url)
        origin = (f"{parsed_index.scheme}://{parsed_index.netloc}/"
                  if parsed_index.netloc else base_url)
        xml = await _discover_sitemap_xml(client, sem, origin)
        if not xml:
            xml = await _discover_sitemap_xml(client, sem, base_url)
        if not xml:
            return []
        locs = _parse_locs(xml)
        # A sitemap index: follow the sub-sitemap most likely to hold authors.
        xml_locs = [l for l in locs if l.lower().split("?")[0].endswith(".xml")]
        if xml_locs and len(xml_locs) >= len(locs) / 2:
            ranked = sorted(xml_locs,
                            key=lambda l: 0 if "author" in l.lower() else 1)
            subs = await asyncio.gather(
                *[_fetch_xml(client, l, sem) for l in ranked[:2]])
            locs = [l for x in subs if x for l in _parse_locs(x)]

        domain = _domain(base_url)
        found: Dict[str, None] = {}
        for loc in locs:
            if _domain(loc) != domain:
                continue
            segments = [s for s in urlparse(loc).path.split("/") if s]
            # /author/<slug>, not /author/ itself and not deeper pagination.
            if len(segments) == 2 and segments[0].lower() in ("author", "authors"):
                found.setdefault(loc.split("#")[0].split("?")[0], None)
        return list(found)
    except Exception:  # noqa: BLE001 - supplementary, never required
        return []


def extract_author_link(html: str, name: str, base_url: str = "") -> Optional[str]:
    """The URL of `name`'s own bio/author page, if the markup links to one.

    A byline is usually wrapped in a link to the writer's profile, and that page
    carries the biography, role and expertise that a post byline cannot. Without
    following it the persona's bio, demographics, goals and behaviours stay
    empty no matter how many posts are scraped, because the detail simply is not
    on the post.
    """
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
        # On a team page the profile link wraps a photo or a "read more", not
        # the name, so anchor text cannot identify its owner. The slug can:
        # /author/chriscct7/ belongs to Chris Christoff and not to Angie Meeker,
        # by the same handle test used for social profiles.
        if fallback is None and _handle_matches_name(href, name):
            fallback = href
    return fallback


# Images that are never a person: site furniture, tracking pixels, and the
# generated placeholder avatars many CMSs emit for users with no photo.
_NON_AVATAR_HINTS = (
    "logo", "icon", "sprite", "banner", "placeholder", "default-avatar",
    "avatar-default", "blank", "spacer", "pixel", "gravatar.com/avatar/00000",
    "favicon", "badge", "arrow", "chevron", "flag", "cookie",
    # Article artwork. On a post the byline sits beside the hero image, so an
    # unfiltered search hands the writer a picture of the subject of their
    # article - 21stcenturyequipment.com produced "Equipment_Buying_FAQs.png"
    # and "article-Company-News-1024x281.jpg" as portraits.
    "article", "hero", "featured", "cover", "thumbnail", "screenshot",
    "diagram", "chart", "infographic", "og-image", "social-share",
)
# A portrait is roughly square and small; article artwork is wide. Dimensions
# are often in the filename or the resize query string.
_WIDE_IMAGE_RE = re.compile(r"(\d{3,4})[x_-](\d{2,4})")
_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")


def _is_person_image(url: str) -> bool:
    """Whether an image URL plausibly shows a person rather than site furniture."""
    if not url or url.startswith("data:"):
        return False
    lowered = url.lower()
    if any(hint in lowered for hint in _NON_AVATAR_HINTS):
        return False
    path = urlparse(lowered).path
    # Query-string image services (Gravatar, Cloudinary) legitimately have no
    # file extension, so only reject a bare path that clearly is not an image.
    if "." in path.rsplit("/", 1)[-1] and not path.endswith(_IMAGE_SUFFIXES):
        return False
    match = _WIDE_IMAGE_RE.search(lowered)
    if match:
        width, height = int(match.group(1)), int(match.group(2))
        if height and width / height > 1.6:      # wider than 16:10 - not a face
            return False
    return True


def _img_src(tag) -> str:
    """Best source from an <img>, allowing for lazy-loading attributes."""
    for attr in ("src", "data-src", "data-lazy-src", "data-original"):
        value = tag.get(attr)
        if value and not value.startswith("data:"):
            return value
    srcset = tag.get("srcset") or tag.get("data-srcset")
    if srcset:
        # Largest candidate last by convention; take the final URL.
        parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return ""


def extract_person_avatars(
    html: str, names: Iterable[str], base_url: str = "",
) -> Dict[str, str]:
    """Map each name to the photo shown with them on the page.

    Anchored on the name and bounded by the same container rule as
    extract_person_socials: a photo is taken only from the smallest block that
    mentions this person and nobody else. Team pages are grids of near-identical
    cards, so an unbounded search would hand every member the first portrait on
    the page - the visual equivalent of giving one person another's LinkedIn.

    An alt attribute naming a different person rejects the image outright, since
    that is direct evidence of whose photo it is.
    """
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
                        continue          # alt names someone else - not theirs
                    src = urljoin(base_url, _img_src(img)).split("#")[0]
                    if _is_person_image(src):
                        found[name] = src
                        break
                if name in found:
                    break
                node = node.parent
            if name in found:
                break
    return found


# A team card pairs a name with a role in adjacent elements. Reading that pair
# directly turns "did the model notice this person" into a question the code can
# answer, which matters because the model silently omits people - the leadership
# pass returned 6 of 11 executives before it was given a prompt of its own, and
# nothing downstream could tell that five were missing.
_CARD_NAME_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6", "strong", "b", "p", "span", "div")
_CARD_MAX_GAP = 3


def extract_team_names(html: str, base_url: str = "") -> Dict[str, str]:
    """Name -> stated role, read from team-card markup rather than from prose.

    Deliberately conservative: a name only counts when a role word sits in the
    element beside it, which is what a roster entry looks like and what a
    paragraph of marketing copy does not. Returns {} on any page that is not
    structured that way, contributing nothing rather than guessing.
    """
    if not html:
        return {}
    # Read from the same cleaned markup the text pass sees. Reading raw HTML
    # here reintroduced exactly what visible_text() removes: revnix.com's
    # testimonial figures gave up "Noah Proser, COO, KitBash3D" as a team
    # member, because a pull quote's attribution is a name beside a role and
    # that is precisely the shape this looks for.
    soup = BeautifulSoup(
        visible_html(html, strip_testimonials=True), "html.parser")

    found: Dict[str, str] = {}
    for node in soup.find_all(_CARD_NAME_TAGS):
        text = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if not _is_person_name(text):
            continue
        # The role usually sits in the next element, occasionally the previous.
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
    """An article's headline: og:title, then <h1>, then <title>."""
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
        # Strip the trailing " | Site Name" most themes append.
        return re.sub(r"\s*[|\-–—]\s*[^|\-–—]{1,40}$", "",
                      re.sub(r"\s+", " ", soup.title.string).strip())[:200]
    return ""


def extract_jsonld_authors(html: str, base_url: str = "") -> List[str]:
    """Every distinct person named as an author in a page's JSON-LD.

    A blog index or topic listing usually embeds structured data for every post
    it lists, each with its own author. One fetch of such a page can therefore
    name a dozen writers - far cheaper than fetching a dozen posts to read one
    byline each, and it reaches authors whose posts are too old to appear in the
    recent-posts list at all.

    extract_byline() returns a single author for one article; this returns all
    of them for a listing.
    """
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
            r'\{[^{}]*"@type"\s*:\s*"Person"[^{}]*?"name"\s*:\s*"([^"]+)"', raw)
        for raw_name in candidates:
            name = re.sub(r"\s+", " ", raw_name).strip()
            if len(name.split()) < 2 or len(name) > 60:
                continue
            collapsed = name.lower()
            if collapsed in _GENERIC_BYLINES:
                continue
            if collapsed.endswith((" team", " staff", " desk", " editors")):
                continue
            if brand and re.sub(r"[^a-z0-9]", "", collapsed).startswith(brand):
                continue
            names.setdefault(name, None)
    return list(names)


# Fragments that betray a name derived from an email address or an account
# handle rather than written by a person: "Devrevnix Com", "Huzaifa Revnixgmail
# Com". A real display name never ends in a domain suffix.
_EMAIL_NAME_PARTS = ("gmail", "com", "net", "org", "co", "io", "outlook",
                     "hotmail", "yahoo", "mail", "email", "admin", "info",
                     "noreply", "no reply", "support", "dev", "test")


# Interface labels, not people. A "Read more »" or "View Profile" link sitting
# beside a byline is the site's own furniture, and the link text is what the
# author-link reader picks up. Left unfiltered these were accepted as names and
# claimed the author slot ahead of the real one, so five wpbeginner.com writers
# arrived as "Read more »" with no post count while their archives went
# unfetched.
_UI_LABEL_WORDS = {"read", "more", "view", "profile", "learn", "continue",
                   "reading", "click", "here", "see", "all", "show", "load",
                   "next", "previous", "back", "home", "share", "follow",
                   "subscribe", "comments", "reply", "posts", "articles",
                   "details", "info", "link", "page", "menu", "search"}


_COLLECTIVE_SUFFIXES = (" team", " staff", " desk", " editors", " editorial",
                        " group", " crew", " contributors", " newsroom")


def _is_collective_name(value: str) -> bool:
    """Whether a byline names a group rather than a person."""
    text = re.sub(r"\s+", " ", (value or "")).strip().lower()
    return text.startswith("editorial") or text.endswith(_COLLECTIVE_SUFFIXES)


def _is_person_name(value: str) -> bool:
    """Whether a string reads as a person's name rather than an address or slug."""
    text = re.sub(r"\s+", " ", (value or "")).strip()
    if not text or len(text) > 60 or "@" in text:
        return False
    words = [w for w in re.sub(r"[^\w\s.]", " ", text.lower()).split() if w]
    # Two to five words. Punctuation is stripped before counting, so without an
    # upper bound "Mark Meissner SVP, Engagement Officer (North America)"
    # collapses to seven all-alphabetic words and reads as a name.
    if not 2 <= len(words) <= 5:
        return False
    # A role word inside the string means it is a name plus a title, not a name.
    if _ROLE_WORD_RE.search(text):
        return False
    # A domain suffix anywhere in the name means it came from an address.
    if any(w in _EMAIL_NAME_PARTS for w in words):
        return False
    # Every word being interface vocabulary means this is a control, not a
    # person. Tested across the whole string rather than word by word so a real
    # name that happens to contain one of these survives.
    if all(w in _UI_LABEL_WORDS for w in words):
        return False
    return all(re.match(r"^[a-z][a-z.'\-]*$", w) for w in words)


# Where a page states when it was published, best evidence first. JSON-LD and
# <meta> carry a machine-readable date the site itself asserts; a <time
# datetime> attribute is nearly as good; visible prose is a last resort because
# "Updated March" without a year cannot be placed.
_DATE_META = ("article:published_time", "datePublished", "publish_date",
              "date", "DC.date.issued", "article:modified_time")
_ISO_DATE = re.compile(r"(19|20)\d{2}-\d{2}-\d{2}")
# Both orders sites write dates in: "18 Aug, 2026" and "Aug 18, 2026".
_MONTHS = ("jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec")
_PROSE_DATE = re.compile(
    r"(?i)(?:\d{1,2}\s+(?:" + _MONTHS + r")[a-z]*,?\s+(?:19|20)\d{2}"
    r"|(?:" + _MONTHS + r")[a-z]*\s+\d{1,2},?\s+(?:19|20)\d{2})")
_DATE_PROSE_WINDOW = 900
_YEAR_ONLY = re.compile(r"\b(19|20)\d{2}\b")
# Older than this and a person counts as inactive unless they also have recent
# work - the brief calls 2020 the floor for eligibility.
ACTIVE_SINCE_YEAR = 2020
RECENT_SINCE_YEAR = 2023


def extract_publish_year(html: str) -> Optional[int]:
    """The year a page says it was published, or None.

    Reads the site's own assertion rather than guessing from page text: a blog
    post mentions many years in its body, and only the declared date says when
    this piece was written. Returns a year rather than a full date because
    recency scoring works in years and a partial date is still useful.
    """
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
        tag = (soup.find("meta", attrs={"property": key})
               or soup.find("meta", attrs={"name": key})
               or soup.find("meta", attrs={"itemprop": key}))
        if tag and tag.get("content"):
            year = _ISO_DATE.search(tag["content"]) or _YEAR_ONLY.search(tag["content"])
            if year:
                return int(year.group(0)[:4])

    for tag in soup.find_all("time"):
        value = tag.get("datetime") or tag.get_text(" ", strip=True)
        year = _ISO_DATE.search(value or "") or _YEAR_ONLY.search(value or "")
        if year:
            return int(year.group(0)[:4])

    # Elements that name themselves as the date - "published", "post-date".
    for node in soup.find_all(attrs={"class": re.compile("(date|published|posted)", re.I)}):
        year = _YEAR_ONLY.search(node.get_text(" ", strip=True))
        if year:
            return int(year.group(0))

    # Prose, and only from the head of the page. blog.pcisecuritystandards.org
    # declares no date in markup at all and writes "Posted by Alicia Malone on
    # 18 Aug, 2026" in the byline line. Restricted to the opening because an
    # article body cites many years and only the byline states this one's.
    # Script and style content sits at the top of the raw document, so the
    # window has to be taken from readable text or it never reaches the byline.
    prose = BeautifulSoup(str(soup), "html.parser")
    # Same regions visible_text() drops. Without removing nav, the window is
    # spent on menu items and never reaches the byline line.
    for tag in prose(["script", "style", "noscript", "svg", "header", "nav", "footer"]):
        tag.decompose()
    head = re.sub(r"\s+", " ", prose.get_text(" ", strip=True))[:_DATE_PROSE_WINDOW]
    written = _PROSE_DATE.search(head)
    if written:
        year = _YEAR_ONLY.search(written.group(0))
        if year:
            return int(year.group(0))
    return None


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

    # Drop comment threads AND testimonial widgets before looking for a byline.
    # visible_text() already removes both from the page text, but the byline is
    # read from the markup separately and was only excluding comments - so
    # wpgrit.com's testimonial carousel, which marks each quote's attribution
    # with class="author-name", had its quoted customers prepended to every
    # service page and blog post as "Article author: <name>". Jeff Evans, who
    # works at Google and appears there praising the agency, became a WPGrit
    # persona on that basis. A testimonial's author is the person being quoted,
    # never the author of the page carrying the quote.
    doomed = []
    for node in soup.find_all(True):
        marker = " ".join(node.get("class") or [])
        marker = f"{marker} {node.get('id') or ''}"
        lowered = marker.lower()
        if _COMMENT_MARKERS.search(marker) or any(
                m in lowered for m in _TESTIMONIAL_MARKERS):
            doomed.append(node)
    for node in doomed:
        node.decompose()

    candidates: List[str] = []
    for node in soup.find_all("script", type="application/ld+json"):
        raw = node.string or node.get_text() or ""
        for match in re.finditer(r'"author"\s*:\s*(\{.*?\}|"[^"]+")', raw, re.S):
            found = re.search(r'"name"\s*:\s*"([^"]+)"', match.group(1)) \
                or re.match(r'"([^"]+)"', match.group(1))
            if found:
                candidates.append(found.group(1))
        # Yoast and similar emit an @graph where "author" is a *reference*
        # ({"@id": "...#schema-author"}) and the name lives on a separate Person
        # node. Matching the author object alone therefore yields nothing, which
        # is why wpmudev.com's declared author was invisible.
        if '"@graph"' in raw or "schema-author" in raw:
            for person in re.finditer(
                    r'\{[^{}]*"@type"\s*:\s*"Person"[^{}]*\}', raw, re.S):
                named = re.search(r'"name"\s*:\s*"([^"]+)"', person.group(0))
                if named:
                    candidates.append(named.group(1))
    # find_all, not find: a page may carry several author metas and the first is
    # routinely empty, which silently discarded the populated one behind it.
    for meta in soup.find_all("meta", attrs={"name": re.compile("^author$", re.I)}):
        if meta.get("content"):
            candidates.append(meta["content"])
    for selector in _BYLINE_SELECTORS:
        for node in soup.select(selector):
            candidates.append(node.get_text(" ", strip=True))
    # Themes namespace their own classes ("dev-post__meta-author"), so an exact
    # selector list can never be complete. Any element whose class/id/rel
    # mentions "author" is a candidate; the person-shape checks below decide.
    for node in soup.find_all(attrs={"class": re.compile("author", re.I)}):
        candidates.append(node.get_text(" ", strip=True))
    for node in soup.find_all(attrs={"id": re.compile("author", re.I)}):
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
        collapsed = re.sub(r"\s+", " ", name.lower()).strip()
        if collapsed in _GENERIC_BYLINES:
            continue
        if collapsed.endswith((" team", " staff", " desk", " editors")):
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
) -> str:
    """Fetch one HTML page, retrying transient failures.

    Returns "" only after every attempt failed, and logs why. The previous
    silent `except Exception: pass` made rate limiting indistinguishable from a
    genuine 404, so a throttled run just quietly produced fewer personas with
    no signal that anything had gone wrong.
    """
    for attempt in range(1, max(1, attempts) + 1):
        try:
            # A request may not outlive the scrape budget. Checking the budget
            # only between stages let a wave already in flight run to
            # completion: on a throttling origin ten requests at ten seconds
            # each turned a 40s budget into a 70s-plus scrape. Sizing each
            # timeout to the time actually left caps the overshoot at one
            # request rather than a whole wave.
            timeout = REQUEST_TIMEOUT
            if deadline is not None:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    return ""
                timeout = max(1.0, min(REQUEST_TIMEOUT, remaining))
            async with sem:
                resp = await client.get(url, timeout=timeout)
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

        if attempt >= max(1, attempts):
            logger.warning("fetch %s failed after %d attempt(s) (%s)",
                           url, max(1, attempts), reason)
            return ""
        # Jittered backoff: a whole gather() batch hitting a rate limit would
        # otherwise retry in lockstep and be throttled again together.
        await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt * (1 + random.random()))
    return ""


# Paths a site puts its people on. Fetched as a fixed parallel wave rather than
# discovered by crawling: discovery depends on a link appearing on a page the
# crawl happened to reach, which is why an author with 81 posts was found on
# roughly half of otherwise identical runs. These are cheap, bounded and always
# the same, so what the scrape finds no longer depends on what it happened to
# see first.
_PEOPLE_PATHS = ("/blog/", "/about/", "/team/", "/authors/",
                 "/contributors/", "/leadership/")


async def discover_people_pages(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, base_url: str,
    deadline: Optional[float] = None,
) -> Dict[str, str]:
    """Author-page URL -> the site's own label for that person.

    One parallel wave over known people paths. A 404 costs nothing and a hit
    yields the author links the crawl would otherwise have to stumble onto.
    """
    targets = [urljoin(base_url, path) for path in _PEOPLE_PATHS]
    pages = await asyncio.gather(
        *[fetch(client, u, sem, attempts=1, deadline=deadline) for u in targets])
    found: Dict[str, str] = {}
    for page_url, html in zip(targets, pages):
        if not html:
            continue
        for archive_url, label in extract_author_links(html, page_url).items():
            if _is_person_name(label):
                found.setdefault(archive_url, label)
    if found:
        logger.info("fixed-path sweep found %d author page(s)", len(found))
    return found


async def scrape_site(
    url: str,
    *,
    max_about_pages: int = 2,
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
    started = asyncio.get_event_loop().time()
    deadline = started + budget_seconds if budget_seconds else None

    def _out_of_time(stage: str, grace: float = 0.0) -> bool:
        """Whether the budget is spent, optionally past a reserved window.

        Author archives get the grace window because they are the highest-value
        request in the crawl: one states a writer's entire output, where a post
        states a single byline. Under the pipeline's 32s budget they were cut on
        every run - Nouman Yaqoob's 81 posts were fetched and counted correctly
        with no budget and never reached the pipeline with one, which is what
        left an active author ranked below an inactive founder.
        """
        if deadline is None or asyncio.get_event_loop().time() < deadline + grace:
            return False
        # Never silent: a truncated crawl looks exactly like a small site.
        logger.warning("scrape budget of %.0fs exhausted, stopping at %s",
                       budget_seconds, stage)
        return True

    sem = asyncio.Semaphore(CONCURRENCY)
    headers = {"User-Agent": USER_AGENT}
    # Best value seen for each archive during this scrape. The same page is
    # fetched more than once - the overlapped pass, the retry, the profile pass
    # - and a reduced response arrives with real markup, a countable listing and
    # no dates. Whichever attempt saw the dates is the one that read the page
    # correctly, so a later empty read must not overwrite it: that alternation
    # is what moved a writer between 100 and 84 on identical input.
    best_year_by_url: Dict[str, int] = {}

    def _best_year(page_url: str, html: str) -> Optional[int]:
        found = extract_archive_latest_year(html)
        if found:
            best_year_by_url[page_url] = max(best_year_by_url.get(page_url, 0), found)
        return best_year_by_url.get(page_url) or None

    # Filled by the crawlers below so scrape_site can return raw HTML per page.
    about_html_by_url: Dict[str, str] = {}
    blog_html_by_url: Dict[str, str] = {}
    team_profile_links: Dict[str, None] = {}
    # Author pages the site links under a person's name, as opposed to profile
    # URLs inferred from markup. A named link is the site stating who writes
    # here, so these are counted first when the fetch budget is smaller than
    # the roster: sorting the whole set alphabetically cut "nyaqoob" and
    # "syedb" - the two the ranking most depends on - in favour of authors
    # whose slugs happened to start with a letter nearer the front.
    named_author_links: set = set()

    def _with_byline(page_url: str, html: str, text: str) -> str:
        """Surface a declared author on any page, not only blog posts.

        Pages reached through the about/team path can still be articles - a
        "meet the ..." slug matches a team keyword - and their author was being
        extracted correctly but never written into the text the model reads.
        """
        who = extract_byline(html, page_url)
        if not who:
            return text
        year = extract_publish_year(html)
        return f"Article author: {who}{f' | {year}' if year else ''}\n{text}"

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
            exclude_keywords=_EXTERNAL_PERSON_KEYWORDS if priority_keywords else (),
        )
        html_list = await asyncio.gather(
            *[fetch(client, link, sem, deadline=deadline) for link in links])
        about_html_by_url.update({l: h for l, h in zip(links, html_list) if h})
        # A leadership page lists the whole executive team in one document, so
        # the ordinary about-page cap truncates it and silently loses everyone
        # below the cut - pcisecuritystandards.org/about_us/leadership/ returned
        # two of its executives for exactly this reason. Team pages are the
        # densest persona source on any site and get a larger budget.
        team_cap = team_max_chars or about_max_chars
        # A team page links each member to their own profile. Those pages carry
        # the bios that a one-line team card cannot, and every such link on a
        # team page belongs to a real member - so unlike the blog case there is
        # no name to match against, and the links are taken as found.
        for link, html in zip(links, html_list):
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
                link, html,
                visible_text(
                    html,
                    team_cap if _matches_keyword(urlparse(link).path, TEAM_KEYWORDS)
                    else about_max_chars,
                    strip_footer=strip_footer, strip_testimonials=strip_testimonials))
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
        candidates_from_links = list(candidates)
        # find_internal_links matches on the path, so a post at
        # blog.example.com/some-title is invisible to it - the only blog signal
        # is in the host. Sites that publish on a dedicated subdomain were
        # therefore never crawled for authors at all.
        soup = BeautifulSoup(home_html, "html.parser")
        base_domain = _domain(url)
        for anchor in soup.find_all("a", href=True):
            href = urljoin(url, anchor["href"]).split("#")[0]
            host = (urlparse(href).netloc or "").lower()
            if _domain(href) == base_domain and (
                    host.startswith("blog.") or host.startswith("news.")):
                root = f"{urlparse(href).scheme}://{host}/"
                if root not in candidates:
                    candidates.append(root)
        # Some sites never link their blog from the homepage nav at all -
        # pcisecuritystandards.org links only training.<domain>, while it
        # publishes at blog.<domain>. The conventional subdomain is worth one
        # speculative request: it either answers and yields the authors, or it
        # does not and costs a single failed fetch.
        for host_root in blog_hosts_from_jsonld(home_html, url):
            if host_root not in candidates:
                candidates.append(host_root)
        for host_root in await discover_blog_hosts(client, sem, url):
            if host_root not in candidates:
                candidates.append(host_root)
        if not candidates:
            return {}
        # Prefer a candidate whose path is *itself* a blog hub ("/blog", "/news")
        # over one that merely contains the keyword deeper in a marketing path;
        # break ties on shortest path, as an index is always shorter than the
        # posts beneath it.
        def _index_rank(candidate: str) -> tuple:
            host = (urlparse(candidate).netloc or "").lower()
            path = urlparse(candidate).path
            segments = [seg for seg in path.split("/") if seg]
            return (
                # A dedicated blog subdomain is the blog, unambiguously.
                # pcisecuritystandards.org publishes at
                # blog.pcisecuritystandards.org while /resources-overview/
                # merely matches "resources", so ranking by path alone picked
                # the resources page and the real blog was never crawled.
                0 if host.startswith("blog.") or host.startswith("news.") else 1,
                0 if len(segments) <= 1 and _matches_keyword(path, BLOG_KEYWORDS) else 1,
                len(path),
            )

        # Try candidates best-first and keep going until one actually yields
        # posts. Committing to a single guess meant one unreachable or
        # post-less index abandoned the entire blog crawl - and with it every
        # author on the site - even when a workable index was next in line.
        ranked = sorted(candidates, key=_index_rank)[:4]
        index_url, index_html, recent_seed = "", "", []
        for candidate in ranked:
            # A speculative host gets one attempt; a link the site actually
            # published gets the normal policy.
            speculative = urlparse(candidate).netloc.lower() not in {
                urlparse(c).netloc.lower() for c in candidates_from_links}
            html = await fetch(client, candidate, sem,
                               attempts=1 if speculative else POST_FETCH_ATTEMPTS,
                               deadline=deadline)
            if not html:
                continue
            found = _find_post_links(html, candidate, max_blog_posts) or _find_post_links(
                html, candidate, max_blog_posts, allow_outside_index_path=True)
            if found:
                index_url, index_html, recent_seed = candidate, html, found
                break
            if not index_html:                     # keep the first readable one
                index_url, index_html = candidate, html
        if not index_html:
            return {}
        logger.info("blog index chosen: %s (%d post links)", index_url, len(recent_seed))
        index_text = visible_text(index_html, blog_index_max_chars,
                                  strip_footer=strip_footer,
                                  strip_testimonials=strip_testimonials)
        listing_authors = extract_jsonld_authors(index_html, index_url)
        if listing_authors:
            # One fetch, many writers - including ones whose posts are far too
            # old to appear in the recent-posts list.
            index_text = ("Article authors: " + ", ".join(listing_authors)
                          + "\n" + index_text)
            logger.info("blog index JSON-LD named %d authors", len(listing_authors))
        blog_pages = {index_url: index_text}

        # Two sources, merged: (1) most-recent posts from the index page itself
        # (general freshness/content signal), and (2) every post the sitemap
        # knows about — ranked by how much its URL looks like a "meet the team"/
        # leadership-announcement post — since those are usually old enough to
        # have fallen off the index page's recent-posts list, but are exactly
        # where real, richly-titled personas live. A third of the budget goes
        # to (1), the rest to (2); (2) is best-effort and simply contributes
        # nothing if the site has no sitemap.
        recent_quota = max(3, max_blog_posts // 3)
        recent_links = recent_seed[:recent_quota] or _find_post_links(
            index_html, index_url, recent_quota)
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
        # Spread the sitemap picks ACROSS the archive instead of taking a
        # contiguous block. A blog index lists only the newest posts, and those
        # are usually all by whoever is currently most active - on
        # blog.pcisecuritystandards.org the eight newest are all by one person,
        # so a recency-ordered sample concluded the site had a single writer
        # when the archive actually carries nine. Striding over 692 posts finds
        # them; reading the first eight never can.
        budget_left = max(0, max_blog_posts - len(recent_links))
        if signal_ranked and budget_left:
            scored = [u for u in signal_ranked if _persona_signal_score(u) > 0]
            rest = [u for u in signal_ranked if _persona_signal_score(u) <= 0]
            take_scored = scored[: budget_left // 2]
            remaining = budget_left - len(take_scored)
            if remaining > 0 and rest:
                stride = max(1, len(rest) // remaining)
                take_rest = rest[::stride][:remaining]
            else:
                take_rest = []
            signal_links = take_scored + take_rest
        else:
            signal_links = signal_ranked[:budget_left]

        post_links = list(dict.fromkeys(recent_links + signal_links))[:max_blog_posts]
        if not post_links:
            return blog_pages
        blog_html_by_url[index_url] = index_html
        # Author pages linked from the index and, as they arrive, from the posts.
        # Declared before the wave loop because that loop writes into it - the
        # previous placement, after the loop, raised UnboundLocalError on every
        # site with a blog and sent the whole scrape into the browser fallback.
        linked_authors: Dict[str, str] = dict(
            extract_author_links(index_html, index_url))
        # Author archives first, before the post waves. One archive states a
        # writer's whole output and their identity; a post states one byline.
        # Fetching them last meant the budget cut them on every slow site, so
        # the roster was known by name but never counted - a top contributor
        # with eighty articles scored the same as someone with one.
        author_pages: Dict[str, str] = {}
        archives_allowed = deadline is None or (
            asyncio.get_event_loop().time() < deadline + ARCHIVE_GRACE_SECONDS)
        if linked_authors and archives_allowed:
            named = [(label, u) for u, label in linked_authors.items()
                     if _is_person_name(label)][:_MAX_AUTHOR_PAGES]
            if named:
                archive_deadline = (deadline + ARCHIVE_GRACE_SECONDS
                                    if deadline else None)
                archives = await asyncio.gather(
                    *[fetch(client, u, sem, attempts=POST_FETCH_ATTEMPTS,
                            deadline=archive_deadline) for _, u in named])
                for (label, archive_url), archive_html in zip(named, archives):
                    if not archive_html:
                        continue
                    counted = extract_author_activity(archive_html, archive_url)
                    blog_html_by_url[archive_url] = archive_html
                    blog_pages[archive_url] = (
                        f"Author profile: {label}"
                        + (f" | posts={counted}" if counted else "") + "\n"
                        + visible_text(archive_html, about_max_chars,
                                       strip_footer=strip_footer,
                                       strip_testimonials=strip_testimonials))
                    author_pages.setdefault(label, archive_url)
                logger.info("fetched %d author archives", len(named))

        authors_seen: set = set()
        dry_waves = 0

        # An author archive starts downloading the moment the site names its
        # author, running alongside the remaining post waves rather than in a
        # stage after them. The ordering was the whole problem: on
        # wpbeginner.com the authors are only discovered *during* the waves, so
        # a stage that ran afterwards found the budget already spent and the
        # counts came back on roughly one run in three. Overlapping the fetches
        # removes the race instead of timing it.
        archive_deadline = deadline + ARCHIVE_GRACE_SECONDS if deadline else None
        archive_tasks: Dict[str, asyncio.Task] = {}
        archive_labels: Dict[str, str] = {}

        def _queue_archive(label: str, archive_url: str) -> None:
            if archive_url in archive_tasks or archive_url in blog_html_by_url:
                return
            if not _is_person_name(label) or _is_collective_name(label):
                return
            if len(archive_tasks) >= _MAX_AUTHOR_PAGES:
                return
            archive_labels[archive_url] = label
            archive_tasks[archive_url] = asyncio.create_task(
                fetch(client, archive_url, sem, attempts=POST_FETCH_ATTEMPTS,
                      deadline=archive_deadline))

        for start in range(0, len(post_links), _POST_WAVE_SIZE):
            # Posts stop early once the site has named authors we can still
            # count. One archive is worth more than one more post: it states a
            # writer's whole output where a post states a single byline.
            reserve = -ARCHIVE_RESERVE_SECONDS if linked_authors else 0.0
            if _out_of_time("blog posts", reserve):
                break
            wave = post_links[start:start + _POST_WAVE_SIZE]
            wave_html = await asyncio.gather(
                *[fetch(client, link, sem, attempts=POST_FETCH_ATTEMPTS,
                        deadline=deadline) for link in wave])
            new_authors = 0
            for post_url, post_html in zip(wave, wave_html):
                if not post_html:
                    continue
                blog_html_by_url[post_url] = post_html
                text = _page_text(post_html, blog_post_max_chars)
                # Prepended, not appended: the byline is the single most useful
                # line on a post for persona extraction, and prepending puts it
                # inside the head slice no matter where it sat in the document.
                byline = extract_byline(post_html, post_url)
                if byline:
                    year = extract_publish_year(post_html)
                    stamp = f" | {year}" if year else ""
                    text = f"Article author: {byline}{stamp}\n{text}"
                    if byline not in authors_seen:
                        authors_seen.add(byline)
                        new_authors += 1
                blog_pages[post_url] = text
            for post_url, post_html in zip(wave, wave_html):
                if not post_html:
                    continue
                found = extract_author_links(post_html, post_url)
                linked_authors.update(found)
                for archive_url, label in found.items():
                    _queue_archive(label, archive_url)
                first = blog_pages.get(post_url, "")
                if first.startswith("Article author:"):
                    who = first.split("\n")[0].replace("Article author: ", "")
                    link = extract_author_link(post_html, who, post_url)
                    if link:
                        author_pages.setdefault(who, link)
                        _queue_archive(who, link)
            if len(authors_seen) >= ENOUGH_AUTHORS:
                logger.info("post crawl stopped: %d distinct authors established "
                            "(%d posts fetched) - further posts cannot raise "
                            "confidence", len(authors_seen), start + len(wave))
                break
            if not new_authors:
                dry_waves += 1
            else:
                dry_waves = 0
            # Two consecutive dry waves, not one. A single dry wave is common
            # when consecutive posts share an author, and stopping on it is how
            # a nine-author blog was read as having one.
            if authors_seen and dry_waves >= 2:
                logger.info("post crawl stopped: %d waves added no new author "
                            "(%d fetched, %d authors)", dry_waves,
                            start + len(wave), len(authors_seen))
                break

        # Follow each writer to their own page. This is where the biography,
        # role and expertise live; posts only carry the name.
        # The site's own author list, where it publishes one. This names writers
        # the post sample never reached - the ones with a single article to
        # their name - and costs one request against a sitemap already read for
        # post URLs. Sampling posts to infer who writes is statistics; the
        # site's list of authors is the answer.
        # Only when the posts came up short. Where bylines already named enough
        # writers the index adds nothing but cost, and its slug-derived entries
        # compete for the same _MAX_AUTHOR_PAGES budget as the real ones -
        # wpmudev.com dropped from seven authors to two when they displaced
        # them. It exists for the site where sampling failed, not to second-guess
        # the sampling that worked.
        index_profiles: List[str] = []
        # A named link to an author page is the site stating that this person
        # writes for it - the same claim the profile page would make, already
        # made on a page in hand. Registering it needs no request, which matters
        # because the profile fetches are the first thing the budget cuts:
        # wpbeginner.com links nine authors from its index and Nouman Yaqoob
        # was reached by none of the ten sampled posts.
        for profile_url, label in linked_authors.items():
            if not _is_person_name(label):
                continue
            author_pages.setdefault(label, profile_url)
            # Queued for the budget-exempt archive stage rather than left as a
            # bare claim. These are the authors the site links by name, so they
            # are exactly the ones worth counting - Nouman Yaqoob arrived here
            # and got a stub, which is why an author with 81 posts scored as
            # though he had none.
            team_profile_links.setdefault(profile_url, None)
            named_author_links.add(profile_url)
            # Fallback for anyone the archive stage could not reach: the link
            # itself is still the site stating they write here.
            blog_pages.setdefault(
                profile_url,
                f"Author profile: {label}\n{label} is credited as an author on "
                f"{_domain(url)} and has an author page at {profile_url}.")

        # Whatever the overlapped archive fetches returned, counted now. They
        # were started during the waves, so most have already landed and this
        # awaits little or nothing.
        if archive_tasks:
            done = await asyncio.gather(*archive_tasks.values(),
                                        return_exceptions=True)
            for archive_url, archive_html in zip(archive_tasks, done):
                if not isinstance(archive_html, str) or not archive_html:
                    continue
                label = _archive_heading(archive_html) or archive_labels.get(archive_url, "")
                if not _is_person_name(label):
                    continue
                counted = extract_author_activity(archive_html, archive_url)
                blog_html_by_url[archive_url] = archive_html
                blog_pages[archive_url] = (
                    f"Author profile: {label}"
                    + (f" | posts={counted}" if counted else "")
                    + (f" | latest={_lat}" if (_lat := _best_year(archive_url, archive_html)) else "")
                    + "\n"
                    + visible_text(archive_html, about_max_chars,
                                   strip_footer=strip_footer,
                                   strip_testimonials=strip_testimonials))
                author_pages.setdefault(label, archive_url)
            logger.info("counted %d overlapped author archives", len(archive_tasks))

        # Archives for authors the site already named are fetched before any
        # speculative discovery. The two blocks below hunt for author pages we
        # have no link to yet, and running them first spent what remained of
        # the budget looking for authors while the archives of the authors
        # already found went unfetched - which is why Nouman Yaqoob's count
        # was 81 on one run and 0 on the next with nothing else changed.
        candidates = [(who, link) for who, link in author_pages.items()
                      if not _is_collective_name(who)]
        for who, link in candidates:
            cached = blog_html_by_url.get(link)
            if not cached or " | posts=" in blog_pages.get(link, ""):
                continue
            counted = extract_author_activity(cached, link)
            if counted:
                blog_pages[link] = (
                    f"Author profile: {who} | posts={counted}"
                    + (f" | latest={_lat}" if (_lat := _best_year(link, cached)) else "")
                    + "\n"
                    + visible_text(cached, about_max_chars,
                                   strip_footer=strip_footer,
                                   strip_testimonials=strip_testimonials))

        wanted = [] if _out_of_time("author profiles", ARCHIVE_GRACE_SECONDS) else \
            [(who, link) for who, link in candidates
             if link not in blog_html_by_url][:_MAX_AUTHOR_PAGES]
        if wanted:
            grace_deadline = deadline + ARCHIVE_GRACE_SECONDS if deadline else None
            bios = await asyncio.gather(
                *[fetch(client, link, sem, deadline=grace_deadline)
                  for _, link in wanted])
            for (who, link), bio_html in zip(wanted, bios):
                if not bio_html:
                    continue
                blog_html_by_url[link] = bio_html
                counted = extract_author_activity(bio_html, link)
                blog_pages[link] = (
                    f"Author profile: {who}"
                    + (f" | posts={counted}" if counted else "")
                    + (f" | latest={_lat}" if (_lat := _best_year(link, bio_html)) else "")
                    + "\n"
                    + visible_text(bio_html, about_max_chars, strip_footer=strip_footer,
                                   strip_testimonials=strip_testimonials))
            logger.info("fetched %d author profile pages", len(wanted))

        if len(author_pages) < ENOUGH_AUTHORS and not _out_of_time("author index"):
            known = set(author_pages.values())
            index_profiles = [u for u in await discover_author_pages(client, sem, url, index_url)
                              if u not in known]

        # A slug is not a name. WordPress derives an author slug from the
        # account's email when no display name is set, so /author/devrevnix-com/
        # is dev@revnix.com and /author/huzaifa-revnixgmail-com/ is
        # huzaifa.revnix@gmail.com. Title-casing those produced "Devrevnix Com"
        # and "Huzaifa Revnixgmail Com" as personas on wpaegis.com. The page
        # itself carries the person's real display name, so it is fetched first
        # and the name read from it; a profile whose real name cannot be read is
        # skipped rather than guessed at.
        if index_profiles and not _out_of_time("author index"):
            resolved = await asyncio.gather(
                *[fetch(client, u, sem, attempts=1)
                  for u in index_profiles[:_MAX_AUTHOR_PAGES]])
            for profile_url, profile_html in zip(index_profiles, resolved):
                if not profile_html:
                    continue
                real = extract_byline(profile_html, profile_url) or ""
                if not real:
                    heading = BeautifulSoup(profile_html, "html.parser").find("h1")
                    real = re.sub(r"\s+", " ", heading.get_text(" ", strip=True)).strip() \
                        if heading else ""
                    real = re.sub(r"(?i)^(author|posts?\s+by|archives?\s+for)\s*[:\-]?\s*",
                                  "", real).strip()
                if _is_person_name(real):
                    author_pages.setdefault(real, profile_url)

        # Anything the archive pass already fetched is skipped rather than
        # requested again. Both passes draw from author_pages, so the archives
        # were being fetched twice - up to six redundant requests, enough to
        # exhaust the budget before the counting ran. That is what made post
        # counts vary between identical runs: Nouman Yaqoob returned 81 on the
        # run that had budget left and 0 on the run that did not.
        # Only so many archives fit in the budget, so the slots go to people.
        # "Editorial Staff" is a masthead, not a writer - it is rejected as a
        # persona downstream either way, and on wpbeginner.com it consumed one
        # of six slots and counted 2141 posts nobody can be credited with,
        # while Nouman Yaqoob's archive went unfetched.
        # An archive already in hand is counted from the cached markup rather
        # than skipped: holding the HTML is not the same as having counted it,
        # and treating the two as equivalent left Nouman Yaqoob's archive
        # fetched, uncounted and reported as zero.
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
        # Kept concurrent. Running the about crawl first so the blog crawl could
        # see its result was tried and rejected: serialising two independent
        # crawls costs more wall clock than the skip saves, on every site. The
        # blog crawl instead stops itself once enough authors are established -
        # see ENOUGH_AUTHORS - which achieves the same saving without the
        # barrier.
        # The fixed-path sweep runs alongside the two crawls, not after them:
        # it is a bounded set of cheap requests and it is what guarantees the
        # author archives are known regardless of what the crawl reaches.
        about_pages, blog_pages, swept = await asyncio.gather(
            _crawl_about(client), _crawl_blog(client),
            discover_people_pages(client, sem, url, deadline))
        for archive_url, label in swept.items():
            if archive_url in blog_pages or archive_url in about_pages:
                continue
            team_profile_links.setdefault(archive_url, None)
            named_author_links.add(archive_url)

    # Team profile pages, fetched after the concurrent crawls because they are
    # discovered by them.
    # This stage is not subject to the scrape budget. It is bounded to at most
    # _MAX_AUTHOR_PAGES fetches with a window of its own, and it carries the
    # signal the ranking turns on: skipping it is what left an author with 81
    # posts scored as though he had none. Letting the leftover budget decide
    # whether it ran is what made the counts differ between identical runs.
    if team_profile_links:
        async with httpx.AsyncClient(headers=headers, verify=False,
                                     follow_redirects=True) as client:
            # Sorted, not in discovery order. team_profile_links is filled by
            # concurrent fetches, so its order is whichever page returned
            # first - which made the *set* of authors differ run to run, not
            # just their counts: one run counted six writers, the next counted
            # three different ones. Sorting picks the same pages every time.
            # Author archives first. They are the only pages that state a post
            # count, and they compete with ordinary team pages for the same
            # bounded number of fetches.
            wanted = sorted((u for u in team_profile_links if u not in about_pages),
                            key=lambda u: (0 if u in named_author_links else 1,
                                           0 if _AUTHOR_PATH_RE.search(u) else 1, u)
                            )[:_MAX_AUTHOR_PAGES]
            grace_deadline = (asyncio.get_event_loop().time()
                              + ARCHIVE_GRACE_SECONDS) if deadline else None
            profile_html = await asyncio.gather(
                *[fetch(client, u, sem, attempts=POST_FETCH_ATTEMPTS,
                        deadline=grace_deadline) for u in wanted])
        # An archive fetched alongside five others sometimes comes back as a
        # reduced page: HTTP 200, real markup, no entry list. The count then
        # reads as zero and a prolific author ranks as a newcomer. Retried once
        # on its own, which is a handful of requests at most and is what makes
        # the counts repeatable rather than right two runs in three.
        retried = []
        for profile_url, html in zip(wanted, profile_html):
            # A missing date is retried as well as a missing count. The reduced
            # page that costs the count also arrives without its entry dates,
            # and recency is worth twenty points - enough to move a prolific
            # active writer between 100 and 84 between identical runs.
            if html and not (extract_author_activity(html, profile_url)
                             and extract_archive_latest_year(html)):
                retried.append(profile_url)
        if retried:
            async with httpx.AsyncClient(headers=headers, verify=False,
                                         follow_redirects=True) as client:
                lone = asyncio.Semaphore(1)
                repeats = await asyncio.gather(
                    *[fetch(client, u, lone, attempts=POST_FETCH_ATTEMPTS,
                            deadline=grace_deadline) for u in retried])
            better = {u: h for u, h in zip(retried, repeats)
                      if h and (extract_author_activity(h, u)
                                or extract_archive_latest_year(h))}
            if better:
                profile_html = [better.get(u, h)
                                for u, h in zip(wanted, profile_html)]
                logger.info("recovered %d author archive(s) on retry", len(better))

        for profile_url, html in zip(wanted, profile_html):
            if not html:
                continue
            blog_html_by_url[profile_url] = html
            # Named and counted like every other author page. This branch used
            # to write a bare "Author profile:" followed by the page text, so
            # whoever it reached arrived with no name and no post count while
            # the same person found via the archive pass arrived with both.
            # wpbeginner.com/author/syedb was reached here on some runs and by
            # the archive pass on others, which is why Syed Balkhi's count
            # alternated between 61 and nothing between identical runs.
            # The heading first. An archive page's byline block describes the
            # author in full - "Syed Balkhi CEO Awesome Motive Inc." - which is
            # correctly rejected as a name, leaving the entry unnamed; the <h1>
            # on the same page is just "Syed Balkhi".
            who = _archive_heading(html) or extract_byline(html, profile_url) or ""
            counted = extract_author_activity(html, profile_url)
            about_pages[profile_url] = (
                "Author profile:"
                + (f" {who}" if _is_person_name(who) else "")
                + (f" | posts={counted}" if counted else "")
                + (f" | latest={_lat}" if (_lat := _best_year(profile_url, html)) else "")
                + "\n"
                + visible_text(html, about_max_chars, strip_footer=strip_footer,
                               strip_testimonials=strip_testimonials))
        logger.info("fetched %d team profile pages", len(wanted))

    pages: Dict[str, str] = {url: _page_text(home_html, home_max_chars)}
    pages.update(about_pages)
    # A counted archive is never replaced by a placeholder for the same URL.
    # The blog crawl registers "X is credited as an author here" for authors it
    # cannot fetch, and merging it last overwrote the counted entry the archive
    # stage had already produced - the same person, the same URL, the measured
    # version discarded. This is what made post counts appear and disappear
    # between identical runs.
    for page_url, text in blog_pages.items():
        existing = pages.get(page_url, "")
        if " | posts=" in existing and " | posts=" not in text:
            continue
        pages[page_url] = text

    # Per-page HTML is kept alongside the text because social profile links live
    # in <a href> attributes, which visible_text() necessarily discards.
    raw_pages: Dict[str, str] = {url: home_html}
    raw_pages.update(about_html_by_url)
    raw_pages.update(blog_html_by_url)

    return {"pages": pages, "raw_home_html": home_html, "raw_pages": raw_pages}
