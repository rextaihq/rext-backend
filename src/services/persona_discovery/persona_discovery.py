import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
import httpx
import re
import json
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree
from bs4 import BeautifulSoup, Comment

# Try to import LLM model loader — fallback gracefully if not available
try:
    from src.flow.model.llm_manager import load_model
    HAS_LLM = True
except ImportError:
    HAS_LLM = False
    load_model = None

logger = logging.getLogger(__name__)
RESULTS_DIR = PROJECT_ROOT / "results"


# ============================================================================
# FILTERING CONFIGURATION
# ============================================================================

MIN_ARTICLE_YEAR = 2020  # Only articles from 2020 onwards
MAX_CRAWL_ARTICLES = 200  # Cap crawl at this (after filtering)

# ============================================================================
# CONSTANTS
# ============================================================================

SOCIAL_NETWORKS = {"twitter.com", "x.com", "linkedin.com", "github.com", "facebook.com", "instagram.com"}
MEDIA_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf",
    ".zip", ".css", ".js", ".xml", ".mp4", ".mp3", ".ico", ".woff", ".woff2"
}

NON_NAME_WORDS = {
    "admin", "administrator", "guest", "wordpress", "comment", "comments",
    "reply", "replies", "contact", "privacy", "policy", "policies", "terms",
    "service", "services", "edit", "delete", "cancel", "home", "next",
    "previous", "read", "more", "click", "here", "view", "all", "leave",
    "share", "related", "posts", "post", "subscribe", "search", "menu",
    "login", "logout", "register", "sign", "up", "down", "cookie", "cookies",
    "rights", "reserved", "author", "authors", "editor", "editorial",
    "team", "staff", "people", "writer", "writers", "contributor",
    "contributors", "profile", "user", "users", "category", "categories",
    "tag", "tags", "page", "pages", "blog", "news", "article", "articles",
    "archive", "archives", "table", "contents", "faq", "faqs", "about",
    "marketing", "digital", "content", "seo", "sem", "ppc", "b2b", "b2c",
    "agency", "agencies", "strategy", "strategies", "case", "study",
    "studies", "resources", "resource", "insights", "insight", "guide",
    "guides", "tips", "tricks", "tutorial", "tutorials", "review", "reviews",
    "download", "downloads", "free", "trial", "signup", "newsletter",
    "welcome", "learn", "explore", "discover", "get", "started", "the",
    "and", "for", "with", "our", "your", "we", "us", "inc", "llc", "ltd",
    "link", "links", "building", "outreach", "backlink", "backlinks",
    "keyword", "keywords", "ranking", "rankings", "analytics", "traffic",
    "conversion", "conversions", "audit", "audits", "campaign", "campaigns",
    "solutions", "solution", "growth", "optimization", "optimisation",
    "cutest", "bark", "ever", "dog", "cat", "pet", "animal",
    "wonderful", "amazing", "awesome", "great", "good", "best",
    "image", "photo", "picture", "avatar", "gravatar",
}

UI_NOISE_PATTERNS = [
    r"^go\s+to\s+the\s+next", r"^next\s+page", r"^previous\s+page",
    r"^read\s+more", r"^click\s+here", r"^view\s+all", r"^leave\s+a\s+reply",
    r"^privacy\s+policy", r"^terms\s+of\s+service", r"^contact\s+us",
    r"^table\s+of\s+contents", r"^share\s+this", r"^related\s+posts",
    r"^subscribe", r"^search",
]

HUB_PATH_HINTS = ("about", "team", "staff", "people", "author", "writer",
                   "writers", "profile", "contributor", "contributors", "meet")
ARTICLE_PATH_HINTS = ("/blog/", "/news/", "/article", "/post/", "/posts/",
                       "/insights/", "/resources/", "/guide", "/tips/",
                       "/story/", "/stories/")
ARTICLE_DATE_PATTERN = re.compile(r"/\d{4}/\d{1,2}/")

STANDARD_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_SAMPLE_ARTICLES_PER_PERSONA = 3
MAX_SNIPPET_CHARS = 1500
CRAWL_CONCURRENCY = 9
REQUEST_TIMEOUT = 5  # Fail fast on slow servers
RETRY_BACKOFF = 0.5  # Don't wait long between retries

