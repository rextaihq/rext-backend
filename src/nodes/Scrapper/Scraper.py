from crawl4ai import AsyncWebCrawler
# from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig, CacheMode
from src.utils.helper import GetBrowserConfig,GetCrawlerRunConfig
from src.states.State import AgentState
from langsmith import traceable
import pandas as pd
import asyncio
import os

@traceable
async def scrape_full_content(state: AgentState) -> AgentState:
    """
    ScrapeFullContent

    Loops through all combined articles and uses crawl4ai to scrape full page content.

    Updates each article in `state['filter_articles']` with:
    - 'scraped_markdown': full clean Markdown content
    - 'scrape_error': error string if scraping fails

    Returns:
        dict: The updated state with enhanced 'filter_articles' (scraped content included).
    """
    print("Scraping full content...")

    browser_config = GetBrowserConfig()
    run_config = GetCrawlerRunConfig()
   

    # Extract list of URLs from your DataFrame or list of dicts
    articles = state.get("filter_articles", [])
    print("Total Articles",len(articles))
    urls = [a["link"] for a in articles]
    print("Total URLs",len(urls))
    async with AsyncWebCrawler(config=browser_config) as crawler:
        results = await crawler.arun_many(urls=urls, config=run_config,)
        # arun_many returns a list of CrawlResult objects :contentReference[oaicite:1]{index=1}

    # Pair each result back to the corresponding article
    for article, result in zip(articles, results):
        if result.success:
            article["Raw Blog Content"] = result.markdown
        else:
            article["Raw Blog Content"] = ""

    print("Scraping completed.")
    df = pd.DataFrame(state['filter_articles'])

    print("Saving the full data in this path data/full_blog.csv")
    # Ensure directory exists in async-safe way
    await asyncio.to_thread(os.makedirs, "data", exist_ok=True)
    await asyncio.to_thread(df.to_csv, "data/full_blog.csv", index=False)

    return {
               "filter_articles": articles
        }