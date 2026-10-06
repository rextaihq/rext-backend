import asyncio
import html
import ipaddress
import re
from typing import List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import httpx
import textstat
from langchain_core.output_parsers import StrOutputParser

from src.api.tool import iso_codes
from src.api.tool.limits import model_tokens
from src.api.tool.prompts.grammar_prompt import grammar_prompt
from src.api.tool.prompts.headline_analyzer_prompt import headline_analyzer_prompt
from src.api.tool.prompts.hook_prompt import hook_prompt
from src.api.tool.prompts.meta_prompt import meta_prompt
from src.api.tool.prompts.outline_prompt import outline_tool_prompt
from src.api.tool.prompts.paragraph_rewriter_prompt import paragraph_rewriter_prompt
from src.api.tool.prompts.question_prompt import question_prompt
from src.api.tool.prompts.seo_blog_title_prompt import seo_blog_title_prompt
from src.api.tool.prompts.title_prompt import idea_prompt, title_prompt
from src.api.tool.schema.schema import (
    GrammarCheckerResponse,
    GrammarIssue,
    HeadlineAnalyzerRequest,
    HeadlineAnalyzerResponse,
    HookGeneratorRequest,
    HookGeneratorResponse,
    IdeaGeneratorRequest,
    IdeaGeneratorResponse,
    KeywordDensityItem,
    KeywordDensityRequest,
    KeywordDensityResponse,
    MetaDescriptionValidation,
    OutlineGeneratorRequest,
    OutlineGeneratorResponse,
    ParagraphRewriterRequest,
    ParagraphRewriterResponse,
    SEOBlogTitleRequest,
    SEOBlogTitleResponse,
    SERPPreviewRequest,
    SERPPreviewResponse,
    SitemapGeneratorRequest,
    SitemapGeneratorResponse,
    TitleTag,
)
from src.flow.model.llm_manager import load_model
from src.utils.url_validator import refuse_private_addresses


def _get_model(tool: str):
    """The model for a free tool, with the output cap its daily budget charges (limits.FREE_TOOLS)."""
    return load_model(max_tokens=model_tokens(tool))


# Word Counter Tool


def count_text_metrics(text: str):
    """Core logic to handle numbers, sentences, and paragraph breaks."""
    if not text or not text.strip():
        return {"words": 0, "characters": 0, "sentences": 0, "paragraphs": 0, "min_read": 0}

    # 1. Count characters
    char_count = len(text)

    # 2. Count words: split() treats numbers like '500' or '12.5' as words
    words = text.split()
    word_count = len(words)

    # 3. Count sentences: Uses findall to capture everything ending in punctuation

    sentence_matches = re.findall(r"[^.!?]+[.!?]", text)
    sentence_count = len(sentence_matches) if sentence_matches else (1 if text.strip() else 0)

    # 4. Count paragraphs: Split by double newlines (standard paragraphing)

    paragraph_list = re.split(r"\n\s*\n", text.strip())
    paragraph_count = len([p for p in paragraph_list if p.strip()])

    # 5. Estimate reading time (average 200 words/min)

    min_read = max(1, round(word_count / 200)) if word_count > 0 else 0

    return {
        "words": word_count,
        "characters": char_count,
        "sentences": sentence_count,
        "paragraphs": paragraph_count,
        "min_read": min_read,
    }


# Meta Description Generator Tool
async def generate_meta_description(page_title: str, target_keywords: List[str]) -> str:

    # Join keywords for the prompt
    keywords_str = ", ".join(target_keywords)

    # Load the LLM
    llm = _get_model("meta-description/generate")

    # Create the chain
    chain = meta_prompt | llm | StrOutputParser()

    # Generate the meta description
    result = await chain.ainvoke({"page_title": page_title, "keywords": keywords_str})

    # Clean up the result (remove any extra whitespace or quotes)
    meta_description = result.strip().strip('"').strip("'")

    # Ensure it's within character limits
    if len(meta_description) > 160:
        meta_description = meta_description[:157] + "..."

    return meta_description


def validate_meta_description(meta_description: str) -> MetaDescriptionValidation:

    length = len(meta_description)

    return MetaDescriptionValidation(
        length=length,
        is_optimal_length=120 <= length <= 160,
        character_count=f"{length}/160",
        warnings=[]
        if 120 <= length <= 160
        else ["Length not in optimal range (120-160 characters)"],
    )


