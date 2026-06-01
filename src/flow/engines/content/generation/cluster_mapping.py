import logging
from typing import Any

from src.flow.states.rext import REXT
from src.services.content_cluster_mapping_service import build_cluster_heading_map

logger = logging.getLogger(__name__)


def map_keyword_clusters(state: REXT) -> dict[str, Any]:
    content_state = state.get("content", {})
    seo_result = state.get("seo_result", {})
    serp_normalized = state.get("serp_normalized", {})

    content_type = content_state.get("content_type", "blog")
    topic = (
        content_state.get("selected_topic")
        or serp_normalized.get("query")
        or state.get("serp_payload", {}).get("query", "")
    )

    cluster_heading_map = build_cluster_heading_map(
        keyword_clusters=seo_result.get("keyword_clusters", []),
        topic=topic,
        content_type=content_type,
        questions=serp_normalized.get("questions", []),
    )

    if cluster_heading_map.get("enabled"):
        logger.info(
            "Mapped %d keyword clusters to heading structure for content_type=%s",
            len(cluster_heading_map.get("h2_sections") or []),
            cluster_heading_map.get("content_type"),
        )
    else:
        logger.info(
            "Keyword cluster heading mapping skipped: %s",
            cluster_heading_map.get("reason"),
        )

    return {
        "content": {
            "cluster_heading_map": cluster_heading_map,
        }
    }
