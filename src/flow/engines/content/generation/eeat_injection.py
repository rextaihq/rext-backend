"""
E-E-A-T Injection Node

This module enhances AI-generated content with Experience, Expertise,
Authoritativeness, and Trustworthiness (E-E-A-T) signals by injecting
persona-based credibility indicators and expert insights.
"""

import logging
from uuid import UUID
from sqlalchemy import select

from src.flow.states.rext import REXT
from src.flow.model.llm_manager import load_model
from src.flow.model.structure.content import GeneratedContent
from src.flow.prompts.human.eeat import get_eeat_prompt
from src.api.database.async_database import get_async_db_context
from src.api.models.knowledge_models.persona_model import Persona

logger = logging.getLogger(__name__)


async def inject_eeat(state: REXT) -> dict:
    """
    Injects E-E-A-T (Experience, Expertise, Authoritativeness, Trustworthiness)
    signals into generated content using persona data from the database.
    
    This node enhances content with:
    - First-hand experience signals ("In practice", "I've found")
    - Expert insights and decision-making frameworks
    - Professional credibility without explicit claims
    - Trust signals through honest limitations and caveats
    
    Args:
        state: REXT state containing generated content and serp_payload with workspace_id
    
    Returns:
        dict: Updated state with E-E-A-T enhanced content
    """
    content_state = state.get("content", {})
    
    try:
        # 1️⃣ Get content from state
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
        
        # 2️⃣ Get workspace_id from serp_payload
        serp_payload = state.get("serp_payload", {})
        workspace_id = serp_payload.get("workspace_id")
        
        if not workspace_id:
            error_msg = "No workspace_id found in serp_payload. Cannot fetch persona."
            logger.error(error_msg)
            return {
                "content": {
                    **content_state,
                    "error": error_msg
                }
            }
        
        # 3️⃣ Fetch persona from database
        async with get_async_db_context() as db:
            result = await db.execute(
                select(Persona)
                .where(Persona.workspace_id == UUID(str(workspace_id)))
                .order_by(Persona.created_at.desc())
                .limit(1)
            )
            persona_record = result.scalar_one_or_none()
        
        if not persona_record:
            error_msg = f"No persona found for workspace {workspace_id}. Please create a persona first."
            logger.error(error_msg)
            return {
                "content": {
                    **content_state,
                    "error": error_msg
                }
            }
        
        # 4️⃣ Extract persona fields
        persona_name = persona_record.full_name or persona_record.name
        persona_role = persona_record.professional_title or "Content Expert"
        
        # Parse areas_of_expertise (comma-separated string)
        focus_areas = []
        if persona_record.areas_of_expertise:
            focus_areas = [area.strip() for area in persona_record.areas_of_expertise.split(",")]
        
        logger.info(f"Using E-E-A-T persona: {persona_name} - {persona_role}")
        
        # 5️⃣ Get topic and primary keyword for context
        topic = content_state.get("selected_topic", "")
        outline = content_state.get("outline", {})
        primary_keyword = outline.get("keywords_to_include", [""])[0] if outline.get("keywords_to_include") else topic
        
        # 6️⃣ Prepare prompt data
        prompt_data = {
            "title": title,
            "body_markdown": body_markdown,
            "topic": topic,
            "primary_keyword": primary_keyword,
            "persona_name": persona_name,
            "persona_role": persona_role,
            "years_experience": 5,  # Default value - could be added to Persona model
            "focus_areas": ", ".join(focus_areas) if focus_areas else "general expertise",
        }
        
        # 7️⃣ Load model and prepare messages
        model = load_model().with_structured_output(GeneratedContent)
        messages = get_eeat_prompt().format_messages(**prompt_data)
        
        # 8️⃣ Invoke LLM for E-E-A-T injection
        logger.info("Invoking LLM for E-E-A-T signal injection...")
        eeat_enhanced_content = await model.ainvoke(messages)
        eeat_dict = eeat_enhanced_content.model_dump()
        
        logger.info(f"E-E-A-T injection completed. Word count: {eeat_dict.get('word_count', 0)}")
        
        # 9️⃣ Update state with E-E-A-T enhanced content
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
