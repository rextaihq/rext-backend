import logging
from src.flow.states.rext import REXT
from src.flow.engines.content.review.content.on_page_scoring import markdown_to_clean_html

logger = logging.getLogger(__name__)


async def calculate_eeat_trust(state: REXT):
    # get the content state form rext state
    content_state = state.get("content", {})
    final_content = content_state.get("final_content", {})

    title = final_content.get("title", "")
    primary_keyword = final_content.get("primary_keyword", "")
    secondary_keywords = final_content.get("secondary_keywords", [])
    introduction = final_content.get("introduction") or ""
    body_markdown = final_content.get("body_markdown") or ""

    full_markdown = f"{introduction}\n\n{body_markdown}".strip()
    if not full_markdown:
        logger.warning("No content available for E-E-A-T evaluation, skipping")
        return {}

    html_content = markdown_to_clean_html(full_markdown)

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