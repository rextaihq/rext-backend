import requests
from datetime import datetime
from src.states.State import AgentState
from src.utils.helper import loadYamlConfig
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
load_dotenv()

def gnews_articles(state: AgentState) -> AgentState:
    """
    GNewsArticles

    Fetches technology-related news articles from the GNews API published in the last 48 hours.

    Returns:
        AgentState: Updated state with 'articles' (list of dicts) or 'error' key.
    """
    try:
        print("Fetching local articles from last 48 hours...")

        # Load API config
        config_instance = state['config']
        api_url =  "https://gnews.io/api/v4/top-headlines"
        print("GNew API URL: ",api_url)
        category = config_instance['category']
        language = config_instance['language']
        country = config_instance['country']
        api_key = os.getenv("GNEWS_API_KEY", "YOUR_GNEWS_API_KEY")

        # Calculate time range for last 48 hours in ISO 8601 format
        print("Country: ",country)
        print("Country: ",language)
        print("Country: ",category)

        now = datetime.utcnow()
        past_48_hours = now - timedelta(hours=48)
        now_str = now.isoformat() + "Z"
        past_str = past_48_hours.isoformat() + "Z"

        # Prepare API query params
        params = {
            "category": category,
            "country": country,
            "from": past_str,
            "to": now_str,
            "apikey": api_key
        }

        # Make the API request
        response = requests.get(api_url, params=params)

        if response.status_code == 200:
            data = response.json()
            raw_articles = data.get("articles", [])

            articles_list = []
            for item in raw_articles:
                published_at = item.get("publishedAt")
                published = (
                    datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ")
                    if published_at else None
                )

                articles_list.append({
                    "title": item.get("title", ""),
                    "link": item.get("url", ""),
                    "source": item.get("source", {}).get("name", "GNews"),
                    "published": published,
                    "summary": item.get("description", "")
                })
                break
            # Return the articles to the new top-level key
            print("G News Articles Fethes")
            return {
            "articles": articles_list
        }

        else:
            # return state
            return {
                    "error": [{"gnews_error": f"Error Occur in G news data getting: {response.status_code}"}]
                }


    except Exception as e:
        return {
                    "error": [{"gnews_exception": str(e)}]
                }