LISTING_ROOT_NAMES = {h.strip("/") for h in ARTICLE_PATH_HINTS}

# ============================================================================
# REGISTRY KEY MANAGEMENT
# ============================================================================

def make_registry_key(name: str) -> str:
    """Create canonical lowercase registry key."""
    if not name or not isinstance(name, str):
        return ""
    key = name.lower().strip()
    key = re.sub(r'[^\w\s\-]', '', key)
    key = re.sub(r'\s+', ' ', key).strip()
    return key


def normalize_persona_name(name: str) -> str:
    """Clean raw text into display form."""
    if not name or not isinstance(name, str):
        return ""
    clean = re.sub(r'^(?:the|about|by|written by|posted by|author:?)\s+', '', name.strip(), flags=re.I)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean.title()


def get_name_variants_for_matching(full_name: str) -> set:
    """Generate registry keys for all variants."""
    if not full_name or not isinstance(full_name, str):
        return set()
    
    full_name = full_name.strip()
    variants = {full_name}
    
    parts = full_name.split()
    for part in parts:
        if len(part) > 2:
            variants.add(part)
    
    if len(parts) >= 2:
        variants.add(f"{parts[0]} {parts[-1]}")
    
    return {make_registry_key(v) for v in variants}


def find_existing_person_key(new_name: str, existing_keys: set) -> str | None:
    """Find if person already exists in registry by variant matching."""
    if not new_name:
        return None
    
    new_key = make_registry_key(new_name)
    new_variants = get_name_variants_for_matching(new_name)
    
    for existing_key in existing_keys:
        if existing_key in new_variants:
            return existing_key
        existing_variants = get_name_variants_for_matching(existing_key)
        if new_key in existing_variants or (existing_variants & new_variants):
            return existing_key
    
    return None


def is_valid_person_name(raw_name: str, base_domain: str, strict: bool = True) -> bool:
    """Validate if text is plausibly a real person name."""
    if not raw_name or not isinstance(raw_name, str):
        return False

    original = raw_name.strip()
    if not original:
        return False

    if original.isupper() and len(original.split()) <= 2:
        return False

    clean = normalize_persona_name(original)
    
    if len(clean) < 3 or len(clean) > 45:
        return False

    clean_lower = clean.lower()
    
    domain_root = base_domain.replace("www.", "").split(".")[0].lower()
    if domain_root and len(domain_root) > 2 and domain_root in clean_lower.replace(" ", ""):
        return False

    for pat in UI_NOISE_PATTERNS:
        if re.search(pat, clean_lower):
            return False

    if re.search(r'[\d<>{}\[\]\\/@_#=$%^*+;:"\']', clean):
        return False

    words = clean.split()
    min_words, max_words = (1, 5) if not strict else (2, 4)
    if not (min_words <= len(words) <= max_words):
        return False

    for w in words:
        w_bare = w.strip(".-'").lower()
        if w_bare in NON_NAME_WORDS:
            return False
        if len(w_bare) < 2 and w_bare not in {"a", "j", "k"}:
            return False

    return True


# ============================================================================
# URL CLASSIFICATION
# ============================================================================

def is_valid_html_url(url: str) -> bool:
    """Reject media extensions."""
    path = urlparse(url).path.lower()
    return not any(path.endswith(ext) for ext in MEDIA_EXTENSIONS)


def is_personal_social_link(url: str, base_domain: str) -> bool:
    """Validate personal social profile."""
    if not url or not isinstance(url, str):
        return False
    url_lower = url.lower()
    if any(pat in url_lower for pat in ["sharer", "sharearticle", "intent/tweet", "display=popup"]):
        return False
    netloc = urlparse(url).netloc.lower()
    if not any(domain in netloc for domain in SOCIAL_NETWORKS):
        return False
    site_handle = base_domain.replace("www.", "").split(".")[0]
    if f"/{site_handle}" in url_lower:
        return False
    return True


def is_listing_root(url: str) -> bool:
    """True for /blog/, /news/ index pages."""
    path = urlparse(url).path.strip("/").lower()
    segments = path.split("/") if path else []
    return len(segments) == 1 and segments[0] in LISTING_ROOT_NAMES


