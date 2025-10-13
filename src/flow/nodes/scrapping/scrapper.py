from crawl4ai import AsyncWebCrawler
from langchain_core.documents import Document
from src.flow.states.content_state import ContentState
from src.utils.helper import GetBrowserConfig, GetCrawlerRunConfig
from src.flow.nodes.scrapping.clean_context import clean_content
from src.flow.utils.progress_helper import update_node_progress
from langsmith import traceable, trace


@traceable(
    run_type="retriever",
    name="Scrape Web Content",
    metadata={
        "description": "Scrapes web pages using Crawl4AI and cleans text content.",
        "inputs": ["urls"],
        "outputs": ["context_documents"],
        "dependencies": ["Crawl4AI", "LangChain Document", "clean_content"],
        "category": "web_scraping"
    },
    tags=["Scraping", "Crawl4AI", "AsyncIO", "LangSmith"],
    project_name="WREXT"
)
async def scrape_content(state: ContentState) -> dict:
    """
    Scrapes full content from URLs in state['urls'] using Crawl4AI,
    traces all major stages with LangSmith.
    """
    node_name = "ScrapeFullContent"
    print(f"\n🕷️ [{node_name}] Starting scrape workflow...")

    payload = state.get("request_payload", {})

    # Update progress (50%)
    content_id = payload.get("content_id")
    if content_id:
        update_node_progress(content_id, "scraping_content")

    urls = state.get("urls", [])
    if not urls:
        error_msg = "No URLs provided in state"
        print(f"⚠️ {error_msg}")
        return {
            "context": [],
            "error": [{"node": node_name, "message": error_msg}]
        }

    try:
        # 1️⃣ Trace browser + run config loading
        with trace(name="Load Crawler Configs", run_type="setup") as config_trace:
            browser_config = GetBrowserConfig()
            run_config = GetCrawlerRunConfig()
            config_trace.end(outputs={
                "browser_config_loaded": bool(browser_config),
                "run_config_loaded": bool(run_config)
            })

        # 2️⃣ Trace crawling stage
        async with AsyncWebCrawler(config=browser_config) as crawler:
            with trace(name="Execute Crawl4AI", run_type="retriever", metadata={"urls_count": len(urls)}) as crawl_trace:
                results = await crawler.arun_many(urls=urls, config=run_config)
                crawl_trace.end(outputs={
                    "success_count": sum(1 for r in results if r.success),
                    "failed_count": sum(1 for r in results if not r.success)
                })

        # 3️⃣ Trace cleaning + document creation
        documents = []
        with trace(name="Process and Clean Results", run_type="data_processing") as clean_trace:
            for result in results:
                if result.success:
                    text = clean_content(result.markdown or "")
                    documents.append(Document(page_content=text, metadata={"url": result.url}))
                else:
                    err_msg = result.error_message or "Unknown scraping error"
                    print(f"❌ Scrape error for {result.url}: {err_msg}")
                    documents.append(
                        Document(page_content="", metadata={"url": result.url, "error": err_msg})
                    )
            clean_trace.end(outputs={"documents_created": len(documents)})

        print(f"✅ Successfully scraped {len(documents)} documents.")
        return {"context": documents}

    except Exception as e:
        error_msg = f"Unexpected error during scraping: {str(e)}"
        print(f"❌ {error_msg}")
        return {
            "context": [],
            "error": [{"node": node_name, "message": error_msg}]
        }