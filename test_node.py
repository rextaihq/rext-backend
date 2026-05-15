#!/usr/bin/env python3

import sys
import os
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.flow.engines.seo.keyword_clustering import keyword_clustering_node

async def test_node():
    # Mock state similar to the test
    state = {
        "serp_normalized": {
            "query": "test query",
            "results": [{"title": "Test", "snippet": "test content"}]
        },
        "seo_result": {},
        "serp_result": {},
        "serp_payload": {}
    }

    print("Calling keyword_clustering_node...")
    result = await keyword_clustering_node(state)
    print("Result:", result)
    print("Check /tmp/keyword_clusters for new files.")

if __name__ == "__main__":
    asyncio.run(test_node())