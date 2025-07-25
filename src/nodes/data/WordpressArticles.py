import feedparser
import time
from datetime import datetime
from typing import List, Dict
from src.states.State import AgentState
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
    rss_sources = loadYamlConfig().get("rss_sources", {})
    
    print("RSS Sources:", rss_sources)
    all_articles = []

    for source_name, url in rss_sources.items():
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
                break
            print("Articles Fetched from", source_name, ":", len(all_articles))
             # Add fetched articles to state
            print("Total articles fetched:", len(all_articles))
            state['wordpress_articles'] = all_articles
            return state
        except Exception as e:
            print(f"[ERROR] Failed to fetch from {source_name}: {e}")
            state['error'] = str(e)
            return str(e)

   