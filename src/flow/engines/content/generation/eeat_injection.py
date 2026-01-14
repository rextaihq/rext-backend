"""
E-E-A-T Injection Node

This module enhances AI-generated content with Experience, Expertise,
Authoritativeness, and Trustworthiness (E-E-A-T) signals by injecting
persona-based credibility indicators and expert insights.
"""

import logging
from src.flow.states.wrext import WREXT
from src.flow.model.llm_manager import load_model
from src.flow.model.structure.content import GeneratedContent
from src.flow.prompts.human.eeat import get_eeat_prompt
from src.flow.model.personas import get_eeat_persona

logger = logging.getLogger(__name__)


def inject_eeat(state: WREXT) -> dict:
    """
    Injects E-E-A-T (Experience, Expertise, Authoritativeness, Trustworthiness)
    signals into generated content using persona data.
    
    This node enhances content with:
    - First-hand experience signals ("In practice", "I've found")
    - Expert insights and decision-making frameworks
    - Professional credibility without explicit claims
    - Trust signals through honest limitations and caveats
    
    Args:
        state: WREXT state containing generated content
    
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
        
        logger.info(f"Injecting E-E-A-T signals into: {title}")
        
        # 2️⃣ Get E-E-A-T persona
        persona = get_eeat_persona("eeat_persona_001")
        logger.info(f"Using E-E-A-T persona: {persona['name']} - {persona['role']}")
        
        # 3️⃣ Get topic and primary keyword for context
        topic = content_state.get("selected_topic", "")
        outline = content_state.get("outline", {})
        primary_keyword = outline.get("keywords_to_include", [""])[0] if outline.get("keywords_to_include") else topic
        
        # 4️⃣ Prepare prompt data
        prompt_data = {
            "title": title,
            "body_markdown": body_markdown,
            "topic": topic,
            "primary_keyword": primary_keyword,
            "persona_name": persona["name"],
            "persona_role": persona["role"],
            "years_experience": persona["years_experience"],
            "focus_areas": ", ".join(persona["focus_areas"]),
        }
        
        # 5️⃣ Load model and prepare messages
        model = load_model().with_structured_output(GeneratedContent)
        messages = get_eeat_prompt().format_messages(**prompt_data)
        
        # 6️⃣ Invoke LLM for E-E-A-T injection
        logger.info("Invoking LLM for E-E-A-T signal injection...")
        eeat_enhanced_content = model.invoke(messages)
        eeat_dict = eeat_enhanced_content.model_dump()
        
        logger.info(f"E-E-A-T injection completed. Word count: {eeat_dict.get('word_count', 0)}")
        
        # 7️⃣ Update state with E-E-A-T enhanced content
        return {
            "content": {
                **content_state,
                "final_content": {
                    **final_content,
                    "title": eeat_dict.get("title", title),
                    "body_markdown": eeat_dict.get("body_markdown", body_markdown),
                    "word_count": eeat_dict.get("word_count", final_content.get("word_count", 0)),
                    "meta_title": eeat_dict.get("meta_title", final_content.get("meta_title", "")),
                    "meta_description": eeat_dict.get("meta_description", final_content.get("meta_description", "")),
                    "tags": eeat_dict.get("tags", final_content.get("tags", [])),
                    "status": "eeat_injected",
                },
                "status": "eeat_injected"
            }
        }
        
    except Exception as e:
        logger.exception(f"Error injecting E-E-A-T signals: {str(e)}")
        return {
            "content": {
                **content_state,
                "error": f"E-E-A-T injection failed: {str(e)}"
            }
        }