def classify_url(url: str) -> str:
    """Classify: 'hub', 'listing', 'article', or 'unknown'."""
    if is_listing_root(url):
        return "listing"
    path = urlparse(url).path.lower()
    if any(f"/{h}" in path or path.strip("/") == h for h in HUB_PATH_HINTS):
        return "hub"
    if any(hint in path for hint in ARTICLE_PATH_HINTS) or ARTICLE_DATE_PATTERN.search(path):
        return "article"
    return "unknown"


# ============================================================================
# DATE EXTRACTION — Filter old articles
# ============================================================================

def extract_date_from_url(url: str) -> tuple[int, int, int] | None:
    match = re.search(r'/(\d{4})/(\d{1,2})(?:/(\d{1,2}))?/', url)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3)) if match.group(3) else 1
        return (year, month, day)
    return None


def is_article_recent(url: str, min_year: int = 2020) -> bool:
    date_tuple = extract_date_from_url(url)
    if date_tuple is None:
        return True
    year, month, day = date_tuple
    return year >= min_year


# ============================================================================
# EXTRACTION (HIGH → MEDIUM → LOW CONFIDENCE)
# ============================================================================

def _strip_non_content(soup: BeautifulSoup) -> None:
    for node in soup.select("#comments, .comments-area, .comment-list, "
                             "#disqus_thread, .responses, .trackbacks, "
                             "footer.comment-meta, nav, footer"):
        node.decompose()
    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()


def extract_json_ld_personas(soup: BeautifulSoup, base_domain: str) -> list[dict]:
    found = []
    for script in soup.find_all("script", type=re.compile(r"application/ld\+json", re.I)):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            continue
        nodes = data if isinstance(data, list) else [data]

        def make_entry(name, job_title=None, description=None, email=None, same_as=None):
            socials = same_as if isinstance(same_as, list) else [same_as] if same_as else []
            return {
                "name": normalize_persona_name(name),
                "role": job_title,
                "bio": description,
                "email": email,
                "same_as": [s for s in socials if is_personal_social_link(s, base_domain)],
                "source": "schema_json_ld",
                "confidence": "high",
            }

        def traverse(node):
            if not isinstance(node, dict):
                return
            if node.get("@type") == "Person" and is_valid_person_name(node.get("name", ""), base_domain, strict=False):
                found.append(make_entry(
                    node["name"], 
                    node.get("jobTitle"),
                    node.get("description"),
                    node.get("email"), 
                    node.get("sameAs")
                ))
            if "author" in node:
                authors = node["author"] if isinstance(node["author"], list) else [node["author"]]
                for a in authors:
                    if isinstance(a, dict) and is_valid_person_name(a.get("name", ""), base_domain, strict=False):
                        found.append(make_entry(a["name"], a.get("jobTitle"), a.get("description"),
                                                 a.get("email"), a.get("sameAs")))
                    elif isinstance(a, str) and is_valid_person_name(a, base_domain, strict=False):
                        found.append(make_entry(a))
            if isinstance(node.get("@graph"), list):
                for child in node["@graph"]:
                    traverse(child)

        for n in nodes:
            traverse(n)
    return found


def extract_meta_tag_personas(soup: BeautifulSoup, base_domain: str) -> list[dict]:
    found = []
    meta_selectors = [
        "meta[name='author']", "meta[property='article:author']",
        "meta[name='dc.creator']", "meta[name='twitter:creator']",
    ]
    for sel in meta_selectors:
        el = soup.select_one(sel)
        if el and el.get("content") and is_valid_person_name(el["content"], base_domain, strict=False):
            found.append({
                "name": normalize_persona_name(el["content"]),
                "role": None, "bio": None, "email": None, "same_as": [],
                "source": "meta_tag", "confidence": "high",
            })
    return found


def extract_microformat_personas(soup: BeautifulSoup, base_domain: str) -> list[dict]:
    found = []
    elements = soup.find_all(attrs={"rel": re.compile(r"\bauthor\b", re.I)}) + \
        soup.find_all(attrs={"itemprop": "author"})
    for el in elements:
        text = el.get_text()
        if is_valid_person_name(text, base_domain, strict=True):
            found.append({
                "name": normalize_persona_name(text),
                "role": None, "bio": None, "email": None,
                "same_as": [el["href"]] if el.has_attr("href") and is_personal_social_link(el["href"], base_domain) else [],
                "source": "w3c_microformat", "confidence": "medium",
            })
    return found


