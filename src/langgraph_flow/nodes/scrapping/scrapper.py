from crawl4ai import AsyncWebCrawler, CacheMode
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
from src.langgraph_flow.states.content_state import ContentState
from src.utils.helper import GetBrowserConfig,GetCrawlerRunConfig
from langchain_core.documents import Document
from src.langgraph_flow.nodes.scrapping.clean_context import clean_content


async def scrape_content(state: ContentState) -> dict:
    """
    Scrapes full content from all URLs in state['urls'] using Crawl4AI.
    Returns LangChain Documents with cleaned content or error messages.
    """
    node_name = "ScrapeFullContent"
    print(f"\n🕷️ [{node_name}] Starting...")

    urls = state.get("urls", [])
    if not urls:
        error_msg = "No URLs provided in state"
        print(f"⚠️ {error_msg}")
        return {
            "context": [],
            "error": [{"node": node_name, "message": error_msg}]
        }

    try:
        browser_config = GetBrowserConfig()
        run_config = GetCrawlerRunConfig()

        async with AsyncWebCrawler(config=browser_config) as crawler:
            results = await crawler.arun_many(urls=urls, config=run_config)

        documents = []
        for result in results:
            if result.success:
                text = clean_content(result.markdown or "")
                documents.append(
                    Document(
                        page_content=text,
                        metadata={"url": result.url}
                    )
                )
            else:
                err_msg = result.error_message or "Unknown scraping error"
                print(f"❌ Scrape error for {result.url}: {err_msg}")
                documents.append(
                    Document(
                        page_content="",
                        metadata={"url": result.url, "error": err_msg}
                    )
                )

        return {"context": documents}

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ {error_msg}")
        return {
            "context": [],
            "error": [{"node": node_name, "message": error_msg}]
        }