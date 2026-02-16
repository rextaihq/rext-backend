import logging
from src.flow.states.rext import REXT
from src.flow.model.structure.outline import Outline
from src.flow.model.llm_manager import load_model
from src.flow.prompts.human.outline import get_outline_prompt
DEFAULT_MAX_TOKENS = 4096

logger = logging.getLogger(__name__)


async def generate_outline(state: REXT):
    """
    Generates a content outline using an LLM.
    """

    # 1. Get topic and content type from state
    content_state = state.get("content", {})
    topic = content_state.get("selected_topic", "")
    content_type = content_state.get("content_type", "article")  # Default to article
    

    # if not topic:
    #     logger.error("No topic found in state")
    #     return {
    #         "content": {
    #             **state.get("content", {}),
    #             "error": "No topic found in state",
    #         }
    #     }

    logger.info(f"Generating outline for: {topic} (content type: {content_type})")

    serp_normalized = state.get("serp_normalized", {})
    seo_result = state.get("seo_result", {})
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

    intent_distribution = ", ".join(
        f"{k}: {v}" for k, v in seo_result.get("intent", {}).items()
    )

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
