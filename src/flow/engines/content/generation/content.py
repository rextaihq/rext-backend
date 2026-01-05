import logging
from src.flow.states.wrext import WREXT
from src.flow.model.llm_manager import load_model
from src.flow.model.structure.content import GeneratedContent
from src.flow.prompts.human.content import get_content_prompt

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
        
        # Invoke LLM 
        generated_content = content_model.invoke(messages)
        logger.info("Content generated successfully")
        
        return {
            "content": {
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