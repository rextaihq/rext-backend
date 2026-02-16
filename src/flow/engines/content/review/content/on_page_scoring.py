"""
On-Page SEO Scoring Node
"""

import logging
from typing import Dict
from src.flow.states.rext import REXT
from src.flow.engines.content.utils.utils import calculate_seokar

logger = logging.getLogger(__name__)


def calculate_on_page_seo(state: REXT) -> Dict:
    """
    LangGraph node to calculate on-page SEO metrics using Seokar
    and store them as SeokarSEOState.
    """
    logger.info("Starting on-page SEO scoring")

    # ---- Safely extract content ----
    content_state = state.get("content", {})
    # Check for upstream errors — skip review if content generation failed
    if content_state.get("error"):
        logger.warning(
            "Skipping on-page SEO calculation due to upstream error: %s",
            content_state["error"],
        )
        return {}
    content_type = content_state.get("content_type")
    final_content = content_state.get("final_content")

    if not final_content:
        logger.warning("Final content not found, skipping SEO analysis")
        return {}

    html_content = final_content.get("html_content")

    if not html_content:
        logger.warning("HTML content missing, skipping SEO analysis")
        return {}

    # ---- Run Seokar ----
    try:
        seokar_state = calculate_seokar(
            html_content=html_content or final_content.get("body_markdown"),
            title=final_content.get("meta_title") or final_content.get("title"),
            meta_description=final_content.get("meta_description"),
            slug=final_content.get("slug"),
            schema_markup=final_content.get("schema_markup"),
            focus_keyphrase=final_content.get("focus_keyphrase"),
            content_type=content_type
        )
    except Exception as e:
        logger.exception("Seokar SEO analysis failed")
        return {
            "content": {
                "review": {
                    "on_page_metrics": None
                }
            },
            "error": str(e)
        }

    # ---- Return LangGraph-compatible state update ----
    return {
        "content": {
            "review": {
                "on_page_metrics": seokar_state
            }
        }
    }
