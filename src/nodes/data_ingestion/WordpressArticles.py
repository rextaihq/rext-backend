import feedparser
import time
from datetime import datetime
from typing import List
from src.states.State import AgentState

from src.api.lib.logger import auto_logger

logger = auto_logger()

def wordpress_articles(state:AgentState):
    """
    WordpressArticles

    Fetches all available WordPress-related articles from popular RSS feeds:
    - WP Tavern
    - WordPress.org News
    - WPBeginner

    Returns:
        List[dict]: A list of articles where each article is a dictionary with the following fields:
            - title (str): The title of the article
            - link (str): The URL of the article
            - source (str): The source name (e.g., "WP Tavern")
            - published (datetime): The publication datetime of the article
            - summary (str): A short summary or snippet of the article (if available)

    Example:
        articles = FetchWordpressArticles()
        for article in articles:
            logger.info(article['title'], article['link'])
    """
    logger.info("Fetching wordpress articles...")
    config_instance = state['config']

    rss_sources = config_instance['WP_URL']
    
    logger.info("RSS Sources:", rss_sources)
    logger.info("RSS Type:", type(rss_sources))
    all_articles = []

    for source_name, url in rss_sources.items():
        logger.info("Loop Start...")
        logger.info("Source Name: ",source_name)
        logger.info("Source URL: ",url)
        try:
            feed = feedparser.parse(url)

            for entry in feed.entries:
                published = None
                if hasattr(entry, 'published_parsed'):
                    published = datetime.fromtimestamp(time.mktime(entry.published_parsed))

                article = {
                    "title": entry.title,
                    "link": entry.link,
                    "source": source_name,
                    "published": published,
                    "summary": entry.get("summary", "")
                }

                all_articles.append(article)
            return {
                    "articles": all_articles
                }
        except Exception as e:
            logger.info(f"[ERROR] Failed to fetch from {source_name}: {e}")
            return {
                "error":str(e)
            }

   