# Title Tag Generator Tool
async def generate_title_tags(keyword: str, topic: str, brand: str, tone: str) -> List[str]:
    """
    Generate 5 SEO-friendly title tags and return them as a clean list.
    Every generated title is validated individually using Pydantic's TitleTag model
    to ensure it is strictly between 50 and 60 characters inclusive.
    """
    llm = _get_model("title-tags")

    prompt = title_prompt.format(keyword=keyword, topic=topic, brand=brand, tone=tone)

    valid_titles: List[str] = []
    seen_titles: set = set()
    invalid_titles: List[str] = []

    def _clean_and_validate(raw_line: str) -> Optional[str]:
        cleaned = raw_line.strip()
        cleaned = re.sub(r"^(?:\d+[\.\)]|[\-\*])\s*", "", cleaned)
        cleaned = re.sub(r"\s*\(\d+\s*char(?:acter)?s?\)\s*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip("\"'").strip()
        if not cleaned:
            return None
        try:
            validated_model = TitleTag(title=cleaned)
            return validated_model.title
        except Exception:
            invalid_titles.append(cleaned)
            return None

    # Initial LLM invocation
    response = await llm.ainvoke(prompt)
    raw_content = response.content if hasattr(response, "content") else str(response)

    for line in raw_content.split("\n"):
        title = _clean_and_validate(line)
        if title and title not in seen_titles:
            seen_titles.add(title)
            valid_titles.append(title)
            if len(valid_titles) == 5:
                break

    # Revision / regeneration loop if Pydantic validation fails for any titles and < 5 valid titles
    max_retries = 2  # three calls at most: the budget charges title-tags for three
    retry_count = 0
    while len(valid_titles) < 5 and retry_count < max_retries:
        retry_count += 1
        needed = 5 - len(valid_titles)

        revision_prompt = (
            f"You are a Senior SEO Content Strategist.\n"
            f"Generate {needed + 4} distinct SEO title tag(s) for the topic '{topic}' using primary keyword '{keyword}' and brand '{brand}'.\n"
            f"Tone: {tone}.\n\n"
            f"### Mandatory Requirements:\n"
            f"1. Every single title MUST be strictly between 50 and 60 characters long inclusive. 60 is a strict maximum. Count letters, spaces, and punctuation before returning.\n"
            f"2. Keep the primary keyword '{keyword}' natural and preferably near the beginning.\n"
            f"3. Include the brand name '{brand}' when provided.\n"
            f"4. Do not blindly truncate titles. Ensure phrasing is natural and complete.\n\n"
        )
        if invalid_titles:
            revision_prompt += "Previous attempts were invalid because their character count was outside 50-60 characters:\n"
            for inv in invalid_titles[-3:]:
                revision_prompt += f"- '{inv}' ({len(inv)} chars)\n"
            revision_prompt += "\n"

        revision_prompt += (
            f"Return ONLY {needed + 4} bullet point candidate title(s), one per line."
        )

        response = await llm.ainvoke(revision_prompt)
        raw_content = response.content if hasattr(response, "content") else str(response)

        for line in raw_content.split("\n"):
            title = _clean_and_validate(line)
            if title and title not in seen_titles:
                seen_titles.add(title)
                valid_titles.append(title)
                if len(valid_titles) == 5:
                    break

    # If retries finish and we still have fewer than 5 titles, fill missing titles dynamically with Pydantic validation
    if len(valid_titles) < 5:
        base_kw = keyword.strip()
        base_brand = brand.strip() if brand else ""
        base_topic = topic.strip()

        descriptors = [
            "Top",
            "Best",
            "New",
            "Fast",
            "Smart",
            "Modern",
            "Robust",
            "Leading",
            "Complete",
            "Advanced",
            "Powerful",
            "Efficient",
            "Automated",
            "2026",
            "Pro",
            "Expert",
            "Proven",
            "Simple",
            "Secure",
            "Core",
            "Global",
            "Ultimate",
        ]
        connectors = [
            f"{base_kw}",
            f"{base_kw} Guide",
            f"{base_kw} Tips",
            f"{base_kw} Tools",
            f"{base_kw} System",
            f"{base_topic} & {base_kw}",
            f"{base_kw}: {base_topic}",
        ]
        suffixes = [
            f" | {base_brand}" if base_brand else "",
            f" - {base_brand}" if base_brand else "",
            f" ({base_brand})" if base_brand else "",
            " | 2026 Guide",
            " (2026 Edition)",
            " | Full Guide",
            " | Top Tips",
            "",
        ]

        for desc in [""] + descriptors:
            for conn in connectors:
                for suff in suffixes:
                    parts = [p for p in [desc, conn] if p]
                    cand_title = f"{' '.join(parts)}{suff}".strip()
                    if 50 <= len(cand_title) <= 60:
                        try:
                            validated = TitleTag(title=cand_title).title
                            if validated not in seen_titles:
                                seen_titles.add(validated)
                                valid_titles.append(validated)
                                if len(valid_titles) == 5:
                                    break
                        except Exception:
                            pass
                if len(valid_titles) == 5:
                    break
            if len(valid_titles) == 5:
                break

    return valid_titles[:5]


