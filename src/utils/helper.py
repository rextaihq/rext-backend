# === Standard library imports ===
import os
import re
import uuid
from typing import Any, Dict, List, Tuple

# === Third-party imports ===
import yaml
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig, CacheMode
from langchain_core.documents import Document
from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from langchain_cohere.rerank import CohereRerank
from pydantic import HttpUrl
from src.utils.url_validator import validate_url_for_ssrf, SSRFValidationError

# === Project-specific imports ===
from src.flow.model.llm_manager import load_model
from src.utils.splitter import split_data
from src.utils.vector_store import load_vector_store
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai import CacheMode
from src.api.lib.logger import auto_logger

logger = auto_logger()



def loadYamlConfig(file_path="config/config.yaml"):
    """
    Load a YAML configuration file and return its contents.

    :param file_path: Path to the YAML file.
    :return: Dictionary containing the YAML file contents.
    """
    try:
        with open(file_path, 'r') as file:
            config = yaml.safe_load(file)

        return config
    except Exception as e:
        return  str(e)


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
        logger.info(f"[ERROR] Failed to load browser configuration: {e}")
        return None
    
def GetCrawlerRunConfig():
    """
    Get the crawler run configuration for web scraping.

    :return: A CrawlerRunConfig object containing the crawler run configuration.
    """
    try:
        config = CrawlerRunConfig(
         word_count_threshold=200,
            remove_forms=True, # Optimization: remove forms
            prettiify=True,
            parser_type="lxml",
            excluded_tags=[ # Scripts & styles
            "script",
            "style",
            "noscript",

            # Embedded / non-text media
            "iframe",
            "object",
            "embed",
            "canvas",
            "svg",
            "math",

            # Audio / video
            "video",
            "audio",
            "source",
            "track",

            # Form elements (no SEO value)
            "form",
            "input",
            "textarea",
            "button",
            "select",
            "option",
            "label",
            "fieldset",
            "legend",

            # UI / interactive only
            "dialog",
            "details",
            "summary",
            "menu",
            "menuitem",

            # Ruby / annotation (rare SEO use)
            "ruby",
            "rt",
            "rp",

            # Misc non-content
            "param",
            "map",
            "area",
            "base"
            ],
            scraping_strategy=LXMLWebScrapingStrategy(),
            # # --- Navigation & Timing ---
            # wait_until="domcontentloaded",
            exclude_external_links=True,
            # Block entire domains
            exclude_social_media_domains=["facebook.com", "twitter.com","youtube.com","instagram.com","tiktok.com","linkedin.com","pinterest.com","reddit.com","telegram.org","whatsapp.com","signal.org","viber.com","snapchat.com"],

            # Media filtering
            exclude_external_images=True,
            exclude_social_media_links=True,
            simulate_user =True,
            magic=True,
            adjust_viewport_to_content=True,
            only_text=True,
        )
        return config
    except Exception as e:
        logger.info(f"[ERROR] Failed to load crawler run configuration: {e}")
        return None

# merge evulation
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

# Merge Context
def merge_contexts(existing: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
        Merge two lists of contexts by 'refine_title', combining their 'docs'.

        Args:
            existing: First list of context dicts.
            new: Second list of context dicts.

        Returns:
            A merged list where docs for the same 'refine_title' are aggregated.
    """
    merged = {}

    for item in (existing or []) + (new or []):
        title = item["refine_title"]
        docs = item.get("docs", [])
        if title not in merged:
            merged[title] = []
        merged[title].extend(docs)

    return [{"refine_title": t, "docs": d} for t, d in merged.items()]

async def web_page_scraper(urls: List[HttpUrl]) -> Tuple[List[Document], list]:
    """
    Asynchronously crawls given URLs and returns LangChain Documents with extracted content.

    Args:
        urls (List[HttpUrl]): List of URLs to crawl.

    Returns:
        Tuple[List[Document], list]: (Chunked Documents, Raw crawl results)

    Raises:
        SSRFValidationError: If any URL fails SSRF validation.
    """
    logger.info("Scraping started")
    browser_config = GetBrowserConfig()
    run_config = GetCrawlerRunConfig()

    # Validate all URLs for SSRF before scraping
    validated_urls = []
    for url in urls:
        url_str = str(url)
        validate_url_for_ssrf(url_str)
        validated_urls.append(url_str)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        results = await crawler.arun(url=validated_urls[0], config=run_config)
    logger.info("Scraping completed")

    documents = []
    for result in results:
        if result.success:
            doc = Document(
                page_content=result.markdown,
                metadata={
                    "id": str(uuid.uuid4()),
                    "url": result.url,
                    "title": result.metadata.get("title", "No title found"),
                    "description": result.metadata.get("description", "No description found"),
                    "keywords": result.metadata.get("keywords", "No keywords found"),
                    "summary": result.metadata.get("summary", "No summary found"),
                }
            )
            documents.append(doc)
        else:
            logger.warning(f"Scraping failed for {result.url}: {result.error_message}")

    chunks_data = split_data(documents)

    return chunks_data, results

# Content Cleaning
def clean_blog_content_with_urls(raw_html: str) -> Tuple[str, List[str]]:
    """
    Cleans raw HTML/markdown content by:
    - Converting escaped newlines to real newlines
    - Extracting and returning unique non-media URLs from markdown and HTML anchors
    - Removing Markdown link syntax but keeping anchor text
    - Stripping HTML tags
    - Removing excessive whitespace

    Args:
        raw_html (str): Raw content containing HTML and markdown.

    Returns:
        Tuple[str, List[str]]: Cleaned text and list of unique URLs (excluding media).
    """
    logger.info("Text Cleaning.....")
    # Convert escaped '\n' sequences into actual newlines
    text = raw_html.replace("\\n", "\n")

    # Extract URLs from markdown links: (https://...)
    urls = re.findall(r'\((https?://[^)]+)\)', text)

    # Extract URLs from HTML anchor tags: href="https://..."
    urls += re.findall(r'href=[\'"]?([^\'" >]+)', text)

    # Remove link syntax but keep anchor text only: [text](url) -> text
    text = re.sub(r'\[(.*?)]\((.*?)\)', r'\1', text)

    # Parse HTML and extract text only
    soup = BeautifulSoup(text, "html.parser")
    clean_text = soup.get_text()

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

    logger.info("Data Clean Successfully...")
    return clean_text, unique_urls


def get_multi_query():
    """
    Create a MultiQueryRetriever using an LLM and a FAISS vector store.

    This retriever expands the input query into multiple queries using the LLM,
    retrieves relevant documents for each expanded query, and combines them
    for better recall and retrieval quality.

    Returns:
        MultiQueryRetriever: A retriever that performs query expansion
                             and document retrieval using FAISS and an LLM.
    """
    return MultiQueryRetriever.from_llm(
        retriever=load_vector_store().as_retriever(), llm=load_model()
    )


from langchain_community.document_compressors import FlashrankRerank

def get_compressor():
    """
    Returns a FlashrankRerank document compressor for reranking retrieved documents.
    """
    compressor = CohereRerank(model="rerank-english-v3.0", api_key=os.getenv("COHERE_API_KEY"))
    return compressor