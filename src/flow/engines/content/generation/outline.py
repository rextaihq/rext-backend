import logging
from src.flow.states.wrext import WREXT
from src.flow.model.structure.outline import Outline
from src.flow.model.llm_manager import load_model
from src.flow.prompts.system.outline import OUTLINE_GENERATION_PROMPT
from langchain.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

def generate_outline(state: WREXT):
    """
    Generates a content outline using an LLM.
    """
    # 1. Get query and context from state
    serp_payload = state.get("serp_payload", {})
    query = serp_payload.get("query")
    
    # Get the outline rejected reason if exists (for iterative improvement)
    content_state = state.get("content", {})
    outline_state = content_state.get("outline", {})
    outline_rejected_reason = outline_state.get("rejected_reason")
    
    if not query:
        logger.error("No query found in state")
        return {"content": {**content_state, "error": "No query found in serp_payload"}}

    logger.info(f"Generating outline for: {query}")
    
    # 2. Load model and generate outline
    try:
        outline_model = load_model().with_structured_output(Outline)
        
        # Prepare context
        messages = [
            SystemMessage(content=OUTLINE_GENERATION_PROMPT),
            HumanMessage(content=f"Primary Query: {query} Rejected Reason: {outline_rejected_reason}")
        ]
        
        # Invoke LLM
        generated_outline = outline_model.invoke(messages)
        outline_dict = generated_outline.model_dump()
        logger.info("Outline generated successfully")
        
        return {
            "content": {
                **content_state,
                "outline": {
                    **outline_dict,
                    "rejected_reason": "",
                    "status": "reviewing"
                },
                "status": "planning"
            }
        }
        
    except Exception as e:
        logger.exception(f"Error generating outline: {str(e)}")
        return {"content": {**content_state, "error": f"Generation failed: {str(e)}"}}