#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.flow.engines.seo.keyword_clustering import _persist_keyword_clusters

# Test data
clusters = [
    {
        "cluster_name": "test cluster",
        "keywords": [{"keyword": "test", "score": 100}],
        "total_score": 100
    }
]
seed_keyword = "test seed"

print("Calling _persist_keyword_clusters...")
_persist_keyword_clusters(clusters, seed_keyword)
print("Done. Check /tmp/keyword_clusters for files.")