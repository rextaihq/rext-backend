import statistics
from src.flow.states.wrext import Competitor, NormalizedOrganicResult, DocumentScrapeData
from typing import List
from src.flow.engines.seo.seo_difficulty_engine.utils.utils import clamp, normalize_freshness
import re

from src.flow.engines.scrape.config.clean_content import clean_content

def normalize_word_count(wc, max_wc=2000):
    """Assume max deep content ~2000 words"""
    return clamp(wc / max_wc)


def normalize_structure(h2_count, h3_count, max_h2=10, max_h3=20):
    if h2_count == 0:
        return 0.0

    return clamp((h2_count/max_h2 * 0.6 + h3_count/max_h3 * 0.4))


def intent_match(keyword_intent, page_intent):
    """
    keyword_intent: 'informational', 'commercial', etc.
    page_intent: dict from competitor intent_distribution
    """

    """
    page_intent
    {
    "informational": 7,
    "commercial": 1,
    "transactional": 0
    }

    """

    if not page_intent:
        return 0.5  # unknown
    total = sum(page_intent.values())
    if total == 0:
        return 0.5
    

    page_score = page_intent.get(keyword_intent, 0) / total
    return clamp(page_score)

def clean_page_content(page_content: str) -> int:
    """
    Clean raw scraped page content and calculate character and word count.
    Return cleaned word count.
    """

    # Step 1: Remove Markdown-style links [text](url) -> keep only 'text'
    clean_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', page_content)

    # Step 2: Remove any remaining raw URLs
    clean_text = re.sub(r'https?://\S+', '', clean_text)

    # Step 3: Remove repeated site menus, footer text, comments placeholders (common patterns)
    # Adjust patterns based on common CMS boilerplate
    boilerplate_patterns = [
        r'Newsletter', r'Resources', r'Categories', r'Hubs', r'Back to top',
        r'Passer en Français', r'Cambiar a Español', r'©.*?WPMarmite', r'Crafted & hosted.*?France',
        r'Leave a Reply', r'Cancel reply', r'Comments', r'Reply', r'Continue reading',
        r'\* \* \*'  # horizontal separators
    ]
    for pat in boilerplate_patterns:
        clean_text = re.sub(pat, '', clean_text, flags=re.IGNORECASE)

    # Step 4: Remove extra symbols like multiple newlines, repeated spaces, asterisks
    clean_text = re.sub(r'\n+', '\n', clean_text)      # multiple newlines -> single
    clean_text = re.sub(r'\s+', ' ', clean_text)       # multiple spaces -> single
    clean_text = re.sub(r'[*#]', '', clean_text)       # remove leftover Markdown headings/asterisks

    # Step 5: Strip leading/trailing spaces
    clean_text = clean_text.strip()

    # Step 6: Count characters and words
    # char_count = len(clean_text)
    word_count = len(clean_text.split())

    return clean_text, word_count


def content_strength(keyword_intent: str, competitor: Competitor, normalized_result: NormalizedOrganicResult, scrape_data: DocumentScrapeData) -> float:
    # Word count proxy
    page_content = getattr(scrape_data['document'], "page_content", "")
    # wc,clean_text = clean_page_content(page_content)
    clean_text = clean_content(page_content)
    wc = len(clean_text)
    # wc = sum(d["content_length"] for d in scrape_data["documents"]) / len(scrape_data["documents"])
    wc_score = normalize_word_count(wc)
    
    # Content structure proxy      
    # Extract H2 and H3 directly from page_content
    h2_matches = re.findall(r'(?m)^##\s+(?!#)(.+)$', page_content)
    h3_matches = re.findall(r'(?m)^###\s+(?!#)(.+)$', page_content)

    h2_count = len(h2_matches)
    h3_count = len(h3_matches)

    article_struct_scores = normalize_structure(h2_count, h3_count)


    # freshness_score = sum(scores) / len(normalized_result)
    freshness_score = normalize_freshness(normalized_result.get("date"))

    # Intent match
    intent_score = intent_match(keyword_intent, competitor.get("intent_distribution", {}))

    # Weighted aggregation (example weights)
    # depth / structure 30%, freshness 30%, intent 40%
    strength = 0.3 * (wc_score + article_struct_scores)/2 + 0.3 * freshness_score + 0.4 * intent_score
    return clamp(strength),clean_text

