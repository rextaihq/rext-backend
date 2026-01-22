import re
from typing import List, Dict, Any
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from src.flow.model.llm_manager import load_model
from src.api.tool.schema import MetaDescriptionValidation
from src.api.tool.prompts.title_prompt import title_prompt

# Word Counter Tool
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
    try:
        import textstat
    except ImportError:
        raise ImportError("textstat library is required for readability analysis. Please install it.")

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


