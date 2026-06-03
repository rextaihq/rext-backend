from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.flow.model.structure.eeat import EEATTrustScore

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 4096
MAX_PROMPT_TEXT_CHARS = 16000
RUBRIC_VERSION = "content-eeat-2026-06"

YMYL_TOPIC_TERMS = (
    "medical",
    "medicine",
    "health",
    "symptom",
    "diagnosis",
    "treatment",
    "drug",
    "finance",
    "financial",
    "investment",
    "loan",
    "tax",
    "insurance",
    "legal",
    "lawyer",
    "attorney",
    "safety",
    "emergency",
)

TRANSPARENCY_TERMS = (
    "about the author",
    "author bio",
    "disclosure",
    "affiliate",
    "sponsored",
    "editorial policy",
    "methodology",
    "how we tested",
    "how this was created",
    "ai disclosure",
    "sources",
    "references",
    "reviewed by",
    "edited by",
    "updated",
    "correction",
    "limitations",
)

EXPERIENCE_ACTION_TERMS = (
    "tested",
    "used",
    "built",
    "implemented",
    "measured",
    "compared",
    "reviewed",
    "visited",
    "observed",
    "deployed",
    "shipped",
    "interviewed",
)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, value))


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def tokenize_words(text: str) -> List[str]:
    return re.findall(r"\b[\w'-]+\b", text or "", flags=re.UNICODE)


