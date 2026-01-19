import requests
import json
import os
from dotenv import load_dotenv
from typing import Dict

# =========================
# 🔐 AUTH
# =========================
load_dotenv()

API_URL = os.getenv("DATAFORSEO_API_URL")
AUTH_HEADER = os.getenv("DATAFORSEO_AUTH_HEADER")

if not API_URL or not AUTH_HEADER:
    raise EnvironmentError("Missing DataForSEO environment variables")

headers = {
    "Authorization": f"Basic {AUTH_HEADER}",
    "Content-Type": "application/json"
}

# =========================
# 🚀 MAIN FUNCTION (SINGLE KEYWORD)
# =========================
def get_dataforseo_data(
    keyword: str,
    location_code: int = 2840,
    language_code: str = "en",
    include_serp_info: bool = True
) -> Dict:

    payload = [{
        "location_code": location_code,
        "language_code": language_code,
        "keywords": [keyword],   # ✅ single keyword wrapped in list
        "include_serp_info": include_serp_info
    }]

    response = requests.post(API_URL, headers=headers, json=payload)
    response.raise_for_status()

    data = response.json()

    items = data.get("tasks", [])[0].get("result", [])[0].get("items", [])

    if not items:
        return {}

    item = items[0]  # ✅ single keyword → first item

    backlinks_info = item.get("avg_backlinks_info", {})
    keyword_info = item.get("keyword_info", {})
    keyword_props = item.get("keyword_properties", {})
    intent_info = item.get("search_intent_info", {})
    serp_info = item.get("serp_info", {})

    serp_item_types = serp_info.get("serp_item_types", [])

    return {
        "keyword": item.get("keyword"),

        # Core metrics
        "search_volume": keyword_info.get("search_volume"),
        "keyword_difficulty": keyword_props.get("keyword_difficulty"),

        # Link metrics
        "backlinks": backlinks_info.get("backlinks", 0),
        "referring_domains": backlinks_info.get("referring_domains", 0),
        "dofollow_links": backlinks_info.get("dofollow", 0),

        # SERP features (bool)
        "images": "images" in serp_item_types,
        "videos": "videos" in serp_item_types,

        # Intent
        "main_intent": intent_info.get("main_intent"),
    }


    