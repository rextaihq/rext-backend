# === Standard library imports ===
import os
import re
import uuid
import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

# === Third-party imports ===
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig, CacheMode
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.retrievers.multi_query import MultiQueryRetriever
from pydantic import HttpUrl

# === Project-specific imports ===
from src.model.model import load_model
from src.utils.splitter import split_data
from src.utils.vector_store import load_vector_store

load_dotenv()

SECRET_KEY= os.getenv("SECRET_KEY")
ALGORITHM= os.getenv("ALGORITHM")
REFRESH_SECRET_KEY = os.getenv('REFRESH_SECRET_KEY')
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/user/login")

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
        process_iframes=False,
        exclude_external_images=True,
        exclude_social_media_domains=[],
        only_text=True,
        )
        return config
    except Exception as e:
        print(f"[ERROR] Failed to load crawler run configuration: {e}")
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
        url (List[HttpUrl]): List of URLs to crawl.

    Returns:
        Tuple[List[Document], list]: (Chunked Documents, Raw crawl results)
    """

    print("Scrapping Stattes")
    browser_config = GetBrowserConfig()
    run_config = GetCrawlerRunConfig()

    # if len(url)
    urls = [str(url) for url in urls]
    async with AsyncWebCrawler(config=browser_config) as crawler:
        results = await crawler.arun(url=urls[0], config=run_config)
    print("DOne")
    documents = []
    for result in results:
        if result.success:
            # Crawl4AI already gives some metadata
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
            print(f"Scraping failed for {result.url}: {result.error_message}")

    # Split into chunks
    chunks_data = split_data(documents)

    return chunks_data, results

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

    print("Data Clean Successfully...")
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

# Encrypt Password
def hash_password(password: str) -> str:
    """
    Hashes a plain text password using bcrypt.

    Args:
        password (str): The plain text password.

    Returns:
        str: The hashed password.
    """
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

# verify password
def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verifies that a plain text password matches the hashed password.

    Args:
        password (str): The plain text password.
        hashed_password (str): The hashed password from the database.

    Returns:
        bool: True if the password matches, False otherwise.
    """
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

# Create Access Token
def create_access_token(data: dict, expires_delta: timedelta = timedelta(hours=24)) -> str:
    """
    Creates a JWT access token.

    Args:
        data (dict): The payload to include in the token.
        expires_delta (timedelta, optional): Token expiration time. Defaults to 1 hour.

    Returns:
        str: The JWT token.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token

# Refresh token
def create_refresh_token(data: dict, expires_delta: timedelta = timedelta(days=7)) -> str:
    """Creates a long-lived refresh token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)

# verify password
def verify_token(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Verifies the JWT token and decodes the payload.

    Args:
        token (str): JWT token passed via the Authorization header.

    Raises:
        HTTPException: If token is invalid or expired.

    Returns:
        dict: The decoded payload.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        exp = payload.get("exp")
        if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )