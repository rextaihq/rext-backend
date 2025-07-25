from src.states.State import AgentState
from crawl4ai import AsyncWebCrawler
from src.utils.helper import GetBrowserConfig
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig, CacheMode
import pandas as pd

async def get_relevant_articles(state: AgentState) -> AgentState:
    """
    Get relevant articles based on user selection.
    """
    try:
        print("Process Selectd Articles..")
        selected_arrticles = state.get('selected_articles', [])
        

        print("Scraping full content…")
        browser_config = BrowserConfig()
        run_config = CrawlerRunConfig(cache_mode=CacheMode.ENABLED)

        # Extract list of URLs from your DataFrame or list of dicts
        articles = state.get("combine_articles", [])
        urls_list = [a["full_links"] for a in articles]
        
        result_content = []
        for urls in urls_list:
            print("Scrapping Content....",urls)
            async with AsyncWebCrawler(config=browser_config) as crawler:
                results = await crawler.arun_many(urls=urls, config=run_config)

                result_content.append(results)
                
        # Pair each result back to the corresponding article
        for article, results in zip(articles, result_content):
            if len(results)>0:
                for result in results:
                    article['Raw Blog Content']+= f"\n\n first Blog Conten \n\n{result.markdown}"            
            

        # Update the state
        state["combine_articles"] = articles
        return state
    except Exception as e:
        state["error"] = str(e)
        return str(e)