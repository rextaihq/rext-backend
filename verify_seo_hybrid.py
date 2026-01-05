import sys
import os
import logging
from pprint import pprint

# Ensure src is in path
sys.path.append(os.getcwd())

from src.flow.engines.seo.seo_engine import create_seo_engine
from src.flow.states.wrext import WREXT

# Mock Data
mock_serp = {
    "query": "best running shoes",
    "normalize_results": [
        {"domain": "runnersworld.com", "title": "Best Running Shoes 2024", "url": "https://runnersworld.com/shoes", "snippet": "Top shoes for runners...", "position": 1},
        {"domain": "nike.com", "title": "Nike Running", "url": "https://nike.com/running", "snippet": "Just do it.", "position": 2},
        {"domain": "adidas.com", "title": "Adidas Running", "url": "https://adidas.com/running", "snippet": "Impossible is nothing.", "position": 3}
    ],
    "related_topics": ["marathon shoes", "trail running"],
    "questions": ["What is the best running shoe?"],
    "domains": ["runnersworld.com", "nike.com", "adidas.com"],
    "domain_stats": {
        "runnersworld.com": {"type": "publisher"},
        "nike.com": {"type": "brand"},
        "adidas.com": {"type": "brand"}
    },
    "features": {
        "people_also_ask": True,
        "top_stories": False
    }
}

mock_competitors = [
    {
        "domain": "runnersworld.com",
        "top_positions": [1],
        "intent_distribution": {"commercial": 0.8, "informational": 0.2},
        "freshness": {"recent": 1},
        "featured_snippet": True
    },
    {
        "domain": "nike.com",
        "top_positions": [2],
        "intent_distribution": {"transactional": 0.9},
        "freshness": {"recent": 0}
    },
    {
        "domain": "adidas.com",
        "top_positions": [3],
        "intent_distribution": {"transactional": 0.9},
        "freshness": {"recent": 0}
    }
]

mock_scrape_context = {
    "documents": [
        {"headings": ["Best Running Shoes", "How to choose running shoes"], "content_length": 2000},
        {"headings": ["Nike Air Zoom", "Buy Now"], "content_length": 500}
    ]
}

def verify():
    print("Initializing SEO Engine...")
    app = create_seo_engine()

    state = WREXT(
        serp_normalized=mock_serp,
        competitors=mock_competitors,
        scrape_context=mock_scrape_context,
        seo_result={} # Empty start
    )

    print("Running Engine...")
    # Run the graph
    try:
        final_state = app.invoke(state)
        
        result = final_state.get("seo_result", {})
        
        print("\n" + "="*50)
        print("VERIFICATION OF SEO RESULT KEYS")
        print("="*50)
        
        keys_to_check = [
            "keyword_difficulty",
            "content_gaps",
            "seo_opportunity",
            "extracted_keywords",
            "title_recommendations"
        ]
        
        all_passed = True
        for key in keys_to_check:
            if key in result and result[key]:
                print(f"✅ {key}: Present")
                # pprint(result[key])
            else:
                print(f"❌ {key}: MISSING or EMPTY")
                all_passed = False

        print("\nDetails for Keyword Difficulty Breakdown:")
        if "keyword_difficulty" in result:
             pprint(result["keyword_difficulty"].get("breakdown"))

        print("\nDetails for Opportunity:")
        if "seo_opportunity" in result:
             pprint(result["seo_opportunity"])

        if all_passed:
            print("\nSUCCESS: All expected keys are present.")
        else:
            print("\nFAILURE: Some keys are missing.")
            
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify()
