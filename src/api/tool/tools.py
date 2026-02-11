import re
import httpx
import textstat
from typing import List, Dict, Any, Optional
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import SystemMessage, HumanMessage
from urllib.parse import urlparse, urlunparse

from src.flow.model.llm_manager import load_model
from src.api.tool.schema.schema import (
    MetaDescriptionValidation,
    IdeaGeneratorResponse,
    IdeaGeneratorRequest,
    HookGeneratorRequest,
    HookGeneratorResponse,
    SEOBlogTitleRequest,
    SEOBlogTitleResponse
)
from src.api.tool.prompts.title_prompt import title_prompt, idea_prompt
from src.api.tool.prompts.meta_prompt import meta_prompt
from src.api.tool.prompts.canonical_prompt import canonical_prompt
from src.api.tool.prompts.hreflang_prompt import hreflang_system_prompt, hreflang_user_prompt
from src.api.tool.prompts.hook_prompt import hook_prompt
from src.api.tool.prompts.seo_blog_title_prompt import seo_blog_title_prompt
from src.api.tool.prompts.question_prompt import question_prompt

def _get_model():
    """Internal helper to consistently load the model."""
    return load_model()

#Word Counter Tool
import re

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
    
    sentence_matches = re.findall(r'[^.!?]+[.!?]', text)
    sentence_count = len(sentence_matches) if sentence_matches else (1 if text.strip() else 0)

    # 4. Count paragraphs: Split by double newlines (standard paragraphing)
    
    paragraph_list = re.split(r'\n\s*\n', text.strip())
    paragraph_count = len([p for p in paragraph_list if p.strip()])

    # 5. Estimate reading time (average 200 words/min)
    
    min_read = max(1, round(word_count / 200)) if word_count > 0 else 0

    return {
        "words": word_count,
        "characters": char_count,
        "sentences": sentence_count,
        "paragraphs": paragraph_count,
        "min_read": min_read
    }


# Meta Description Generator Tool
async def generate_meta_description(page_title: str, target_keywords: List[str]) -> str:

    # Join keywords for the prompt
    keywords_str = ", ".join(target_keywords)

    # Load the LLM
    llm = _get_model()

    # Create the chain
    chain = meta_prompt | llm | StrOutputParser()

    # Generate the meta description
    result = await chain.ainvoke({
        "page_title": page_title,
        "keywords": keywords_str
    })

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
        warnings=[] if 120 <= length <= 160 else ["Length not in optimal range (120-160 characters)"]
    )


# Title Tag Generator Tool
async def generate_title_tags(keyword: str, topic: str, brand: str, tone: str) -> List[str]:
    """
    Generate 5 SEO-friendly title tags and return them as a clean list.
    """
    llm = _get_model()
    
    prompt = title_prompt.format(
        keyword=keyword,
        topic=topic,
        brand=brand,
        tone=tone
    )
    
    # Get the response from the LLM
    response = await llm.ainvoke(prompt)

    raw_content = response.content if hasattr(response, 'content') else str(response)
    titles_list = [
        line.strip("- ").strip() 
        for line in raw_content.split("\n") 
        if line.strip()
    ]
    
    return titles_list[:5]


# Schema Builder Tool
def build_schema(data) -> dict: # Using data as flexible input (SchemaRequest or dict-like)
    """Build Schema.org JSON-LD directly from request data."""
    schema = {
        "@context": "https://schema.org",
        "@type": data.schema_type,
        "name": data.name
    }
    if data.description: schema["description"] = data.description
    if data.url: schema["url"] = str(data.url)
    if data.image_url: schema["image"] = str(data.image_url)
    if data.author_name:
        schema["author"] = {"@type": "Person", "name": data.author_name}
    if data.date_published: schema["datePublished"] = data.date_published
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
        for param in parsed.query.split('&'):
            if '=' in param:
                key = param.split('=')[0].lower()
                if key not in ['fbclid', 'gclid'] and not key.startswith('utm_'):
                    query_params.append(param)
    
    query = '&'.join(query_params)
    path = parsed.path.rstrip("/") or "/"

    return urlunparse((scheme, netloc, path, "", query, ""))


