import logging
from urllib.parse import urlparse
from typing import Dict, Any, List
from crawl4ai import AsyncWebCrawler
from langchain_core.documents import Document
from src.flow.engines.scrape.config.crawler_config import CrawlerConfiguration
from src.flow.states.wrext import WREXT

logger = logging.getLogger(__name__)

async def scrape_serp_content(state: WREXT) -> Dict[str, Any]:
    """
    Scrapes full content from SERP results using Crawl4AI.

    This function:
    1. Extracts URLs from the SERP results in the state.
    2. Configures the AsyncWebCrawler with appropriate settings.
    3. Performs concurrent scraping of all identified URLs.
    4. Processes the results, extracting markdown content and detailed link information.
    5. Returns a list of Document objects containing the scraped content and metadata.

    Args:
        state (WREXT): The current state containing 'serp_result' and 'serp_payload'.

    Returns:
        Dict[str, Any]: A dictionary containing 'scrape_context' which is a list of Document objects.
    """
    logger.info("Starting SERP content scraping process")

    serp_result = state.get("serp_result", {})
    organic = serp_result.get("organic_results", [])
    serp_payload = state.get("serp_payload", {})

    if not organic:
        logger.warning("No organic results found in state - exiting early")
        return {"scrape_context": []}

    query = serp_payload.get("query")
    config = CrawlerConfiguration(query=query) 

    
    urls = [item.get("link") for item in organic if item.get("link")]
    logger.info(f"Queued {len(urls)} URLs for crawling based on query: '{query}'")

    browser_config = config.get_browser_config()
    run_config = config.get_run_config()

    documents = []

    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            logger.debug("Initializing AsyncWebCrawler and starting concurrent crawl")
            results = await crawler.arun_many(urls=urls[:3], config=run_config)
            logger.info(f"Crawling completed for {len(results)} URLs")

        for idx, result in enumerate(results, start=1):
            url = result.url
            domain = urlparse(url).netloc.replace("www.", "")

            logger.debug(f"Processing result [{idx}/{len(results)}]: {url}")

            if result.success:
                text = result.markdown or result.text or ""
                content_length = len(text.strip())
                logger.debug(f"Successfully scraped {url} ({content_length} characters)")

                # Safely handle internal and external links
                internal_links = result.links.get('internal', []) if result.links else []
                external_links = result.links.get('external', []) if result.links else []

                # Filter links with head data
                links_with_head = [link for link in internal_links if link.get("head_data") is not None]
                logger.debug(f"Extracted {len(internal_links)} internal and {len(external_links)} external links for {url}")

                links_detail = []
                for link in links_with_head[:]:
                    href = link.get("href", "N/A")
                    link_text = link.get("text", "No text")[:50]
                    intrinsic = link.get("intrinsic_score")
                    contextual = link.get("contextual_score")
                    total = link.get("total_score")
                    head_data = link.get("head_data", {})

                    title = head_data.get("title", "No title")
                    description = head_data.get("meta", {}).get("description", "No description")
                    status = link.get("head_extraction_status", "unknown")

                    links_detail.append({
                        "href": href,
                        "text": link_text,
                        "intrinsic_score": round(intrinsic, 2) if intrinsic is not None else None,
                        "contextual_score": round(contextual, 3) if contextual is not None else None,
                        "total_score": total,
                        "head_data": head_data,
                        "title": title,
                        "description": description,
                        "status": status
                    })

                documents.append(
                    Document(
                        page_content=text,
                        metadata={
                            "url": url,
                            "domain": domain,
                            "status": "success",
                            "links_detail": links_detail
                        }
                    )
                )
            else:
                logger.error(f"Failed to scrape {url}: {result.error_message}")
                documents.append(
                    Document(
                        page_content="",
                        metadata={
                            "url": url,
                            "domain": domain,
                            "status": "error",
                            "error_message": result.error_message,
                            "links_detail": []
                        }
                    )
                )

    except Exception as e:
        logger.exception(f"An unexpected error occurred during the scraping process: {str(e)}")
        return {"scrape_context": []}

    logger.info(f"Scraping finished. Successfully created {len(documents)} context documents")
    return {"scrape_context": documents}