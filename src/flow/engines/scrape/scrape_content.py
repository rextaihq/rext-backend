import logging
import re
from urllib.parse import urlparse
from typing import Dict, Any, List
from crawl4ai import AsyncWebCrawler
from langchain_core.documents import Document
from src.flow.engines.scrape.config.crawler_config import CrawlerConfiguration
from src.flow.states.wrext import WREXT
from src.services.seo_service import KeywordExtractor

logger = logging.getLogger(__name__)

def _extract_headings(markdown_text: str) -> List[str]:
    """Extracts headings (h1-h6) from markdown text."""
    if not markdown_text:
        return []
    # Match lines starting with #, ##, ###, etc.
    heading_pattern = r'^(#{1,6})\s+(.*)$'
    headings = re.findall(heading_pattern, markdown_text, re.MULTILINE)
    return [h[1].strip() for h in headings]

async def scrape_serp_content(state: WREXT) -> Dict[str, Any]:
    """
    Scrapes full content from SERP results using Crawl4AI.

    This function:
    1. Extracts URLs from the SERP results in the state.
    2. Configures the AsyncWebCrawler with appropriate settings.
    3. Performs concurrent scraping of all identified URLs.
    4. Processes the results, extracting markdown content and detailed link information.
    5. Returns a list of DocumentScrapeData objects containing the scraped content and metadata.

    Args:
        state (WREXT): The current state containing 'serp_result' and 'serp_payload'.

    Returns:
        Dict[str, Any]: A dictionary containing 'scrape_context' which is a list of DocumentScrapeData objects.
    """
    logger.info("Starting SERP content scraping process")

    serp_result = state.get("serp_result", {})
    organic = serp_result.get("organic_results", [])
    serp_payload = state.get("serp_payload", {})
    
    if not organic:
        logger.warning("No organic results found in state - exiting early")
        return {"scrape_context": {"documents": [], "total_documents": 0}}

    query = serp_payload.get("query")
    config = CrawlerConfiguration(query=query) 
    
    urls = [item.get("link") for item in organic if item.get("link")]
    logger.info(f"Queued {len(urls)} URLs for crawling based on query: '{query}'")

    browser_config = config.get_browser_config()
    run_config = config.get_run_config()

    scrape_data_list = []
    keyword_extractor = KeywordExtractor()

    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            logger.debug("Initializing AsyncWebCrawler and starting concurrent crawl")
            results = await crawler.arun_many(
                urls=urls[:], 
                config=run_config,
            )
            logger.info(f"Crawling completed for {len(results)} URLs")

        for idx, result in enumerate(results, start=1):
            url = result.url
            domain = urlparse(url).netloc.replace("www.", "")

            logger.debug(f"Processing result [{idx}/{len(results)}]: {url}")

            if result.success:
                text = result.markdown or result.text or ""
                content_length = len(text.strip())
                logger.debug(f"Successfully scraped {url} ({content_length} characters)")

                # Extract headings and keywords
                headings = _extract_headings(text)
                keyword_results = keyword_extractor.extract_keywords(text=text, top_n=15)
                keywords = [kw["keyword"] for kw in keyword_results]

                # Safely handle internal and external links
                internal_links = result.links.get('internal', []) if result.links else []
                external_links = result.links.get('external', []) if result.links else []

                links_detail = []
                for link in internal_links:
                    href = link.get("href", "N/A")
                    link_text = link.get("text", "No text")[:50]
                    intrinsic = link.get("intrinsic_score")
                    contextual = link.get("contextual_score")
                    total = link.get("total_score")
                    head_data = link.get("head_data", {})

                    links_detail.append({
                        "href": href,
                        "text": link_text,
                        "intrinsic_score": round(intrinsic, 2) if intrinsic is not None else None,
                        "contextual_score": round(contextual, 3) if contextual is not None else None,
                        "total_score": total,
                        "head_data": head_data,
                    })

                doc = Document(
                    page_content=text,
                    metadata={
                        "url": url,
                        "domain": domain,
                        "status": "success",
                        "links_detail": links_detail,
                        "length": content_length
                    }
                )
                
                scrape_data_list.append({
                    "document": doc,
                    "content_length": content_length,
                    "keywords": keywords,
                    "headings": headings
                })
            else:
                logger.error(f"Failed to scrape {url}: {result.error_message}")
                doc = Document(
                    page_content="",
                    metadata={
                        "url": url,
                        "domain": domain,
                        "status": "error",
                        "error_message": result.error_message,
                        "links_detail": []
                    }
                )
                scrape_data_list.append({
                    "document": doc,
                    "content_length": 0,
                    "keywords": [],
                    "headings": []
                })

    except Exception as e:
        logger.exception(f"An unexpected error occurred during the scraping process: {str(e)}")
        return {"scrape_context": {"documents": [], "total_documents": 0}}

    logger.info(f"Scraping finished. Successfully created {len(scrape_data_list)} context documents")
    return {
        "scrape_context": {
            "documents": scrape_data_list,
            "total_documents": len(scrape_data_list)
        }
    }