import re
import logging
from bs4 import BeautifulSoup
from typing import List

logger = logging.getLogger(__name__)

# ========================================
# NOISE PATTERNS TO REMOVE
# ========================================
NOISE_PATTERNS: List[str] = [
    # Navigation & UI elements
    r'Newsletter',
    r'Subscribe',
    r'Sign up',
    r'Resources',
    r'Categories',
    r'Hubs',
    r'Back to top',
    r'Menu',
    r'Skip to content',
    r'Skip to main',
    r'Toggle navigation',
    
    # Language switchers
    r'Passer en Français',
    r'Cambiar a Español',
    r'Switch to English',
    
    # Comments section
    r'Leave a Reply',
    r'Cancel reply',
    r'Comments?\s*\(\d+\)',
    r'Reply',
    r'Post a Comment',
    r'Add a Comment',
    r'Join the discussion',
    
    # Read more / Continue
    r'Continue reading',
    r'Read more',
    r'See more',
    r'Show more',
    r'View all',
    r'Load more',
    
    # Social sharing
    r'Share on',
    r'Tweet this',
    r'Pin it',
    r'Share this',
    r'Follow us',
    
    # Cookie notices
    r'We use cookies',
    r'Cookie policy',
    r'Accept cookies',
    r'Privacy policy',
    
    # Footer noise
    r'©\s*\d{4}.*?(?:All rights reserved)?',
    r'Crafted & hosted.*?France',
    r'Powered by',
    r'Built with',
    
    # Horizontal separators
    r'\* \* \*',
    r'---+',
    r'___+',
    r'===+',
    
    # Breadcrumbs
    r'Home\s*[>»›]\s*',
    r'You are here:',
    
    # Print/PDF
    r'Print this page',
    r'Download PDF',
    r'Save as PDF',
    
    # Table of contents noise
    r'Table of Contents',
    r'On this page',
    r'In this article',
    
    # Advertisement markers
    r'Advertisement',
    r'Sponsored',
    r'Ad\s*$',
]

# Compile patterns for efficiency
COMPILED_NOISE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE | re.MULTILINE) 
    for pattern in NOISE_PATTERNS
]


def clean_content(raw_markdown: str) -> str:
    """
    Cleans raw HTML/markdown content for SEO analysis.
    
    Cleaning steps:
    1. Convert escaped newlines to real newlines
    2. Strip HTML tags (keeping text only)
    3. Remove markdown link syntax (keep anchor text)
    4. Remove markdown image syntax
    5. Remove common website noise (nav, footer, comments, etc.)
    6. Normalize whitespace
    7. Remove empty lines and excessive spacing
    
    Args:
        raw_markdown (str): Raw content containing HTML and/or markdown.
    
    Returns:
        str: Cleaned, readable text optimized for content analysis.
    """
    if not raw_markdown or not raw_markdown.strip():
        return ""
    
    logger.debug("Starting text cleaning process")
    
    text = raw_markdown
    
    # ========================================
    # STEP 1: Convert escaped newlines
    # ========================================
    text = text.replace("\\n", "\n")
    text = text.replace("\\r", "\r")
    text = text.replace("\\t", "\t")
    
    # ========================================
    # STEP 2: Strip HTML tags
    # ========================================
    # Check if content has HTML tags
    if '<' in text and '>' in text:
        try:
            soup = BeautifulSoup(text, "html.parser")
            
            # Remove script and style elements entirely
            for element in soup(['script', 'style', 'noscript', 'iframe']):
                element.decompose()
            
            text = soup.get_text(separator="\n")
        except Exception as e:
            logger.warning(f"BeautifulSoup parsing failed: {e}")
            # Fallback: simple tag removal
            text = re.sub(r'<[^>]+>', '', text)
    
    # ========================================
    # STEP 3: Remove markdown link syntax
    # ========================================
    # [text](url) -> text
    text = re.sub(r'\[([^\]]*)\]\([^)]+\)', r'\1', text)
    
    # Reference-style links: [text][ref] -> text
    text = re.sub(r'\[([^\]]*)\]\[[^\]]*\]', r'\1', text)
    
    # Reference definitions: [ref]: url -> remove entirely
    text = re.sub(r'^\s*\[[^\]]+\]:\s*\S+.*$', '', text, flags=re.MULTILINE)
    
    # ========================================
    # STEP 4: Remove markdown image syntax
    # ========================================
    # ![alt](url) -> remove entirely (images have no text value)
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', text)
    
    # ========================================
    # STEP 5: Remove common noise patterns
    # ========================================
    for pattern in COMPILED_NOISE_PATTERNS:
        text = pattern.sub('', text)
    
    # ========================================
    # STEP 6: Remove other markdown formatting
    # ========================================
    # Remove bold/italic markers: **text** -> text, *text* -> text
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    
    # Remove inline code markers: `code` -> code
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # Remove heading markers: ### Heading -> Heading
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    
    # Remove blockquote markers: > text -> text
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    
    # Remove list markers: - item, * item, 1. item -> item
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    
    # ========================================
    # STEP 7: Normalize whitespace
    # ========================================
    # Collapse multiple spaces/tabs into single space
    text = re.sub(r'[ \t]+', ' ', text)
    
    # Remove spaces at start/end of lines
    text = re.sub(r'^ +| +$', '', text, flags=re.MULTILINE)
    
    # Collapse 3+ newlines into 2 (preserve paragraph breaks)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Remove lines that are just whitespace
    text = re.sub(r'^\s*$\n', '', text, flags=re.MULTILINE)
    
    # Final strip
    text = text.strip()
    
    logger.debug(f"Text cleaning completed: {len(raw_markdown)} -> {len(text)} chars")
    return text