# Schema Builder Tool
def build_schema(data) -> dict:  # Using data as flexible input (SchemaRequest or dict-like)
    """Build Schema.org JSON-LD directly from request data."""
    schema = {"@context": "https://schema.org", "@type": data.schema_type, "name": data.name}
    if data.description:
        schema["description"] = data.description
    if data.url:
        schema["url"] = str(data.url)
    if data.image_url:
        schema["image"] = str(data.image_url)
    if data.author_name:
        schema["author"] = {"@type": "Person", "name": data.author_name}
    if data.date_published:
        schema["datePublished"] = data.date_published
    return schema


# Readability Checker Tool
def calculate_readability(content: str) -> dict:

    flesch = round(textstat.flesch_reading_ease(content), 2)
    fk_grade = round(textstat.flesch_kincaid_grade(content), 2)

    metrics = {
        "readability_score": flesch,
        "grade_level": fk_grade,
        "sentence_complexity": round(textstat.gunning_fog(content), 2),
        "word_count": textstat.lexicon_count(content, removepunct=True),
        "sentence_count": textstat.sentence_count(content),
    }
    # Add a human-readable level
    if flesch >= 70:
        metrics["reading_level"] = "Easy"
    elif flesch >= 50:
        metrics["reading_level"] = "Standard"
    else:
        metrics["reading_level"] = "Difficult"

    return metrics


# =========================
# Canonical Tag Tool
# =========================


HOST_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
HOSTNAME = re.compile(rf"(?=.{{1,253}}$){HOST_LABEL}(?:\.{HOST_LABEL})*\.?", re.IGNORECASE)


def absolute_url(url: str) -> bool:
    """Whether url is a full http or https address: a valid host name (international ones too) or
    IP, a valid port if any, no spaces."""
    try:
        parsed = urlparse(url.strip())
        host = parsed.hostname or ""
        parsed.port  # raises for a port that isn't a number from 0 to 65535
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or re.search(r"\s", url.strip()):
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    try:
        host = host.encode("idna").decode("ascii")  # an international name, in its punycode form
    except UnicodeError:
        return False
    return HOSTNAME.fullmatch(host) is not None


def normalize_url(url: str) -> str:
    """
    Normalize URL for canonical usage.
    - Force https
    - Lowercase domain
    - Remove tracking parameters (fbclid, gclid, utm_*)
    - Normalize trailing slash
    """
    parsed = urlparse(url)

    scheme = "https"
    netloc = parsed.netloc.lower()

    # Filter out common tracking parameters
    query_params = []
    if parsed.query:
        for param in parsed.query.split("&"):
            if "=" in param:
                key = param.split("=")[0].lower()
                if key not in ["fbclid", "gclid"] and not key.startswith("utm_"):
                    query_params.append(param)

    query = "&".join(query_params)
    path = parsed.path.rstrip("/") or "/"

    return urlunparse((scheme, netloc, path, "", query, ""))


async def generate_canonical_tag(url: str):
    """
    Canonical Tag Generator: the tag for the normalized URL. Built in code: the rules are mechanical
    (normalize_url), so a model would add cost and nothing else.
    """
    address = url.strip()
    if "://" not in address:
        address = "https://" + address.lstrip("/")  # example.com/page
    normalized_url = normalize_url(address)
    if not absolute_url(normalized_url):
        raise ValueError("Enter a full address, such as https://example.com/page.")
    canonical_tag = f'<link rel="canonical" href="{html.escape(normalized_url)}" />'
    return {"canonical_tag": canonical_tag, "url": url, "normalized_url": normalized_url}


# =========================
# Hreflang Tag Tool
# =========================


