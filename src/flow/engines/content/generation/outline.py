import logging
from src.flow.states.rext import REXT
from src.flow.model.structure.outline import Outline
from src.flow.model.llm_manager import load_model
from src.flow.prompts.human.outline import get_outline_prompt
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
    topic = content_state.get("selected_topic", "")
    content_type = content_state.get("content_type", "article")

    if not topic:
        logger.error("No topic found in state")
        return {
            "content": {
                **content_state,
                "error": "No topic found in state",
            }
        }
    logger.info("Generating outline for: %s (content type: %s)", topic, content_type)


    logger.info(f"Generating outline for: {topic} (content type: {content_type})")

    serp_normalized = state.get("serp_normalized", {})
    seo_result = state.get("seo_result", {})
    serp_backlinks = seo_result.get("serp_backlinks", {})
    content_state = state.get("content", {})
    outline_state = content_state.get("outline", {})

    outline_rejected_reason = outline_state.get("rejected_reason", "None")

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

    # 3. Generate outline
    try:
        outline_model = load_model(max_tokens=DEFAULT_MAX_TOKENS).with_structured_output(Outline)
        prompt_template = get_outline_prompt()

        messages = prompt_template.format_messages(
            content_type=content_type,
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

        generated_outline = await outline_model.ainvoke(messages)
        outline_dict = generated_outline.model_dump()

        logger.info("Outline generated successfully")

        return {
            "content": {
                "outline": {
                    **outline_dict,
                    "rejected_reason": "",
                    "status": "reviewing",
                },
                "status": "planning",
            }
        }

    except Exception as e:
        logger.exception("Error generating outline")
        return {
            "content": {
                "error": f"Generation failed: {str(e)}",
            }
        }