async def generate_canonical_tag(url: str):
    """
    AI-powered Canonical Tag Generator logic.
    """
    normalized_url = normalize_url(url)
    
    model = _get_model()

    # Format the prompt
    formatted_prompt = canonical_prompt.format(url=url)

    response = await model.ainvoke([
        SystemMessage(content="You generate SEO ONLY valid HTML canonical tags."),
        HumanMessage(content=formatted_prompt)
    ])

    canonical_tag = response.content if hasattr(response, 'content') else str(response)
    canonical_tag = canonical_tag.strip().strip('`').replace('html\n', '').strip()

    # Safety fallback
    if not canonical_tag.startswith("<link") or 'rel="canonical"' not in canonical_tag:
        canonical_tag = f'<link rel="canonical" href="{normalized_url}" />'

    return {
        "canonical_tag": canonical_tag,
        "url": url,
        "normalized_url": normalized_url
    }


# =========================
# Hreflang Tag Tool
# =========================

async def generate_hreflang_tags(request):
    """
    AI-powered Google-compliant Hreflang Tag Generator logic.
    Expects a HreflangRequest object (duck-typed).
    """
    model = _get_model()

    if len(request.language_region_urls) > 50:
        raise ValueError("Maximum of 50 URLs allowed for hreflang generation.")

    # Identical URL check for SEO warnings
    warnings = []
    urls_seen = {}
    for entry in request.language_region_urls:
        url_str = str(entry.url)
        if url_str in urls_seen:
            warnings.append(f"Identical URL used for both '{urls_seen[url_str]}' and '{entry.language or 'unknown'}'. Google recommends unique URLs for different language versions.")
        urls_seen[url_str] = entry.language or "unknown"

    # Determine format rules
    if request.output_format == "sitemap":
        format_rule = "- Output ONLY valid XML <xhtml:link> tags"
        format_instruction = 'Return ONLY valid XML <xhtml:link rel="alternate" hreflang="..." href="..." /> tags.'
        context_note = "Your output must be ready to paste directly inside a <url> block of an XML sitemap."
    else:
        format_rule = "- Output ONLY valid HTML <link> tags"
        format_instruction = 'Return ONLY valid HTML <link rel="alternate" hreflang="..." href="..." /> tags.'
        context_note = "Your output must be ready to paste directly inside the <head> section of an HTML document."

    # Prepare input for LLM
    lang_region_urls_str = "\n".join([
        f"- url: {entry.url}, language: {entry.language or 'unknown'}, region: {entry.region or 'unknown'}"
        for entry in request.language_region_urls
    ])

    # Format prompts
    system_content = hreflang_system_prompt.format(
        format_rule=format_rule,
        context_note=context_note
    )
    
    user_content = hreflang_user_prompt.format(
        default_url=request.default_url,
        lang_region_urls_str=lang_region_urls_str,
        include_x_default=str(request.include_x_default).lower(),
        format_instruction=format_instruction
    )

    response = await model.ainvoke([
        SystemMessage(content=system_content.strip()),
        HumanMessage(content=user_content.strip())
    ])

    hreflang_tags = response.content if hasattr(response, 'content') else str(response)
    hreflang_tags = hreflang_tags.strip()

    # Final cleanup: Remove markdown code blocks if any
    if hreflang_tags.startswith("```"):
        lines = hreflang_tags.split("\n")
        if lines[0].startswith("```") and lines[-1].startswith("```"):
            hreflang_tags = "\n".join(lines[1:-1]).strip()
        else:
            hreflang_tags = hreflang_tags.replace("```html", "").replace("```xml", "").replace("```", "").strip()

    return {
        "hreflang_tags": hreflang_tags,
        "warnings": warnings if warnings else None
    }


# =========================
# Broken Link Checker Tool
# =========================

async def broken_link_checker(url):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=5, follow_redirects=True)
            return response.status_code == 200
    except httpx.HTTPError:
        return False


# =========================
# Robots.txt Generator Tool
# =========================

