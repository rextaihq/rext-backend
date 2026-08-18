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
import re
from typing import Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
import tldextract
from bs4 import BeautifulSoup

from src.utils.url_validator import validate_url_for_ssrf

USER_AGENT = "Mozilla/5.0 (compatible; RextBot/1.0)"
CONCURRENCY = 10
REQUEST_TIMEOUT = 10

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
_TAXONOMY_SEGMENTS = {"page", "category", "tag", "author"}
# How many blog/news-keyword-matching links to consider before picking the index —
# see the shortest-path selection in scrape_site() for why more than 1 is needed.
_BLOG_INDEX_CANDIDATES = 5

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


def _domain(url: str) -> str:
    ext = tldextract.extract(url)
    return ".".join(p for p in [ext.domain, ext.suffix] if p)


def visible_text(html: str, max_chars: Optional[int] = 3000, *, strip_footer: bool = True) -> str:
    """`max_chars=None` returns the full extracted text, untruncated."""
    soup = BeautifulSoup(html, "html.parser")
    strip_tags = ["script", "style", "noscript", "svg", "header", "nav"]
    if strip_footer:
        strip_tags.append("footer")
    for tag in soup(strip_tags):
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


def find_internal_links(html: str, base_url: str, keywords: Iterable[str], limit: int) -> List[str]:
    """Links on `html` whose path matches one of `keywords`, same-domain only."""
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
        if any(k in path for k in keywords):
            candidates.append(href.split("#")[0])
    seen, out = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:limit]


def _find_post_links(index_html: str, index_url: str, limit: int) -> List[str]:
    """Individual post links from a blog/news index page.

    Heuristic: same-domain links one path segment deeper than the index itself
    (index `/blog` -> post `/blog/<slug>`), excluding pagination/taxonomy noise.
    Takes the first `limit` in page order (blog templates are almost always
    newest-first, but this isn't guaranteed for every site).
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
        if not path.startswith(index_path + "/"):
            continue
        segments = [s for s in path[len(index_path) + 1:].split("/") if s]
        if not segments or any(seg in _TAXONOMY_SEGMENTS for seg in segments):
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


async def _fetch_sitemap_post_urls(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, base_url: str, index_url: str,
) -> List[str]:
    """Best-effort: every blog/news post URL under `index_url`'s path, from
    sitemap.xml — not just the recent ones a paginated index page shows.

    Handles both a flat sitemap (loc entries are pages) and a sitemap *index*
    (loc entries are other .xml files, common with WordPress/Yoast) by
    following up to 5 sub-sitemaps one level deep. Returns [] on any failure
    — this is a supplementary source, never required.
    """
    try:
        xml = await _fetch_xml(client, urljoin(base_url, "/sitemap.xml"), sem)
        if not xml:
            return []
        locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", xml)
        if locs and all(l.lower().endswith(".xml") for l in locs):
            sub_xmls = await asyncio.gather(*[_fetch_xml(client, l, sem) for l in locs[:5]])
            locs = [l for x in sub_xmls if x for l in re.findall(r"<loc>\s*(.*?)\s*</loc>", x)]

        domain = _domain(base_url)
        index_path = urlparse(index_url).path.rstrip("/")
        posts, seen = [], set()
        for loc in locs:
            if _domain(loc) != domain:
                continue
            path = urlparse(loc).path.rstrip("/")
            if not path.startswith(index_path + "/"):
                continue
            segments = [s for s in path[len(index_path) + 1:].split("/") if s]
            if not segments or any(seg in _TAXONOMY_SEGMENTS for seg in segments):
                continue
            clean = loc.split("#")[0].split("?")[0]
            if clean not in seen:
                seen.add(clean)
                posts.append(clean)
        return posts
    except Exception:
        return []


async def fetch(client: httpx.AsyncClient, url: str, sem: asyncio.Semaphore) -> str:
    try:
        async with sem:
            resp = await client.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
                return resp.text
    except Exception:
        pass
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

    def _page_text(html: str, max_chars: int) -> str:
        if sample_head_and_tail:
            return _head_tail(visible_text(html, None, strip_footer=strip_footer), max_chars)
        return visible_text(html, max_chars, strip_footer=strip_footer)

    async def _crawl_about(client: httpx.AsyncClient) -> Dict[str, str]:
        links = find_internal_links(home_html, url, about_keywords, max_about_pages)
        html_list = await asyncio.gather(*[fetch(client, link, sem) for link in links])
        return {
            link: visible_text(html, about_max_chars, strip_footer=strip_footer)
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
        index_url = min(candidates, key=lambda u: len(urlparse(u).path))

        index_html = await fetch(client, index_url, sem)
        if not index_html:
            return {}
        blog_pages = {index_url: visible_text(index_html, blog_index_max_chars, strip_footer=strip_footer)}

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

        sitemap_urls = await _fetch_sitemap_post_urls(client, sem, url, index_url)
        signal_ranked = sorted(
            (u for u in sitemap_urls if u not in recent_links),
            key=_persona_signal_score, reverse=True,
        )
        signal_links = [u for u in signal_ranked if _persona_signal_score(u) > 0][: max_blog_posts - len(recent_links)]

        post_links = list(dict.fromkeys(recent_links + signal_links))
        if not post_links:
            return blog_pages
        post_html_list = await asyncio.gather(*[fetch(client, link, sem) for link in post_links])
        for post_url, post_html in zip(post_links, post_html_list):
            if post_html:
                blog_pages[post_url] = _page_text(post_html, blog_post_max_chars)
        return blog_pages

    async with httpx.AsyncClient(headers=headers, verify=False, follow_redirects=True) as client:
        home_html = await fetch(client, url, sem)
        if not home_html:
            return {"pages": {}, "raw_home_html": ""}

        # About/product/team pages and the blog/news crawl are independent —
        # run them concurrently rather than staged one after the other.
        about_pages, blog_pages = await asyncio.gather(_crawl_about(client), _crawl_blog(client))

    pages: Dict[str, str] = {url: _page_text(home_html, home_max_chars)}
    pages.update(about_pages)
    pages.update(blog_pages)

    return {"pages": pages, "raw_home_html": home_html}
