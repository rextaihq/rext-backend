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
    # 1. Get outline and context from stats
    content_state = state.get("content", {})
    print("Content State: ", content_state)

    outline = content_state.get("outline", {})
    print("Outline: ", outline)

    # 1. Get query and context from stats
    serp_payload = state.get("serp_payload", {})
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

    import json
    
    # prepare data for content generation
    # Ensure outline is a string for the prompt
    outline_str = json.dumps(outline, indent=2) if outline else "NO OUTLINE FOUND"
    
    data = {
        "query": query,
        "outline": outline_str,
        "title": outline.get("title", "")
    }
    
    logger.info(f"Generating content using Title: '{data['title']}'")
    # logger.info(f"Outline Payload: {outline_str[:500]}...") # Log start of outline

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