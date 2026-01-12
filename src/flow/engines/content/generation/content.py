import logging
import json
from src.flow.states.wrext import WREXT
from src.flow.model.llm_manager import load_model
from src.flow.model.structure.content import GeneratedContent
from src.flow.prompts.human.content import get_content_prompt
from src.flow.engines.content.generation.eeat_injection import get_eeat_persona

logger = logging.getLogger(__name__)

def generate_content(state: WREXT):
    """
    Generates SEO content using an LLM, integrating outline, context, and EEAT persona.
    """
    try:
        # 1️⃣ Get content state and outline
        content_state = state.get("content", {})
        topic = content_state.get("selected_topic", "")

        # if not topic:
        #     logger.error("No topic found in state")
        #     return {
        #         "content": {
        #             **state.get("content", {}),
        #             "error": "No topic found in state",
        #         }
        #     }

        logger.info(f"Generating content for: {topic}")

        
        outline = content_state.get("outline", {})
        if not outline:
            logger.warning("No outline found in state. Proceeding without it.")
        outline_str = json.dumps(outline, indent=2) if outline else "NO OUTLINE FOUND"

        logger.info(f"Outline extracted: {outline_str}")

        # 3️⃣ Get relevant context
        relevant_context = state.get("relevant_context", [])
        page_content = "\n\n".join(
            chunk.get("chunk", "") for chunk in relevant_context
        )
        logger.info(f"Page content length: {len(page_content.split())} words")

        # 5️⃣ Prepare prompt data
        prompt_data = {
            "topic": topic,
            "outline": outline_str,
            "reference_text": page_content,
        }

        # 6️⃣ Load model and prepare messages
        content_model = load_model().with_structured_output(GeneratedContent)
        messages = get_content_prompt().format_messages(**prompt_data)
        logger.info(f"Number of messages sent to LLM: {len(messages)}")

        # 7️⃣ Invoke LLM
        generated_content = content_model.invoke(messages)
        content_dict = generated_content.model_dump()
        logger.info(f"Content generated successfully. Keys: {content_dict.keys()}")

        # 8️⃣ Return structured content
        return {
            "content": {
                "outline": outline,
                "final_content": {
                    **content_dict,
                    "status": "reviewing",
                    "rejected_reason": ""
                },
                "status": "content_generation"
            }
        }

    except Exception as e:
        logger.exception(f"Error generating content: {str(e)}")
        return {
            "content": {
                **content_state,
                "error": f"Generation failed: {str(e)}"
            }
        }
