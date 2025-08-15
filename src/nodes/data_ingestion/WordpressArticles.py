import feedparser
import time
from datetime import datetime
from typing import List, Dict
from src.states.State import AgentState,URLCONFIF
from src.utils.helper import loadYamlConfig

def wordpress_articles(state:AgentState) -> AgentState:
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
            print(article['title'], article['link'])
    """
    print("Fetching wordpress articles...")
    config_instance = state['config']

    rss_sources = config_instance['WP_URL']
    
    print("RSS Sources:", rss_sources)
    print("RSS Type:", type(rss_sources))
    all_articles = []

    for source_name, url in rss_sources.items():
        print("Loop Start...")
        print("Source Name: ",source_name)
        print("Source URL: ",url)
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
            print(f"[ERROR] Failed to fetch from {source_name}: {e}")
            return {
                "error":str(e)
            }

   