def to_plain_data(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return to_plain_data(value.model_dump())
    if isinstance(value, Mapping):
        return {str(k): to_plain_data(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_plain_data(item) for item in value]
    return value


def as_mapping(value: Any) -> Dict[str, Any]:
    value = to_plain_data(value)
    return dict(value) if isinstance(value, Mapping) else {}


def as_list(value: Any) -> List[Any]:
    value = to_plain_data(value)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def safe_json_loads(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def safe_domain(url: str) -> str:
    try:
        domain = (urlparse(url).netloc or "").lower()
    except Exception:
        return ""
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def is_external_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_https_url(url: str) -> bool:
    try:
        return urlparse(url).scheme == "https"
    except Exception:
        return False


def unique_non_empty(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        text = normalize_whitespace(str(value or ""))
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _parse_jsonld_value(value: Any) -> Any:
    value = to_plain_data(value)
    if isinstance(value, str):
        parsed = safe_json_loads(value)
        return parsed if parsed is not None else value
    return value


def iter_jsonld_nodes(value: Any) -> Iterable[Dict[str, Any]]:
    value = _parse_jsonld_value(value)
    if isinstance(value, list):
        for item in value:
            yield from iter_jsonld_nodes(item)
        return
    if not isinstance(value, Mapping):
        return

    node = dict(value)
    yield node

    graph = node.get("@graph")
    if graph:
        yield from iter_jsonld_nodes(graph)


def extract_json_ld_blocks(
    soup: BeautifulSoup, metadata: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []

    for script in soup.find_all("script"):
        script_type = (script.get("type") or "").lower()
        if "ld+json" not in script_type:
            continue
        parsed = safe_json_loads(script.get_text(" ", strip=True))
        if parsed is None:
            continue
        blocks.extend(iter_jsonld_nodes(parsed))

    schema_markup = as_mapping(metadata or {}).get("schema_markup")
    schema_data = (
        schema_markup.get("schema_data") if isinstance(schema_markup, Mapping) else schema_markup
    )
    if schema_data:
        blocks.extend(iter_jsonld_nodes(schema_data))

    return blocks


def _jsonld_types(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)] if value else []


def _collect_names(value: Any) -> List[str]:
    value = _parse_jsonld_value(value)
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        names: List[str] = []
        for item in value:
            names.extend(_collect_names(item))
        return names
    if isinstance(value, Mapping):
        name = value.get("name")
        if name:
            return [str(name)]
        given = value.get("givenName")
        family = value.get("familyName")
        full = normalize_whitespace(f"{given or ''} {family or ''}")
        return [full] if full else []
    return []


def _collect_values(value: Any) -> List[str]:
    value = _parse_jsonld_value(value)
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        values: List[str] = []
        for item in value:
            values.extend(_collect_values(item))
        return values
    if isinstance(value, Mapping):
        url = value.get("url") or value.get("@id") or value.get("name")
        return [str(url)] if url else []
    return []


def flatten_schema_values(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "types": [],
        "authors": [],
        "publishers": [],
        "reviewed_by": [],
        "citations": [],
        "date_published": None,
        "date_modified": None,
        "headline": None,
        "description": None,
    }

    for block in blocks:
        result["types"].extend(_jsonld_types(block.get("@type")))
        result["authors"].extend(_collect_names(block.get("author")))
        result["publishers"].extend(_collect_names(block.get("publisher")))
        result["reviewed_by"].extend(_collect_names(block.get("reviewedBy")))
        result["citations"].extend(_collect_values(block.get("citation")))

        if block.get("headline") and not result["headline"]:
            result["headline"] = str(block.get("headline"))
        if block.get("description") and not result["description"]:
            result["description"] = str(block.get("description"))
        if block.get("datePublished") and not result["date_published"]:
            result["date_published"] = str(block.get("datePublished"))
        if block.get("dateModified") and not result["date_modified"]:
            result["date_modified"] = str(block.get("dateModified"))

    for key in ("types", "authors", "publishers", "reviewed_by", "citations"):
        result[key] = unique_non_empty(result[key])
    return result


def clean_soup_for_visible_text(html_content: str) -> BeautifulSoup:
    soup = BeautifulSoup(html_content or "", "html.parser")
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()
    return soup


def extract_text_and_structure(soup: BeautifulSoup) -> Dict[str, Any]:
    visible_text = normalize_whitespace(soup.get_text(" ", strip=True))
    words = tokenize_words(visible_text)

    headings = [
        {"level": tag.name, "text": normalize_whitespace(tag.get_text(" ", strip=True))}
        for tag in soup.find_all(["h1", "h2", "h3", "h4"])
        if normalize_whitespace(tag.get_text(" ", strip=True))
    ]
    paragraphs = [
        normalize_whitespace(tag.get_text(" ", strip=True))
        for tag in soup.find_all("p")
        if normalize_whitespace(tag.get_text(" ", strip=True))
    ]

    images = soup.find_all("img")
    image_alt_count = sum(1 for image in images if normalize_whitespace(image.get("alt") or ""))

    return {
        "visible_text": visible_text,
        "word_count": len(words),
        "sentence_count": max(1, len(re.findall(r"[.!?]+", visible_text))),
        "paragraph_count": len(paragraphs),
        "heading_count": len(headings),
        "h1_count": sum(1 for item in headings if item["level"] == "h1"),
        "h2_count": sum(1 for item in headings if item["level"] == "h2"),
        "h3_count": sum(1 for item in headings if item["level"] == "h3"),
        "headings": headings[:40],
        "list_count": len(soup.find_all(["ul", "ol"])),
        "list_item_count": len(soup.find_all("li")),
        "table_count": len(soup.find_all("table")),
        "blockquote_count": len(soup.find_all("blockquote")),
        "code_block_count": len(soup.find_all(["pre", "code"])),
        "image_count": len(images),
        "image_alt_count": image_alt_count,
        "paragraph_samples": paragraphs[:8],
    }


def extract_readability(visible_text: str) -> Dict[str, Any]:
    try:
        import textstat
    except Exception:
        return {}

    try:
        return {
            "flesch_reading_ease": float(textstat.flesch_reading_ease(visible_text)),
            "gunning_fog": float(textstat.gunning_fog(visible_text)),
            "smog_index": float(textstat.smog_index(visible_text)),
        }
    except Exception:
        return {}


def extract_link_signals(
    soup: BeautifulSoup, metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    anchors = soup.find_all("a", href=True)
    html_hrefs = [normalize_whitespace(a.get("href") or "") for a in anchors if a.get("href")]

    metadata = as_mapping(metadata)
    outbound_links = [
        as_mapping(item).get("url")
        for item in as_list(metadata.get("outbound_links"))
        if as_mapping(item).get("url")
    ]
    internal_links = [
        as_mapping(item).get("url")
        for item in as_list(metadata.get("internal_links"))
        if as_mapping(item).get("url")
    ]

    all_hrefs = unique_non_empty([*html_hrefs, *outbound_links, *internal_links])
    external_urls = [url for url in all_hrefs if is_external_http_url(url)]
    https_external_urls = [url for url in external_urls if is_https_url(url)]
    http_external_urls = [url for url in external_urls if urlparse(url).scheme == "http"]
    unique_domains = sorted({safe_domain(url) for url in external_urls if safe_domain(url)})

    anchor_texts = [normalize_whitespace(a.get_text(" ", strip=True)).lower() for a in anchors]
    generic_anchor_count = sum(
        1 for text in anchor_texts if text in {"click here", "read more", "here", "more", "link"}
    )
    rel_values = [
        rel for anchor in anchors for rel in (anchor.get("rel") or []) if isinstance(rel, str)
    ]

    word_count = max(1, len(tokenize_words(soup.get_text(" ", strip=True))))

    return {
        "html_link_count": len(html_hrefs),
        "metadata_outbound_count": len(outbound_links),
        "metadata_internal_count": len(internal_links),
        "external_link_count": len(external_urls),
        "https_external_count": len(https_external_urls),
        "http_external_count": len(http_external_urls),
        "https_ratio": len(https_external_urls) / max(1, len(external_urls)),
        "unique_external_domain_count": len(unique_domains),
        "external_domains": unique_domains[:30],
        "generic_anchor_count": generic_anchor_count,
        "link_density": len(html_hrefs) / word_count,
        "sponsored_or_nofollow_count": sum(
            1 for rel in rel_values if rel in {"sponsored", "nofollow"}
        ),
        "external_urls": external_urls[:40],
    }


def parse_date_value(raw: Any) -> Optional[date]:
    if raw is None:
        return None
    text = normalize_whitespace(str(raw))
    if not text:
        return None

    iso_text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso_text).date()
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    try:
        return parsedate_to_datetime(text).date()
    except Exception:
        return None


def extract_date_signals(
    soup: BeautifulSoup, schema: Dict[str, Any], visible_text: str
) -> Dict[str, Any]:
    meta_selectors = [
        ("meta", {"property": "article:published_time"}, "content"),
        ("meta", {"property": "article:modified_time"}, "content"),
        ("meta", {"name": "date"}, "content"),
        ("meta", {"name": "datePublished"}, "content"),
        ("meta", {"name": "dateModified"}, "content"),
        ("time", {}, "datetime"),
    ]

    raw_dates: List[str] = []
    for tag_name, attrs, attr_name in meta_selectors:
        for tag in soup.find_all(tag_name, attrs=attrs):
            if tag.get(attr_name):
                raw_dates.append(str(tag.get(attr_name)))

    raw_dates.extend(
        date_value
        for date_value in (schema.get("date_published"), schema.get("date_modified"))
        if date_value
    )

    visible_date_patterns = [
        r"\b20\d{2}-\d{2}-\d{2}\b",
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+20\d{2}\b",
        r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+20\d{2}\b",
    ]
    visible_dates: List[str] = []
    for pattern in visible_date_patterns:
        visible_dates.extend(re.findall(pattern, visible_text, flags=re.IGNORECASE))
    raw_dates.extend(visible_dates)

    parsed_dates = [parsed for parsed in (parse_date_value(item) for item in raw_dates) if parsed]
    newest_date = max(parsed_dates) if parsed_dates else None
    today = date.today()
    age_days = (today - newest_date).days if newest_date else None

    return {
        "raw_dates": unique_non_empty(raw_dates)[:20],
        "visible_dates": unique_non_empty(visible_dates)[:20],
        "has_any_date": bool(parsed_dates),
        "has_visible_date": bool(visible_dates),
        "has_structured_date": bool(schema.get("date_published") or schema.get("date_modified")),
        "newest_date": newest_date.isoformat() if newest_date else None,
        "age_days": age_days,
        "mentions_current_year": str(today.year) in visible_text,
    }


def extract_author_signals(
    soup: BeautifulSoup, schema: Dict[str, Any], visible_text: str
) -> Dict[str, Any]:
    byline_pattern = (
        r"\b(?:by|written by|reviewed by|edited by)\s+"
        r"([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,3})\b"
    )
    byline_matches = re.findall(
        byline_pattern,
        visible_text,
        flags=re.IGNORECASE,
    )

    author_selector = (
        '[rel="author"], .author, .author-name, .byline, .by-author, '
        '[class*="author"], [id*="author"]'
    )
    author_nodes = soup.select(
        author_selector
    )
    author_node_texts = unique_non_empty(node.get_text(" ", strip=True) for node in author_nodes)[
        :10
    ]

    meta_authors = [
        tag.get("content")
        for tag in soup.find_all("meta", attrs={"name": "author"})
        if tag.get("content")
    ]

    schema_authors = schema.get("authors", [])
    reviewed_by = schema.get("reviewed_by", [])
    publishers = schema.get("publishers", [])

    all_visible_author_cues = unique_non_empty(
        [*byline_matches, *author_node_texts, *meta_authors, *schema_authors, *reviewed_by]
    )

    return {
        "author_present": bool(all_visible_author_cues),
        "byline_names": unique_non_empty(byline_matches),
        "author_node_texts": author_node_texts,
        "meta_authors": unique_non_empty(meta_authors),
        "schema_authors": schema_authors,
        "reviewed_by": reviewed_by,
        "publishers": publishers,
        "responsible_party_present": bool(all_visible_author_cues or publishers),
    }


def extract_transparency_signals(soup: BeautifulSoup, visible_text: str) -> Dict[str, Any]:
    text_lower = visible_text.lower()
    markers = [term for term in TRANSPARENCY_TERMS if term in text_lower]

    internal_trust_links = []
    for anchor in soup.find_all("a", href=True):
        href = (anchor.get("href") or "").lower()
        text = normalize_whitespace(anchor.get_text(" ", strip=True)).lower()
        if is_external_http_url(href):
            continue
        if any(
            token in f"{href} {text}"
            for token in ("about", "contact", "privacy", "editorial", "author")
        ):
            internal_trust_links.append(anchor.get("href"))

    return {
        "transparency_markers": unique_non_empty(markers),
        "transparency_marker_count": len(markers),
        "internal_trust_link_count": len(unique_non_empty(internal_trust_links)),
    }


def extract_experience_indicators(visible_text: str) -> Dict[str, Any]:
    text_lower = visible_text.lower()
    first_person_count = len(
        re.findall(r"\b(?:i|me|my|mine|we|our|ours|us)\b", visible_text, flags=re.IGNORECASE)
    )
    action_hits = sum(
        len(re.findall(rf"\b{re.escape(term)}\b", text_lower)) for term in EXPERIENCE_ACTION_TERMS
    )
    phrase_hits = len(
        re.findall(
            (
                r"\b(?:in my experience|from experience|our testing|case study|"
                r"lessons learned|what happened|what we found)\b"
            ),
            text_lower,
        )
    )

    return {
        "first_person_count": first_person_count,
        "experience_action_hits": action_hits,
        "experience_phrase_hits": phrase_hits,
    }


def extract_quality_risk_signals(
    visible_text: str, soup: BeautifulSoup, metadata: Dict[str, Any]
) -> Dict[str, Any]:
    words = [word.lower() for word in tokenize_words(visible_text)]
    word_count = len(words)

    shingles = [" ".join(words[index : index + 5]) for index in range(max(0, len(words) - 4))]
    shingle_counts = Counter(shingles)
    repeated_shingles = sum(count - 1 for count in shingle_counts.values() if count > 1)
    repetition_ratio = repeated_shingles / max(1, len(shingles))

    focus_keyphrase = normalize_whitespace(
        str(metadata.get("focus_keyphrase") or metadata.get("primary_keyword") or "")
    ).lower()
    keyphrase_hits = 0
    keyphrase_density = 0.0
    if focus_keyphrase:
        keyphrase_hits = len(re.findall(re.escape(focus_keyphrase), visible_text.lower()))
        keyphrase_density = keyphrase_hits / max(1, word_count)

    link_density = len(soup.find_all("a", href=True)) / max(1, word_count)

    return {
        "word_count": word_count,
        "repetition_ratio": repetition_ratio,
        "keyphrase_hits": keyphrase_hits,
        "keyphrase_density": keyphrase_density,
        "link_density": link_density,
    }


def extract_metadata_evidence(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    metadata = as_mapping(metadata)
    facts = [as_mapping(item) for item in as_list(metadata.get("facts")) if as_mapping(item)]
    outbound_links = [
        as_mapping(item) for item in as_list(metadata.get("outbound_links")) if as_mapping(item)
    ]
    images = [as_mapping(item) for item in as_list(metadata.get("images")) if as_mapping(item)]

    fact_source_urls = unique_non_empty(fact.get("source_url") or fact.get("url") for fact in facts)
    outbound_urls = unique_non_empty(link.get("url") for link in outbound_links)
    all_source_urls = unique_non_empty([*fact_source_urls, *outbound_urls])

    return {
        "fact_count": len(facts),
        "sourced_fact_count": len(fact_source_urls),
        "unsourced_fact_count": max(0, len(facts) - len(fact_source_urls)),
        "fact_source_urls": fact_source_urls[:40],
        "outbound_link_count": len(outbound_urls),
        "outbound_urls": outbound_urls[:40],
        "source_url_count": len(all_source_urls),
        "source_domain_count": len(
            {safe_domain(url) for url in all_source_urls if safe_domain(url)}
        ),
        "image_suggestion_count": len(images),
    }


def detect_content_purpose(metadata: Dict[str, Any], visible_text: str) -> Dict[str, Any]:
    content_type = normalize_whitespace(str(metadata.get("content_type") or "")).lower()
    title = normalize_whitespace(
        str(metadata.get("title") or metadata.get("meta_title") or "")
    ).lower()
    haystack = f"{content_type} {title} {visible_text[:2000].lower()}"

    is_review_like = any(
        token in haystack
        for token in (
            "review",
            "best ",
            "comparison",
            "compare",
            "vs",
            "buying guide",
            "alternatives",
        )
    )
    is_ymyl = any(re.search(rf"\b{re.escape(term)}\b", haystack) for term in YMYL_TOPIC_TERMS)

    return {
        "content_type": content_type or None,
        "is_review_like": is_review_like,
        "is_ymyl_likely": is_ymyl,
    }


def extract_eeat_signals(
    html_content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata = as_mapping(metadata)
    raw_soup = BeautifulSoup(html_content or "", "html.parser")
    schema = flatten_schema_values(extract_json_ld_blocks(raw_soup, metadata=metadata))
    soup = clean_soup_for_visible_text(html_content)
    structure = extract_text_and_structure(soup)
    visible_text = structure["visible_text"]

    links = extract_link_signals(soup, metadata=metadata)
    evidence = extract_metadata_evidence(metadata)
    purpose = detect_content_purpose(metadata, visible_text)

    source_count = len(
        unique_non_empty(
            [*links["external_urls"], *evidence["fact_source_urls"], *evidence["outbound_urls"]]
        )
    )
    source_domains = {
        safe_domain(url)
        for url in [
            *links["external_urls"],
            *evidence["fact_source_urls"],
            *evidence["outbound_urls"],
        ]
        if safe_domain(url)
    }

    signals = {
        "rubric_version": RUBRIC_VERSION,
        "metadata": {
            "title": metadata.get("title"),
            "meta_title": metadata.get("meta_title"),
            "meta_description": metadata.get("meta_description"),
            "focus_keyphrase": metadata.get("focus_keyphrase") or metadata.get("primary_keyword"),
            "secondary_keywords": metadata.get("secondary_keywords") or [],
            "content_type": metadata.get("content_type"),
        },
        "purpose": purpose,
        "structure": structure,
        "readability": extract_readability(visible_text),
        "schema": {
            "types": schema.get("types", []),
            "authors": schema.get("authors", []),
            "publishers": schema.get("publishers", []),
            "reviewed_by": schema.get("reviewed_by", []),
            "date_published": schema.get("date_published"),
            "date_modified": schema.get("date_modified"),
            "citation_count": len(schema.get("citations", [])),
        },
        "author": extract_author_signals(soup, schema, visible_text),
        "dates": extract_date_signals(soup, schema, visible_text),
        "links": links,
        "evidence": {
            **evidence,
            "combined_source_count": source_count,
            "combined_source_domain_count": len(source_domains),
        },
        "transparency": extract_transparency_signals(soup, visible_text),
        "experience": extract_experience_indicators(visible_text),
        "quality_risks": extract_quality_risk_signals(visible_text, soup, metadata),
    }
    return signals


def _soft_count_score(count: int, points_each: float, max_points: float) -> float:
    return min(max_points, max(0, count) * points_each)


def score_author_identity(signals: Dict[str, Any]) -> float:
    author = signals["author"]
    score = 0.0
    score += 35 if author.get("schema_authors") else 0
    score += 25 if author.get("meta_authors") else 0
    score += 25 if author.get("byline_names") or author.get("author_node_texts") else 0
    score += 10 if author.get("reviewed_by") else 0
    score += 10 if author.get("publishers") else 0
    return clamp(score)


def score_evidence_strength(signals: Dict[str, Any]) -> float:
    evidence = signals["evidence"]
    links = signals["links"]
    structure = signals["structure"]
    transparency = signals["transparency"]

    fact_count = evidence.get("fact_count", 0)
    sourced_fact_count = evidence.get("sourced_fact_count", 0)
    source_count = evidence.get("combined_source_count", 0)
    source_domain_count = evidence.get("combined_source_domain_count", 0)

    source_coverage = sourced_fact_count / fact_count if fact_count else 0.0

    score = 18.0
    score += _soft_count_score(source_count, 7.0, 28.0)
    score += _soft_count_score(source_domain_count, 6.0, 18.0)
    score += source_coverage * 22.0
    score += _soft_count_score(structure.get("table_count", 0), 5.0, 8.0)
    score += _soft_count_score(structure.get("image_count", 0), 2.0, 6.0)
    score += _soft_count_score(structure.get("blockquote_count", 0), 4.0, 8.0)
    score += _soft_count_score(transparency.get("transparency_marker_count", 0), 3.0, 8.0)

    if source_count == 0 and fact_count == 0 and links.get("external_link_count", 0) == 0:
        score = min(score, 38.0)

    return clamp(score)


def score_experience(signals: Dict[str, Any]) -> float:
    experience = signals["experience"]
    structure = signals["structure"]
    evidence = signals["evidence"]
    purpose = signals["purpose"]

    score = 28.0
    score += _soft_count_score(experience.get("experience_phrase_hits", 0), 8.0, 24.0)
    score += _soft_count_score(experience.get("experience_action_hits", 0), 2.5, 18.0)
    score += _soft_count_score(max(0, experience.get("first_person_count", 0) - 2), 1.5, 12.0)
    score += _soft_count_score(structure.get("image_count", 0), 3.0, 8.0)
    score += _soft_count_score(
        structure.get("table_count", 0) + structure.get("code_block_count", 0), 4.0, 10.0
    )
    score += _soft_count_score(evidence.get("sourced_fact_count", 0), 2.0, 8.0)

    if purpose.get("is_review_like") and evidence.get("combined_source_count", 0) == 0:
        score -= 12.0

    return clamp(score)


def score_expertise(signals: Dict[str, Any], evidence_strength: float) -> float:
    structure = signals["structure"]
    text = structure.get("visible_text", "")
    word_count = structure.get("word_count", 0)
    numeric_count = len(
        re.findall(r"\b\d+(?:\.\d+)?(?:%|k|m|bn|million|billion)?\b", text, flags=re.IGNORECASE)
    )

    score = 30.0
    score += min(18.0, word_count / 120.0)
    score += _soft_count_score(structure.get("heading_count", 0), 3.0, 15.0)
    score += _soft_count_score(structure.get("list_count", 0), 3.0, 9.0)
    score += _soft_count_score(
        structure.get("table_count", 0) + structure.get("code_block_count", 0), 5.0, 12.0
    )
    score += _soft_count_score(numeric_count, 1.5, 12.0)
    score += evidence_strength * 0.12

    if word_count < 350:
        score -= 12.0

    return clamp(score)


def score_transparency(signals: Dict[str, Any]) -> float:
    transparency = signals["transparency"]
    author = signals["author"]
    dates = signals["dates"]
    evidence = signals["evidence"]

    score = 25.0
    score += _soft_count_score(transparency.get("transparency_marker_count", 0), 7.0, 28.0)
    score += _soft_count_score(transparency.get("internal_trust_link_count", 0), 8.0, 16.0)
    score += 16.0 if author.get("responsible_party_present") else 0.0
    score += 12.0 if dates.get("has_any_date") else 0.0
    score += 9.0 if evidence.get("combined_source_count", 0) > 0 else 0.0
    return clamp(score)


def score_freshness(signals: Dict[str, Any]) -> float:
    dates = signals["dates"]
    if not dates.get("has_any_date"):
        return 60.0

    age_days = dates.get("age_days")
    if age_days is None:
        return 70.0
    if age_days < 0:
        return 68.0
    if age_days <= 180:
        return 92.0
    if age_days <= 365:
        return 84.0
    if age_days <= 730:
        return 72.0
    if age_days <= 1460:
        return 58.0
    return 45.0


def score_structure_quality(signals: Dict[str, Any]) -> float:
    structure = signals["structure"]
    word_count = structure.get("word_count", 0)

    score = 20.0
    score += _soft_count_score(structure.get("heading_count", 0), 4.0, 20.0)
    score += _soft_count_score(structure.get("paragraph_count", 0), 2.0, 14.0)
    score += _soft_count_score(structure.get("list_count", 0), 4.0, 14.0)
    score += _soft_count_score(structure.get("table_count", 0), 6.0, 10.0)
    score += _soft_count_score(structure.get("image_alt_count", 0), 3.0, 8.0)
    score += _soft_count_score(structure.get("code_block_count", 0), 4.0, 8.0)
    score += 6.0 if word_count >= 600 else 0.0
    return clamp(score)


def score_link_hygiene(signals: Dict[str, Any]) -> float:
    links = signals["links"]
    if links.get("external_link_count", 0) == 0:
        return 75.0

    score = 30.0
    score += links.get("https_ratio", 0.0) * 45.0
    score += _soft_count_score(links.get("unique_external_domain_count", 0), 4.0, 16.0)
    score -= _soft_count_score(links.get("generic_anchor_count", 0), 4.0, 14.0)
    score -= _soft_count_score(links.get("http_external_count", 0), 5.0, 15.0)
    return clamp(score)


def score_spam_cleanliness(signals: Dict[str, Any]) -> float:
    risks = signals["quality_risks"]
    word_count = risks.get("word_count", 0)

    penalty = 0.0
    penalty += min(35.0, risks.get("repetition_ratio", 0.0) * 350.0)
    penalty += min(25.0, max(0.0, risks.get("keyphrase_density", 0.0) - 0.035) * 900.0)
    penalty += min(20.0, max(0.0, risks.get("link_density", 0.0) - 0.08) * 350.0)
    if word_count and word_count < 250:
        penalty += 8.0

    return clamp(100.0 - penalty)


def score_content_accuracy(signals: Dict[str, Any], evidence_strength: float) -> float:
    evidence = signals["evidence"]
    purpose = signals["purpose"]
    structure = signals["structure"]
    text = structure.get("visible_text", "")

    fact_count = evidence.get("fact_count", 0)
    sourced_fact_count = evidence.get("sourced_fact_count", 0)
    source_coverage = sourced_fact_count / fact_count if fact_count else 0.0
    numeric_count = len(re.findall(r"\b\d+(?:\.\d+)?%?\b", text))

    score = 52.0 + (evidence_strength * 0.28)
    if fact_count:
        score += source_coverage * 18.0
        score -= min(18.0, evidence.get("unsourced_fact_count", 0) * 5.0)
    if numeric_count > 8 and evidence.get("combined_source_count", 0) < 2:
        score -= 10.0
    if purpose.get("is_ymyl_likely") and evidence_strength < 65:
        score -= 12.0

    return clamp(score)


def score_trustworthiness(signals: Dict[str, Any], sub_scores: Dict[str, float]) -> float:
    score = (
        sub_scores["content_accuracy"] * 0.30
        + sub_scores["evidence_strength"] * 0.23
        + sub_scores["transparency"] * 0.16
        + sub_scores["author_identity"] * 0.10
        + sub_scores["spam_signals"] * 0.12
        + sub_scores["link_hygiene"] * 0.09
    )

    if signals["purpose"].get("is_ymyl_likely") and sub_scores["evidence_strength"] < 60:
        score -= 8.0

    return clamp(score)


def weighted_final_score(sub_scores: Dict[str, float]) -> float:
    weights = {
        "trustworthiness": 0.32,
        "content_accuracy": 0.18,
        "expertise": 0.15,
        "experience": 0.12,
        "evidence_strength": 0.13,
        "transparency": 0.04,
        "author_identity": 0.02,
        "structure_quality": 0.02,
        "freshness": 0.01,
        "link_hygiene": 0.01,
    }
    return clamp(sum(sub_scores.get(key, 0.0) * weight for key, weight in weights.items()))


def build_reasoning(sub_scores: Dict[str, float], signals: Dict[str, Any]) -> str:
    positives: List[str] = []
    gaps: List[str] = []

    if sub_scores["trustworthiness"] >= 75:
        positives.append("trust signals are strong")
    if sub_scores["expertise"] >= 75:
        positives.append("the content shows strong depth")
    if sub_scores["experience"] >= 75:
        positives.append("first-hand experience is visible")
    if sub_scores["evidence_strength"] >= 70:
        positives.append("claims are well supported")

    if sub_scores["evidence_strength"] < 55:
        gaps.append("evidence is thin")
    if sub_scores["author_identity"] < 45:
        gaps.append("authorship is unclear")
    if sub_scores["content_accuracy"] < 60:
        gaps.append("accuracy confidence is limited")
    if signals["purpose"].get("is_ymyl_likely") and sub_scores["evidence_strength"] < 70:
        gaps.append("YMYL-like content needs stronger proof")

    if positives and not gaps:
        return "Strong content-level E-E-A-T: " + ", ".join(positives) + "."
    if positives and gaps:
        return (
            "Mixed content-level E-E-A-T: "
            + ", ".join(positives)
            + ", but "
            + ", ".join(gaps)
            + "."
        )
    if gaps:
        return "Weak to moderate content-level E-E-A-T: " + ", ".join(gaps) + "."
    return "Moderate content-level E-E-A-T with no severe single weakness detected."


def build_recommendations(sub_scores: Dict[str, float], signals: Dict[str, Any]) -> List[str]:
    recommendations: List[str] = []
    if sub_scores["author_identity"] < 60:
        recommendations.append("Add a clear byline or responsible reviewer for this content.")
    if sub_scores["evidence_strength"] < 65:
        recommendations.append(
            "Add cited sources near factual claims, especially statistics or recommendations."
        )
    if sub_scores["experience"] < 60:
        recommendations.append(
            "Add first-hand testing, examples, screenshots, measurements, or field notes."
        )
    if sub_scores["transparency"] < 60:
        recommendations.append(
            "Add methodology, disclosure, update, or editorial context where readers expect it."
        )
    if sub_scores["structure_quality"] < 60:
        recommendations.append(
            "Improve scannability with clearer headings, lists, examples, or tables."
        )
    if signals["purpose"].get("is_ymyl_likely") and sub_scores["content_accuracy"] < 75:
        recommendations.append(
            "Raise the standard for YMYL-like claims with stronger sourcing and expert review."
        )
    return recommendations[:6]


def calculate_confidence(signals: Dict[str, Any], llm_used: bool) -> float:
    evidence = signals["evidence"]
    author = signals["author"]
    structure = signals["structure"]

    confidence = 45.0
    confidence += 12.0 if llm_used else 0.0
    confidence += min(18.0, evidence.get("combined_source_count", 0) * 4.0)
    confidence += 10.0 if author.get("responsible_party_present") else 0.0
    confidence += 8.0 if structure.get("word_count", 0) >= 600 else 0.0
    confidence += 5.0 if signals["dates"].get("has_any_date") else 0.0
    return clamp(confidence)


def _round_scores(result: Dict[str, Any]) -> Dict[str, Any]:
    score_fields = {
        "score",
        "experience",
        "expertise",
        "trustworthiness",
        "evidence_strength",
        "content_accuracy",
        "transparency",
        "author_identity",
        "freshness",
        "structure_quality",
        "spam_signals",
        "link_hygiene",
        "confidence",
    }
    rounded = dict(result)
    for field in score_fields:
        if field in rounded:
            rounded[field] = round(clamp(rounded[field]), 2)
    return rounded


def _public_signal_summary(signals: Dict[str, Any]) -> Dict[str, Any]:
    structure = signals["structure"]
    return {
        "rubric_version": signals["rubric_version"],
        "content_type": signals["purpose"].get("content_type"),
        "is_review_like": signals["purpose"].get("is_review_like"),
        "is_ymyl_likely": signals["purpose"].get("is_ymyl_likely"),
        "word_count": structure.get("word_count", 0),
        "heading_count": structure.get("heading_count", 0),
        "source_count": signals["evidence"].get("combined_source_count", 0),
        "source_domain_count": signals["evidence"].get("combined_source_domain_count", 0),
        "sourced_fact_count": signals["evidence"].get("sourced_fact_count", 0),
        "author_present": signals["author"].get("author_present", False),
        "date_present": signals["dates"].get("has_any_date", False),
        "external_link_count": signals["links"].get("external_link_count", 0),
        "https_ratio": round(float(signals["links"].get("https_ratio", 0.0)), 3),
    }


def deterministic_eeat_score(
    html_content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    signals = extract_eeat_signals(html_content, metadata=metadata)

    author_identity = score_author_identity(signals)
    evidence_strength = score_evidence_strength(signals)
    experience = score_experience(signals)
    expertise = score_expertise(signals, evidence_strength=evidence_strength)
    transparency = score_transparency(signals)
    freshness = score_freshness(signals)
    structure_quality = score_structure_quality(signals)
    link_hygiene = score_link_hygiene(signals)
    spam_signals = score_spam_cleanliness(signals)
    content_accuracy = score_content_accuracy(signals, evidence_strength=evidence_strength)

    sub_scores = {
        "experience": experience,
        "expertise": expertise,
        "trustworthiness": 0.0,
        "evidence_strength": evidence_strength,
        "content_accuracy": content_accuracy,
        "transparency": transparency,
        "author_identity": author_identity,
        "freshness": freshness,
        "structure_quality": structure_quality,
        "spam_signals": spam_signals,
        "link_hygiene": link_hygiene,
    }
    sub_scores["trustworthiness"] = score_trustworthiness(signals, sub_scores)
    sub_scores["score"] = weighted_final_score(sub_scores)

    result = {
        **sub_scores,
        "reasoning": build_reasoning(sub_scores, signals),
        "recommendations": build_recommendations(sub_scores, signals),
        "confidence": calculate_confidence(signals, llm_used=False),
        "rubric_version": RUBRIC_VERSION,
        "scoring_scope": "content_level_only",
        "signal_summary": _public_signal_summary(signals),
        "_signals": signals,
    }
    return _round_scores(result)


def _compact_prompt_payload(signals: Dict[str, Any], deterministic: Dict[str, Any]) -> str:
    payload = {
        "metadata": signals.get("metadata", {}),
        "purpose": signals.get("purpose", {}),
        "schema": signals.get("schema", {}),
        "author": signals.get("author", {}),
        "dates": signals.get("dates", {}),
        "links": {k: v for k, v in signals.get("links", {}).items() if k != "external_urls"},
        "evidence": signals.get("evidence", {}),
        "transparency": signals.get("transparency", {}),
        "experience": signals.get("experience", {}),
        "quality_risks": signals.get("quality_risks", {}),
        "structure": {
            key: value
            for key, value in signals.get("structure", {}).items()
            if key not in {"visible_text", "paragraph_samples"}
        },
        "readability": signals.get("readability", {}),
        "deterministic_scores": {
            key: value
            for key, value in deterministic.items()
            if key
            in {
                "score",
                "experience",
                "expertise",
                "trustworthiness",
                "evidence_strength",
                "content_accuracy",
                "transparency",
                "author_identity",
                "freshness",
                "structure_quality",
                "spam_signals",
                "link_hygiene",
            }
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _build_llm_prompt(
    visible_text: str, signals: Dict[str, Any], deterministic: Dict[str, Any]
) -> str:
    excerpt = visible_text[:MAX_PROMPT_TEXT_CHARS]
    return f"""
You are a senior content-quality and E-E-A-T auditor.
Evaluate only the main content provided here. Do not infer site-wide reputation,
domain authority, backlink authority, platform security, or off-page author reputation.

Use the current public Google Search quality framing:
- E-E-A-T means Experience, Expertise, Authoritativeness, and Trustworthiness.
- Trust is the most important part; the other dimensions contribute to trust.
- Page quality depends on how well the main content achieves its purpose.
- Reward effort, originality, talent or skill, accuracy, honesty, and helpfulness.
- For YMYL-like topics, apply a stricter standard for accuracy and evidence.
- AI-assisted content is not automatically bad; judge usefulness, originality, accuracy,
  transparency, and added value.

Scoring boundaries:
- Score every numeric field from 0 to 100.
- content_accuracy is an internal confidence score based on the excerpt and provided
  evidence signals. Do not pretend you have externally fact-checked claims.
- evidence_strength measures source support and proof inside this content, not the
  reputation of domains.
- author_identity measures clarity of responsibility only, not real-world credentials.
- spam_signals means cleanliness from repetition, excessive links, stuffing, or
  low-effort scaled-content patterns. 100 is clean.

Visible content excerpt:
{excerpt}

Extracted content-level signals:
{_compact_prompt_payload(signals, deterministic)}

Return a complete EEATTrustScore object with concise reasoning.
"""


def _blend_field(field: str, deterministic_value: float, llm_value: float) -> float:
    deterministic_weight = {
        "experience": 0.30,
        "expertise": 0.30,
        "trustworthiness": 0.35,
        "evidence_strength": 0.62,
        "content_accuracy": 0.35,
        "transparency": 0.62,
        "author_identity": 0.75,
        "freshness": 0.78,
        "structure_quality": 0.70,
        "spam_signals": 0.65,
        "link_hygiene": 0.78,
    }.get(field, 0.50)
    return clamp(
        (deterministic_value * deterministic_weight) + (llm_value * (1.0 - deterministic_weight))
    )


def _apply_evidence_guardrails(merged: Dict[str, Any], signals: Dict[str, Any]) -> None:
    source_count = signals["evidence"].get("combined_source_count", 0)
    author_present = signals["author"].get("responsible_party_present", False)

    if source_count == 0:
        merged["evidence_strength"] = min(merged["evidence_strength"], 50.0)
        merged["content_accuracy"] = min(merged["content_accuracy"], 76.0)
    if not author_present:
        merged["author_identity"] = min(merged["author_identity"], 42.0)
    if signals["purpose"].get("is_ymyl_likely") and source_count < 2:
        merged["content_accuracy"] = min(merged["content_accuracy"], 68.0)
        merged["trustworthiness"] = min(merged["trustworthiness"], 70.0)


async def calculate_eeat_trust_score(
    html_content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluate content-level E-E-A-T.

    The scorer deliberately excludes site-level reputation, domain authority,
    backlinks, traffic metrics, and independent fact verification. It combines
    deterministic extraction for visible/provable signals with an LLM rubric for
    qualitative judgments such as experience, expertise, and helpfulness.
    """
    logger.info("Starting content-level E-E-A-T evaluation")

    deterministic = deterministic_eeat_score(html_content=html_content, metadata=metadata)
    signals = deterministic.pop("_signals", {})

    try:
        from src.flow.model.llm_manager import load_model

        visible_text = signals.get("structure", {}).get("visible_text", "")
        prompt = _build_llm_prompt(visible_text, signals, deterministic)
        llm = load_model(max_tokens=DEFAULT_MAX_TOKENS).with_structured_output(EEATTrustScore)
        llm_result = await llm.ainvoke(prompt)
        llm_scores = llm_result.model_dump()

        score_fields = [
            "experience",
            "expertise",
            "trustworthiness",
            "evidence_strength",
            "content_accuracy",
            "transparency",
            "author_identity",
            "freshness",
            "structure_quality",
            "spam_signals",
            "link_hygiene",
        ]

        merged: Dict[str, Any] = {}
        for field in score_fields:
            det = clamp(deterministic.get(field, 0.0))
            llm_value = clamp(llm_scores.get(field, det))
            merged[field] = _blend_field(field, det, llm_value)

        _apply_evidence_guardrails(merged, signals)
        merged["trustworthiness"] = score_trustworthiness(signals, merged)
        merged["score"] = weighted_final_score(merged)
        merged["reasoning"] = normalize_whitespace(
            str(llm_scores.get("reasoning") or "")
        ) or build_reasoning(merged, signals)
        merged["recommendations"] = build_recommendations(merged, signals)
        merged["confidence"] = calculate_confidence(signals, llm_used=True)
        merged["rubric_version"] = RUBRIC_VERSION
        merged["scoring_scope"] = "content_level_only"
        merged["signal_summary"] = _public_signal_summary(signals)

        logger.info("Content-level E-E-A-T score calculated: %s", round(merged["score"], 2))
        return _round_scores(merged)

    except Exception as exc:
        logger.exception("LLM E-E-A-T evaluation failed, returning deterministic fallback: %s", exc)
        deterministic["confidence"] = calculate_confidence(signals, llm_used=False)
        deterministic["signal_summary"] = _public_signal_summary(signals)
        return _round_scores(deterministic)
