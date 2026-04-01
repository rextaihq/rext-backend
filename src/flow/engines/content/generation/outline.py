import logging

from src.flow.states.rext import REXT
from src.flow.model.llm_manager import load_model
from src.flow.engines.content.generation.config.base_prompt import BASE_PROMPT
from src.flow.engines.content.generation.config.blueprints import BLUEPRINTS
from src.flow.engines.content.generation.config.content_patterns import resolve_pattern
from src.flow.engines.content.generation.config.schema_router import PATTERN_TO_SCHEMA

from pydantic import ValidationError

from src.flow.model.llm_manager import load_model
from src.flow.model.structure.outline_schemas import get_outline_schema, validate_outline_quality
from src.flow.model.structure.outlines.postprocess import post_process_outline
from src.flow.prompts.human.outline import get_outline_prompt, normalize_content_type
from src.flow.states.rext import REXT

DEFAULT_MAX_TOKENS = 4096

logger = logging.getLogger(__name__)


async def generate_outline(state: REXT) -> dict:
    content_state = state.get("content", {})
    topic = content_state.get("selected_topic", "")
    content_type = content_state.get("content_type", "article")
    outline_state = content_state.get("outline", {})
    content_type = normalize_content_type(content_state.get("content_type", "blog")) or "blog"

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
    serp_normalized = state.get("serp_normalized", {})
    seo_result = state.get("seo_result", {})
    serp_backlinks = seo_result.get("serp_backlinks", {})
    content_state = state.get("content", {})
    outline_state = content_state.get("outline", {})

    outline_rejected_reason = outline_state.get("rejected_reason", "None")
    iteration_count = int(outline_state.get("iteration_count", 0) or 0)

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

    intent_distribution = serp_backlinks.get("main_intent", "informational")

    try:
        model = load_model().with_structured_output(schema)
        result = await model.ainvoke(prompt)
        result_dict = result.model_dump()
        previous_iterations = outline_state.get("iteration_count", 0) if isinstance(outline_state, dict) else 0
        SchemaClass = get_outline_schema(content_type)
        outline_model = load_model(max_tokens=DEFAULT_MAX_TOKENS).with_structured_output(
            SchemaClass
        )
        prompt_template = get_outline_prompt(content_type=content_type)

        content_type_guidelines = CONTENT_TYPE_GUIDELINES.get(content_type, DEFAULT_GUIDELINE)

        messages = prompt_template.format_messages(
            content_type=content_type,
            content_type_guidelines=content_type_guidelines,
            topic=topic,
            related_topics=", ".join(related_topics),
            questions="\n".join(f"- {q}" for q in questions),
            competitors_context="\n".join(competitors_context),
            intent_distribution=intent_distribution,
            rejected_reason=outline_rejected_reason,
            previous_outline=outline_state,
        )

        # 🔒 Fail-fast guard
        for m in messages:
            assert "{topic}" not in m.content, "Prompt variables not interpolated"

        logger.info("Outline prompt formatted successfully")

        generated_outline_raw = await outline_model.ainvoke(messages)
        generated_outline = post_process_outline(content_type, generated_outline_raw)
        validate_outline_quality(content_type, generated_outline)
        outline_dict = generated_outline.model_dump()

        logger.info("Outline generated successfully")

        return {
            "content": {
                **content_state,
                "outline": {
                    **result_dict,
                "error": "",
                "outline": {
                    **outline_dict,
                    "iteration_count": iteration_count,
                    "rejected_reason": "",
                    "status": "reviewing",
                    "rejected_reason": "",
                    "iteration_count": previous_iterations + 1,
                },
                "status": "planning",
            }
        }

    except (ValueError, ValidationError) as e:
        # Auto-reject so the workflow can loop without bothering the user.
        logger.warning("Outline auto-rejected; regenerating (%s)", str(e))
        return {
            "content": {
                **content_state,
                "error": "",
                "outline": {
                    **outline_state,
                    "iteration_count": iteration_count + 1,
                    "status": "rejected",
                    "auto_rejected": True,
                    "message": "Outline auto-rejected; regenerating.",
                    "rejected_reason": f"Auto-validation failed: {str(e)}",
                },
                "status": "planning",
            }
        }
    except Exception as e:
        # Unexpected failure (API, network, infra). Keep error for observability.
        logger.exception("Error generating outline")
        return {
            "content": {
                **content_state,
                "outline": {
                    **outline_state,
                    "iteration_count": iteration_count + 1,
                    "status": "rejected",
                    "auto_rejected": True,
                    "message": "Outline generation failed; regenerating.",
                    "rejected_reason": f"Generation failed: {str(e)}",
                },
                "error": f"Generation failed: {str(e)}",
            }
        }
