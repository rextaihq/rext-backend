import logging

from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


def calculate_eeat_trust(state: REXT):
    # get the content state form rext state
    content_state = state.get("content", {})
    final_content = content_state.get("final_content", {})

    # get the full final content data
    title = final_content.get("title", "")
    body_markdown = final_content.get("body_markdown", "")
    # meta title
    meta_title = final_content.get("meta_title", "")
    # meta description
    meta_description = final_content.get("meta_description", "")
    # tags
    tags = final_content.get("tags", [])
    # primary keyword
    primary_keyword = final_content.get("primary_keyword", "")
    # secondary keywords
    secondary_keywords = final_content.get("secondary_keywords", [])

    from src.flow.engines.content.utils.eeat import calculate_eeat_trust_score

    # We need HTML content for better regex analysis
    html_content = final_content.get("html_content", "")
    
    # Run hybrid evaluation
    try:
        eeat_results = calculate_eeat_trust_score(
            html_content=html_content,
            metadata={
                "title": title,
                "primary_keyword": primary_keyword,
                "secondary_keywords": secondary_keywords
            }
        )
        
        # Return only the update delta for deep merging
        return {
            "content": {
                "review": {
                    "trust_score": eeat_results
                }
            }
        }
    except Exception as e:
        logger.error(f"E-E-A-T calculation node failed: {e}")
        return {}