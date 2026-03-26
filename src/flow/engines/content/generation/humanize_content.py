"""
Content Humanization Middleware

This module transforms AI-generated content to appear naturally human-written,
targeting 90% human-written detection score (10% AI detection).
"""

import logging
from typing import Any
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.config import RunnableConfig
from sqlalchemy import select

from src.api.database.async_database import get_sync_db
from src.api.models.knowledge_models.persona_model import Persona
from src.flow.model.llm_manager import load_humanize_model
from src.flow.model.structure.content import GeneratedContent
from src.flow.prompts.human.humanize import get_humanize_prompt

logger = logging.getLogger(__name__)


def _load_persona(workspace_id: str) -> dict:
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

    # Apply fallbacks for persona fields if they are missing
    persona_data["persona_full_name"] = persona_data.get("persona_full_name") or "[Writer name]"
    persona_data["persona_professional_title"] = persona_data.get("persona_professional_title") or "[e.g., WordPress dev, Security engineer, SaaS founder]"
    persona_data["persona_areas_of_expertise"] = persona_data.get("persona_areas_of_expertise") or "[e.g., WP-CLI, Git, Nginx, Cloudflare, Woo, etc]"
    persona_data["persona_goals"] = persona_data.get("persona_goals") or "[what they should know/do after]"
    persona_data["persona_behaviors"] = persona_data.get("persona_behaviors") or "[Behaviors]"
    persona_data["persona_tone_of_voice"] = persona_data.get("persona_tone_of_voice") or "Personal Tone"
    
    return persona_data


async def _humanize_generated_content(
    generated: GeneratedContent,
    metadata: dict
) -> GeneratedContent:
    if not generated.title or not generated.body_markdown:
        logger.warning("No title or body content found. Skipping humanization.")
        return generated
    
    logger.info(f"Humanizing content: {generated.title}")
    
    workspace_id = metadata.get("workspace_id", "")
    persona_data = _load_persona(workspace_id)
    
    prompt_data = {
        "title": generated.title,
        "introduction": generated.introduction or "",
        "body_markdown": generated.body_markdown,
        "html_content": generated.html_content or "",
        "selected_topic": metadata.get("selected_topic", ""),
        "content_type": metadata.get("content_type", ""),
        "word_count": generated.word_count or "[word count]",
        "target_audience": metadata.get("target_audience", "[exact persona + skill level]"),
        "content_tone": metadata.get("tone", "[casual/direct/spicy/calm]"),
        **persona_data # Inject persona fields
    }
    
    model = load_humanize_model().with_structured_output(GeneratedContent)
    messages = get_humanize_prompt().format_messages(**prompt_data)
    
    logger.info("Invoking LLM for content humanization (target: 90% human-written)...")
    humanized_content = await model.ainvoke(messages)
    logger.info("Humanization completed.")
    return humanized_content


def humanization_after_model_middleware():
    """
    Returns a RunnableLambda middleware that humanizes GeneratedContent 
    using the loaded persona and humanize_model if enabled in config.
    """
    async def _middleware(output: Any, config: RunnableConfig) -> Any:
        # Type check to handle both direct GeneratedContent and Agent Output Dict
        generated = None
        is_dict_wrapper = False
        
        if isinstance(output, GeneratedContent):
            generated = output
        elif isinstance(output, dict) and isinstance(output.get("structured_response"), GeneratedContent):
            generated = output["structured_response"]
            is_dict_wrapper = True
            
        if not generated:
            return output
            
        metadata = config.get("metadata", {})
        if not metadata.get("enable_humanization", True):
            return output
            
        if getattr(generated, "word_count", 0) and generated.word_count < 300:
            logger.info("Content word count < 300. Skipping humanization.")
            return output
            
        try:
            logger.info("Starting humanization middleware...")
            humanized = await _humanize_generated_content(generated, metadata)
            if is_dict_wrapper:
                new_output = dict(output)
                new_output["structured_response"] = humanized
                return new_output
            return humanized
        except Exception as e:
            logger.error(f"Fallback to original. Humanization error: {e}")
            return output
            
    return RunnableLambda(_middleware)