BYLINE_PATTERNS = [
    re.compile(r"\bby\s+([A-Z][a-zA-Z.\-']+(?:\s+[A-Z][a-zA-Z.\-']+){1,3})\b"),
    re.compile(r"\b(?:written|posted|authored)\s+by\s+([A-Z][a-zA-Z.\-']+(?:\s+[A-Z][a-zA-Z.\-']+){1,3})\b", re.I),
]


def extract_byline_regex_personas(soup: BeautifulSoup, base_domain: str) -> list[dict]:
    scope = soup.find("article") or soup.find("main") or soup
    text = scope.get_text(separator=" ", strip=True)
    head = text[:600]
    tail = text[-800:]
    found = []
    for chunk in (head, tail):
        for pattern in BYLINE_PATTERNS:
            m = pattern.search(chunk)
            if m and is_valid_person_name(m.group(1), base_domain, strict=True):
                found.append({
                    "name": normalize_persona_name(m.group(1)),
                    "role": None, "bio": None, "email": None, "same_as": [],
                    "source": "byline_text_pattern", "confidence": "medium",
                })
    return found


def extract_semantic_anchor_personas(soup: BeautifulSoup, base_domain: str) -> list[dict]:
    found = []
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if any(seg in href for seg in ("/author/", "/writer/", "/profile/", "/contributor/")):
            text = a.get_text()
            if is_valid_person_name(text, base_domain, strict=True):
                found.append({
                    "name": normalize_persona_name(text),
                    "role": None, "bio": None, "email": None, "same_as": [],
                    "source": "semantic_author_anchor", "confidence": "low",
                })
    return found


