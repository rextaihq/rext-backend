# Content Cleaning
import re
from bs4 import BeautifulSoup
from typing import Tuple, List

def clean_content(raw_html: str) -> Tuple[str, List[str]]:
    """
    Cleans raw HTML/markdown content by:
    - Converting escaped newlines to real newlines
    - Extracting and returning unique non-media URLs from markdown and HTML anchors
    - Removing markdown link syntax but keeping anchor text
    - Stripping HTML tags
    - Removing excessive whitespace

    Args:
        raw_html (str): Raw content containing HTML and markdown.

    Returns:
        Tuple[str, List[str]]: Cleaned text and list of unique URLs (excluding media).
    """
    print("Text Cleaning.....")
    # Convert escaped '\n' sequences into actual newlines
    text = raw_html.replace("\\n", "\n")

    # Extract URLs from markdown links: (https://...)
    urls = re.findall(r'\((https?://[^\)]+)\)', text)

    # Extract URLs from HTML anchor tags: href="https://..."
    urls += re.findall(r'href=[\'"]?([^\'" >]+)', text)

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

    # Filter out URLs ending with common media file extensions
    media_extensions = (
        '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp',
        '.mp4', '.mp3', '.wav', '.avi', '.mov', '.wmv',
        '.m4a', '.flac', '.ogg', '.webm'
    )

    print("Data Clean Successfully...")
    return clean_text