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
    
    serp_normalized = state.get("serp_normalized", {})
    seo_result = state.get("seo_result", {})
    seo_strategy = seo_result.get("seo_strategy", {})
    
    # Get the outline rejected reason if exists (for iterative improvement)
    content_state = state.get("content", {})
    outline_state = content_state.get("outline", {})
    outline_rejected_reason = outline_state.get("rejected_reason", "None")
    
    if not query:
        logger.error("No query found in state")
        return {"content": {**content_state, "error": "No query found in serp_payload"}}

    logger.info(f"Generating outline for: {query}")
    
    # 2. Extract context for the prompt
    related_topics = serp_normalized.get("related_topics", [])
    questions = serp_normalized.get("questions", [])
    
    # Summary of competitors
    competitors = state.get("competitors", [])
    competitors_context = [
        f"Domain: {c.get('domain')}, Intent: {c.get('intent_distribution')}" 
        for c in competitors[:5]
    ]

    # 3. Load model and generate outline
    try:
        outline_model = load_model().with_structured_output(Outline)
        
        # Prepare prompt
        prompt_template = get_outline_prompt()
        messages = prompt_template.format_messages(
            query=query,
            related_topics=related_topics,
            questions=questions,
            competitors_context=competitors_context,
            intent_distribution=seo_result.get("intent", {}),
            rejected_reason=outline_rejected_reason
        )
        logger.info("Outline messages",messages)
        # Invoke LLM
        generated_outline = outline_model.invoke(messages)
        outline_dict = generated_outline.model_dump()
        logger.info("Outline generated successfully",outline_dict)
        
        return {
            "content": {
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
        return {"content": { "error": f"Generation failed: {str(e)}"}}