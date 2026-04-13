import logging
from typing import Any, List

from langchain_core.messages import HumanMessage

from src.flow.states.rext import REXT
from src.flow.model.structure.outlines import get_outline_model
from src.flow.model.llm_manager import load_model
from src.flow.prompts.human.outline import get_outline_guidance, get_outline_prompt
from src.flow.model.structure.content_types import normalize_content_type
DEFAULT_MAX_TOKENS = 4096

logger = logging.getLogger(__name__)


async def generate_outline(state: REXT) -> dict:
    """Generate a content outline using an LLM.

    Uses the selected topic, content type, SERP context, competitor
    insights, and SEO intent data to produce a structured outline via
    LLM structured output. If the outline was previously rejected,
    the rejection reason is included in the prompt for revision.

    Args:
        state: REXT state containing ``content.selected_topic``,
            ``content.content_type``, ``serp_normalized``, ``seo_result``,
            ``competitors``, and optionally ``content.outline.rejected_reason``.

    Returns:
        dict: State update with ``content.outline`` and ``content.status``
        set to ``"planning"``, or error state on failure.
    """
    content_state = state.get("content", {})
    topic = content_state.get("selected_topic")
    try:
        content_type = normalize_content_type(content_state.get("content_type") or "blog")
    except ValueError as e:
        logger.error("Invalid content_type in state: %s", e)
        return {
            "content": {
                **content_state,
                "error": str(e),
            }
        }
    content_state["content_type"] = content_type

    if not topic:
        logger.error("No topic found in state")
        return {
            "content": {
                **content_state,
                "error": "No topic found in state",
            }
        }
    logger.info("Generating outline for: %s (content type: %s)", topic, content_type)

    serp_normalized = state.get("serp_normalized", {})
    seo_result = state.get("seo_result", {})
    serp_backlinks = seo_result.get("serp_backlinks", {})
    outline_state = content_state.get("outline", {})

    outline_rejected_reason = outline_state.get("rejected_reason", "None")
    iteration_count = int(outline_state.get("iteration_count", 0)) + 1

    # 2. Normalize SERP context for LLM
    related_topics = serp_normalized.get("related_topics", [])
    questions = serp_normalized.get("questions", [])

    competitors = state.get("competitors", [])[:5]
    competitors_context = [
        f"Domain: {c.get('domain')} | Intent: "
        + ", ".join(
            f"{k}:{v}"
            for k, v in (c.get("intent_distribution") or {}).items()
        )
        for c in competitors
    ]

    intent_distribution = serp_backlinks.get("main_intent", "Informational")
    
    # 2b. Format Keyword Clusters for prompt (if available)
    keyword_clusters = seo_result.get("keyword_clusters", [])
    clusters_context = "None"
    if keyword_clusters:
        clusters_context = "\n".join([
            f"- Topic Bucket: {c.get('cluster_name')}\n  Supporting Keywords: {', '.join([k.get('keyword') for k in c.get('keywords', [])[:8]])}"
            for c in keyword_clusters
        ])
    

    # 3. Generate outline
    try:
        # 1. Select the correct Pydantic model for this content type
        model_schema = get_outline_model(content_type)
        
        outline_model = load_model(max_tokens=DEFAULT_MAX_TOKENS).with_structured_output(model_schema)
        prompt_template = get_outline_prompt()
        required_keys = ", ".join(model_schema.model_json_schema().get("required", []))
        content_type_guidance = get_outline_guidance(content_type)

        messages = prompt_template.format_messages(
            content_type=content_type,
            required_keys=required_keys,
            content_type_guidance=content_type_guidance,
            topic=topic,
            related_topics=", ".join(related_topics),
            questions="\n".join(f"- {q}" for q in questions),
            competitors_context="\n".join(competitors_context),
            intent_distribution=intent_distribution,
            keyword_clusters=clusters_context,
            rejected_reason=outline_rejected_reason,
            previous_outline=outline_state,
        )

        # 🔒 Fail-fast guard
        for m in messages:
            assert "{topic}" not in m.content, "Prompt variables not interpolated"

        logger.info("Outline prompt formatted successfully")

        last_error: Exception | None = None
        outline_dict = None

        # Retry a few times with explicit repair instructions (models sometimes slip tool JSON).
        for attempt in range(1, 4):
            try:
                attempt_messages: List[Any] = list(messages)
                if last_error is not None:
                    attempt_messages.append(
                        HumanMessage(
                            content=(
                                "Your previous output did not validate against the Outline schema.\n"
                                f"Error: {type(last_error).__name__}: {last_error}\n"
                                "Fix the JSON to exactly match the schema and return ONLY JSON."
                            )
                        )
                    )

                generated_outline = await outline_model.ainvoke(attempt_messages)
                outline_dict = generated_outline.model_dump()
                if outline_dict.get("content_type") != content_type:
                    raise ValueError(
                        "content_type mismatch: "
                        f"expected={content_type!r} got={outline_dict.get('content_type')!r}"
                    )
                break
            except Exception as e:
                last_error = e
                logger.warning("Outline attempt %d/3 failed: %s", attempt, str(e))

        if outline_dict is None and last_error is not None:
            raise last_error
        
        # Persist the selected topic as the outline title
        outline_dict["title"] = topic

        logger.info("Outline generated successfully")

        return {
            "content": {
                **content_state,
                "outline": {
                    **outline_dict,
                    "rejected_reason": "",
                    "iteration_count": iteration_count,
                    "status": "reviewing",
                },
                "status": "planning",
            }
        }

    except Exception as e:
        logger.exception("Error generating outline")
        return {
            "content": {
                **content_state,
                "error": f"Generation failed: {str(e)}",
            }
        }