def _hreflang_code(
    language: Optional[str], region: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    """
    Google's hreflang value for a language and an optional region: an ISO 639-1 language, an ISO
    15924 script, an ISO 3166-1 region, as en, en-US or zh-Hant-TW (EN_us is en-US). Returns the
    value and a note for the warnings: why it isn't one when the value is None.
    """
    parts = [p for p in re.split(r"[-_\s]+", (language or "").strip()) if p]
    if region and region.strip():
        parts = parts[:2] if len(parts) > 1 and len(parts[1]) == 4 else parts[:1]
        parts.append(region.strip())
    if not parts or parts[0].lower() not in iso_codes.LANGUAGES:
        return (
            None,
            f"'{language or ''}' is not a language code: use an ISO 639-1 code such as en or es.",
        )
    code = [parts[0].lower()]
    rest = parts[1:]
    if rest and rest[0].title() in iso_codes.SCRIPTS:
        code.append(rest.pop(0).title())
    if rest:
        region = rest[0].upper()
        if len(rest) == 1 and region == "UK":
            code.append("GB")
            return "-".join(code), "UK is not a region code; GB (the United Kingdom) is used."
        if len(rest) > 1 or region not in iso_codes.REGIONS:
            return (
                None,
                f"'{'-'.join(rest)}' is not a region code: use an ISO 3166-1 code such as US or GB.",
            )
        code.append(region)
    return "-".join(code), None


async def generate_hreflang_tags(request):
    """
    Google-compliant Hreflang Tag Generator: one alternate tag per language version (each version
    lists every other and itself), and x-default for the default URL. Built in code: Google's rules
    are mechanical, so a model would add cost and nothing else. Expects a HreflangRequest object
    (duck-typed).
    """
    if len(request.language_region_urls) > 50:
        raise ValueError("Maximum of 50 URLs allowed for hreflang generation.")

    # Identical URL check for SEO warnings
    warnings = []
    urls_seen = {}
    for entry in request.language_region_urls:
        url_str = str(entry.url)
        if url_str in urls_seen:
            warnings.append(
                f"Identical URL used for both '{urls_seen[url_str]}' and '{entry.language or 'unknown'}'. Google recommends unique URLs for different language versions."
            )
        urls_seen[url_str] = entry.language or "unknown"

    tag = "xhtml:link" if request.output_format == "sitemap" else "link"
    pairs = []
    codes_seen = {}
    for entry in request.language_region_urls:
        if not absolute_url(str(entry.url)):
            warnings.append(f"'{entry.url}' is not a full address (https://...): left out.")
            continue
        code, note = _hreflang_code(entry.language, entry.region)
        if note:
            warnings.append(note if code else f"{note} Left out: {entry.url}")
        if not code:
            continue
        if code in codes_seen:
            if codes_seen[code] != str(entry.url):
                warnings.append(
                    f"'{code}' is given twice; the first URL is kept: {codes_seen[code]}"
                )
            continue
        codes_seen[code] = str(entry.url)
        pairs.append((code, str(entry.url)))
    if request.include_x_default and not absolute_url(str(request.default_url)):
        warnings.append(
            f"'{request.default_url}' is not a full address (https://...): no x-default."
        )
    elif request.include_x_default:
        pairs.append(("x-default", str(request.default_url)))

    hreflang_tags = "\n".join(
        f'<{tag} rel="alternate" hreflang="{code}" href="{html.escape(url)}" />'
        for code, url in pairs
    )
    return {"hreflang_tags": hreflang_tags, "warnings": warnings if warnings else None}


# =========================
# Broken Link Checker Tool
# =========================


# The whole check, redirects and the private-address check's name lookups included:
# httpx's own timeout covers neither the lookups nor the number of redirects.
LINK_CHECK_SECONDS = 10


async def broken_link_checker(url):
    """Whether the address answers 200 within LINK_CHECK_SECONDS. A private or reserved
    address, or a redirect to one, is never fetched and counts as not working."""
    try:
        url_str = str(url)
        async with asyncio.timeout(LINK_CHECK_SECONDS):
            async with httpx.AsyncClient(
                event_hooks={"request": [refuse_private_addresses()]}
            ) as client:
                response = await client.get(url_str, timeout=5, follow_redirects=True)
                return response.status_code == 200
    except Exception:
        return False


# =========================
# Robots.txt Generator Tool
# =========================


def generate_robots_txt(
    user_agent: str, allow: List[str], disallow: List[str], sitemap_url: Optional[str] = None
) -> str:
    """
    Robots.txt Generator: Generates a valid robots.txt file as formatted plain text.
    Follows Google's robots.txt standards and best practices.
    """
    lines = []

    # 1. User-agent (Mandatory)
    # Default to * if not provided, though schema handles this
    ua = user_agent.strip() if user_agent else "*"
    lines.append(f"User-agent: {ua}")

    # 2. Allow rules (Best practice to group rules)
    for path in allow:
        if path and str(path).strip():
            lines.append(f"Allow: {str(path).strip()}")

    # 3. Disallow rules
    for path in disallow:
        if path and str(path).strip():
            lines.append(f"Disallow: {str(path).strip()}")

    # 4. Sitemap URL (Optional but highly recommended)
    if sitemap_url:
        # Ensure sitemap URL is a string and not just "None"
        url_str = str(sitemap_url).strip()
        if url_str and url_str.lower() != "none":
            lines.append(f"Sitemap: {url_str}")

    return "\n".join(lines)


# =========================
# Grammar Checker Tool
# =========================
PYTHON_BUILTINS_AND_KEYWORDS = {
    "str",
    "len",
    "int",
    "float",
    "list",
    "dict",
    "set",
    "tuple",
    "bool",
    "bytes",
    "range",
    "print",
    "type",
    "id",
    "input",
    "open",
    "dir",
    "help",
    "max",
    "min",
    "sum",
    "abs",
    "all",
    "any",
    "enumerate",
    "filter",
    "map",
    "zip",
    "def",
    "class",
    "import",
    "from",
    "return",
    "yield",
    "raise",
    "try",
    "except",
    "finally",
    "with",
    "as",
    "lambda",
    "async",
    "await",
    "global",
    "nonlocal",
    "assert",
    "break",
    "continue",
    "pass",
    "if",
    "elif",
    "else",
    "while",
    "for",
    "in",
    "is",
    "not",
    "and",
    "or",
    "true",
    "false",
    "none",
    "self",
    "cls",
    "args",
    "kwargs",
    "object",
    "exception",
    "valueerror",
    "typeerror",
    "keyerror",
    "indexerror",
    "attributeerror",
    "importerror",
    "stopiteration",
    "property",
    "staticmethod",
    "classmethod",
}

KNOWN_TECH_TERMS = {
    "pydantic",
    "fastapi",
    "langchain",
    "pytest",
    "python",
    "sql",
    "json",
    "html",
    "css",
    "rest",
    "graphql",
    "grpc",
    "docker",
    "kubernetes",
    "git",
    "github",
    "postgresql",
    "mysql",
    "mongodb",
    "redis",
    "aws",
    "azure",
    "gcp",
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "shopify",
    "wordpress",
    "beautifulsoup",
    "numpy",
    "pandas",
    "pytorch",
    "tensorflow",
    "react",
    "vue",
    "angular",
    "nextjs",
    "nodejs",
    "typescript",
    "javascript",
    "c++",
    "java",
    "rust",
    "golang",
    "php",
    "ruby",
    "llm",
    "api",
    "sdk",
    "url",
    "uri",
    "http",
    "https",
    "uuid",
    "jwt",
    "bcrypt",
    "alembic",
    "orm",
    "crud",
    "dto",
    "cli",
    "regex",
    "gui",
    "ui",
    "ux",
    "pydanticdeprecatedsince20",
    "contentidea",
    "titletag",
    "grammarchecker",
    "serp",
    "sitemap",
    "hreflang",
    "flesch",
    "kincaid",
    "gunning",
}


def _is_code_identifier(phrase: str) -> bool:
    """Check if phrase matches programming identifier patterns (PascalCase, camelCase, snake_case, dotted)."""
    s = phrase.strip()

    # PascalCase or camelCase (e.g., ContentIdea, TitleTag, parsePRD)
    if re.fullmatch(r"^[A-Z][a-zA-Z0-9]*[A-Z0-9][a-zA-Z0-9]*$", s) or re.fullmatch(
        r"^[a-z]+[A-Z][a-zA-Z0-9]*$", s
    ):
        return True

    # snake_case or has underscores (e.g., content_idea, generate_title_tags, __init__)
    if "_" in s and re.fullmatch(r"^[a-zA-Z0-9_]+$", s):
        return True

    # Dotted identifiers (e.g., pydantic.BaseModel, os.path.join)
    if "." in s and re.fullmatch(r"^[a-zA-Z0-9_\.]+$", s) and not s.endswith("."):
        return True

    # Code call syntax (e.g., len(), str(), func())
    if s.endswith("()") or "(" in s or ")" in s:
        return True

    return False


def _is_inside_code_span(phrase: str, full_text: str) -> bool:
    """Check if phrase occurs inside inline backticks (`...`) or fenced code blocks (```...```)."""
    code_spans = []
    for m in re.finditer(r"```[\s\S]*?```", full_text):
        code_spans.append((m.start(), m.end()))
    for m in re.finditer(r"`[^`\n]+`", full_text):
        code_spans.append((m.start(), m.end()))

    if not code_spans:
        return False

    for m in re.finditer(re.escape(phrase), full_text):
        p_start, p_end = m.start(), m.end()
        for c_start, c_end in code_spans:
            if c_start <= p_start and p_end <= c_end:
                return True

    return False


def _is_protected_term(phrase: str, full_text: str) -> bool:
    """Check if phrase is a protected code block, builtin keyword, tech term, or identifier."""
    phrase_clean = phrase.strip()
    phrase_lower = phrase_clean.lower()

    # 1. Inside code block or inline backticks
    if _is_inside_code_span(phrase_clean, full_text):
        return True

    # 2. Python keywords / builtins
    if phrase_lower in PYTHON_BUILTINS_AND_KEYWORDS:
        return True

    # 3. Known technical terms / framework & package names
    if phrase_lower in KNOWN_TECH_TERMS:
        return True

    # 4. Code identifier syntax (PascalCase, camelCase, snake_case)
    if _is_code_identifier(phrase_clean):
        return True

    # 5. Token-level check for multi-word phrase
    tokens = [t.strip(",.()[]{}") for t in phrase_clean.split()]
    for token in tokens:
        t_lower = token.lower()
        if (
            t_lower in PYTHON_BUILTINS_AND_KEYWORDS
            or t_lower in KNOWN_TECH_TERMS
            or _is_code_identifier(token)
        ):
            return True

    return False


# =========================
# Grammar Checker Tool
# =========================
async def grammar_checker(text: str) -> GrammarCheckerResponse:
    """
    Grammar Checker: Detects natural language grammar, spelling, punctuation, and clarity issues.
    Context-aware: Preserves code blocks, inline code, technical terms (Pydantic, FastAPI, etc.),
    Python builtins/keywords (str, len, etc.), and programming identifiers (ContentIdea).
    Validates issues with Pydantic and ensures strict correction integrity.
    """
    if not text or not text.strip():
        return GrammarCheckerResponse(corrected_text=text or "", issues=[])

    llm = _get_model("grammar-checker")
    structured_llm = llm.with_structured_output(GrammarCheckerResponse)

    prompt = grammar_prompt.format(text=text)

    try:
        raw_response: GrammarCheckerResponse = await structured_llm.ainvoke(prompt)
    except Exception:
        # Fallback if LLM invocation fails
        return GrammarCheckerResponse(corrected_text=text, issues=[])

    valid_issues: List[GrammarIssue] = []

    for issue in raw_response.issues:
        orig = issue.original_phrase.strip()
        corr = issue.suggested_correction.strip()

        if not orig or not corr:
            continue

        # 1. Correction integrity: orig must exist as an exact substring in full text
        if orig not in text:
            continue

        # 2. Technical term preservation: check if orig is a protected technical term or code identifier
        if _is_protected_term(orig, text):
            continue

        # 3. No-op check: if orig == corr
        if orig == corr:
            continue

        valid_issues.append(
            GrammarIssue(
                original_phrase=issue.original_phrase,
                suggested_correction=issue.suggested_correction,
                issue_type=issue.issue_type,
            )
        )

    # Reconstruct corrected_text using only validated issues to ensure 100% integrity
    if not valid_issues:
        final_corrected_text = text
    else:
        final_corrected_text = text
        for issue in valid_issues:
            if issue.original_phrase in final_corrected_text:
                final_corrected_text = final_corrected_text.replace(
                    issue.original_phrase, issue.suggested_correction, 1
                )

    return GrammarCheckerResponse(corrected_text=final_corrected_text, issues=valid_issues)


# Ai Content idea Generater tool
async def generate_content_ideas(data: IdeaGeneratorRequest) -> IdeaGeneratorResponse:
    """Generate high-quality content ideas using structured LLM output."""
    llm = _get_model("content-idea-generator")
    structured_llm = llm.with_structured_output(IdeaGeneratorResponse)
    prompt = idea_prompt.format(
        ideas_count=data.ideas_count, topic=data.topic, content_type=data.content_type
    )
    return await structured_llm.ainvoke(prompt)


# Hook Generater Tool
async def generate_hooks(data: HookGeneratorRequest) -> HookGeneratorResponse:
    """Generate catchy hooks using LLM."""
    llm = _get_model("hook-generator")

    formatted_prompt = hook_prompt.format(
        number_of_variations=data.number_of_variations,
        topic_description=data.topic_description,
        goal_of_content=data.goal_of_content,
    )

    response = await llm.ainvoke(formatted_prompt)

    raw_content = response.content if hasattr(response, "content") else str(response)
    hooks = [line.strip("- ").strip() for line in raw_content.split("\n") if line.strip()]

    return HookGeneratorResponse(
        topic=data.topic_description, hooks=hooks[: data.number_of_variations]
    )


# Blog Topic Generater Tool
async def generate_seo_blog_titles(data: SEOBlogTitleRequest) -> SEOBlogTitleResponse:
    """Generate SEO-friendly blog titles using LLM."""
    llm = _get_model("seo-blog-titles")

    formatted_prompt = seo_blog_title_prompt.format(
        number_of_topics=data.number_of_topics,
        keyword=data.keyword,
        min_words=data.min_words,
        max_words=data.max_words,
    )

    response = await llm.ainvoke(formatted_prompt)

    raw_content = response.content if hasattr(response, "content") else str(response)
    titles = [line.strip("- ").strip() for line in raw_content.split("\n") if line.strip()]

    return SEOBlogTitleResponse(keyword=data.keyword, blog_titles=titles[: data.number_of_topics])


async def generate_questions(text: str) -> List[str]:
    """Generate engaging questions from text using LLM."""
    llm = _get_model("question-generator")

    formatted_prompt = question_prompt.format(text=text)

    response = await llm.ainvoke(formatted_prompt)

    raw_content = response.content if hasattr(response, "content") else str(response)
    questions = [line.strip("- ").strip() for line in raw_content.split("\n") if line.strip()]

    return questions


# Content Outline Generator Tool
async def generate_content_outline(data: OutlineGeneratorRequest) -> OutlineGeneratorResponse:
    """Generate a structured content outline using LLM with auto section calculation."""
    llm = _get_model("outline-generator")
    structured_llm = llm.with_structured_output(OutlineGeneratorResponse)

    word_count = data.target_word_count or 1500
    if word_count < 800:
        sections_count = 4
    elif word_count <= 1500:
        sections_count = 5
    elif word_count <= 2500:
        sections_count = 7
    else:
        sections_count = 9

    prompt = outline_tool_prompt.format(
        topic=data.topic,
        target_word_count=word_count,
        tone=data.tone or "Informative",
        sections_count=sections_count,
    )
    res: OutlineGeneratorResponse = await structured_llm.ainvoke(prompt)
    res.estimated_word_count = word_count
    res.sections_count = len(res.sections) if res.sections else sections_count
    return res


# Headline Analyzer Tool
async def analyze_headline(data: HeadlineAnalyzerRequest) -> HeadlineAnalyzerResponse:
    """Analyze headline CTR, sentiment, and quality using LLM and text analysis."""
    llm = _get_model("headline-analyzer")
    structured_llm = llm.with_structured_output(HeadlineAnalyzerResponse)

    prompt = headline_analyzer_prompt.format(headline=data.headline)
    res: HeadlineAnalyzerResponse = await structured_llm.ainvoke(prompt)

    clean_hl = data.headline.strip()
    words = clean_hl.split()
    res.headline = clean_hl
    res.word_count = len(words)
    res.character_count = len(clean_hl)
    res.score = max(0, min(100, res.score))
    return res


# Keyword Density Checker Tool
def calculate_keyword_density(data: KeywordDensityRequest) -> KeywordDensityResponse:
    """Calculate word count, n-gram frequencies, and keyword density percentages."""
    import string
    from collections import Counter

    text = data.text or ""
    # Translate punctuation to spaces to prevent merging tokens (e.g. SEO/SEM -> SEO SEM, word1.word2 -> word1 word2)
    clean_text = text.lower().translate(
        str.maketrans(string.punctuation, " " * len(string.punctuation))
    )
    words = [w for w in clean_text.split() if w]
    total_words = len(words)
    total_chars = len(text)

    if total_words == 0:
        return KeywordDensityResponse(
            total_words=0,
            total_characters=total_chars,
            top_single_words=[],
            top_phrases=[],
            target_keyword_analysis=None,
        )

    stopwords = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "up",
        "about",
        "into",
        "through",
        "after",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "must",
        "can",
        "could",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "they",
        "them",
        "their",
        "we",
        "us",
        "our",
        "you",
        "your",
        "i",
        "my",
    }

    filtered_words = [w for w in words if w not in stopwords and len(w) > 1]
    word_counts = Counter(filtered_words)

    top_single = []
    for word, count in word_counts.most_common(10):
        density = round((count / total_words) * 100, 2)
        top_single.append(KeywordDensityItem(keyword=word, count=count, density_percentage=density))

    bigrams = [" ".join(words[i : i + 2]) for i in range(len(words) - 1)]
    trigrams = [" ".join(words[i : i + 3]) for i in range(len(words) - 2)]

    filtered_bigrams = [b for b in bigrams if not any(w in stopwords for w in b.split())]
    filtered_trigrams = [t for t in trigrams if not any(w in stopwords for w in t.split())]

    phrase_counts = Counter(filtered_bigrams + filtered_trigrams)

    top_phrases = []
    for phrase, count in phrase_counts.most_common(5):
        density = round((count / total_words) * 100, 2)
        top_phrases.append(
            KeywordDensityItem(keyword=phrase, count=count, density_percentage=density)
        )

    target_analysis = None
    if data.target_keyword and data.target_keyword.strip():
        raw_tk = data.target_keyword.strip()
        clean_tk = raw_tk.lower().translate(
            str.maketrans(string.punctuation, " " * len(string.punctuation))
        )
        tk_words = [w for w in clean_tk.split() if w]

        if tk_words:
            pattern = r"\b" + r"\s+".join(re.escape(w) for w in tk_words) + r"\b"
            matches = re.findall(pattern, clean_text)
            tk_count = len(matches)
            # Phrase word-weighted density %
            tk_density = round((tk_count * len(tk_words) / total_words) * 100, 2)

            if tk_density < 0.5:
                status = "Low (under 0.5%)"
            elif 0.5 <= tk_density <= 2.5:
                status = "Optimal (0.5% - 2.5%)"
            else:
                status = "Over-stuffed (above 2.5%)"

            target_analysis = {
                "target_keyword": raw_tk,
                "count": tk_count,
                "density_percentage": tk_density,
                "status": status,
            }

    return KeywordDensityResponse(
        total_words=total_words,
        total_characters=total_chars,
        top_single_words=top_single,
        top_phrases=top_phrases,
        target_keyword_analysis=target_analysis,
    )


