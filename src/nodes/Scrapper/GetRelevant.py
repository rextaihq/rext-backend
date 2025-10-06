from src.states.State import AgentState
from crawl4ai import AsyncWebCrawler
# from src.utils.helper import GetBrowserConfig
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig, CacheMode
from langsmith import traceable

from src.api.lib.logger import auto_logger

logger = auto_logger()
# import pandas as pd

@traceable
async def get_relevant_articles(state: AgentState) -> AgentState:
    """
    Get relevant articles based on user selection.
    """
    try:
        logger.info("Process Selectd Articles..")
        # selected articles = state.get('selected_articles', [])
        

        logger.info("Scraping full content…")
        browser_config = BrowserConfig()
        run_config = CrawlerRunConfig(cache_mode=CacheMode.ENABLED)

        # Extract list of URLs from your DataFrame or list of dicts
        articles = state.get("selected_articles", [])
        urls_list = [a["full_links"] for a in articles]
        
        result_content = []
        for urls in urls_list:
            logger.info("Scrapping Content....",urls)
            async with AsyncWebCrawler(config=browser_config) as crawler:
                results = await crawler.arun_many(urls=urls, config=run_config)

                result_content.append(results)
                
        # Pair each result back to the corresponding article
        for article, results in zip(articles, result_content):
            if len(results)>0:
                for result in results:
                    article['Raw Blog Content']+= f"\n\n first Blog Content \n\n{result.markdown}"
            

        # Update the state
        state["selected_articles"] = articles
        return state
    except Exception as e:
        state["error"] = [{
            "error": str(e)
        }
        ]
        return state