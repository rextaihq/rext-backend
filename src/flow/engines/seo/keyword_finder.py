from typing import Dict, Any
from src.flow.states.wrext import WREXT
from src.services.seo_service import KeywordExtractor

def keyword_finder(state: WREXT) -> Dict[str, Any]:
    """
    LangGraph node: Extract keywords from SERP data using N-grams + TF-IDF.
    
    This implements the classic SEO keyword extraction approach used by
    early Ahrefs and SEMrush - combining NLTK n-gram generation with
    TF-IDF scoring to identify valuable keywords from SERP data.
    """
    serp_normalized = state.get("serp_normalized")
    
    if not serp_normalized:
        return {
            "seo_result": {
                "extracted_keywords":{
                    "all": [],
                    "head": [],
                    "body": [],
                    "long_tail": [],
                    "total_count": 0,
                    "query": "",
                    "extraction_method": "nltk_ngram_tfidf",
                    "sources": {
                        "titles": 0,
                        "snippets": 0,
                        "related_topics": 0,
                        "questions": 0
                    }
                },
                "keyword_difficulty": {
                    "keywords": [],
                    "difficulty_level": "medium",
                    "serp_competition": 0,
                    "authority_barrier": "low",
                }
            }
        }
    
    # Extract data from normalized SERP
    query = serp_normalized.get("query", "")
    normalize_results = serp_normalized.get("normalize_results", [])
    related_topics = serp_normalized.get("related_topics", [])
    questions = serp_normalized.get("questions", [])
    
    # Initialize extractor and extract keywords
    extractor = KeywordExtractor()
    keywords = extractor.extract_keywords(
        normalize_results=normalize_results,
        related_topics=related_topics,
        questions=questions,
        query=query,
        top_n=50
    )
    
    # Categorize keywords by type
    head_keywords = [k for k in keywords if k["type"] == "head"]
    body_keywords = [k for k in keywords if k["type"] == "body"]
    longtail_keywords = [k for k in keywords if k["type"] == "long-tail"]
    
    # Build keyword difficulty state (for SEORESULT compatibility)
    keyword_difficulty = {
        "keywords": [k["keyword"] for k in keywords[:10]],
        "difficulty_level": "medium",
        "serp_competition": len(normalize_results) if normalize_results else 0,
        "authority_barrier": "medium",
    }
    
    return {
        "seo_result": {
            "extracted_keywords": {
                "all": keywords,
                "head": head_keywords,
                "body": body_keywords,
                "long_tail": longtail_keywords,
                "total_count": len(keywords),
                "query": query,
                "extraction_method": "nltk_ngram_tfidf",
                "sources": {
                    "titles": len(normalize_results) if normalize_results else 0,
                    "snippets": len(normalize_results) if normalize_results else 0,
                    "related_topics": len(related_topics) if related_topics else 0,
                    "questions": len(questions) if questions else 0
                }
            },
            "keyword_difficulty": keyword_difficulty
        }
    }

