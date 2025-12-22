import re
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def clean_content(raw_html: str) -> str:
    """
    Cleans raw HTML/markdown content by:
    - Converting escaped newlines to real newlines
    - Removing markdown link syntax but keeping anchor text
    - Stripping HTML tags
    - Removing excessive whitespace

    Args:
        raw_html (str): Raw content containing HTML and markdown.

    Returns:
        str: Cleaned text.
    """
    logger.debug("Starting text cleaning process")
    
    # Convert escaped '\n' sequences into actual newlines
    text = raw_html.replace("\\n", "\n")

    # Remove markdown link syntax but keep anchor text only: [text](url) -> text
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'\1', text)

    # Parse HTML and extract text only
    soup = BeautifulSoup(text, "html.parser")
    clean_text = soup.get_text(separator="\n")

    # Remove excessive blank lines and trim
    clean_text = re.sub(r'\n\s*\n+', '\n\n', clean_text).strip()

    # Collapse multiple spaces/tabs into one
    clean_text = re.sub(r'[ \t]+', ' ', clean_text)

    # Strip leading/trailing spaces and newlines
    clean_text = clean_text.strip()

    logger.debug("Text cleaning completed successfully")
    return clean_text