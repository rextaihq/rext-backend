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
from src.flow.model.llm_manager import load_humanize_model
from src.flow.model.structure.content import GeneratedContent
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

        final_content = content_state.get("final_content", {})
        content_outline = content_state.get("outline", {})

        
        if not final_content:
            logger.warning("No final_content found in state. Skipping humanization.")
            return {"content": content_state}
        
        title = final_content.get("title", "")
        body_markdown = final_content.get("body_markdown", "")
        html_content = final_content.get("html_content", "")
        
        if not body_markdown:
            logger.warning("No body content found. Skipping humanization.")
            return {"content": content_state}
        
        logger.info(f"Humanizing content: {title}")
        
        # 2️⃣ Fetch Persona data from DB
        workspace_id = state.get("serp_payload", {}).get("workspace_id")
        persona_data = {
            "persona_full_name": "Writer",
            "persona_professional_title": "Subject Matter Expert",
            "persona_areas_of_expertise": "Industry Expertise",
            "persona_bio": "A seasoned professional with deep industry knowledge.",
            "persona_tone_of_voice": "Professional and authoritative",
            "persona_description": "Expert writer",
            "persona_goals": "Provide high-quality, actionable insights",
            "persona_behaviors": "Conversational, direct, and insightful",
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
                        persona_data = {
                            "persona_full_name": persona.full_name or persona.name or "Writer",
                            "persona_professional_title": persona.professional_title or "Subject Matter Expert",
                            "persona_areas_of_expertise": persona.areas_of_expertise or "Industry Expertise",
                            "persona_bio": persona.bio or "A seasoned professional with deep industry knowledge.",
                            "persona_tone_of_voice": persona.tone_of_voice or "Professional and authoritative",
                            "persona_description": persona.description or "Expert writer",
                            "persona_goals": persona.goals or "Provide high-quality, actionable insights",
                            "persona_behaviors": persona.behaviors or "Conversational, direct, and insightful",
                        }
                        logger.info(f"Loaded persona '{persona_data['persona_full_name']}' for humanization (Workspace: {workspace_id})")
                    else:
                        logger.info(f"No persona found for workspace {workspace_id}. Using defaults.")
                finally:
                    db.close()
            except Exception as db_exc:
                logger.error(f"Database error fetching persona: {db_exc}. Using defaults.")

        # 3️⃣ Prepare prompt data
        prompt_data = {
            "title": title,
            "introduction": final_content.get("introduction", ""),
            "body_markdown": body_markdown,
            "html_content":html_content,
            "selected_topic": content_state.get("selected_topic", ""),
            "content_type": content_state.get("content_type", ""),
            "word_count": final_content.get("word_count") or "[word count]",
            "target_audience": content_outline.get("target_audience") or "[exact persona + skill level]",
            "content_tone": content_outline.get("tone") or "[casual/direct/spicy/calm]",
            **persona_data # Inject persona fields
        }

        # Apply fallbacks for persona fields if they are missing
        prompt_data["persona_full_name"] = prompt_data.get("persona_full_name") or "[Writer name]"
        prompt_data["persona_professional_title"] = prompt_data.get("persona_professional_title") or "[e.g., WordPress dev, Security engineer, SaaS founder]"
        prompt_data["persona_areas_of_expertise"] = prompt_data.get("persona_areas_of_expertise") or "[e.g., WP-CLI, Git, Nginx, Cloudflare, Woo, etc]"
        prompt_data["persona_goals"] = prompt_data.get("persona_goals") or "[what they should know/do after]"
        prompt_data["persona_behaviors"] = prompt_data.get("persona_behaviors") or "[Behaviors]"
        prompt_data["persona_tone_of_voice"] = prompt_data.get("persona_tone_of_voice") or "Personal Tone"
        
        # 3️⃣ Load model and prepare messages
        # model = load_model().with_structured_output(GeneratedHumanizeContent)
        model = load_humanize_model().with_structured_output(GeneratedContent)
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
                    "title": humanized_dict.get("title", title),
                    "introduction": humanized_dict.get("introduction", final_content.get("introduction", "")),
                    "body_markdown": humanized_dict.get("body_markdown", body_markdown),
                    # "html_content": humanized_dict.get("html_content", html_content),
                    "word_count": humanized_dict.get("word_count", final_content.get("word_count", 0)),
                    "meta_title": humanized_dict.get("meta_title", final_content.get("meta_title", "")),
                    "meta_description": humanized_dict.get("meta_description", final_content.get("meta_description", "")),
                    "tags": humanized_dict.get("tags", final_content.get("tags", [])),
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

