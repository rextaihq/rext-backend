import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from src.flow.engines.content.review.content.on_page_scoring import (
    markdown_to_clean_html,
    wrap_full_html,
)
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


def _to_plain_data(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _to_plain_data(value.model_dump())
    if isinstance(value, dict):
        return {key: _to_plain_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain_data(item) for item in value]
    return value


def _get_field(data: Dict[str, Any], key: str, default: Any = None) -> Any:
    value = data.get(key, default)
    return _to_plain_data(value)


def _build_eeat_metadata(
    content_state: Dict[str, Any], final_content: Dict[str, Any]
) -> Dict[str, Any]:
    focus_keyphrase = (
        _get_field(final_content, "focus_keyphrase")
        or _get_field(final_content, "primary_keyword")
        or ""
    )

    return {
        "title": _get_field(final_content, "title", ""),
        "meta_title": _get_field(final_content, "meta_title", ""),
        "meta_description": _get_field(final_content, "meta_description", ""),
        "slug": _get_field(final_content, "slug", ""),
        "focus_keyphrase": focus_keyphrase,
        "primary_keyword": focus_keyphrase,
        "secondary_keywords": _get_field(final_content, "secondary_keywords", []),
        "keyphrase_density": _get_field(final_content, "keyphrase_density"),
        "tags": _get_field(final_content, "tags", []),
        "content_type": content_state.get("content_type"),
        "facts": _get_field(final_content, "facts", []),
        "outbound_links": _get_field(final_content, "outbound_links", []),
        "internal_links": _get_field(final_content, "internal_links", []),
        "images": _get_field(final_content, "images", []),
        "schema_markup": _get_field(final_content, "schema_markup"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _extract_schema_data(final_content: Dict[str, Any]) -> Any:
    schema = _get_field(final_content, "schema_markup")
    if isinstance(schema, dict):
        return schema.get("schema_data")
    return getattr(schema, "schema_data", None)


def _debug_print_eeat_html(html_content: str, metadata: Dict[str, Any]) -> None:
    if os.getenv("REXT_DEBUG_EEAT_HTML", "").lower() not in {"1", "true", "yes"}:
        return

    print("\n========== E-E-A-T HTML INPUT ==========")
    print(html_content)
    print("========== E-E-A-T METADATA ==========")
    print(
        {
            "title": metadata.get("title"),
            "content_type": metadata.get("content_type"),
            "focus_keyphrase": metadata.get("focus_keyphrase"),
            "fact_count": len(metadata.get("facts") or []),
            "outbound_link_count": len(metadata.get("outbound_links") or []),
            "has_schema_markup": bool(metadata.get("schema_markup")),
            "generated_at": metadata.get("generated_at"),
        }
    )
    print("========== END E-E-A-T INPUT ==========\n")


async def calculate_eeat_trust(state: REXT):
    content_state = state.get("content", {}) or {}
    final_content = _to_plain_data(content_state.get("final_content", {}) or {})

    title = final_content.get("title") or final_content.get("meta_title") or ""
    introduction = final_content.get("introduction") or ""
    body_markdown = final_content.get("body_markdown") or ""

    body_parts = []
    if title:
        body_parts.append(f"# {title}")
    if introduction:
        body_parts.append(introduction)
    if body_markdown:
        body_parts.append(body_markdown)

    full_markdown = "\n\n".join(body_parts).strip()
    if not full_markdown:
        logger.warning("No content available for E-E-A-T evaluation, skipping")
        return {}
    print("full markdown to pass in eaat:", full_markdown)
    html_body = markdown_to_clean_html(full_markdown)
    print("$$$$$$$$$$$$$$$$$$$$$$$$$$$")
    print("html body to pass in eaat:", html_body)
    print("$$$$$$$$$$$$$$$$$$$$$$$$$$$")
    metadata = _build_eeat_metadata(content_state, final_content)
    html_content = wrap_full_html(
        html_body=html_body,
        meta_title=metadata.get("meta_title") or metadata.get("title") or "",
        meta_description=metadata.get("meta_description") or "",
        slug=metadata.get("slug") or "",
        focus_keyphrase=metadata.get("focus_keyphrase") or "",
        schema_data=_extract_schema_data(final_content),
    )
    _debug_print_eeat_html(html_content, metadata)
    print("E-E-A-T html content input:", html_content)
    print("$$$$$$$$$$$$$$$$$$$$$$$$$$$")
    print("metadata html content input:", metadata)
    print("$$$$$$$$$$$$$$$$$$$$$$$$$$$")

    from src.flow.engines.content.utils.eeat import calculate_eeat_trust_score

    try:
        eeat_results = await calculate_eeat_trust_score(
            html_content=html_content,
            metadata=metadata,
        )
        print("E-E-A-T results:", eeat_results)

        return {
            "content": {
                "review": {
                    "trust_score": eeat_results,
                }
            }
        }
    except Exception as exc:
        logger.error("E-E-A-T calculation node failed: %s", exc, exc_info=True)
        return {}
