"""
Test runner for persona_discovery FIXED

Usage:
    python test_run_discovery.py https://example.com
    python test_run_discovery.py                       # uses default test URL
"""
import sys
import asyncio
import logging
import json
from pathlib import Path



# Automatically add current directory to Python module search path
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from persona_discovery import run_pipeline, MAX_CRAWL_ARTICLES

# Assuming this runs from the same directory
from persona_discovery import run_pipeline, MAX_CRAWL_ARTICLES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)


async def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "https://21stcenturyequipment.com/"
    
    logger.info(f"=" * 70)
    logger.info(f"PERSONA DISCOVERY - FIXED VERSION")
    logger.info(f"=" * 70)
    logger.info(f"Target: {target}")
    logger.info(f"Max articles: {MAX_CRAWL_ARTICLES}")
    logger.info(f"=" * 70)
    
    result = await run_pipeline(target, max_articles=MAX_CRAWL_ARTICLES)
    
    logger.info(f"\n" + "=" * 70)
    logger.info(f"RESULTS")
    logger.info(f"=" * 70)
    logger.info(f"Total personas found: {result['total_personas_found']}")
    logger.info(f"Timestamp: {result['timestamp']}")
    
    # Print summary table
    logger.info(f"\n{'Name':<30} {'Role':<20} {'Articles':<10} {'Sources':<30}")
    logger.info("-" * 90)
    
    for p in result['authors_and_team'][:20]:  # Show top 20
        name = p['name'][:29]
        role = (p['role'] or "")[:19]
        articles = str(p.get('article_count', 0))
        sources = ", ".join(p.get('sources', []))[:29]
        logger.info(f"{name:<30} {role:<20} {articles:<10} {sources:<30}")
    
    if result['total_personas_found'] > 20:
        logger.info(f"\n... and {result['total_personas_found'] - 20} more")
    
    logger.info(f"\n" + "=" * 70)
    

if __name__ == "__main__":
    asyncio.run(main())