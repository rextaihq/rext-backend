# Standard library imports
import os
import re
from typing import Dict, List, Tuple

# Third-party imports
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# Project-specific / local imports
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig, CacheMode
from langgraph_sdk import get_sync_client
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
import torch
load_dotenv()


def loadYamlConfig(file_path="config/config.yaml"):
    """
    Load a YAML configuration file and return its contents.

    :param file_path: Path to the YAML file.
    :return: Dictionary containing the YAML file contents.
    """

    with open(file_path, 'r') as file:
        config = yaml.safe_load(file)
    
    return config


def GetBrowserConfig():
    """
    Get the browser configuration for web scraping.

    :return: A dictionary containing the browser configuration.
    """
    try:
        config = BrowserConfig(
            headless=True,
            # use_managed_browser=True,
            verbose=False,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/115.0.0.0 Safari/537.36",
            browser_type="chromium"
        )
        return config
    except Exception as e:
        print(f"[ERROR] Failed to load browser configuration: {e}")
        return None
    
def GetCrawlerRunConfig():
    """
    Get the crawler run configuration for web scraping.

    :return: A CrawlerRunConfig object containing the crawler run configuration.
    """
    try:
        config = CrawlerRunConfig(
        cache_mode=CacheMode.ENABLED,
            word_count_threshold=100,        # Minimum words per content block
            exclude_external_links=True,    # Remove external links
            remove_overlay_elements=True,   # Remove popups/modals
            process_iframes=True,
            exclude_external_images=True,
        exclude_social_media_domains=True,
        only_text=True,           # Only text content
        # verbose=False,
        )
        return config
    except Exception as e:
        print(f"[ERROR] Failed to load crawler run configuration: {e}")
        return None


def get_client():
    # Initialize LangGraph client
    client = get_sync_client(
        url="http://localhost:8123/",
        api_key=os.getenv('LANGSMITH_API_KEY')
    )
    return client

def merge_evaluations(a: Dict[str, List[int]], b: Dict[str, List[int]]) -> Dict[str, List[int]]:
    """
    Merges two dictionaries containing lists of evaluation results.
    Assumes keys are evaluation names (e.g., 'relevance_rating') and values are lists of scores/weights.
    """
    merged = dict(a)  # start with first dict
    for key, val_list in b.items():
        if key in merged:
            # Extend the existing list with the new list
            merged[key].extend(val_list)
        else:
            merged[key] = val_list
    return merged



def get_embedder():
    """Return a lightweight SentenceTransformer embedder."""
    if torch.cuda.is_available():
        return SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2',device="cpu")
    else:
        return SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2',device="cpu")

def get_hf_embedding():
    """Return a HuggingFace embedding model for retrieval tasks."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    try:
        return HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en",
            model_kwargs={"device": 'cpu'}
        )
    except RuntimeError:
        # fallback to CPU if CUDA fails
        return HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en",
            model_kwargs={"device": "cpu"}
        )

# Content Cleaning
def clean_blog_content_with_urls(raw_html: str) -> Tuple[str, List[str]]:
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

    # Filter out URLs ending with common media file extensions
    media_extensions = (
        '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp',
        '.mp4', '.mp3', '.wav', '.avi', '.mov', '.wmv',
        '.m4a', '.flac', '.ogg', '.webm'
    )
    urls = [u for u in urls if not u.lower().endswith(media_extensions)]

    # Deduplicate URLs while preserving order
    seen = set()
    unique_urls = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    print("Data Clean Successfully...")
    return clean_text, unique_urls

def Splitting(text,chunk_size=5000,chunk_overlap=200):
    print("Splitting.....")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        is_separator_regex=False,
    )
    chunks_text = text_splitter.create_documents([text])
    print("Spltting Done")
    return chunks_text