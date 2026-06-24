import logging
from datetime import datetime, timezone
from typing import Any, Dict

from src.flow.model.structure.outlines import normalize_content_type
from src.flow.states.rext import REXT
from src.utils.credit_manager import STAGE_CREDITS, consume_stage_credits, InsufficientCreditsError, _emit_credit_event

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


def _assemble_markdown(final_content: Dict[str, Any]) -> str:
    title = final_content.get("title") or final_content.get("meta_title") or ""
    introduction = final_content.get("introduction") or ""
    body_markdown = final_content.get("body_markdown") or ""

    parts = []
    if title:
        parts.append(f"# {title}")
    if introduction:
        parts.append(introduction)
    if body_markdown:
        parts.append(body_markdown)

    return "\n\n".join(parts).strip()


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
        "content_type": normalize_content_type(content_state.get("content_type")),
        "facts": _get_field(final_content, "facts", []),
        "outbound_links": _get_field(final_content, "outbound_links", []),
        "internal_links": _get_field(final_content, "internal_links", []),
        "images": _get_field(final_content, "images", []),
        "schema_markup": _get_field(final_content, "schema_markup"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def calculate_eeat_trust(state: REXT):
    content_state = state.get("content", {}) or {}
    final_content = _to_plain_data(content_state.get("final_content", {}) or {})

    full_markdown = _assemble_markdown(final_content)
    if not full_markdown:
        logger.warning("No content available for E-E-A-T evaluation, skipping")
        return {}

    # Deduct eeat_optimization credit before LLM scoring call
    _user_id = (state.get("serp_payload") or {}).get("user_id")
    try:
        await consume_stage_credits(_user_id, STAGE_CREDITS["eeat_optimization"], "eeat_optimization")
    except InsufficientCreditsError as e:
        _emit_credit_event(e.available, e.stage, e.required, step="credits.exhausted")
        return {}

    metadata = _build_eeat_metadata(content_state, final_content)

    from src.flow.engines.content.utils.eeat import calculate_eeat_trust_score

    try:
        eeat_results = await calculate_eeat_trust_score(
            markdown_content=full_markdown,
            metadata=metadata,
        )
        print("E-E-A-T results:", eeat_results)
        if not eeat_results:
            return {}

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