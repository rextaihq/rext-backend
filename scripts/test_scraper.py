
import asyncio
from src.utils.helper import web_page_scraper
from pydantic import HttpUrl

async def test_scraper():
    url = "https://revnix.com"
    try:
        chunks, results = await web_page_scraper(urls=[url])
        print(f"Scraped {len(chunks)} chunks.")
        print(f"Results type: {type(results)}")
        if isinstance(results, list):
             print(f"Number of results: {len(results)}")
    except Exception as e:
        print(f"Scraper failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_scraper())
