import requests
from datetime import datetime
from src.states.State import AgentState
from src.utils.helper import loadYamlConfig
from dotenv import load_dotenv
import os
load_dotenv()

def gnews_articles(state:AgentState)->AgentState:
    """
    GNewsArticles

    Fetches technology-related news articles from the GNews API for Pakistan.

    Returns:
        List[dict]: A list of articles where each article is a dictionary with the following fields:
            - title (str): The article title
            - link (str): The article URL
            - source (str): The source name (e.g., 'GNews')
            - published (datetime): The publication datetime
            - summary (str): A short description of the article

        Returns an empty list if the request fails or no articles are found.
        If an exception occurs, returns a string with the error message.

    Example:
        articles = FetchArticles()
        for article in articles:
            print(article['title'], article['link'])
    """
    try:
        print("Fetching local articles...")
        config = loadYamlConfig()
        api_url = config.get("GNews", {}).get("url", "https://gnews.io/api/v4/top-headlines")
        params = {
            "category": config.get("GNews", {}).get("category", "technology"),
            "country": config.get("GNews", {}).get("country", "pk"),
            "apikey": os.getenv("GNEWS_API_KEY", "YOUR_GNEWS_API_KEY")
        }

        response = requests.get(api_url, params=params)

        if response.status_code == 200:
            data = response.json()
            raw_articles = data.get("articles", [])

            articles = []
            for item in raw_articles:
                published_at = item.get("publishedAt")
                published = (
                    datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ")
                    if published_at else None
                )

                articles.append({
                    "title": item.get("title", ""),
                    "link": item.get("url", ""),
                    "source": item.get("source", {}).get("name", "GNews"),
                    "published": published,
                    "summary": item.get("description", "")
                })
                break


            # return articles
            return {'articles':articles}
        else:
            return []
    except Exception as e:
        state['error'] = str(e)
        return str(e)