# Paragraph Rewriter Tool
async def rewrite_paragraph(data: ParagraphRewriterRequest) -> ParagraphRewriterResponse:
    """Rewrite a paragraph according to specified goal and tone."""
    llm = _get_model("paragraph-rewriter")
    structured_llm = llm.with_structured_output(ParagraphRewriterResponse)

    prompt = paragraph_rewriter_prompt.format(
        text=data.text,
        goal=data.goal or "improve clarity",
        tone=data.tone or "Natural and Professional",
    )
    res: ParagraphRewriterResponse = await structured_llm.ainvoke(prompt)
    res.original_text = data.text
    res.goal = data.goal or "improve clarity"
    return res


# SERP Preview Tool
def generate_serp_preview(data: SERPPreviewRequest) -> SERPPreviewResponse:
    """Calculate SERP snippet lengths, truncation estimates, and Google search preview strings."""
    title_str = str(data.title).strip()
    desc_str = str(data.description).strip()
    url_str = str(data.url).strip()

    title_len = len(title_str)
    desc_len = len(desc_str)

    title_truncated = title_len > 60
    desc_truncated = desc_len > 160

    title_preview = title_str[:57] + "..." if title_truncated else title_str
    desc_preview = desc_str[:157] + "..." if desc_truncated else desc_str

    # Heuristic estimate: Average desktop title rendering in Arial 18px ~ 9.5px per character
    pixel_width = int(title_len * 9.5)

    warnings = []
    if title_len < 30:
        warnings.append(
            "Title tag is short (under 30 characters). Recommended 50-60 characters for optimal visibility."
        )
    elif title_truncated:
        warnings.append(
            f"Title tag is {title_len} characters (~{pixel_width}px heuristic estimate) and may be truncated on Google desktop search (over ~600px/60 chars). Note: Pixel widths and character thresholds are heuristic estimates, not exact Google rendering measurements or guaranteed cutoffs; search engines dynamically rewrite titles."
        )

    if desc_len < 70:
        warnings.append(
            "Meta description is short (under 70 characters). Recommended 120-160 characters."
        )
    elif desc_truncated:
        warnings.append(
            f"Meta description is {desc_len} characters and may be truncated on Google search results (over ~160 chars). Note: Snippet lengths are heuristic estimates and vary by device, screen resolution, and search query."
        )

    return SERPPreviewResponse(
        title_preview=title_preview,
        title_length=title_len,
        title_truncated=title_truncated,
        description_preview=desc_preview,
        description_length=desc_len,
        description_truncated=desc_truncated,
        url_preview=url_str,
        desktop_pixel_width_approx=pixel_width,
        warnings=warnings,
    )


