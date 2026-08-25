"""Targeted quality-repair LangGraph node.

A single structured-output-only LLM call (no tools, no full agent
re-invocation) that fixes exactly the checks validate_content flagged.
Always loops back to validate_content (see router/content_quality.py's
validation_router) — bounded by MAX_REPAIR_ATTEMPTS (validation.py).
Soft-fails on any error: the attempt counter still increments so a
transient model failure can never create an infinite loop.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.model.llm_manager import load_content_model
from src.flow.model.structure.contents import get_generated_content_model
from src.flow.prompts.human.repair import get_repair_prompt
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


def _build_issues_block(failed_checks: list[dict]) -> str:
    if not failed_checks:
        return "(none)"
    return "\n".join(
        f"{i}. [{c.get('name')}] {c.get('detail')}" for i, c in enumerate(failed_checks, 1)
    )


def _build_sources_block(failed_checks: list[dict], searched_results: list[dict]) -> str:
    """Real search-tool results to draw a genuine replacement citation from.

    Without this, telling the model "this citation is fabricated, fix it"
    just produces a second fabrication — it needs real material to pick from.
    """
    needs_sources = any(c.get("name") == "facts_and_external_links" for c in failed_checks)
    if not needs_sources or not searched_results:
        return ""
    lines = ["AVAILABLE VERIFIED SOURCES — only use one of these to replace an unverifiable citation:"]
    for r in searched_results[:6]:
        lines.append(f"- URL: {r.get('url')}\n  TITLE: {r.get('title')}\n  EXCERPT: {(r.get('snippet') or '')[:400]}")
    return "\n".join(lines)


def _build_brand_block(failed_checks: list[dict], brand_context: Optional[dict]) -> str:
    brand_related = any(
        c.get("name") in ("brand_url_accuracy", "brand_presence", "brand_placement") for c in failed_checks
    )
    if not brand_related or not brand_context:
        return ""
    url_line = (
        f"Approved brand URL (use exactly this): {brand_context.get('brand_url')}"
        if brand_context.get("brand_url")
        else "No approved brand URL — mention as plain text only, do not invent one."
    )
    return f"BRAND CONTEXT — Brand: {brand_context.get('brand_name')}. {url_line}"


async def repair_content(state: REXT) -> dict:
    content_state = state.get("content") or {}
    final_content = content_state.get("final_content") or {}
    outline = content_state.get("outline") or {}
    content_type = content_state.get("content_type", "")
    review = content_state.get("review") or {}
    searched_results = (content_state.get("generation_meta") or {}).get("searched_results") or []

    validation = review.get("validation") or {}
    failed_checks = validation.get("failed_checks") or []
    attempt_number = review.get("repair_attempts", 0) + 1
    # deep_merge_dicts replaces lists wholesale rather than merging them, so
    # this must read the existing history and return the FULL appended list —
    # never a single-entry list, or prior attempts silently vanish.
    repair_history = list(review.get("repair_history") or [])

    updated_final_content = final_content
    targeted_checks = [c.get("name") for c in failed_checks]

    if not failed_checks:
        logger.info("repair_content: no failed checks to repair; passing through unchanged.")
    else:
        schema = get_generated_content_model(content_type)
        if schema is None:
            logger.warning("repair_content: no schema for content_type=%r; cannot repair.", content_type)
        else:
            spec = build_requirements_spec(outline, content_type)
            sources_block = "\n\n".join(
                filter(None, [
                    _build_sources_block(failed_checks, searched_results),
                    _build_brand_block(failed_checks, spec.get("brand_context")),
                ])
            )
            prompt_data = {
                "article_stage": "pre-humanization (raw draft — tone not yet finalized)",
                "issues_block": _build_issues_block(failed_checks),
                "sources_block": f"\n{sources_block}\n" if sources_block else "",
                "title": final_content.get("title") or "",
                "introduction": final_content.get("introduction") or "",
                "body_markdown": final_content.get("body_markdown") or "",
            }

            try:
                model = load_content_model().with_structured_output(schema)
                messages = get_repair_prompt().format_messages(**prompt_data)
                repaired_obj = await model.ainvoke(messages)
                repaired_payload = (
                    repaired_obj.model_dump() if hasattr(repaired_obj, "model_dump") else dict(repaired_obj)
                )
                # Merge onto the original rather than trusting every unrelated
                # field was echoed back verbatim, then re-validate through the
                # Pydantic model so enforce_internal_links_in_body re-applies.
                # model_dump() only covers schema fields, so bookkeeping keys
                # generate_content added outside the schema (status,
                # rejected_reason) are layered back on top afterward.
                merged = {**final_content, **repaired_payload}
                revalidated = schema.model_validate(merged)
                updated_final_content = {**merged, **revalidated.model_dump()}
                logger.info(
                    "repair_content: attempt %d succeeded, targeted_checks=%s",
                    attempt_number, targeted_checks,
                )
            except Exception:
                logger.exception(
                    "repair_content: attempt %d failed (model error) — keeping pre-repair "
                    "content; attempt counter still increments to bound the loop.",
                    attempt_number,
                )

    repair_history.append({
        "attempt": attempt_number,
        "targeted_checks": targeted_checks,
        "at": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "content": {
            **content_state,
            "final_content": updated_final_content,
            "review": {
                **review,
                "repair_attempts": attempt_number,
                "repair_history": repair_history,
            },
        }
    }
