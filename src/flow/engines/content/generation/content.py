import logging
from src.flow.states.wrext import WREXT
from src.flow.model.llm_manager import load_model
from src.flow.model.structure.content import GeneratedContent
from src.flow.prompts.human.content import get_content_prompt
from src.flow.engines.content.generation.eeat_injection import get_eeat_persona

logger = logging.getLogger(__name__)


def generate_content(state: WREXT):
    """
    Generates content using an LLM.
    """
    print("Generating Content......")
    # 1. Get outline and context from state
    content_state = state.get("content")
    outline = content_state.get("outline")
    logger.info(f"Outline retrieved: {outline}")

    # 1. Get query and context from state
    serp_payload = state.get("serp_payload")
    query = serp_payload.get("query")
    logger.info(f"Query extracted: {query}")

    # 2. Get the relevant context from state
    relevant_context = state.get("relevant_context")
    logger.info(f"Number of relevant context chunks: {len(relevant_context)}")  # Debug

    # 3. Get the only page content of the relevant context
    page_content = "\n\n".join(
            chunk["chunk"]
            for chunk in relevant_context
            if "chunk" in chunk
        )
    logger.info(f"Page content length: {len(page_content.split())} words")  # Existing

    # prepare data for content generation
    data = {
        "query": query,
        "outline": outline,
        "persona": get_eeat_persona(),
        "reference_text": page_content,
    }
    logger.info(f"Data prepared for content generation: query length={len(str(query))}, "
                 f"persona keys={list(data['persona'].keys()) if isinstance(data['persona'], dict) else type(data['persona'])}, "
                 f"reference_text_words={len(page_content.split())}")  # New debug

    # 2. Load model and generate content
    try:
        content_model = load_model().with_structured_output(GeneratedContent)

        # Prepare context
        messages = get_content_prompt().format_messages(**data)
        logger.info(f"Number of messages sent to LLM: {len(messages)}")  # New debug

        # Invoke LLM 
        generated_content = content_model.invoke(messages)
        logger.info("Content generated successfully")
        logger.info(f"Generated content keys: {generated_content.model_dump().keys()}")  # New debug

        return {
            "content": {
               "outline": outline,
                "final_content": {
                    **generated_content.model_dump(),
                    "status": "reviewing",
                    "rejected_reason": ""
                },
                "status": "content_generation",
            }
        }

    except Exception as e:
        logger.exception(f"Error generating content: {str(e)}")
        return {"content": {**outline, "error": f"Generation failed: {str(e)}"}}