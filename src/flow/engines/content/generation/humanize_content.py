"""
Content Humanization Node

This module transforms AI-generated content to appear naturally human-written,
targeting 90% human-written detection score (10% AI detection).
"""

import logging
from sqlalchemy import select
from src.flow.states.rext import REXT
from src.api.database.async_database import get_sync_db
from src.api.models.knowledge_models.persona_model import Persona
from src.flow.model.llm_manager import load_model, load_humanize_model
from src.flow.model.structure.content import GeneratedContent, GeneratedHumanizeContent
from src.flow.prompts.human.humanize import get_humanize_prompt

logger = logging.getLogger(__name__)


async def humanize_content(state: REXT) -> dict:
    """
    Humanizes AI-generated content to make it appear naturally written by a human.
    
    This node applies aggressive techniques to reduce AI detection and make content
    feel authentic, conversational, and genuinely human-like. Target: 90% human score.
    
    Humanization strategies:
    - Add natural language variations and imperfections
    - Use conversational tone with contractions and casual language
    - Include personal voice and relatable examples
    - Vary sentence structure dramatically (short, long, fragments)
    - Add transitional phrases and natural flow
    - Use informal language and colloquialisms
    - Active voice with direct reader engagement
    - Rhetorical questions and storytelling elements
    - Break formal writing rules occasionally
    - Add personality and unique voice
    
    Args:
        state: REXT state containing content to humanize
    
    Returns:
        dict: Updated state with humanized content (90% human-written)
    """
    try:
        # 1️⃣ Get content from state
        content_state = state.get("content", {})
        content_outline = content_state.get("outline", {})

        final_content = content_state.get("final_content", {})
        
        if not final_content:
            logger.warning("No final_content found in state. Skipping humanization.")
            return {"content": content_state}
        
        title = final_content.get("title", "")
        body_markdown = final_content.get("body_markdown", "")
        
        if not body_markdown:
            logger.warning("No body content found. Skipping humanization.")
            return {"content": content_state}
        
        logger.info(f"Humanizing content: {title}")
        
        # 2️⃣ Fetch Persona data from DB
        workspace_id = state.get("serp_payload", {}).get("workspace_id")
        
        # Initialize with user-requested fallbacks
        persona_data = {
            "persona_full_name": "[Writer name]",
            "persona_professional_title": "[e.g., WordPress dev, Security engineer, SaaS founder]",
            "persona_areas_of_expertise": "[e.g., WP-CLI, Git, Nginx, Cloudflare, Woo, etc]",
            "persona_bio": "[A short professional bio]",
            "persona_tone_of_voice": "Personal Tone",
            "persona_description": "[Writer persona details]",
            "persona_goals": "[what they should know/do after]",
            "persona_behaviors": "[Behaviors]",
        }

        if workspace_id:
            try:
                db_gen = get_sync_db()
                db = next(db_gen)
                try:
                    # Fetch the first persona for this workspace
                    result = db.execute(select(Persona).where(Persona.workspace_id == workspace_id))
                    persona = result.scalars().first()
                    
                    if persona:
                        # Override defaults ONLY if persona fields are not None/empty
                        persona_data["persona_full_name"] = persona.full_name or persona.name or persona_data["persona_full_name"]
                        persona_data["persona_professional_title"] = persona.professional_title or persona_data["persona_professional_title"]
                        persona_data["persona_areas_of_expertise"] = persona.areas_of_expertise or persona_data["persona_areas_of_expertise"]
                        persona_data["persona_bio"] = persona.bio or persona_data["persona_bio"]
                        persona_data["persona_tone_of_voice"] = persona.tone_of_voice or persona_data["persona_tone_of_voice"]
                        persona_data["persona_description"] = persona.description or persona_data["persona_description"]
                        persona_data["persona_goals"] = persona.goals or persona_data["persona_goals"]
                        persona_data["persona_behaviors"] = persona.behaviors or persona_data["persona_behaviors"]
                        
                        logger.info(f"Loaded persona '{persona_data['persona_full_name']}' for humanization (Workspace: {workspace_id})")
                    else:
                        logger.info(f"No persona found for workspace {workspace_id}. Using defaults.")
                finally:
                    db.close()
            except Exception as db_exc:
                logger.error(f"Database error fetching persona: {db_exc}. Using defaults.")

        # 3️⃣ Prepare prompt data with safe fallbacks
        prompt_data = {
            "title": title,
            "introduction": final_content.get("introduction", ""),
            "body_markdown": body_markdown,
            "selected_topic": content_state.get("selected_topic") or title,
            "content_type": content_state.get("content_type") or "Article",
            "word_count": final_content.get("word_count") or "[word count]",
            "target_audience": content_outline.get("target_audience") or "[exact persona + skill level]",
            "content_tone": content_outline.get("tone") or "[casual/direct/spicy/calm]",
            **persona_data # Inject persona fields
        }
        
        # 3️⃣ Load model and prepare messages
        # model = load_model().with_structured_output(GeneratedHumanizeContent)
        model = load_humanize_model().with_structured_output(GeneratedHumanizeContent)
        messages = get_humanize_prompt().format_messages(**prompt_data)
        
        # 4️⃣ Invoke LLM for humanization
        logger.info("Invoking LLM for content humanization (target: 90% human-written)...")
        humanized_content = await model.ainvoke(messages)
        humanized_dict = humanized_content.model_dump()
        
        logger.info(f"Humanization completed (90% human target). Keys: {humanized_dict.keys()}")
        
        # 5️⃣ Update state with humanized content
        return {
            "content": {
                **content_state,
                "final_content": {
                    **final_content,
                    # "humanized_content":humanized_content
                    "humanized_title": humanized_dict.get("title", title),
                    "humanized_introduction": humanized_dict.get("introduction", final_content.get("introduction", "")),
                    "humanized_body_markdown": humanized_dict.get("body_markdown", body_markdown),
                },
                "status": "humanized"
            }
        }
        
    except Exception as e:
        logger.exception(f"Error humanizing content: {str(e)}")
        return {
            "content": {
                **content_state,
                "error": f"Humanization failed: {str(e)}"
            }
        }