def generate_robots_txt(user_agent: str, allow: List[str], disallow: List[str], sitemap_url: Optional[str] = None) -> str:
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
def grammar_checker(text: str):
    """
    Grammar Checker: Detects grammar, spelling, and punctuation issues.
    Uses LanguageTool (Remote API - No Java, No LLM).
    """
    try:
        import language_tool_python
    except ImportError:
        raise ImportError("language-tool-python library is required. Please install it with 'uv add language-tool-python'.")

    # Use Public LanguageTool API (No Java required)
    try:
        # We use api.languagetool.org as a reliable high-accuracy source
        tool = language_tool_python.LanguageTool('en-US', remote_server='https://api.languagetool.org/v2')
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Grammar Checker service: {str(e)}")

    try:
        # Perform the check
        matches = tool.check(text)
        
        # Generate corrected text
        corrected_text = tool.correct(text)
        
        # Extract issues
        issues = []
        for match in matches:
            # Determine issue type from category or ruleId
            issue_type = "grammar"
            cat = match.category.lower()
            if "spelling" in cat:
                issue_type = "spelling"
            elif "punctuation" in cat or "typographical" in cat:
                issue_type = "punctuation"
                
            issues.append({
                "original_phrase": text[match.offset : match.offset + match.error_length],
                "suggested_correction": match.replacements[0] if match.replacements else "",
                "issue_type": issue_type
            })

        return {
            "corrected_text": corrected_text,
            "issues": issues
        }

    except Exception as e:
        raise RuntimeError(f"Grammar processing failed: {str(e)}")
    finally:
        # Close the connection
        tool.close()

#Ai Content idea Generater tool
async def generate_content_ideas(data: IdeaGeneratorRequest) -> IdeaGeneratorResponse:
    """Generate high-quality content ideas using structured LLM output."""
    llm = _get_model()
    structured_llm = llm.with_structured_output(IdeaGeneratorResponse)
    prompt = idea_prompt.format(
        ideas_count=data.ideas_count,
        topic=data.topic,
        content_type=data.content_type
    )
    return await structured_llm.ainvoke(prompt)

# Hook Generater Tool
async def generate_hooks(data: HookGeneratorRequest) -> HookGeneratorResponse:
    """Generate catchy hooks using LLM."""
    llm = _get_model()

    formatted_prompt = hook_prompt.format(
        number_of_variations=data.number_of_variations,
        topic_description=data.topic_description,
        goal_of_content=data.goal_of_content
    )

    response = await llm.ainvoke(formatted_prompt)
    
    raw_content = response.content if hasattr(response, 'content') else str(response)
    hooks = [
        line.strip("- ").strip() 
        for line in raw_content.split("\n") 
        if line.strip()
    ]
    
    return HookGeneratorResponse(
        topic=data.topic_description,
        hooks=hooks[:data.number_of_variations]
    )

# Blog Topic Generater Tool
async def generate_seo_blog_titles(data: SEOBlogTitleRequest) -> SEOBlogTitleResponse:
    """Generate SEO-friendly blog titles using LLM."""
    llm = _get_model()

    formatted_prompt = seo_blog_title_prompt.format(
        number_of_topics=data.number_of_topics,
        keyword=data.keyword,
        min_words=data.min_words,
        max_words=data.max_words
    )

    response = await llm.ainvoke(formatted_prompt)
    
    raw_content = response.content if hasattr(response, 'content') else str(response)
    titles = [
        line.strip("- ").strip() 
        for line in raw_content.split("\n") 
        if line.strip()
    ]
    
    return SEOBlogTitleResponse(
        keyword=data.keyword,
        blog_titles=titles[:data.number_of_topics]
    )

async def generate_questions(text: str) -> List[str]:
    """Generate engaging questions from text using LLM."""
    llm = _get_model()

    formatted_prompt = question_prompt.format(text=text)

    response = await llm.ainvoke(formatted_prompt)
    
    raw_content = response.content if hasattr(response, 'content') else str(response)
    questions = [
        line.strip("- ").strip() 
        for line in raw_content.split("\n") 
        if line.strip()
    ]
    
    return questions
