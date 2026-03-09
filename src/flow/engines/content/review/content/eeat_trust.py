import logging
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


async def calculate_eeat_trust(state: REXT):
    """Calculate E-E-A-T trust score for generated content.

    Uses a hybrid approach combining regex signal extraction
    and LLM qualitative analysis.
    """
    content_state = state.get("content", {})
    final_content = content_state.get("final_content", {})

    title = final_content.get("title", "")
    primary_keyword = final_content.get("primary_keyword", "")
    secondary_keywords = final_content.get("secondary_keywords", [])
    html_content = final_content.get("html_content", "")

    if not html_content:
        logger.warning("No HTML content available for E-E-A-T evaluation, skipping")
        return {}

    from src.flow.engines.content.utils.eeat import calculate_eeat_trust_score

    try:
        eeat_results = await calculate_eeat_trust_score(
            html_content=html_content,
            metadata={
                "title": title,
                "primary_keyword": primary_keyword,
                "secondary_keywords": secondary_keywords,
            },
        )

        return {
            "content": {
                "review": {
                    "trust_score": eeat_results,
                }
            }
        }
    except Exception as e:
        logger.error("E-E-A-T calculation node failed: %s", e, exc_info=True)
        return {}