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
from src.utils.url_validator import validate_url_for_ssrf

#for scraping many pages
from src.utils.multi_page_scraper import discover_relevant_links, scrape_extra_pages

# === Project-specific imports ===
from src.flow.model.llm_manager import load_model
from src.utils.splitter import split_data
from src.utils.vector_store import load_vector_store
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from src.api.lib.logger import auto_logger
from src.config.crawler import CrawlerConfiguration

#imports from content_qulaity.py
from src.utils.content_quality import assess_content_quality, build_thin_content_document

logger = auto_logger()


async def web_page_scraper(urls: List[HttpUrl]) -> Tuple[List[Document], list]:
    """
        Asynchronously crawls given URLs and returns LangChain Documents with extracted content.

        Args:
            urls (List[HttpUrl]): List of URLs to crawl.

        Returns:
            Tuple[List[Document], list]: (Chunked Documents, Raw crawl results)

        Raises:
    : If any URL fails SSRF validation.
    """
    logger.info("Scraping started")
    config = CrawlerConfiguration()
    browser_config = config.get_browser_config()
    run_config = config.get_run_config()

    # Validate all URLs for SSRF before scraping
    validated_urls = []
    for url in urls:
        url_str = str(url)
        validate_url_for_ssrf(url_str)
        validated_urls.append(url_str)

    #async with AsyncWebCrawler(config=browser_config) as crawler:
    #    results = await crawler.arun(url=validated_urls[0], config=run_config)
    #logger.info("Scraping completed")

    async with AsyncWebCrawler(config=browser_config) as crawler:
        results = await crawler.arun(url=validated_urls[0], config=run_config)

        # Discover and scrape secondary pages (about/team/etc) for richer
        # brand voice and persona extraction. Non-fatal if this fails.
        extra_content = ""
        try:
            homepage_result = results[0] if isinstance(results, list) else results
            if homepage_result.success and homepage_result.html:
                extra_links = discover_relevant_links(homepage_result.html, validated_urls[0])
                if extra_links:
                    extra_content = await scrape_extra_pages(crawler, extra_links, run_config)
        except Exception as e:
            logger.warning(f"Secondary page discovery/scrape failed: {e}")

    logger.info("Scraping completed")

    documents = []
    for result in results:
        if result.success:
            assessment = assess_content_quality(result)
            if assessment["is_thin"]:
                documents.append(build_thin_content_document(result, assessment))
                continue

            doc = Document(
                page_content=result.markdown + ("\n\n" + extra_content if extra_content else ""),
               
                metadata={
                    "id": str(uuid.uuid4()),
                    "url": result.url,
                    "title": result.metadata.get("title", "No title found"),
                    "description": result.metadata.get("description", "No description found"),
                    "keywords": result.metadata.get("keywords", "No keywords found"),
                    "summary": result.metadata.get("summary", "No summary found"),
                },
            )
            documents.append(doc)
        else:
            logger.warning(f"Scraping failed for {result.url}: {result.error_message}")

    chunks_data = split_data(documents)

    return chunks_data, results

    #documents = []
    #for result in results:
    #    if result.success:
    #        doc = Document(
    #            page_content=result.markdown,
    #            metadata={
    #                "id": str(uuid.uuid4()),
    #                "url": result.url,
    #                "title": result.metadata.get("title", "No title found"),
    #                "description": result.metadata.get("description", "No description found"),
    #                "keywords": result.metadata.get("keywords", "No keywords found"),
    #                "summary": result.metadata.get("summary", "No summary found"),
    #            },
    #        )
    #        documents.append(doc)
    #    else:
    #        logger.warning(f"Scraping failed for {result.url}: {result.error_message}")

    chunks_data = split_data(documents)

    return chunks_data, result