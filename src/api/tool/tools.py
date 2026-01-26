import re
import requests
import textstat
from typing import List, Dict, Any
from langchain_core.prompts import PromptTemplate
from src.api.tool.prompts.prompts import generate_conclusion_prompt_template
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import SystemMessage, HumanMessage
from urllib.parse import urlparse, urlunparse

from src.flow.model.llm_manager import load_model, tools_model
from src.api.tool.schema.schema import  MetaDescriptionValidation, IdeaGeneratorResponse,IdeaGeneratorRequest
from src.api.tool.prompts.title_prompt import idea_prompt,title_prompt

#Word Counter Tool
def count_text_metrics(text: str):
    # Count characters including spaces
    char_count = len(text)

    # Count words: split the text by whitespace and count resulting elements
    words = re.split(r'\s+', text.strip())
    word_count = len([word for word in words if word])
    
    # Count sentences: a rough estimate by counting common end punctuation
    sentence_count = text.count('.') + text.count('!') + text.count('?')

    # Count paragraphs: split by double newline characters using a loop
    paragraph_list = text.strip().split('\n\n')
    paragraph_count = 0
    for p in paragraph_list:
        if p.strip(): # Check if the paragraph content is not empty
            paragraph_count += 1

    # Estimate reading time (e.g., 200 words per minute average)
    min_read = round(word_count / 200) if word_count > 0 else 0

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

    # Create the prompt template
    prompt_template = PromptTemplate(
        input_variables=["page_title", "keywords"],
        template="""
You are an expert SEO copywriter. Create a compelling meta description for a webpage that will improve click-through rates from search results.

Page Title: {page_title}
Target Keywords: {keywords}

Requirements:
- Length: Between 120-160 characters (aim for 140-150)
- Include the primary keyword naturally
- Write compelling, benefit-focused copy that encourages clicks
- Make it unique and specific to this page
- Include a call-to-action when appropriate
- Focus on value proposition and urgency/benefits

Generate only the meta description text, no additional explanations or quotes.
"""
    )

    # Load the LLM
    llm = load_model()

    # Create the chain
    chain = prompt_template | llm | StrOutputParser()

    # Generate the meta description
    result = chain.invoke({
        "page_title": page_title,
        "keywords": keywords_str
    })

    # Clean up the result (remove any extra whitespace)
    meta_description = result.strip()

    # Ensure it's within character limits (though the prompt should handle this)
    if len(meta_description) > 160:
        meta_description = meta_description[:157] + "..."
    elif len(meta_description) < 120:
        # If too short, we could regenerate, but for now, return as is
        pass

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
    llm = load_model()
    
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
    if data.url: schema["url"] = data.url
    if data.image_url: schema["image"] = data.image_url
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
    - Remove query params & fragments
    - Normalize trailing slash
    """
    parsed = urlparse(url)

    scheme = "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"

    return urlunparse((scheme, netloc, path, "", "", ""))


def generate_canonical_tag(url: str):
    """
    AI-powered Canonical Tag Generator logic.
    """
    normalized_url = normalize_url(url)
    
    try:
        model = tools_model()
    except NameError:
         model = load_model()
    except Exception:
        model = load_model()

    prompt = f"""
You are an SEO expert.

Generate a valid HTML canonical tag for the given URL.

URL:
{url}

Rules:
- Use https
- Remove tracking parameters
- Normalize trailing slashes
- Prefer lowercase URLs
- Follow SEO best practices

Return ONLY the canonical tag.
Example:
<link rel="canonical" href="https://example.com/page" />

"""

    response = model.invoke([
        SystemMessage(content="You generate SEO ONLY valid HTML canonical tags."),
        HumanMessage(content=prompt)
    ])

    canonical_tag = response.content if hasattr(response, 'content') else str(response)
    canonical_tag = canonical_tag.strip()

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

def generate_hreflang_tags(request):
    """
    AI-powered Google-compliant Hreflang Tag Generator logic.
    Expects a HreflangRequest object (duck-typed).
    """
    if len(request.language_region_urls) > 50:
        raise ValueError("Maximum of 50 URLs allowed for hreflang generation.")

    try:
        model = tools_model()
    except:
        model = load_model()

    if request.output_format == "sitemap":
        format_rule = "- Output ONLY valid XML <xhtml:link> tags"
        format_instruction = 'Return ONLY valid XML <xhtml:link rel="alternate" hreflang="..." href="..." /> tags.'
        context_note = "Your output must be ready to paste directly inside a <url> block of an XML sitemap."
    else:
        format_rule = "- Output ONLY valid HTML <link> tags"
        format_instruction = 'Return ONLY valid HTML <link rel="alternate" hreflang="..." href="..." /> tags.'
        context_note = "Your output must be ready to paste directly inside the <head> section of an HTML document."

    # Identical URL check for SEO warnings
    warnings = []
    urls_seen = {}
    for entry in request.language_region_urls:
        url_str = str(entry.url)
        if url_str in urls_seen:
            warnings.append(f"Identical URL used for both '{urls_seen[url_str]}' and '{entry.language or 'unknown'}'. Google recommends unique URLs for different language versions.")
        urls_seen[url_str] = entry.language or "unknown"

    system_prompt = f"""
You are a senior SEO engineer and international search optimization expert.

Your sole task is to generate Google Search–compliant hreflang tags for multilingual and multi-regional websites.

STRICT RULES (DO NOT VIOLATE):
- Follow Google's official hreflang implementation guidelines
- Use ISO 639-1 language codes (lowercase)
- Use ISO 3166-1 Alpha-2 region codes (uppercase) when provided
- Format hreflang values strictly as: language-REGION (e.g., en-US, es-ES)
- Normalize incorrect input formats (e.g., EN_us → en-US)
- If language or region are not provided for a URL, infer them from the URL path, subdomain, or TLD if possible.
- Do NOT invent, guess, or modify URLs
- Remove duplicate hreflang entries
- Each hreflang value must be unique
- Self-referencing URLs MUST be included in the output for all versions.
- Generate x-default for the default URL provided.
{format_rule}
- One tag per line
- No explanations
- No comments
- No markdown
- No code blocks
- No additional text before or after output

{context_note}
"""

    # Prepare input for LLM
    lang_region_urls_str = "\n".join([
        f"- url: {entry.url}, language: {entry.language or 'unknown'}, region: {entry.region or 'unknown'}"
        for entry in request.language_region_urls
    ])

    user_prompt = f"""
Generate hreflang tags using the following input.

Default URL (for x-default):
{request.default_url}

Language and Region URLs:
{lang_region_urls_str}

Include x-default:
{str(request.include_x_default).lower()}

{format_instruction}
"""

    response = model.invoke([
        SystemMessage(content=system_prompt.strip()),
        HumanMessage(content=user_prompt.strip())
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

def broken_link_checker(url):
    try:
        response = requests.get(url, timeout=2)
        if response.status_code == 200:
            return True
        else:
            return False
    except requests.exceptions.RequestException:
        return False
#Ai Content idea Generater tool
def generate_content_ideas(data: IdeaGeneratorRequest) -> IdeaGeneratorResponse:
    """Generate high-quality content ideas using structured LLM output."""
    llm = load_model()
    structured_llm = llm.with_structured_output(IdeaGeneratorResponse)
    prompt = idea_prompt.format(
        ideas_count=data.ideas_count,
        topic=data.topic,
        content_type=data.content_type
    )
    return structured_llm.invoke(prompt)


# =========================
# Conclusion Generator Tool
# =========================
def generate_conclusion(content: str, tone: str = "professional", length: str = "medium") -> str:
    """ Generate a concise conclusion for the given content. """
    
    llm = load_model()

    chain = generate_conclusion_prompt_template | llm | StrOutputParser()

    response = chain.invoke({
        "content": content,
        "tone": tone,
        "length": length
    })
    conclusion = response.content if hasattr(response, 'content') else str(response)
    return conclusion.strip()

