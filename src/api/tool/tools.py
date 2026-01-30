import re
import requests
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


from src.api.tool.prompts.hook_prompt import hook_prompt
from src.api.tool.prompts.seo_blog_title_prompt import seo_blog_title_prompt

def _get_model():
    """Internal helper to consistently load the model."""
    return load_model()

#Word Counter Tool
def count_text_metrics(text: str):
    # Count characters including spaces
    char_count = len(text)

    # Count words: split the text by whitespace and count resulting elements
    words = re.split(r'\s+', text.strip())
    word_count = len([word for word in words if word])
    
    # Count sentences: more robust estimate
    sentence_count = len(re.findall(r'[^.!?]+[.!?]', text)) or (1 if text.strip() else 0)

    # Count paragraphs: split by one or more newline characters
    paragraphs = [p for p in re.split(r'\n+', text) if p.strip()]
    paragraph_count = len(paragraphs)

    # Estimate reading time (e.g., 200 words per minute average)
    min_read = max(1, round(word_count / 200)) if word_count > 0 else 0

    return {
        'words': word_count,
        'characters': char_count,
        'sentences': sentence_count,
        'paragraphs': paragraph_count,
        'min_read': min_read
    }

# Meta Description Generator Tool
def generate_meta_description(page_title: str, target_keywords: List[str]) -> str:

    # Join keywords for the prompt
    keywords_str = ", ".join(target_keywords)

    # Load the LLM
    llm = _get_model()

    # Create the chain
    chain = meta_prompt | llm | StrOutputParser()

    # Generate the meta description
    result = chain.invoke({
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
def generate_title_tags(keyword: str, topic: str, brand: str, tone: str) -> List[str]:
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
    response = llm.invoke(prompt)
    
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


def generate_canonical_tag(url: str):
    """
    Logic-based Canonical Tag Generator.
    - Normalizes the URL
    - Returns a standard HTML canonical tag
    - No AI/LLM usage
    """
    normalized_url = normalize_url(url)
    
    # Construct the tag directly
    canonical_tag = f'<link rel="canonical" href="{normalized_url}" />'

    return {
        "canonical_tag": canonical_tag,
        "url": url,
        "normalized_url": normalized_url
    }


# =========================
# Hreflang Tag Tool
# =========================

def generate_hreflang_tags(request):
    """
    Logic-based Hreflang Tag Generator.
    - Iterates through the provided URL/Language/Region entries.
    - Constructs standard HTML <link rel="alternate" hreflang="..." href="..." /> tags.
    - Handles x-default if requested.
    """
    tags = []
    
    # helper for constructing code
    def get_lang_code(lang, region):
        if region:
            return f"{lang}-{region}"
        return lang

    # 1. Generate tags for each entry
    for entry in request.language_region_urls:
        # Construct hreflang code (e.g., "en-us" or just "en")
        code = get_lang_code(entry.language, entry.region)
        
        if request.output_format == "sitemap":
            # Sitemap format: <xhtml:link rel="alternate" hreflang="xx" href="url" />
            # Note: usually this is nested inside <url>, we just return the link line
            tag = f'<xhtml:link rel="alternate" hreflang="{code}" href="{entry.url}" />'
        else:
            # HTML Header format
            tag = f'<link rel="alternate" hreflang="{code}" href="{entry.url}" />'
        
        tags.append(tag)
        
    # 2. Add x-default if requested
    if request.include_x_default:
        if request.output_format == "sitemap":
            tag = f'<xhtml:link rel="alternate" hreflang="x-default" href="{request.default_url}" />'
        else:
            tag = f'<link rel="alternate" hreflang="x-default" href="{request.default_url}" />'
        tags.append(tag)
        
    return {
        "hreflang_tags": "\n".join(tags),
        "warnings": None
    }


# =========================
# Broken Link Checker Tool
# =========================

def broken_link_checker(url):
    try:
        response = requests.get(url, timeout=2)
        if response.status_code == 200:
            return True
        else:
            return False
    except requests.exceptions.RequestException:
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
def generate_content_ideas(data: IdeaGeneratorRequest) -> IdeaGeneratorResponse:
    """Generate high-quality content ideas using structured LLM output."""
    llm = _get_model()
    structured_llm = llm.with_structured_output(IdeaGeneratorResponse)
    prompt = idea_prompt.format(
        ideas_count=data.ideas_count,
        topic=data.topic,
        content_type=data.content_type
    )
    return structured_llm.invoke(prompt)

# Hook Generater Tool
def generate_hooks(data: HookGeneratorRequest) -> HookGeneratorResponse:
    """Generate catchy hooks using LLM."""
    llm = _get_model()
    
    formatted_prompt = hook_prompt.format(
        number_of_variations=data.number_of_variations,
        topic_description=data.topic_description,
        goal_of_content=data.goal_of_content
    )
    
    response = llm.invoke(formatted_prompt)
    
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
def generate_seo_blog_titles(data: SEOBlogTitleRequest) -> SEOBlogTitleResponse:
    """Generate SEO-friendly blog titles using LLM."""
    llm = _get_model()
    
    formatted_prompt = seo_blog_title_prompt.format(
        number_of_topics=data.number_of_topics,
        keyword=data.keyword,
        min_words=data.min_words,
        max_words=data.max_words
    )
    
    response = llm.invoke(formatted_prompt)
    
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
