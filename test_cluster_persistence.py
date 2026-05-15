#!/usr/bin/env python
"""
Test script to validate keyword cluster persistence functionality.
Run with: python test_cluster_persistence.py
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch
import numpy as np

async def test_cluster_persistence():
    """Test that clusters are persisted to disk."""
    print("=" * 80)
    print("TEST: Keyword Cluster Persistence")
    print("=" * 80)
    
    # Mock embeddings
    mock_embeddings_model = AsyncMock()
    
    async def mock_embed(texts):
        # Return embeddings (semantic groups)
        if isinstance(texts, str):
            texts = [texts]
        # Python-related keywords close to [1, 0, 0]
        if any("python" in t.lower() or "learn" in t.lower() or "tutorial" in t.lower() for t in texts):
            return [[0.9 + 0.01*i, 0.1, 0.0] for i in range(len(texts))]
        # JavaScript-related close to [0, 1, 0]
        return [[0.1, 0.9 + 0.01*i, 0.0] for i in range(len(texts))]
    
    mock_embeddings_model.aembed_documents = mock_embed
    
    # Patch and import service
    with patch("src.services.keyword_clustering_service.get_embedding", return_value=mock_embeddings_model):
        from src.services.keyword_clustering_service import KeywordClusteringService
        
        # Create service
        service = KeywordClusteringService()
        
        # Check resolved directory
        validation_dir = service._resolve_cluster_validation_dir()
        print(f"\n✓ Cluster validation directory: {validation_dir}")
        
        # Test data
        keywords = [
            {"keyword": "python programming", "score": 100},
            {"keyword": "learn python", "score": 95},
            {"keyword": "python tutorial", "score": 90},
            {"keyword": "javascript basics", "score": 80},
            {"keyword": "js tutorial", "score": 75},
        ]
        
        print(f"\n✓ Test keywords: {len(keywords)} keywords")
        for kw in keywords:
            print(f"  - {kw['keyword']} (score: {kw['score']})")
        
        # Run clustering
        print("\n⏳ Running cluster_keywords...")
        try:
            clusters = await service.cluster_keywords(
                keywords,
                seed_keyword="python",
                seed_intent="informational"
            )
            print(f"✓ Clustering complete: {len(clusters)} clusters created")
            for i, cluster in enumerate(clusters, 1):
                print(f"  Cluster {i}: {cluster['cluster_name']} (score: {cluster['total_score']})")
        except Exception as e:
            print(f"✗ Clustering failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # Check if files were created
        print("\n⏳ Checking for persisted files...")
        validation_dir.mkdir(parents=True, exist_ok=True)
        files = list(validation_dir.glob("keyword_clusters_*.json"))
        
        if not files:
            print(f"✗ No cluster files found in {validation_dir}")
            print(f"  Directory contents: {list(validation_dir.iterdir())}")
            return False
        
        print(f"✓ Found {len(files)} persisted file(s)")
        
        # Validate latest file
        latest_file = sorted(files)[-1]
        print(f"\n✓ Latest file: {latest_file.name}")
        
        try:
            content = json.loads(latest_file.read_text(encoding="utf-8"))
            print(f"✓ File parsed successfully")
            print(f"  - Created at: {content.get('created_at')}")
            print(f"  - Seed keyword: {content['source'].get('seed_keyword')}")
            print(f"  - Seed intent: {content['source'].get('seed_intent')}")
            print(f"  - Original count: {content['source'].get('original_keyword_count')}")
            print(f"  - Clusters: {len(content.get('clusters', []))}")
            print(f"  - Diagnostics: {content.get('diagnostics', {})}")
            return True
        except Exception as e:
            print(f"✗ Failed to parse file: {e}")
            return False

if __name__ == "__main__":
    result = asyncio.run(test_cluster_persistence())
    print("\n" + "=" * 80)
    if result:
        print("✓ TEST PASSED: Cluster persistence is working!")
    else:
        print("✗ TEST FAILED: Cluster persistence issue detected")
    print("=" * 80)
