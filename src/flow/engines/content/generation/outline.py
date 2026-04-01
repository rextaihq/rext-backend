import logging

from src.flow.states.rext import REXT
from src.flow.model.llm_manager import load_model
from src.flow.engines.content.generation.config.base_prompt import BASE_PROMPT
from src.flow.engines.content.generation.config.blueprints import BLUEPRINTS
from src.flow.engines.content.generation.config.content_patterns import resolve_pattern
from src.flow.engines.content.generation.config.schema_router import PATTERN_TO_SCHEMA


logger = logging.getLogger(__name__)


async def generate_outline(state: REXT) -> dict:
    content_state = state.get("content", {})
    topic = content_state.get("selected_topic", "")
    content_type = content_state.get("content_type", "article")
    outline_state = content_state.get("outline", {})

    if not topic:
        logger.error("No topic found in state")
        return {
            "content": {
                **content_state,
                "error": "No topic found in state",
            }
        }

    pattern = resolve_pattern(content_type)
    blueprint = BLUEPRINTS.get(pattern, BLUEPRINTS["educational"])
    schema = PATTERN_TO_SCHEMA[pattern]

    serp_normalized = state.get("serp_normalized", {})
    related_topics = ", ".join(serp_normalized.get("related_topics", [])[:10]) or "None"
    questions = "\n".join(f"- {q}" for q in serp_normalized.get("questions", [])[:8]) or "- None"
    rejected_reason = outline_state.get("rejected_reason", "None") or "None"
    previous_outline = outline_state.get("sections", []) if isinstance(outline_state, dict) else []

    prompt = BASE_PROMPT.format(
        content_type=content_type,
        topic=topic,
        pattern=pattern,
        structure="\n".join(f"- {item}" for item in blueprint["structure"]),
        style=blueprint["style"],
        format_rules=blueprint.get("format_rules", {}),
        related_topics=related_topics,
        questions=questions,
        rejected_reason=rejected_reason,
        previous_outline=previous_outline,
    )

    try:
        model = load_model().with_structured_output(schema)
        result = await model.ainvoke(prompt)
        result_dict = result.model_dump()
        previous_iterations = outline_state.get("iteration_count", 0) if isinstance(outline_state, dict) else 0

        return {
            "content": {
                **content_state,
                "outline": {
                    **result_dict,
                    "status": "reviewing",
                    "rejected_reason": "",
                    "iteration_count": previous_iterations + 1,
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
