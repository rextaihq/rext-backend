import asyncio
import logging
from src.flow.engines.scrape.scrape_content import scrape_serp_content

# Configure logging
logging.basicConfig(level=logging.DEBUG)

async def test_scrape():
    # Mock state
    urls = [
        "https://www.wisoftsolutions.com/services/wordpress-development-dubai",
        "https://svdigital.ae/wordpress-development-dubai/",
        "https://www.royex.ae/services/wordpress-development-company-in-dubai/",
        "https://number9.ae/wordpress-development-services/",
        "https://zentroa.com/wordpress-development-dubai/",
        "https://www.digitalgravity.ae/services/web-development/wordpress-development-dubai/",
        "https://netarabia.ae/services/wordpress-development-services/",
        "https://www.vsourz.com/content-management-system/wordpress-development/",
        "https://redberries.ae/services/wordpress-development-company-in-dubai/",
        "https://www.fiverr.com/categories/programming-tech/website-development/wordpress-development"
    ]
    
    organic_results = [{"link": url} for url in urls]
    
    state = {
        "serp_result": {"organic_results": organic_results},
        "serp_payload": {"query": "wordpress development dubai"}
    }
    
    print("Starting scrape test...")
    result = await scrape_serp_content(state)
    print(f"Scrape completed. Documents: {len(result['scrape_context']['documents'])}")
    for doc in result['scrape_context']['documents']:
        print(f"Scraped {doc['document'].metadata['url']} - Length: {doc['content_length']}")

if __name__ == "__main__":
    asyncio.run(test_scrape())