def extract_personas_from_page(html: str, base_domain: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    _strip_non_content(soup)

    high = extract_json_ld_personas(soup, base_domain) + extract_meta_tag_personas(soup, base_domain)
    if high:
        return _dedupe_on_page(high)

    medium = extract_microformat_personas(soup, base_domain) + extract_byline_regex_personas(soup, base_domain)
    if medium:
        return _dedupe_on_page(medium)

    low = extract_semantic_anchor_personas(soup, base_domain)
    return _dedupe_on_page(low)


def extract_team_members_from_page(html: str, base_domain: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    _strip_non_content(soup)
    
    found = []
    team_cards = soup.select(".team-member, .staff-member, .team-card, "
                              "[class*='team'], [class*='staff'], "
                              "li.member, div.profile")
    
    for card in team_cards[:20]:
        name_el = card.select_one("h3, h4, .name, [class*='name']")
        name = name_el.get_text(strip=True) if name_el else None
        
        if not name or not is_valid_person_name(name, base_domain, strict=False):
            continue
        
        role_el = card.select_one(".role, .title, .position, [class*='role']")
        role = role_el.get_text(strip=True) if role_el else None
        
        bio_el = card.select_one(".bio, .description, p")
        bio = bio_el.get_text(strip=True) if bio_el else None
        
        socials = []
        for a in card.find_all("a", href=True):
            href = a["href"]
            if is_personal_social_link(href, base_domain):
                socials.append(href)
        
        found.append({
            "name": normalize_persona_name(name),
            "role": role,
            "bio": bio,
            "email": None,
            "same_as": socials,
            "source": "team_page_markup",
            "confidence": "high",
            "is_team_member": True,
        })
    
    return found


def _dedupe_on_page(personas: list[dict]) -> list[dict]:
    unique = {}
    for p in personas:
        key = make_registry_key(p["name"])
        if key not in unique:
            unique[key] = p
    return list(unique.values())


def get_main_content_snippet(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    _strip_non_content(soup)
    scope = soup.find("article") or soup.find("main") or soup.find("body") or soup
    text = scope.get_text(separator=" ", strip=True)
    return text[:MAX_SNIPPET_CHARS]


# ============================================================================
# DISCOVERY
# ============================================================================

def _local_tag(elem) -> str:
    return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag


async def get_robots_sitemaps(base_url: str, client: httpx.AsyncClient) -> list[str]:
    sitemaps = []
    try:
        resp = await client.get(urljoin(base_url, "/robots.txt"), 
                                headers=STANDARD_BROWSER_HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            sitemaps = re.findall(r"(?im)^sitemap:\s*(\S+)", resp.text)
    except Exception as e:
        logger.debug(f"robots.txt: {e}")
    if not sitemaps:
        sitemaps = [urljoin(base_url, "/sitemap.xml")]
    return sitemaps


async def parse_sitemap_recursive(url: str, client: httpx.AsyncClient, depth: int = 0,
                                   seen: set | None = None, max_urls: int = 5000) -> list[str]:
    if seen is None:
        seen = set()
    if url in seen or depth > 2 or len(seen) >= max_urls:
        return []
    seen.add(url)

    try:
        resp = await client.get(url, headers=STANDARD_BROWSER_HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return []
        root = ElementTree.fromstring(resp.content)
    except Exception as e:
        logger.debug(f"Sitemap parse: {e}")
        return []

    root_tag = _local_tag(root)
    collected = []

    if root_tag == "sitemapindex":
        child_sitemaps = [loc.text.strip() for sm in root for loc in sm if _local_tag(loc) == "loc" and loc.text]
        results = await asyncio.gather(*[
            parse_sitemap_recursive(sm_url, client, depth + 1, seen, max_urls)
            for sm_url in child_sitemaps
        ])
        for r in results:
            collected.extend(r)
    elif root_tag == "urlset":
        for u in root:
            loc = next((c for c in u if _local_tag(c) == "loc"), None)
            if loc is not None and loc.text:
                collected.append(loc.text.strip())

    return collected[:max_urls]


async def discover_target_urls(base_url: str, client: httpx.AsyncClient) -> tuple[list[str], list[str]]:
    base_domain = urlparse(base_url).netloc
    hub_urls, article_urls, listing_roots = set(), set(), set()

    try:
        resp = await client.get(base_url, headers=STANDARD_BROWSER_HEADERS, timeout=REQUEST_TIMEOUT)
        print(f"  [homepage] HTTP {resp.status_code}")
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")

            feed_link = soup.select_one("link[type*='rss'], link[type*='atom']")
            if feed_link and feed_link.get("href"):
                feed_url = urljoin(base_url, feed_link["href"])
                try:
                    f_resp = await client.get(feed_url, headers=STANDARD_BROWSER_HEADERS, timeout=REQUEST_TIMEOUT)
                    if f_resp.status_code == 200:
                        feed_xml = ElementTree.fromstring(f_resp.content)
                        for item in feed_xml.iter("item"):
                            link_el = item.find("link")
                            if link_el is not None and link_el.text:
                                article_urls.add(link_el.text.strip())
                except Exception:
                    pass

            for a in soup.find_all("a", href=True):
                full_url = urljoin(base_url, a["href"].strip())
                if urlparse(full_url).netloc != base_domain or not is_valid_html_url(full_url):
                    continue
                kind = classify_url(full_url)
                if kind == "listing":
                    listing_roots.add(full_url)
                elif kind == "hub":
                    hub_urls.add(full_url)
                elif kind == "article":
                    article_urls.add(full_url)
            print(f"  [homepage] hub:{len(hub_urls)} listing:{len(listing_roots)} article:{len(article_urls)}")
    except Exception as e:
        print(f"  [homepage] EXCEPTION: {e!r}")

    for sitemap_url in await get_robots_sitemaps(base_url, client):
        sitemap_result = await parse_sitemap_recursive(sitemap_url, client, max_urls=5000)
        print(f"  [sitemap] {len(sitemap_result)} URLs")
        for u in sitemap_result:
            if urlparse(u).netloc != base_domain or not is_valid_html_url(u):
                continue
            kind = classify_url(u)
            if kind == "listing":
                listing_roots.add(u)
            elif kind == "hub":
                hub_urls.add(u)
            else:
                article_urls.add(u)

    print(f"  [pagination] SKIPPED (sitemap/nav already covers active authors)")

    return list(hub_urls), list(article_urls)


# ============================================================================
# FETCHING WITH RETRY
# ============================================================================

async def fetch_and_extract(client: httpx.AsyncClient, url: str, base_domain: str,
                             semaphore: asyncio.Semaphore, retry: int = 3) -> tuple[str, str, list[dict], str]:
    async with semaphore:
        for attempt in range(retry):
            try:
                resp = await client.get(url, headers=STANDARD_BROWSER_HEADERS, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    personas = extract_personas_from_page(resp.text, base_domain)
                    snippet = get_main_content_snippet(resp.text)
                    return url, classify_url(url), personas, snippet
                elif resp.status_code == 429:
                    wait_time = (RETRY_BACKOFF ** attempt)
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    break
            except Exception as e:
                logger.debug(f"Fetch attempt {attempt + 1} failed: {e}")
                if attempt < retry - 1:
                    await asyncio.sleep(RETRY_BACKOFF ** attempt)
    return url, "unknown", [], ""


# ============================================================================
# LLM ANALYSIS — TONE & EXPERTISE
# ============================================================================

async def analyze_persona_with_llm(model, name: str, samples: list[tuple[str, str]]) -> dict:
    if not samples:
        return {"tone_and_vocabulary": None, "expertise_topics": None}

    combined = "\n\n---\n\n".join(f"[Source: {url}]\n{text}" for url, text in samples if text)
    if not combined.strip():
        return {"tone_and_vocabulary": None, "expertise_topics": None}

    prompt = (
        f"Analyze the writing of {name} based on these real article excerpts:\n\n"
        f"{combined}\n\n"
        f"Respond with ONLY a JSON object (no markdown, no preamble) with these exact two keys:\n"
        f'{{"tone_and_vocabulary": "1-2 sentences describing their writing tone and vocabulary level",\n'
        f'"expertise_topics": "1-2 sentences describing their subject-matter expertise"}}\n\n'
        f"If excerpts are too short to judge, use null. Do not guess."
    )
    
    try:
        if hasattr(model, 'ainvoke'):
            resp = await model.ainvoke(prompt)
            raw = resp.content.strip() if hasattr(resp, 'content') else str(resp).strip()
        else:
            resp = model.invoke(prompt)
            raw = resp.content.strip() if hasattr(resp, 'content') else str(resp).strip()
        
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
        return {
            "tone_and_vocabulary": parsed.get("tone_and_vocabulary") or None,
            "expertise_topics": parsed.get("expertise_topics") or None,
        }
    except Exception as e:
        logger.debug(f"LLM analysis failed for {name}: {e}")
        return {"tone_and_vocabulary": None, "expertise_topics": None}


# ============================================================================
# MASTER PIPELINE
# ============================================================================

async def run_pipeline(base_url: str, max_articles: int = MAX_CRAWL_ARTICLES) -> dict:
    base_domain = urlparse(base_url).netloc
    print("\n" + "=" * 80)
    print(f"AUTHOR DISCOVERY PIPELINE v2.3 (COMPLETE): {base_url}")
    print(f"Mode: {'Crawl ALL articles' if max_articles is None else f'Limit to {max_articles} articles'}")
    print("=" * 80)

    registry: dict[str, dict] = {}
    semaphore = asyncio.Semaphore(2)

    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    async with httpx.AsyncClient(limits=limits, follow_redirects=True, verify=False) as client:
        print("\n[PHASE 1] Discovering hub + article URLs...")
        hub_urls, article_urls = await discover_target_urls(base_url, client)

        print(f"  [filter] Filtering articles older than year {MIN_ARTICLE_YEAR}...")
        recent_article_urls = [u for u in article_urls if is_article_recent(u, MIN_ARTICLE_YEAR)]
        print(f"  [filter] Filtered: {len(article_urls)} → {len(recent_article_urls)} recent articles ({MIN_ARTICLE_YEAR}+)")

        if max_articles is not None and len(recent_article_urls) > max_articles:
            recent_article_urls = recent_article_urls[:max_articles]
            print(f"  [cap] Capped article crawl at {max_articles}")

        print(f"  Hub: {len(hub_urls)}  |  Articles: {len(recent_article_urls)}")
        all_targets = list(set(hub_urls + recent_article_urls))
        
        print(f"\n[PHASE 2] Crawling {len(all_targets)} targets (hubs + articles)...")

        tasks = [
            fetch_and_extract(client, url, base_domain, semaphore)
            for url in all_targets
        ]
        
        completed = 0
        chunk_size = 50
        for i in range(0, len(tasks), chunk_size):
            chunk = tasks[i:i + chunk_size]
            results = await asyncio.gather(*chunk)
            completed += len(chunk)
            print(f"  Progress: {completed}/{len(tasks)} URLs processed...")

            for url, kind, personas, snippet in results:
                # 1. Store team member info if found on hub/team pages
                if kind == "hub":
                    team_members = extract_team_members_from_page(snippet, base_domain)
                    for tm in team_members:
                        name = tm["name"]
                        reg_key = make_registry_key(name)
                        if not reg_key:
                            continue
                        
                        existing_key = find_existing_person_key(name, registry.keys())
                        target_key = existing_key if existing_key else reg_key

                        if target_key not in registry:
                            registry[target_key] = {
                                "role": tm.get("role"),
                                "bio": tm.get("bio"),
                                "email": tm.get("email"),
                                "same_as": list(tm.get("same_as", [])),
                                "sample_articles": [],
                                "sources": {tm.get("source", "team_page")}
                            }
                        else:
                            entry = registry[target_key]
                            if not entry.get("role") and tm.get("role"):
                                entry["role"] = tm.get("role")
                            if not entry.get("bio") and tm.get("bio"):
                                entry["bio"] = tm.get("bio")
                            if not entry.get("email") and tm.get("email"):
                                entry["email"] = tm.get("email")
                            for s in tm.get("same_as", []):
                                if s not in entry["same_as"]:
                                    entry["same_as"].append(s)

                # 2. Process author personas from articles/hubs
                for p in personas:
                    name = p["name"]
                    reg_key = make_registry_key(name)
                    if not reg_key:
                        continue

                    existing_key = find_existing_person_key(name, registry.keys())
                    target_key = existing_key if existing_key else reg_key

                    if target_key not in registry:
                        registry[target_key] = {
                            "role": p.get("role"),
                            "bio": p.get("bio"),
                            "email": p.get("email"),
                            "same_as": list(p.get("same_as", [])),
                            "sample_articles": [],
                            "sources": {p.get("source", "unknown")}
                        }
                    else:
                        entry = registry[target_key]
                        if not entry.get("role") and p.get("role"):
                            entry["role"] = p.get("role")
                        if not entry.get("bio") and p.get("bio"):
                            entry["bio"] = p.get("bio")
                        if not entry.get("email") and p.get("email"):
                            entry["email"] = p.get("email")
                        for s in p.get("same_as", []):
                            if s not in entry["same_as"]:
                                entry["same_as"].append(s)
                        entry["sources"].add(p.get("source", "unknown"))

                    if kind == "article" and snippet and len(registry[target_key]["sample_articles"]) < MAX_SAMPLE_ARTICLES_PER_PERSONA:
                        registry[target_key]["sample_articles"].append((url, snippet))

        # 3. LLM Analysis Phase
        print(f"\n[PHASE 3] Running LLM analysis on {len(registry)} discovered personas...")
        model = None
        if HAS_LLM:
            try:
                model = load_model()
                print("  [LLM] Model loaded successfully.")
            except Exception as e:
                print(f"  [LLM] Failed to load model: {e}")
                model = None
        else:
            print("  [LLM] LLM not available; skipping style/expertise analysis.")

        final_output = []
        for reg_key, data in registry.items():
            display_name = normalize_persona_name(reg_key.replace("-", " "))
            
            tone_vocab = None
            expertise = None

            if model is not None and data["sample_articles"]:
                print(f"  Analyzing tone/expertise for: {display_name}...")
                analysis = await analyze_persona_with_llm(model, display_name, data["sample_articles"])
                tone_vocab = analysis.get("tone_and_vocabulary")
                expertise = analysis.get("expertise_topics")

            final_output.append({
                "name": display_name,
                "role": data.get("role"),
                "bio": data.get("bio"),
                "email": data.get("email"),
                "same_as": data.get("same_as", []),
                "tone_and_vocabulary": tone_vocab,
                "expertise_topics": expertise,
                "sources": list(data["sources"])
            })

        result = {
            "base_url": base_url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_personas_found": len(final_output),
            "authors_and_team": final_output
        }

        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        out_file = RESULTS_DIR / f"{base_domain.replace('.', '_')}_authors.json"
        out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n[Done] Saved {len(final_output)} personas to {out_file}")
        return result


