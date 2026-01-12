"""
E-E-A-T Injection Node

This module injects E-E-A-T (Experience, Expertise, Authoritativeness, Trustworthiness)
signals into generated content to enhance credibility and authority.
"""

import logging
from src.flow.states.wrext import WREXT
from src.flow.model.llm_manager import load_model
from src.flow.model.structure.content import GeneratedContent
from src.flow.model.personas import get_eeat_persona
from src.flow.prompts.human.eeat import get_eeat_prompt

logger = logging.getLogger(__name__)


def inject_eeat_persona(state: WREXT) -> dict:
    """
    Injects E-E-A-T persona signals into the generated content.
    
    This node:
    1. Retrieves the current content from state
    2. Gets the E-E-A-T persona configuration
    3. Uses an LLM to enhance the content with E-E-A-T signals
    4. Updates the content in the state with the enhanced version
    
    Args:
        state: WREXT state containing content to enhance
    
    Returns:
        dict: Updated state with E-E-A-T enhanced content
    """
    try:
        # 1️⃣ Get content from state
        content_state = state.get("content", {})
        final_content = content_state.get("final_content", {})
        
        if not final_content:
            logger.warning("No final_content found in state. Skipping E-E-A-T injection.")
            return {"content": content_state}
        
        title = final_content.get("title", "")
        body_markdown = final_content.get("body_markdown", "")
        
        if not body_markdown:
            logger.warning("No body content found. Skipping E-E-A-T injection.")
            return {"content": content_state}
        
        logger.info(f"Injecting E-E-A-T into content: {title}")
        
        # 2️⃣ Get E-E-A-T persona
        persona = get_eeat_persona("eeat_persona_001")
        logger.info(f"Using E-E-A-T persona: {persona['name']} - {persona['role']}")
        
        # 3️⃣ Prepare prompt data
        prompt_data = {
            "persona_name": persona["name"],
            "persona_role": persona["role"],
            "years_experience": persona["years_experience"],
            "focus_areas": ", ".join(persona["focus_areas"]),
            "worked_with": ", ".join(persona["worked_with"]),
            "writing_style": persona["writing_style"],
            "language_patterns": ", ".join(persona["eeat"]["experience"]["language_patterns"]),
            "tone": persona["eeat"]["authoritativeness"]["tone"],
            "title": title,
            "body_markdown": body_markdown
        }
        
        # 4️⃣ Load model and prepare messages
        model = load_model().with_structured_output(GeneratedContent)
        messages = get_eeat_prompt().format_messages(**prompt_data)
        
        # 5️⃣ Invoke LLM to enhance content
        logger.info("Invoking LLM for E-E-A-T enhancement...")
        enhanced_content = model.invoke(messages)
        enhanced_dict = enhanced_content.model_dump()
        
        logger.info(f"E-E-A-T injection completed. Enhanced content keys: {enhanced_dict.keys()}")
        
        # 6️⃣ Update state with enhanced content
        return {
            "content": {
                **content_state,
                "final_content": {
                    **final_content,
                    "title": enhanced_dict.get("title", title),
                    "body_markdown": enhanced_dict.get("body_markdown", body_markdown),
                    "word_count": enhanced_dict.get("word_count", final_content.get("word_count", 0)),
                    "meta_title": enhanced_dict.get("meta_title", final_content.get("meta_title", "")),
                    "meta_description": enhanced_dict.get("meta_description", final_content.get("meta_description", "")),
                    "tags": enhanced_dict.get("tags", final_content.get("tags", [])),
                },
                "status": "eeat_injected"
            }
        }
        
    except Exception as e:
        logger.exception(f"Error injecting E-E-A-T: {str(e)}")
        return {
            "content": {
                **content_state,
                "error": f"E-E-A-T injection failed: {str(e)}"
            }
        }