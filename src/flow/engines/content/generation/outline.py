import logging
from src.flow.states.wrext import WREXT
from src.flow.model.structure.outline import Outline
from src.flow.model.llm_manager import load_model
from src.flow.prompts.human.outline import get_outline_prompt

logger = logging.getLogger(__name__)


def generate_outline(state: WREXT):
    """
    Generates a content outline using an LLM.
    """

    # 1. Get query and context from state
    serp_payload = state.get("serp_payload", {})
    query = serp_payload.get("query")

    if not query:
        logger.error("No query found in state")
        return {
            "content": {
                **state.get("content", {}),
                "error": "No query found in serp_payload",
            }
        }

    logger.info(f"Generating outline for: {query}")

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
        outline_model = load_model().with_structured_output(Outline)
        prompt_template = get_outline_prompt()

        messages = prompt_template.format_messages(
            query=query,
            related_topics=", ".join(related_topics),
            questions="\n".join(f"- {q}" for q in questions),
            competitors_context="\n".join(competitors_context),
            intent_distribution=intent_distribution,
            rejected_reason=outline_rejected_reason,
        )

        # 🔒 Fail-fast guard
        for m in messages:
            assert "{query}" not in m.content, "Prompt variables not interpolated"

        logger.info("Outline prompt formatted successfully")

        generated_outline = outline_model.invoke(messages)
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