# Sitemap Generator Tool
def generate_xml_sitemap(data: SitemapGeneratorRequest) -> SitemapGeneratorResponse:
    """Generate valid sitemap.xml string from list of SitemapItems or string URLs with XML escaping and deduplication."""
    import xml.sax.saxutils

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    seen_urls = set()
    total_valid = 0
    valid_changefreqs = {"always", "hourly", "daily", "weekly", "monthly", "yearly", "never"}

    for item in data.urls:
        if isinstance(item, str):
            raw_url = item.strip()
            priority_val = 0.8
            changefreq_val = "weekly"
            lastmod_val = None
        else:
            raw_url = str(item.url).strip()
            priority_val = item.priority if item.priority is not None else 0.8
            changefreq_val = item.changefreq if item.changefreq else "weekly"
            lastmod_val = str(item.lastmod).strip() if item.lastmod else None

        if not raw_url:
            continue

        if raw_url in seen_urls:
            continue
        seen_urls.add(raw_url)

        escaped_url = xml.sax.saxutils.escape(raw_url)

        if priority_val < 0.0:
            priority_val = 0.0
        elif priority_val > 1.0:
            priority_val = 1.0

        if changefreq_val and changefreq_val.lower() not in valid_changefreqs:
            changefreq_val = "weekly"

        lines.append("  <url>")
        lines.append(f"    <loc>{escaped_url}</loc>")
        if lastmod_val:
            lines.append(f"    <lastmod>{xml.sax.saxutils.escape(lastmod_val)}</lastmod>")
        if changefreq_val:
            lines.append(f"    <changefreq>{changefreq_val.lower()}</changefreq>")
        lines.append(f"    <priority>{priority_val:.1f}</priority>")
        lines.append("  </url>")
        total_valid += 1

    lines.append("</urlset>")
    sitemap_xml = "\n".join(lines)

    return SitemapGeneratorResponse(
        sitemap_xml=sitemap_xml,
        total_urls=total_valid,
    )
