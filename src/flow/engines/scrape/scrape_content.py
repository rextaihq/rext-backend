import logging
import re
from urllib.parse import urlparse
from typing import Dict, Any, List

from crawl4ai import AsyncWebCrawler
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.flow.engines.scrape.config.clean_content import clean_content
from src.flow.engines.scrape.config.crawler_config import CrawlerConfiguration
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


def _extract_headings(markdown_text: str) -> List[str]:
    """Extract h1–h6 headings from markdown text."""
    if not markdown_text:
        return []

    pattern = r'^(#{1,6})\s+(.*)$'
    matches = re.findall(pattern, markdown_text, re.MULTILINE)
    return [heading.strip() for _, heading in matches]


def _chunk_document(
    doc: Document,
    chunk_size: int = 800,
    chunk_overlap: int = 150,
) -> List[Document]:
    """
    Split a document into overlapping text chunks while
    preserving metadata.
    """
    if not doc.page_content:
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    texts = splitter.split_text(doc.page_content)

    chunks: List[Document] = []
    total_chunks = len(texts)

    for idx, text in enumerate(texts):
        chunks.append(
            Document(
                page_content=text,
                metadata={
                    **doc.metadata,
                    "chunk_index": idx,
                    "chunk_total": total_chunks,
                },
            )
        )

    return chunks


async def scrape_serp_content(state: REXT) -> Dict[str, Any]:
    """
    Scrape full content from SERP URLs, extract headings,
    and chunk each document for downstream processing.
    """
    logger.info("Starting SERP content scraping")

    serp_result = state.get("serp_result", {})
    organic_results = serp_result.get("organic_results", [])
    serp_payload = state.get("serp_payload", {})
    competitors = state.get("competitors", [])

    if not organic_results:
        logger.warning("No organic SERP results found")
        return {"scrape_context": {"documents": [], "total_documents": 0}}

    query = serp_payload.get("query")
    crawler_config = CrawlerConfiguration(query=query)

    urls = [item["link"] for item in organic_results if item.get("link")]
    logger.info("Queued %d URLs for crawling", len(urls))

    browser_config = crawler_config.get_browser_config()
    run_config = crawler_config.get_run_config()

    scrape_data_list = []

    # Domain → best rank position map
    domain_rank_map = {
        comp["domain"]: min(comp["top_positions"])
        for comp in competitors
        if comp.get("domain") and comp.get("top_positions")
    }

    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            results = await crawler.arun_many(urls=urls, config=run_config)

        for idx, result in enumerate(results, start=1):
            parsed_domain = urlparse(result.url).netloc.lower()
            domain = parsed_domain.replace("www.", "")
            rank_position = domain_rank_map.get(domain)

            logger.debug(
                "Processing [%d/%d]: %s", idx, len(results), result.url
            )

            if not result.success:
                logger.error("Failed to scrape %s: %s", result.url, result.error_message)
                doc = Document(
                    page_content="",
                    metadata={
                        "url": result.url,
                        "domain": domain,
                        "rank_position": rank_position,
                        "status": "error",
                        "error_message": result.error_message,
                        "links_detail": [],
                    },
                )

                scrape_data_list.append({
                    "document": doc,
                    "content_length": 0,
                    "keywords": [],
                    "headings": [],
                    "chunks": [],
                    "chunk_count": 0,
                })
                continue

            text = clean_content(result.markdown or result.text or "")
            content_length = len(text.strip())

            headings = _extract_headings(text)
            keywords = []  # intentionally empty (SEO engine responsibility)

            internal_links = result.links.get("internal", []) if result.links else []

            links_detail = []
            for link in internal_links:
                links_detail.append({
                    "href": link.get("href"),
                    "text": (link.get("text") or "")[:50],
                    "intrinsic_score": (
                        round(link["intrinsic_score"], 2)
                        if link.get("intrinsic_score") is not None
                        else None
                    ),
                    "contextual_score": (
                        round(link["contextual_score"], 3)
                        if link.get("contextual_score") is not None
                        else None
                    ),
                    "total_score": link.get("total_score"),
                    "head_data": link.get("head_data", {}),
                })

            doc = Document(
                page_content=text,
                metadata={
                    "url": result.url,
                    "domain": domain,
                    "rank_position": rank_position,
                    "status": "success",
                    "length": content_length,
                    "links_detail": links_detail,
                },
            )

            # 🔹 CHUNKING HAPPENS HERE
            chunks = _chunk_document(doc)

            scrape_data_list.append({
                "document": doc,
                "content_length": content_length,
                "keywords": keywords,
                "headings": headings,
                "chunks": chunks,
                "chunk_count": len(chunks),
            })

    except Exception as exc:
        logger.exception("Scraping failed: %s", exc)
        return {"scrape_context": {"documents": [], "total_documents": 0}}

    logger.info("Scraping completed: %d documents", len(scrape_data_list))

    return {
        "scrape_context": {
            "documents": scrape_data_list,
            "total_documents": len(scrape_data_list),
        }
    }