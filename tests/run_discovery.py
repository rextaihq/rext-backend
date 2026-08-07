cat > test_author_pipeline.py << 'EOF'
import asyncio
import json
from crawl4ai import AsyncWebCrawler
from src.config.crawler import CrawlerConfiguration
from author_discovery_production import run_pipeline

async def main():
    config = CrawlerConfiguration()
    browser_config = config.get_browser_config()
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await run_pipeline("https://www.wpbeginner.com/", crawler, max_articles=10)
        print(json.dumps(result, indent=2, default=str))

asyncio.run(main())
EOF