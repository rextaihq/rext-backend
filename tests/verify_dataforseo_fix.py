import asyncio
import logging
from src.flow.engines.seo.fetch_dataforseo_backlinks import get_dataforseo_data

logging.basicConfig(level=logging.INFO)

async def test_api():
    keyword = "unlimited wordpress support"
    print(f"\n--- Testing get_dataforseo_data for: {keyword} ---")
    data = await get_dataforseo_data(keyword)
    if data:
        print("✅ Data fetched successfully!")
        print(f"Keyword: {data.get('keyword')}")
        print(f"Main Intent: {data.get('main_intent')}")
        print(f"Search Volume: {data.get('search_volume')}")
    else:
        print("❌ No data fetched. API format might still be wrong.")

if __name__ == "__main__":
    asyncio.run(test_api())
